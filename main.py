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

# ================= DATABASE =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit()
    con.close()

def db(q, p=()):
    con = sqlite3.connect("dados.db")
    con.execute(q, p)
    con.commit()
    con.close()

def salvar(ch, v):
    db("INSERT OR REPLACE INTO config VALUES (?,?)",(ch,str(v)))

def pegar(ch):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?",(ch,)).fetchone()
    con.close()
    return r[0] if r else None

async def perm(it, chave):
    if it.user.guild_permissions.administrator: return True
    r = pegar(chave)
    if r and any(role.id == int(r) for role in it.user.roles): return True
    return False

# ================= CONFIRMA =================
class ViewConfirm(View):
    def __init__(self,p1,p2,med,modo,valor,gelo):
        super().__init__(timeout=None)
        self.p1=p1; self.p2=p2; self.med=med
        self.modo=modo; self.valor=valor; self.gelo=gelo
        self.ok=[]

    @discord.ui.button(label="Confirmar pagamento",style=discord.ButtonStyle.green)
    async def conf(self,it,b):
        if it.user not in [self.p1,self.p2]: return
        if it.user in self.ok: return
        self.ok.append(it.user)

        if len(self.ok)==1:
            return await it.response.send_message("⏳ Aguardando o outro jogador...",ephemeral=True)

        canais=[pegar(f"canal_{i}") for i in range(1,4)]
        canais=[int(c) for c in canais if c]
        canal=bot.get_channel(random.choice(canais))

        thread=await canal.create_thread(name=f"{self.p1.name} vs {self.p2.name}")

        partidas[thread.id]={"jogadores":[self.p1,self.p2],"med":self.med}

        con=sqlite3.connect("dados.db")
        pix1=con.execute("SELECT nome,chave FROM pix WHERE user_id=?",(self.p1.id,)).fetchone()
        pix2=con.execute("SELECT nome,chave FROM pix WHERE user_id=?",(self.p2.id,)).fetchone()
        con.close()

        emb=discord.Embed(title="🎮 PARTIDA CRIADA",color=0x2ecc71)
        emb.add_field(name="Modo",value=self.gelo)
        emb.add_field(name="Valor",value=f"R$ {self.valor}")
        emb.set_image(url=BANNER_URL)

        await thread.send(f"{self.p1.mention} vs {self.p2.mention}\nMediador: <@{self.med}>")
        await thread.send(embed=emb)

        if pix1:
            await thread.send(f"💰 PIX {self.p1.mention}\nNome: {pix1[0]}\nChave: `{pix1[1]}`")
        if pix2:
            await thread.send(f"💰 PIX {self.p2.mention}\nNome: {pix2[0]}\nChave: `{pix2[1]}`")

        await thread.send("Use `.aux` para gerenciar.")
        await it.response.send_message(f"✅ Tópico criado: {thread.mention}")

# ================= AUX =================
class ViewAux(View):
    def __init__(self,tid):
        super().__init__(timeout=None)
        self.tid=tid

    def botoes(self,tipo):
        dados=partidas.get(self.tid)
        class V(View):
            def __init__(self):
                super().__init__()
                for j in dados["jogadores"]:
                    bt=Button(label=j.name)
                    async def cb(i,alvo=j):
                        await i.response.send_message(f"🏆 Vitória {tipo} para {alvo.mention}")
                    bt.callback=cb
                    self.add_item(bt)
        return V()

    @discord.ui.button(label="Dar vitória",style=discord.ButtonStyle.green)
    async def v(self,it,b):
        await it.response.send_message("Escolha:",view=self.botoes("normal"),ephemeral=True)

    @discord.ui.button(label="Vitória W.O",style=discord.ButtonStyle.gray)
    async def wo(self,it,b):
        await it.response.send_message("Escolha:",view=self.botoes("W.O"),ephemeral=True)

    @discord.ui.button(label="Finalizar aposta",style=discord.ButtonStyle.red)
    async def f(self,it,b):
        await it.channel.edit(archived=True,locked=True)
        partidas.pop(self.tid,None)

