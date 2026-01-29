import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio

TOKEN = os.getenv("TOKEN")

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
filas = {}
partidas = {}

# ================= DB =================
def init_db():
    conn = sqlite3.connect("dados.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    conn.commit()
    conn.close()

def db_exec(q, p=()):
    conn = sqlite3.connect("dados.db")
    c = conn.cursor()
    c.execute(q, p)
    conn.commit()
    conn.close()

def salvar(ch, val):
    db_exec("INSERT OR REPLACE INTO config VALUES (?,?)", (ch, str(val)))

def puxar(ch):
    conn = sqlite3.connect("dados.db")
    r = conn.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    conn.close()
    return r[0] if r else None

async def perm(it, chave):
    if it.user.guild_permissions.administrator:
        return True
    c = puxar(chave)
    if c and any(r.id == int(c) for r in it.user.roles):
        return True
    return False

# ================= AUX =================
class ViewAux(View):
    def __init__(self, tid):
        super().__init__(timeout=None)
        self.tid = tid

    @discord.ui.button(label="Dar Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, b):
        dados = partidas.get(self.tid)
        if not dados: return
        class V(View):
            def __init__(self):
                super().__init__()
                for j in dados["jogadores"]:
                    bt = Button(label=j.name)
                    async def cb(i, alvo=j):
                        await i.response.send_message(f"🏆 Vitória para {alvo.mention}")
                    bt.callback = cb
                    self.add_item(bt)
        await it.response.send_message("Escolha:", view=V(), ephemeral=True)

    @discord.ui.button(label="Vitória W.O", style=discord.ButtonStyle.gray)
    async def wo(self, it, b):
        dados = partidas.get(self.tid)
        if not dados: return
        class V(View):
            def __init__(self):
                super().__init__()
                for j in dados["jogadores"]:
                    bt = Button(label=j.name)
                    async def cb(i, alvo=j):
                        await i.response.send_message(f"🏆 W.O para {alvo.mention}")
                    bt.callback = cb
                    self.add_item(bt)
        await it.response.send_message("Escolha:", view=V(), ephemeral=True)

    @discord.ui.button(label="Finalizar Aposta", style=discord.ButtonStyle.red)
    async def fin(self, it, b):
        await it.channel.edit(archived=True, locked=True)
        partidas.pop(self.tid, None)

# ================= CONFIRMA =================
class ViewConfirm(View):
    def __init__(self, p1, p2, med, modo, valor, gelo):
        super().__init__(timeout=None)
        self.p1 = p1
        self.p2 = p2
        self.med = med
        self.modo = modo
        self.valor = valor
        self.gelo = gelo
        self.ok = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def conf(self, it, b):
        if it.user not in [self.p1, self.p2]: return
        if it.user in self.ok: return
        self.ok.append(it.user)

        if len(self.ok) == 1:
            return await it.response.send_message("⏳ Aguardando o outro jogador...", ephemeral=True)

        canais = [puxar(f"canal_{i}") for i in range(1,4)]
        canais = [int(c) for c in canais if c]
        canal = bot.get_channel(random.choice(canais))

        thread = await canal.create_thread(name=f"{self.p1.name} vs {self.p2.name}")

        partidas[thread.id] = {"jogadores":[self.p1,self.p2],"med":self.med}

        emb = discord.Embed(title="🎮 PARTIDA CRIADA")
        emb.add_field(name="Modo", value=self.gelo)
        emb.add_field(name="Valor", value=self.valor)
        emb.set_image(url=BANNER_URL)

        await thread.send(f"{self.p1.mention} vs {self.p2.mention}\nMediador: <@{self.med}>")
        await thread.send(embed=emb)
        await thread.send("Use `.aux` para gerenciar.")

        await it.response.send_message(f"✅ Tópico criado: {thread.mention}")

# ================= FILA =================
class ViewFila(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.modo = modo
        self.valor = valor

    async def atualizar(self, msg):
        lista = filas.get(self.chave, [])
        txt = "\n".join([f"{u.mention} - {g}" for u,g in lista]) if lista else "Nenhum jogador"
        e = discord.Embed(title="🎮 FILA DE PARTIDA")
        e.add_field(name="Modo", value=self.modo)
        e.add_field(name="Valor", value=self.valor)
        e.add_field(name="Jogadores", value=txt, inline=False)
        e.set_image(url=BANNER_URL)
        await msg.edit(embed=e, view=self)

    async def entrar(self, it, gelo):
        filas.setdefault(self.chave, [])

        for u,g in filas[self.chave]:
            if u.id == it.user.id:
                return await it.response.send_message("Você já está na fila.", ephemeral=True)

        filas[self.chave].append((it.user, gelo))

        if len(filas[self.chave]) == 2:
            g1 = filas[self.chave][0][1]
            g2 = filas[self.chave][1][1]

            if g1 != g2:
                await it.response.send_message("❌ Os dois devem escolher o MESMO modo.", ephemeral=True)
                return

            if not fila_mediadores:
                return await it.response.send_message("❌ Nenhum mediador disponível.", ephemeral=True)

            med = fila_mediadores.pop(0)
            await it.response.send_message("💰 Confirmem o pagamento:", view=ViewConfirm(
                filas[self.chave][0][0],
                filas[self.chave][1][0],
                med,
                self.modo,
                self.valor,
                g1
            ))
        else:
            await it.response.send_message("Você entrou na fila.", ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal")
    async def g1(self, it, b): await self.entrar(it, "gelo normal")

    @discord.ui.button(label="Gelo infinito")
    async def g2(self, it, b): await self.entrar(it, "gelo infinito")

# ================= COMANDOS =================
@bot.command()
async def fila(ctx, modo: str, valor: str, tipo: str="mobile"):
    modo_final = f"{modo}-{tipo}"
    chave = str(ctx.message.id)
    v = ViewFila(chave, modo_final, valor)
    msg = await ctx.send("Criando fila...", view=v)
    await v.atualizar(msg)

@bot.command()
async def mediar(ctx):
    class V(View):
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user.id not in fila_mediadores:
                fila_mediadores.append(it.user.id)
            await it.response.send_message("Você entrou na fila de mediadores.", ephemeral=True)
    await ctx.send("🎧 Fila de mediadores:", view=V())

@bot.command()
async def Pix(ctx):
    class V(View):
        @discord.ui.button(label="Cadastrar Pix")
        async def p(self, it, b):
            class M(Modal, title="Cadastrar Pix"):
                nome = TextInput(label="Nome")
                chave = TextInput(label="Chave")
                async def on_submit(self, i):
                    db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?)",(i.user.id,self.nome.value,self.chave.value))
                    await i.response.send_message("Pix salvo.", ephemeral=True)
            await it.response.send_modal(M())
    await ctx.send("💠 Painel Pix:", view=V())

@bot.command()
async def canal(ctx):
    class V(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 1")
        async def c1(self, it, sel): salvar("canal_1", sel.values[0].id)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 2")
        async def c2(self, it, sel): salvar("canal_2", sel.values[0].id)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 3")
        async def c3(self, it, sel): salvar("canal_3", sel.values[0].id)
    await ctx.send("Escolha os canais:", view=V())

@bot.command()
async def botconfig(ctx):
    class V(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Quem usa .aux")
        async def a(self, it, sel): salvar("perm_aux", sel.values[0].id)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem é mediador")
        async def b(self, it, sel): salvar("perm_mediador", sel.values[0].id)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem usa comandos")
        async def c(self, it, sel): salvar("perm_geral", sel.values[0].id)
    await ctx.send("⚙️ Configurações:", view=V())

@bot.command()
async def aux(ctx):
    if not isinstance(ctx.channel, discord.Thread):
        return await ctx.send("Use este comando dentro do tópico.")
    await ctx.send("🛠️ Gerenciar partida:", view=ViewAux(ctx.channel.id))

@bot.event
async def on_ready():
    init_db()
    print("🔥 BOT PREMIUM ONLINE")

bot.run(TOKEN)
