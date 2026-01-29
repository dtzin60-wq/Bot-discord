import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio, aiohttp

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 

# ================= BANCO DE DADOS =================
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

# ================= GATILHO ID E SENHA (PAINEL FINAL) =================
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
                await message.channel.send("✅ **ID recebido.** Envie a **Senha** agora.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados.pop(tid)
                await message.delete()
                
                emb = discord.Embed(title="🚀 DADOS DA PARTIDA", color=0x2ecc71)
                emb.description = (
                    f"**Modo :** {dados['modo']}\n"
                    f"**Valor :** R$ {dados['valor']}\n"
                    f"**Jogadores :** <@{dados['p1']}> vs <@{dados['p2']}>\n"
                    f"**Mediador :** <@{dados['med']}>\n\n"
                    f"**Id da sala :** `{id_sala}`\n"
                    f"**Senha da sala:** `{senha}`"
                )
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    await bot.process_commands(message)

# ================= LÓGICA DO TÓPICO (PAINEL DE CONFIRMAÇÃO DA FOTO) =================
class ViewTopico(View):
    def __init__(self, p1, p2, med, val, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.modo = p1, p2, med, val, modo
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        if it.user.id not in [self.p1, self.p2]:
            return await it.response.send_message("❌ Você não está nesta partida!", ephemeral=True)
        
        if it.user.id in self.conf:
            return await it.response.send_message("⚠️ Você já confirmou!", ephemeral=True)
            
        self.conf.add(it.user.id)
        
        # --- PAINEL IGUAL À FOTO ENVIADA ---
        emb_confirmacao = discord.Embed(
            title="🟩 | Partida Confirmada", 
            description=f"{it.user.mention} confirmou a aposta!\n╰👉 O outro jogador precisa confirmar para continuar.", 
            color=0x2ecc71
        )
        await it.response.send_message(embed=emb_confirmacao)

        if len(self.conf) == 2:
            await asyncio.sleep(2)
            await it.channel.purge(limit=15)
            
            con = sqlite3.connect("dados.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()
            con.close()
            
            # Taxa de 0.10 aplicada automaticamente
            v_f = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            
            emb_p = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_p.add_field(name="👤 Titular", value=r[0] if r else "Não cadastrado", inline=True)
            emb_p.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Não cadastrada", inline=True)
            emb_p.add_field(name="💰 Valor Total", value=f"R$ {v_f}", inline=False)
            
            if r and r[2]: # Exibe o QR Code se o link for válido
                emb_p.set_image(url=r[2])
            
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_p)

# ================= COMANDO .FILA =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.users = modo, valor, []

    def gerar_embed(self):
        txt = "Vazio" if not self.users else "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users])
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Jogadores", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.users): return
        self.users.append((it.user, gelo))
        
        if len(self.users) == 2:
            p1, p2 = self.users[0][0], self.users[1][0]
            self.users = []
            
            if not fila_mediadores: 
                return await it.response.send_message("❌ Sem mediadores online!", ephemeral=True)
            
            med_id = fila_mediadores.pop(0)
            c_id = pegar_config("canal_1")
            canal = bot.get_channel(int(c_id)) if c_id else it.channel
            
            th = await canal.create_thread(name=f"⚔️-aposta-{self.valor}", type=discord.ChannelType.public_thread)
            partidas_ativas[th.id] = {'modo': f"{self.modo} ({gelo})", 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            
            emb_local = discord.Embed(title="⚔️ Partida Localizada", description=f"{p1.mention} vs {p2.mention}\n\nAmbos confirmem abaixo para liberar o PIX.")
            await th.send(embed=emb_local, view=ViewTopico(p1.id, p2.id, med_id, self.valor, self.modo))
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gelo Infinito")

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger)
    async def s(self, it, b):
        self.users = [u for u in self.users if u[0].id != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

# ================= COMANDOS DE ADMIN E CONFIG =================
@bot.command()
async def fila(ctx, modo, valor):
    await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Cadastrar Dados Pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class MPix(Modal, title="Configurar PIX"):
                n = TextInput(label="Nome do titular da conta")
                c = TextInput(label="Chave Pix")
                q = TextInput(label="QR Code (Link da Imagem)", required=False)
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
                    await i.response.send_message("✅ Seus dados foram salvos!", ephemeral=True)
            await it.response.send_modal(MPix())
    await ctx.send(embed=discord.Embed(title="💳 Configuração de Pagamento", color=0x4b0082), view=VPix())

@bot.command()
async def mediar(ctx):
    class VMed(View):
        def ge(self):
            txt = "\n".join([f"🟢 <@{u}>" for u in fila_mediadores]) if fila_mediadores else "Vazia"
            return discord.Embed(title="Fila de Mediadores", description=txt, color=0x4b0082)
        @discord.ui.button(label="Ficar Online", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.ge())
    await ctx.send(embed=VMed().ge(), view=VMed())

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i):
        salvar_config("canal_1", sel.values[0].id)
        await i.response.send_message(f"✅ Canal definido: {sel.values[0].mention}", ephemeral=True)
    sel.callback = cb; v.add_item(sel)
    await ctx.send("Selecione onde criar os tópicos:", view=v)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ Bot Online: {bot.user}")

bot.run(TOKEN)
    
