import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio, re, aiohttp

# --- Configurações de Identidade ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
THUMBNAIL_MED = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Memória Temporária
fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 

# ================= DATABASE =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    con = sqlite3.connect("dados.db")
    con.execute(q, p)
    con.commit()
    con.close()

def salvar_config(ch, v):
    db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", (ch, str(v)))

def pegar_config(ch):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

# ================= GATILHO ID/SENHA + RENAME =================
@bot.event
async def on_message(message):
    if message.author.bot: return
    
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        
        if message.author.id == dados['med'] and message.content.isdigit():
            tid = message.channel.id
            
            if tid not in temp_dados:
                temp_dados[tid] = message.content
                await message.delete()
                await message.channel.send("✅ ID recebido. Agora envie a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados.pop(tid)
                await message.delete()
                
                # MUDANÇA DE NOME DO TÓPICO
                novo_nome = f"💰｜Pagar-{dados['valor']}"
                await message.channel.edit(name=novo_nome)
                
                emb = discord.Embed(title="🚀 INÍCIO DE PARTIDA", color=0x2ecc71)
                emb.description = "A partida será iniciada em 3 a 5 minutos!"
                emb.add_field(name="👑 Modo", value=dados['modo'], inline=True)
                emb.add_field(name="💎 Valor", value=f"R$ {dados['valor']}", inline=True)
                emb.add_field(name="👥 Jogadores", value=f"<@{dados['p1']}>\n<@{dados['p2']}>", inline=False)
                emb.add_field(name="🆔 ID", value=f"`{id_sala}`", inline=True)
                emb.add_field(name="🔑 Senha", value=f"`{senha}`", inline=True)
                await message.channel.send(embed=emb)

    await bot.process_commands(message)

# ================= PAINEL MEDIADOR (ORG FIRE) =================
class ViewMed(View):
    def __init__(self): super().__init__(timeout=None)
    def gerar_embed(self):
        txt = "\n".join([f"{i+1} • <@{uid}> `{uid}`" for i, uid in enumerate(fila_mediadores)]) if fila_mediadores else "Nenhum mediador em serviço"
        emb = discord.Embed(title="Painel da fila controladora", description=f"**Entre na fila para começar a mediar suas filas**\n\n{txt}", color=0x2b2d31)
        emb.set_thumbnail(url=THUMBNAIL_MED)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def e(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def s(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def r(self, it, b):
        if it.user.guild_permissions.administrator:
            fila_mediadores.clear()
            await it.response.edit_message(embed=self.gerar_embed())

# ================= SISTEMA PIX =================
@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class MPix(Modal, title="Configurar PIX"):
                n = TextInput(label="Nome Completo"); c = TextInput(label="Chave PIX"); q = TextInput(label="Link QR Code", required=False)
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
                    await i.response.send_message("✅ PIX Salvo!", ephemeral=True)
            await it.response.send_modal(MPix())
        @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.blurple, emoji="🔍")
        async def sc(self, it, b):
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
            if r:
                emb = discord.Embed(title="💠 Seu PIX", description=f"**Nome:** {r[0]}\n**Chave:** `{r[1]}`", color=0x4b0082)
                if r[2]: emb.set_image(url=r[2])
                await it.response.send_message(embed=emb, ephemeral=True)
    await ctx.send(embed=discord.Embed(title="Painel Para Configurar Chave PIX", color=0x4b0082), view=VPix())

# ================= TÓPICO E CONFIRMAÇÃO (SOMA 0.10) =================
class ViewTopico(View):
    def __init__(self, p1_id, p2_id, med_id, valor_base):
        super().__init__(timeout=None)
        self.p1_id = p1_id; self.p2_id = p2_id; self.med_id = med_id; self.valor_base = valor_base
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, it, b):
        if it.user.id not in [self.p1_id, self.p2_id]: return
        self.confirmados.add(it.user.id)
        
        emb_confirm = discord.Embed(title="✅ | Partida Confirmada", color=0x2ecc71)
        emb_confirm.description = f"{it.user.mention} confirmou a aposta!\n↳ O outro jogador precisa confirmar para continuar."
        await it.response.send_message(embed=emb_confirm)

        if len(self.confirmados) == 2:
            await asyncio.sleep(2); await it.channel.purge(limit=15)
            
            # Lógica para somar 0.10 ao valor
            try:
                # Remove 'R$' ou vírgulas para converter em número
                limpo = self.valor_base.replace("R$", "").replace(",", ".").strip()
                valor_final = float(limpo) + 0.10
                valor_exibir = f"{valor_final:.2f}".replace(".", ",")
            except:
                valor_exibir = self.valor_base # Caso não consiga somar, mantém o texto

            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med_id,)).fetchone(); con.close()
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            if r:
                emb_pix.description = f"**Valor Total (Aposta + Sala):** R$ {valor_exibir}\n\n**Nome:** {r[0]}\n**Chave:** `{r[1]}`"
                if r[2]: emb_pix.set_image(url=r[2])
            await it.channel.send(embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, b): await it.channel.delete()

