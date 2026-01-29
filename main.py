import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3, asyncio, aiohttp, os

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 
DB_PATH = "dados.db"

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS stats (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0, consecutivas INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    con = sqlite3.connect(DB_PATH); con.execute(q, p); con.commit(); con.close()

def salvar_config(ch, v): db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", (ch, str(v)))
def pegar_config(ch):
    con = sqlite3.connect(DB_PATH); r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone(); con.close()
    return r[0] if r else None

async def tem_permissao(ctx, chave_config):
    if ctx.author.guild_permissions.administrator: return True
    role_id = pegar_config(chave_config)
    return any(r.id == int(role_id) for r in ctx.author.roles) if role_id else False

# ================= GATILHO ID/SENHA =================
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
                await message.channel.send("✅ **ID OK.** Envie a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados.pop(tid)
                await message.delete()
                await message.channel.edit(name=f"💰｜Pagar-{dados['valor']}")
                emb = discord.Embed(title="🚀 INÍCIO DE PARTIDA", color=0x2ecc71)
                emb.add_field(name="🆔 ID", value=f"`{id_sala}`", inline=True)
                emb.add_field(name="🔑 Senha", value=f"`{senha}`", inline=True)
                await message.channel.send(embed=emb)
    await bot.process_commands(message)

# ================= COMANDO FILA (ESTILO FINAL) =================
@bot.command()
async def fila(ctx, modo_input, valor):
    class VFila(View):
        def __init__(self):
            super().__init__(timeout=None)
            self.jogadores = [] 

        def gerar_embed(self):
            # Layout solicitado: Jogadores logo abaixo de Valor e Modo
            txt_jogadores = "Vazio" if not self.jogadores else "\n".join([f"{p[0].mention} - {p[1]}" for p in self.jogadores])

            emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
            emb.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
            emb.add_field(name="🏆 Modo", value=modo_input, inline=True)
            emb.add_field(name="Jogadores", value=txt_jogadores, inline=False)
            emb.set_image(url=BANNER_URL)
            return emb

        async def entrar(self, it, tipo):
            if any(p[0].id == it.user.id for p in self.jogadores):
                return await it.response.send_message("Você já está na fila!", ephemeral=True)
            
            if len(self.jogadores) < 2:
                self.jogadores.append((it.user, tipo))
                await it.response.edit_message(embed=self.gerar_embed())
            
            if len(self.jogadores) == 2:
                p1, p2 = self.jogadores[0][0], self.jogadores[1][0]
                self.jogadores = [] # Limpa para o próximo
                med = fila_mediadores.pop(0) if fila_mediadores else None
                if not med: return await it.channel.send("❌ Sem mediadores online!")
                
                c_id = pegar_config("canal_1")
                canal = bot.get_channel(int(c_id)) if c_id else ctx.channel
                th = await canal.create_thread(name="⌛｜aguardando-confirmaçao")
                partidas_ativas[th.id] = {'modo': modo_input, 'valor': valor, 'p1': p1.id, 'p2': p2.id, 'med': med}
                
                # Criar a View do Tópico (Confirmar)
                view_topico = ViewTopico(p1.id, p2.id, med, valor)
                await th.send(f"⚔️ **Partida:** {p1.mention} vs {p2.mention}", view=view_topico)

        @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="🧊")
        async def b_normal(self, it, b): await self.entrar(it, "Gelo Normal")

        @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
        async def b_infinito(self, it, b): await self.entrar(it, "Gelo Infinito")

        @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪")
        async def b_sair(self, it, b):
            removido = False
            for p in self.jogadores:
                if p[0].id == it.user.id:
                    self.jogadores.remove(p)
                    removido = True
                    break
            if removido:
                await it.response.edit_message(embed=self.gerar_embed())
            else:
                await it.response.send_message("Você não está na fila.", ephemeral=True)

    await ctx.send(embed=VFila().gerar_embed(), view=VFila())

# ================= TÓPICO DE PARTIDA =================
class ViewTopico(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val = p1, p2, med, val
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, emoji="✅")
    async def c(self, it, b):
        if it.user.id not in [self.p1, self.p2]: return
        self.conf.add(it.user.id)
        await it.response.send_message(f"✅ {it.user.mention} confirmou!")
        if len(self.conf) == 2:
            await asyncio.sleep(1); await it.channel.purge(limit=10)
            v_f = f"{(float(self.val.replace(',','.'))+0.10):.2f}".replace('.',',')
            con = sqlite3.connect(DB_PATH); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            emb = discord.Embed(title="💸 PAGAMENTO", color=0xF1C40F, description=f"**Total:** R$ {v_f}\n**Chave:** `{r[1] if r else 'N/A'}`")
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(embed=emb)

# ================= COMANDOS AUXILIARES =================
@bot.command()
async def Pix(ctx):
    if not await tem_permissao(ctx, "perm_pix"): return
    class MPix(Modal, title="Cadastro PIX"):
        n = TextInput(label="Nome Titular")
        c = TextInput(label="Chave PIX")
        q = TextInput(label="Link QR Code (Opcional)", required=False)
        async def on_submit(self, i):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
            await i.response.send_message("✅ Salvo!", ephemeral=True)
    class VPix(View):
        @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
        async def cp(self, it, b): await it.response.send_modal(MPix())
    await ctx.send("💠 Configure seu PIX", view=VPix())

@bot.command()
async def mediar(ctx):
    if not await tem_permissao(ctx, "perm_med"): return
    class VMed(View):
        def ge(self):
            txt = "\n".join([f"<@{u}>" for u in fila_mediadores]) if fila_mediadores else "Vazia"
            return discord.Embed(title="Fila Mediadores", description=txt, color=0x2b2d31)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
        async def e(self, it, b): 
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.ge())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.ge())
    await ctx.send(embed=VMed().ge(), view=VMed())

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i): salvar_config("canal_1", sel.values[0].id); await i.response.send_message("Canal OK!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal de tópicos:", view=v)

@bot.event
async def on_ready(): init_db(); print("✅ Bot Online")
bot.run(TOKEN)
