import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio, re

# Configurações de Ambiente
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Cache e Memória
fila_mediadores = []
partidas_ativas = {} 

# ================= DATABASE =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)")
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

# ================= COMANDO .CANAL (CONFIGURAR 3 CANAIS) =================
@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Apenas administradores.")

    class ViewCanais(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Selecione o Canal 1", channel_types=[discord.ChannelType.text])
        async def c1(self, it, s):
            salvar_config("canal_1", s.values[0].id)
            await it.response.send_message(f"✅ Canal 1 definido: {s.values[0].mention}", ephemeral=True)

        @discord.ui.select(cls=ChannelSelect, placeholder="Selecione o Canal 2", channel_types=[discord.ChannelType.text])
        async def c2(self, it, s):
            salvar_config("canal_2", s.values[0].id)
            await it.response.send_message(f"✅ Canal 2 definido: {s.values[0].mention}", ephemeral=True)

        @discord.ui.select(cls=ChannelSelect, placeholder="Selecione o Canal 3", channel_types=[discord.ChannelType.text])
        async def c3(self, it, s):
            salvar_config("canal_3", s.values[0].id)
            await it.response.send_message(f"✅ Canal 3 definido: {s.values[0].mention}", ephemeral=True)

    emb = discord.Embed(title="📍 Configuração de Canais", description="Selecione os 3 canais onde os tópicos de partida podem ser criados.", color=discord.Color.blue())
    await ctx.send(embed=emb, view=ViewCanais())

# ================= EVENTO GATILHO DE NÚMERO (ID/SENHA) =================
@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        if re.fullmatch(r'\d+', message.content): # Se digitar qualquer número
            dados = partidas_ativas[message.channel.id]
            if message.author.id == dados['med']:
                emb = discord.Embed(title="🚀 INÍCIO DE PARTIDA", color=0x2ecc71)
                emb.description = "A partida será iniciada em 3 a 5 minutos!"
                emb.add_field(name="👑 Modo", value=dados['modo'], inline=True)
                emb.add_field(name="💎 Valor", value=f"R$ {dados['valor']}", inline=True)
                emb.add_field(name="👥 Jogadores", value=f"<@{dados['p1']}>\n<@{dados['p2']}>", inline=False)
                emb.add_field(name="🆔 ID", value="`Aguardando...`", inline=True)
                emb.add_field(name="🔑 Senha", value="`Aguardando...`", inline=True)
                await message.channel.send(embed=emb)
    await bot.process_commands(message)

# ================= LÓGICA DO TÓPICO (CONFIRMAÇÃO E PIX) =================
class ViewTopico(View):
    def __init__(self, p1_id, p2_id, med_id):
        super().__init__(timeout=None)
        self.p1_id = p1_id; self.p2_id = p2_id; self.med_id = med_id
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, it, b):
        if it.user.id not in [self.p1_id, self.p2_id]:
            return await it.response.send_message("Você não é um jogador!", ephemeral=True)
        self.confirmados.add(it.user.id)
        await it.response.send_message(f"✅ **{it.user.mention}** confirmou!", delete_after=2)

        if len(self.confirmados) == 2:
            await it.channel.purge(limit=10) # Limpa o chat
            con = sqlite3.connect("dados.db")
            res = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (self.med_id,)).fetchone()
            con.close()
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            pix_info = f"**Nome:** {res[0]}\n**Chave:** `{res[1]}`" if res else "Mediador sem PIX cadastrado."
            emb_pix.description = f"Ambos confirmaram! Realizem o pagamento:\n\n{pix_info}"
            await it.channel.send(content=f"<@{self.p1_id}> <@{self.p2_id}>", embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, b):
        await it.channel.delete()

# ================= FILA DE JOGADORES =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo; self.valor = valor; self.users = []

    def gerar_embed(self):
        txt = "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users]) if self.users else "Nenhum jogador na fila"
        emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=0x3498DB)
        emb.add_field(name="👑 Modo", value=self.modo, inline=True)
        emb.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="⚡ Jogadores na Fila", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.users): return
        self.users.append((it.user, gelo))
        
        if len(self.users) == 2:
            p1, g1 = self.users[0]; p2, g2 = self.users[1]
            self.users = []
            await it.message.edit(embed=self.gerar_embed())
            
            if not fila_mediadores:
                return await it.response.send_message("❌ Sem mediadores online!", ephemeral=True)
            
            med_id = fila_mediadores.pop(0)
            
            # Escolher um dos 3 canais configurados
            canais_ids = [pegar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [int(i) for i in canais_ids if i]
            canal_alvo = bot.get_channel(random.choice(validos)) if validos else it.channel

            thread = await canal_alvo.create_thread(name=f"Aposta-{self.valor}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {'modo': f"{self.modo} | {gelo}", 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}

            emb_p = discord.Embed(title="Partida Confirmada", color=0x2b2d31)
            emb_p.add_field(name="🎮 Estilo de Jogo", value=f"1v1 | {gelo}", inline=False)
            emb_p.add_field(name="ℹ️ Informações", value=f"Valor Da Sala: R$ 0,10\nMediador: <@{med_id}>", inline=False)
            emb_p.add_field(name="💸 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            emb_p.add_field(name="👥 Jogadores", value=f"{p1.mention}\n{p2.mention}", inline=False)
            
            await thread.send(f"{p1.mention} {p2.mention} | Mediador: <@{med_id}>")
            await thread.send(embed=emb_p, view=ViewTopico(p1.id, p2.id, med_id))
            await it.response.send_message(f"✅ Tópico Criado: {thread.mention}", ephemeral=True)
        else:
            await it.response.edit_message(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gel Normal")
    @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gel Infinito")
    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, it, b):
        self.users = [u for u in self.users if u[0].id != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed(), view=self)

# ================= COMANDOS GERAIS =================
@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class MPix(Modal, title="Cadastrar PIX"):
                n = TextInput(label="Nome Completo"); c = TextInput(label="Chave PIX")
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (i.user.id, self.n.value, self.c.value))
                    await i.response.send_message("✅ Salvo!", ephemeral=True)
            await it.response.send_modal(MPix())
        @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.blurple, emoji="🔍")
        async def sc(self, it, b):
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
            await it.response.send_message(f"💠 {r[0]} | `{r[1]}`" if r else "Sem chave.", ephemeral=True)
    await ctx.send("💠 Painel PIX", view=VPix())

@bot.command()
async def mediar(ctx):
    class VMed(View):
        def gerar(self):
            t = "\n".join([f"🟢 <@{u}>" for u in fila_mediadores]) if fila_mediadores else "Vazia"
            return discord.Embed(title="Fila Controladora", description=t, color=0x4b0082)
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar())
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar())
    await ctx.send(embed=VMed().gerar(), view=VMed())

@bot.command()
async def fila(ctx, modo: str, valor: str):
    v = ViewFila(modo, valor)
    await ctx.send(embed=v.gerar_embed(), view=v)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ Bot Conectado!")

bot.run(TOKEN)
    