# ================= FILA E CRIAÇÃO =================
@bot.command()
async def fila(ctx, modo: str, valor: str):
    class ViewFila(View):
        def __init__(self): super().__init__(timeout=None); self.users = []
        def ge(self):
            txt = "\n".join([f"👤 {u.mention} - {g}" for u, g in self.users]) if self.users else "Vazia"
            emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=0x3498DB)
            emb.add_field(name="👑 Modo", value=modo); emb.add_field(name="💎 Valor", value=f"R$ {valor}")
            emb.add_field(name="⚡ Jogadores", value=txt, inline=False); emb.set_image(url=BANNER_URL)
            return emb
        
        async def en(self, it, g):
            if any(x.id == it.user.id for x, _ in self.users): return
            self.users.append((it.user, g))
            if len(self.users) == 2:
                p1, g1 = self.users[0]; p2, g2 = self.users[1]; self.users = []; await it.message.edit(embed=self.ge())
                if not fila_mediadores: return await it.response.send_message("Sem mediadores!", ephemeral=True)
                
                med_id = fila_mediadores.pop(0)
                canais = [pegar_config(f"canal_{i}") for i in range(1, 4)]
                validos = [int(i) for i in canais if i]
                canal_alvo = bot.get_channel(random.choice(validos)) if validos else it.channel
                
                th = await canal_alvo.create_thread(name="⌛｜aguardando-confirmaçao", type=discord.ChannelType.public_thread)
                partidas_ativas[th.id] = {'modo': f"{modo} | {g}", 'valor': valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
                
                emb_p = discord.Embed(title="Partida Confirmada", color=0x2b2d31)
                emb_p.add_field(name="🎮 Estilo", value=f"1v1 | {g}", inline=False)
                emb_p.add_field(name="ℹ️ Info", value=f"Valor Da Sala: R$ 0,10\nMediador: <@{med_id}>", inline=False)
                emb_p.add_field(name="💸 Valor da Aposta", value=f"R$ {valor}", inline=False)
                emb_p.add_field(name="👥 Jogadores", value=f"{p1.mention}\n{p2.mention}", inline=False)
                
                await th.send(embed=emb_p, view=ViewTopico(p1.id, p2.id, med_id, valor))
                await it.response.send_message(f"✅ Tópico: {th.mention}", ephemeral=True)
            else: await it.response.edit_message(embed=self.ge())

        @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
        async def b1(self, it, b): await self.en(it, "Gel Normal")
        @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
        async def b2(self, it, b): await self.en(it, "Gel Infinito")
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger)
        async def s(self, it, b): self.users = [x for x in self.users if x[0].id != it.user.id]; await it.response.edit_message(embed=self.ge())
    
    await ctx.send(embed=ViewFila().ge(), view=ViewFila())

# ================= COMANDOS DE CONFIG =================
@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class VConfig(View):
        @discord.ui.button(label="Mudar Nome", style=discord.ButtonStyle.secondary)
        async def mn(self, it, b):
            class M(Modal, title="Nome"):
                n = TextInput(label="Novo Nome")
                async def on_submit(self, i): await bot.user.edit(username=self.n.value); await i.response.send_message("OK!", ephemeral=True)
            await it.response.send_modal(M())
        @discord.ui.button(label="Mudar Foto", style=discord.ButtonStyle.secondary)
        async def mf(self, it, b):
            class M(Modal, title="Link Foto"):
                u = TextInput(label="URL")
                async def on_submit(self, i):
                    async with aiohttp.ClientSession() as s:
                        async with s.get(self.u.value) as r: d = await r.read(); await bot.user.edit(avatar=d)
                    await i.response.send_message("OK!", ephemeral=True)
            await it.response.send_modal(M())
    await ctx.send("⚙️ Configurações de Identidade:", view=VConfig())

@bot.command()
async def canal(ctx):
    class VC(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 1")
        async def c1(self, it, s): salvar_config("canal_1", s.values[0].id); await it.response.send_message("✅ Canal 1 OK", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 2")
        async def c2(self, it, s): salvar_config("canal_2", s.values[0].id); await it.response.send_message("✅ Canal 2 OK", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 3")
        async def c3(self, it, s): salvar_config("canal_3", s.values[0].id); await it.response.send_message("✅ Canal 3 OK", ephemeral=True)
    await ctx.send("📍 Canais dos Tópicos:", view=VC())

@bot.event
async def on_ready(): init_db(); print(f"✅ Logado")

bot.run(TOKEN)
        
