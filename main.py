import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio, aiohttp

# --- Configurações de Identidade ---
TOKEN = "SEU_TOKEN_AQUI"
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
THUMBNAIL_MED = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

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

# ================= GATILHO ID/SENHA + RENOMEAR TÓPICO =================
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
                await message.channel.send("✅ **ID recebido.** Agora envie a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados.pop(tid)
                await message.delete()
                
                # RENOMEAR TÓPICO: Muda de "aguardando" para "Pagar-(valor)"
                await message.channel.edit(name=f"💰｜Pagar-{dados['valor']}")
                
                emb = discord.Embed(title="🚀 INÍCIO DE PARTIDA", color=0x2ecc71)
                emb.add_field(name="👑 Modo", value=dados['modo'], inline=True)
                emb.add_field(name="💎 Valor", value=f"R$ {dados['valor']}", inline=True)
                emb.add_field(name="👥 Jogadores", value=f"<@{dados['p1']}>\n<@{dados['p2']}>", inline=False)
                emb.add_field(name="🆔 ID", value=f"`{id_sala}`", inline=True)
                emb.add_field(name="🔑 Senha", value=f"`{senha}`", inline=True)
                await message.channel.send(embed=emb)
    await bot.process_commands(message)

# ================= COMANDO .MEDIAR (IGUAL À FOTO) =================
class ViewMed(View):
    def __init__(self): super().__init__(timeout=None)
    def gerar_embed(self):
        txt = "\n".join([f"{i+1} • <@{uid}> `{uid}`" for i, uid in enumerate(fila_mediadores)]) if fila_mediadores else "Nenhum mediador em serviço"
        emb = discord.Embed(title="Painel da fila controladora", description=f"**Entre na fila para começar a mediar suas filas**\n\n{txt}", color=0x2b2d31)
        emb.set_thumbnail(url=THUMBNAIL_MED)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def e(self, it, b):
        if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def s(self, it, b):
        if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def r(self, it, b):
        if it.user.guild_permissions.administrator: fila_mediadores.clear(); await it.response.edit_message(embed=self.gerar_embed())
    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def st(self, it, b): await it.response.send_message("Painel Staff", ephemeral=True)

@bot.command()
async def mediar(ctx): await ctx.send(embed=ViewMed().gerar_embed(), view=ViewMed())

# ================= COMANDO .PIX (COM QR CODE) =================
@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class M(Modal, title="Configurar PIX"):
                n = TextInput(label="Nome Completo"); c = TextInput(label="Chave PIX"); q = TextInput(label="Link da Imagem QR Code", required=False)
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
                    await i.response.send_message("✅ PIX e QR Code salvos com sucesso!", ephemeral=True)
            await it.response.send_modal(M())
    await ctx.send(embed=discord.Embed(title="Configuração de Chave PIX e QR Code", color=0x4b0082), view=VPix())

# ================= CONFIRMAÇÃO (BARRA VERDE + SOMA 0.10) =================
class ViewTopico(View):
    def __init__(self, p1_id, p2_id, med_id, valor_base):
        super().__init__(timeout=None)
        self.p1_id = p1_id; self.p2_id = p2_id; self.med_id = med_id; self.valor_base = valor_base
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, it, b):
        if it.user.id not in [self.p1_id, self.p2_id]: return
        self.confirmados.add(it.user.id)
        
        # Embed Barra Verde Lateral
        emb_c = discord.Embed(title="✅ | Partida Confirmada", color=0x2ecc71, description=f"{it.user.mention} confirmou a aposta!\n↳ Aguardando confirmação do oponente.")
        await it.response.send_message(embed=emb_c)

        if len(self.confirmados) == 2:
            await asyncio.sleep(2); await it.channel.purge(limit=15)
            
            # CÁLCULO: Soma 0.10 ao valor da aposta
            try:
                v_limpo = self.valor_base.replace("R$", "").replace(",", ".").strip()
                total_soma = float(v_limpo) + 0.10
                total_formatado = f"{total_soma:.2f}".replace(".", ",")
            except: total_formatado = self.valor_base
            
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med_id,)).fetchone(); con.close()
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            if r:
                emb_pix.description = f"**Valor Total (Aposta + Sala):** R$ {total_formatado}\n\n**Nome:** {r[0]}\n**Chave:** `{r[1]}`"
                if r[2]: emb_pix.set_image(url=r[2]) # QR Code cadastrado
            else:
                emb_pix.description = "O mediador não cadastrou chave PIX."
            await it.channel.send(embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, b): await it.channel.delete()