# ================= FILA =================
class ViewFila(View):
    def __init__(self,chave,modo,valor):
        super().__init__(timeout=None)
        self.chave=chave; self.modo=modo; self.valor=valor

    async def atualizar(self,msg):
        lista=filas.get(self.chave,[])
        txt="\n".join([f"{u.mention} - {g}" for u,g in lista]) if lista else "Nenhum jogador"
        e=discord.Embed(title="🎮 FILA")
        e.add_field(name="Modo",value=self.modo)
        e.add_field(name="Valor",value=self.valor)
        e.add_field(name="Jogadores",value=txt,inline=False)
        e.set_image(url=BANNER_URL)
        await msg.edit(embed=e,view=self)

    async def entrar(self,it,gelo):
        filas.setdefault(self.chave,[])
        if any(u.id==it.user.id for u,g in filas[self.chave]):
            return await it.response.send_message("Você já está.",ephemeral=True)

        filas[self.chave].append((it.user,gelo))

        if len(filas[self.chave])==2:
            g1=filas[self.chave][0][1]
            g2=filas[self.chave][1][1]
            if g1!=g2:
                return await it.response.send_message("❌ Escolham o mesmo modo.",ephemeral=True)
            if not fila_mediadores:
                return await it.response.send_message("❌ Sem mediador.",ephemeral=True)

            med=fila_mediadores.pop(0)
            await it.response.send_message("💰 Confirmem:",view=ViewConfirm(
                filas[self.chave][0][0],
                filas[self.chave][1][0],
                med,
                self.modo,
                self.valor,
                g1
            ))
            filas[self.chave]=[]
        else:
            await it.response.send_message("Você entrou.",ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="🧊 Gelo normal")
    async def g1(self,it,b): await self.entrar(it,"gelo normal")

    @discord.ui.button(label="❄️ Gelo infinito")
    async def g2(self,it,b): await self.entrar(it,"gelo infinito")

# ================= COMANDOS =================
@bot.command()
async def fila(ctx,modo:str,valor:str,tipo:str="mobile"):
    modo_final=f"{modo}-{tipo}"
    chave=str(ctx.message.id)
    v=ViewFila(chave,modo_final,valor)
    msg=await ctx.send("Criando fila...",view=v)
    await v.atualizar(msg)

@bot.command()
async def mediar(ctx):
    class V(View):
        @discord.ui.button(label="Entrar na fila",style=discord.ButtonStyle.green)
        async def e(self,it,b):
            if it.user.id not in fila_mediadores:
                fila_mediadores.append(it.user.id)
            await it.response.send_message("Você virou mediador.",ephemeral=True)
    await ctx.send("🎧 Fila mediadores:",view=V())

@bot.command()
async def Pix(ctx):
    class V(View):
        @discord.ui.button(label="Cadastrar Pix")
        async def p(self,it,b):
            class M(Modal,title="Pix"):
                nome=TextInput(label="Nome")
                chave=TextInput(label="Chave")
                async def on_submit(self,i):
                    db("INSERT OR REPLACE INTO pix VALUES (?,?,?)",(i.user.id,self.nome.value,self.chave.value))
                    await i.response.send_message("Pix salvo.",ephemeral=True)
            await it.response.send_modal(M())
    await ctx.send("💠 Painel Pix:",view=V())

@bot.command()
async def canal(ctx):
    class V(View):
        @discord.ui.select(cls=ChannelSelect,placeholder="Canal 1")
        async def c1(self,it,s): salvar("canal_1",s.values[0].id)
        @discord.ui.select(cls=ChannelSelect,placeholder="Canal 2")
        async def c2(self,it,s): salvar("canal_2",s.values[0].id)
        @discord.ui.select(cls=ChannelSelect,placeholder="Canal 3")
        async def c3(self,it,s): salvar("canal_3",s.values[0].id)
    await ctx.send("Escolha canais:",view=V())

@bot.command()
async def botconfig(ctx):
    class V(View):
        @discord.ui.select(cls=RoleSelect,placeholder="Quem usa .aux")
        async def a(self,it,s): salvar("perm_aux",s.values[0].id)
        @discord.ui.select(cls=RoleSelect,placeholder="Quem é mediador")
        async def b(self,it,s): salvar("perm_mediador",s.values[0].id)
        @discord.ui.select(cls=RoleSelect,placeholder="Quem usa comandos")
        async def c(self,it,s): salvar("perm_geral",s.values[0].id)
    await ctx.send("⚙️ Config:",view=V())

@bot.command()
async def aux(ctx):
    if not isinstance(ctx.channel,discord.Thread):
        return await ctx.send("Use no tópico.")
    await ctx.send("🛠️ Gerenciar:",view=ViewAux(ctx.channel.id))

@bot.event
async def on_ready():
    init_db()
    print("🔥 BOT ULTRA ONLINE")

bot.run(TOKEN)
