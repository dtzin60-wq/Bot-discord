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
partidas_ativas = {} # Para rastrear confirmações e mediador do tópico

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

# ================= COMANDO BOTCONFIG =================
@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Apenas administradores.")

    class ViewConfig(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar os comandos?")
        async def p_geral(self, it, s):
            salvar_config("role_geral", s.values[0].id)
            await it.response.send_message("✅ Permissão Geral configurada.", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode dar aux?")
        async def p_aux(self, it, s):
            salvar_config("role_aux", s.values[0].id)
            await it.response.send_message("✅ Permissão Auxiliar configurada.", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode entrar na fila controladora?")
        async def p_med(self, it, s):
            salvar_config("role_mediador", s.values[0].id)
            await it.response.send_message("✅ Permissão Mediadores configurada.", ephemeral=True)

    emb = discord.Embed(title="⚙️ Painel de Configuração", color=discord.Color.blue())
    await ctx.send(embed=embed, view=ViewConfig())

# ================= FILA CONTROLADORA =================
class ViewMed(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        txt = "\n".join([f"🟢 <@{uid}>" for uid in fila_mediadores]) if fila_mediadores else "Nenhum mediador em serviço"
        emb = discord.Embed(title="Painel da fila controladora", description="Clique abaixo para entrar ou sair da fila.", color=0x4b0082)
        emb.add_field(name="Mediadores Online:", value=txt)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def e(self, it, b):
        role_id = pegar_config("role_mediador")
        if role_id and not any(r.id == int(role_id) for r in it.user.roles):
            return await it.response.send_message("❌ Sem permissão.", ephemeral=True)
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed(), view=self)
        else:
            await it.response.send_message("Já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def s(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed(), view=self)

@bot.command()
async def mediar(ctx):
    v = ViewMed()
    await ctx.send(embed=v.gerar_embed(), view=v)

# ================= SISTEMA DE PIX =================
@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class MPix(Modal, title="Configurar PIX"):
                n = TextInput(label="Nome Completo")
                c = TextInput(label="Chave PIX")
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (i.user.id, self.n.value, self.c.value))
                    await i.response.send_message("✅ PIX Salvo!", ephemeral=True)
            await it.response.send_modal(MPix())

        @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.blurple, emoji="🔍")
        async def sc(self, it, b):
            con = sqlite3.connect("dados.db")
            res = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (it.user.id,)).fetchone()
            con.close()
            if res:
                await it.response.send_message(f"💠 **Seu PIX:**\n**Nome:** {res[0]}\n**Chave:** `{res[1]}`", ephemeral=True)
            else:
                await it.response.send_message("❌ Nenhuma chave cadastrada.", ephemeral=True)

    emb = discord.Embed(title="💠 Painel Para Configurar Chave PIX", description="Configure ou visualize sua chave PIX abaixo.", color=0x4b0082)
    await ctx.send(embed=emb, view=VPix())

# ================= LÓGICA DO TÓPICO E CONFIRMAÇÃO =================
class ViewTopico(View):
    def __init__(self, p1_id, p2_id, med_id):
        super().__init__(timeout=None)
        self.p1_id = p1_id
        self.p2_id = p2_id
        self.med_id = med_id
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, it, b):
        if it.user.id not in [self.p1_id, self.p2_id]:
            return await it.response.send_message("Você não é um dos jogadores!", ephemeral=True)
        
        self.confirmados.add(it.user.id)
        await it.response.send_message(f"✅ **{it.user.mention}** confirmou!", delete_after=5)

        if len(self.confirmados) == 2:
            # LIMPAR MENSAGENS E MOSTRAR PIX
            await it.channel.purge(limit=10) # Apaga as mensagens anteriores do tópico
            
            con = sqlite3.connect("dados.db")
            res = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (self.med_id,)).fetchone()
            con.close()
            
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=discord.Color.gold())
            if res:
                emb_pix.description = f"Ambos confirmaram! Realizem o pagamento para o mediador:\n\n**Nome:** {res[0]}\n**Chave PIX:** `{res[1]}`"
            else:
                emb_pix.description = f"Ambos confirmaram! O mediador <@{self.med_id}> ainda não cadastrou o PIX no comando `.Pix`."
            
            await it.channel.send(content=f"<@{self.p1_id}> <@{self.p2_id}>", embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, b):
        await it.response.send_message("❌ Aposta cancelada. Deletando tópico...")
        await asyncio.sleep(3)
        await it.channel.delete()

# ================= FILA DE JOGADORES =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo; self.valor = valor; self.users = []

    def gerar_embed(self):
        txt = "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users]) if self.users else "Nenhum jogador na fila"
        emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=discord.Color.blue())
        emb.add_field(name="👑 Modo", value=self.modo)
        emb.add_field(name="💎 Valor", value=f"R$ {self.valor}")
        emb.add_field(name="⚡ Jogadores", value=txt, inline=False)
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
            thread = await it.channel.create_thread(name=f"Aposta-{self.valor}", type=discord.ChannelType.public_thread)
            
            emb_p = discord.Embed(title="Partida Confirmada", color=0x2b2d31)
            emb_p.add_field(name="🎮 Estilo de Jogo", value=f"1v1 | {gelo}", inline=False)
            emb_p.add_field(name="ℹ️ Informações da Aposta", value=f"Mediador: <@{med_id}>", inline=False)
            emb_p.add_field(name="💸 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            emb_p.add_field(name="👥 Jogadores", value=f"{p1.mention}\n{p2.mention}", inline=False)
            
            await thread.send(f"{p1.mention} {p2.mention} | Mediador: <@{med_id}>")
            await thread.send(embed=emb_p, view=ViewTopico(p1.id, p2.id, med_id))
            await it.response.send_message(f"✅ Tópico: {thread.mention}", ephemeral=True)
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

@bot.command()
async def fila(ctx, modo: str, valor: str):
    v = ViewFila(modo, valor)
    await ctx.send(embed=v.gerar_embed(), view=v)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} ONLINE")

bot.run(TOKEN)
            