# ================= COMANDO .FILA (INICIA TÓPICO AGUARDANDO) =================
@bot.command()
async def fila(ctx, modo: str, valor: str):
    class VF(View):
        def __init__(self): super().__init__(timeout=None); self.u = []
        def ge(self):
            txt = "\n".join([f"👤 {u.mention} - {g}" for u, g in self.u]) if self.u else "Fila Vazia"
            emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=0x3498DB)
            emb.add_field(name="👑 Modo", value=modo); emb.add_field(name="💎 Valor", value=f"R$ {valor}")
            emb.add_field(name="⚡ Jogadores", value=txt, inline=False); emb.set_image(url=BANNER_URL)
            return emb
        
        async def entrar(self, it, g):
            if any(x.id == it.user.id for x, _ in self.u): return
            self.u.append((it.user, g))
            if len(self.u) == 2:
                p1, g1 = self.u[0]; p2, g2 = self.u[1]; self.u = []; await it.message.edit(embed=self.ge())
                if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores disponíveis!", ephemeral=True)
                
                med_id = fila_mediadores.pop(0)
                c_ids = [pegar_config(f"canal_{i}") for i in range(1,4)]; val = [int(i) for i in c_ids if i]
                chan = bot.get_channel(random.choice(val)) if val else it.channel
                
                # TÓPICO: Inicia como "⌛｜aguardando-confirmaçao"
                th = await chan.create_thread(name="⌛｜aguardando-confirmaçao", type=discord.ChannelType.public_thread)
                partidas_ativas[th.id] = {'modo': f"{modo} | {g}", 'valor': valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
                
                emb_p = discord.Embed(title="⚔️ Partida Localizada", color=0x2b2d31)
                emb_p.add_field(name="💸 Valor", value=f"R$ {valor}", inline=True)
                emb_p.add_field(name="🎙️ Mediador", value=f"<@{med_id}>", inline=True)
                emb_p.add_field(name="👥 Jogadores", value=f"{p1.mention} vs {p2.mention}", inline=False)
                await th.send(embed=emb_p, view=ViewTopico(p1.id, p2.id, med_id, valor))
                await it.response.send_message(f"✅ Tópico criado: {th.mention}", ephemeral=True)
            else: await it.response.edit_message(embed=self.ge())

        @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
        async def b1(self, it, b): await self.entrar(it, "Gel Normal")
        @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
        async def b2(self, it, b): await self.entrar(it, "Gel Infinito")
    await ctx.send(embed=VF().ge(), view=VF())

# ================= CONFIGURAÇÕES E CANAL =================
@bot.command()
async def canal(ctx):
    class VC(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Selecionar Canal de Tópicos")
        async def c1(self, it, s): salvar_config("canal_1", s.values[0].id); await it.response.send_message("✅ Canal configurado!", ephemeral=True)
    await ctx.send("📍 Selecione onde os tópicos serão criados:", view=VC())

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class VConfig(View):
        @discord.ui.button(label="Mudar Nome", style=discord.ButtonStyle.secondary)
        async def mn(self, it, b):
            class M(Modal, title="Novo Nome"):
                n = TextInput(label="Nome")
                async def on_submit(self, i): await bot.user.edit(username=self.n.value); await i.response.send_message("Nome alterado!", ephemeral=True)
            await it.response.send_modal(M())
        @discord.ui.button(label="Mudar Foto", style=discord.ButtonStyle.secondary)
        async def mf(self, it, b):
            class M(Modal, title="Link da Foto"):
                u = TextInput(label="Link URL")
                async def on_submit(self, i):
                    async with aiohttp.ClientSession() as s:
                        async with s.get(self.u.value) as r: d = await r.read(); await bot.user.edit(avatar=d)
                    await i.response.send_message("Foto alterada!", ephemeral=True)
            await it.response.send_modal(M())
    await ctx.send("⚙️ Painel de Identidade do Bot:", view=VConfig())

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} pronto para mediar!")

bot.run(TOKEN)
                                                              
