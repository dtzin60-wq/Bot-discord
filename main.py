import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio

# Configurações de Ambiente
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Cache temporário
fila_mediadores = []
partidas = {}

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

# ================= VIEWS DO TÓPICO (PAINEL DE CONFIRMAÇÃO) =================
class ViewTopico(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, it, b):
        # Gera o embed de confirmação parcial
        embed = discord.Embed(title="✅ | Partida Confirmada", color=discord.Color.green())
        embed.description = f"**{it.user.mention}** confirmou a aposta!\n↳ O outro jogador precisa confirmar para continuar."
        await it.response.send_message(embed=embed)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, b):
        await it.response.send_message("❌ Aposta recusada. O tópico será deletado em 5 segundos...")
        await asyncio.sleep(5)
        await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it, b):
        # Embed informativo de regras
        embed = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=discord.Color.blue())
        embed.description = ("• Regras adicionais podem ser combinadas entre os participantes.\n"
                             "• Se a regra não existir no regulamento oficial, tire print do acordo.")
        await it.response.send_message(embed=embed)

# ================= FILA (APARIÇÃO IMEDIATA E EXPULSÃO) =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.users = [] # Lista de (member, tipo_gelo)

    def gerar_embed(self):
        # Lista os jogadores ou exibe mensagem de fila vazia
        txt = "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users]) if self.users else "Nenhum jogador na fila"
        emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=discord.Color.blue())
        emb.add_field(name="👑 Modo", value=f"**{self.modo}**", inline=True)
        emb.add_field(name="💎 Valor", value=f"**R$ {self.valor}**", inline=True)
        emb.add_field(name="⚡ Jogadores", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.users):
            return await it.response.send_message("Você já está na fila!", ephemeral=True)
        
        self.users.append((it.user, gelo))
        
        if len(self.users) == 2:
            # PARTIDA FORMADA: Jogadores são expulsos da fila
            p1, g1 = self.users[0]
            p2, g2 = self.users[1]
            self.users = [] 
            await it.message.edit(embed=self.gerar_embed()) # Limpa o painel da fila

            if not fila_mediadores:
                return await it.response.send_message("❌ Sem mediadores em serviço!", ephemeral=True)

            med_id = fila_mediadores.pop(0)
            
            # Seleção de canal para o tópico
            canal_id = pegar_config("canal_1")
            canal_alvo = bot.get_channel(int(canal_id)) if canal_id else it.channel
            
            thread = await canal_alvo.create_thread(
                name=f"Aposta-{self.valor}-{p1.name}", 
                type=discord.ChannelType.public_thread
            )

            # Painel do Tópico Fiel às fotos
            emb_p = discord.Embed(title="Partida Confirmada", color=0x2b2d31)
            emb_p.add_field(name="🎮 Estilo de Jogo", value=f"1v1 | {gelo}", inline=False)
            emb_p.add_field(name="ℹ️ Informações da Aposta", value=f"Valor Da Sala: R$ 0,00\nMediador: <@{med_id}>", inline=False)
            emb_p.add_field(name="💸 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            emb_p.add_field(name="👥 Jogadores", value=f"{p1.mention}\n{p2.mention}", inline=False)
            emb_p.set_thumbnail(url="https://i.imgur.com/8NnO8Z1.png")

            await thread.send(f"{p1.mention} {p2.mention} | Mediador: <@{med_id}>")
            await thread.send(embed=emb_p, view=ViewTopico())
            await it.response.send_message(f"✅ Partida Iniciada! Tópico: {thread.mention}", ephemeral=True)
        else:
            # Aparição imediata do nome na fila ao clicar
            await it.response.edit_message(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gel Normal")

    @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gel Infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, it, b):
        self.users = [u for u in self.users if u[0].id != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed(), view=self)

# ================= COMANDOS E PAINÉIS ADICIONAIS =================

@bot.command()
async def mediar(ctx):
    class VMed(View):
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
        async def e(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.send_message("Você agora é um mediador ativo.", ephemeral=True)
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            await it.response.send_message("Você saiu da fila de mediadores.", ephemeral=True)
        @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️")
        async def r(self, it, b): await it.response.send_message("Ação restrita.", ephemeral=True)
        @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️")
        async def ps(self, it, b): await it.response.send_message("Painel restrito.", ephemeral=True)

    emb = discord.Embed(title="Painel da fila controladora", description="Entre na fila para começar a mediar suas filas", color=0x4b0082)
    await ctx.send(embed=emb, view=VMed()) # Baseado na imagem

@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class MPix(Modal, title="Cadastro de PIX"):
                n = TextInput(label="Nome Completo")
                c = TextInput(label="Chave PIX")
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (i.user.id, self.n.value, self.c.value))
                    await i.response.send_message("✅ Chave salva com sucesso!", ephemeral=True)
            await it.response.send_modal(MPix())
        @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍")
        async def sc(self, it, b): await it.response.send_message("Sua chave está configurada.", ephemeral=True)
        @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
        async def vm(self, it, b): await it.response.send_message("Apenas para administradores.", ephemeral=True)

    emb = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.", color=0x4b0082)
    await ctx.send(embed=emb, view=VPix()) # Baseado na imagem

@bot.command()
async def fila(ctx, modo: str, valor: str, tipo: str = "MOBILE"):
    v = ViewFila(f"{modo} {tipo}", valor)
    await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def canal(ctx):
    class VCanal(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Selecione o canal para os tópicos")
        async def c(self, it, s): 
            salvar_config("canal_1", s.values[0].id)
            await it.response.send_message("Canal configurado!", ephemeral=True)
    await ctx.send("📍 Onde as partidas serão criadas?", view=VCanal())

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} pronto no Railway!")

bot.run(TOKEN)
        
