import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging
import datetime
import sys

# ==============================================================================
#                               SISTEMA DE LOGS
# ==============================================================================

# Configuração de logs para capturar erros de comandos que não funcionam
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('discord')

# ==============================================================================
#                               CONFIGURAÇÕES
# ==============================================================================

TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

# IMPORTANTE: Certifique-se de que MESSAGE CONTENT INTENT está ligada no Discord Developer Portal
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Estados de Memória
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================

def init_db():
    try:
        with sqlite3.connect("dados_bot.db") as con:
            con.execute("""CREATE TABLE IF NOT EXISTS pix (
                user_id INTEGER PRIMARY KEY,
                nome TEXT,
                chave TEXT,
                qrcode TEXT,
                partidas_feitas INTEGER DEFAULT 0
            )""")
            con.execute("""CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY,
                valor TEXT
            )""")
            con.commit()
        print("✅ Banco de dados sincronizado.")
    except Exception as e:
        print(f"❌ Erro ao iniciar Banco de Dados: {e}")

def db_execute(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

def buscar_mediador(user_id):
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (user_id,)).fetchone()

# ==============================================================================
#                             AUDITORIA INTERNA
# ==============================================================================

async def log_sistema(titulo, acao, cor=0x3498db):
    canal_id = pegar_config("canal_logs")
    if canal_id:
        canal = bot.get_channel(int(canal_id))
        if canal:
            emb = discord.Embed(title=f"🛠️ SISTEMA: {titulo}", description=acao, color=cor)
            emb.timestamp = datetime.datetime.now()
            try: await canal.send(embed=emb)
            except: pass

# ==============================================================================
#                           INTERFACE DO MEDIADOR (.Pix)
# ==============================================================================

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar Minha Chave", style=discord.ButtonStyle.green, emoji="💠", custom_id="v17_cad")
    async def cadastrar(self, it: discord.Interaction, b: Button):
        modal = Modal(title="Configurar Recebimento")
        nome = TextInput(label="Nome do Titular", placeholder="Nome completo")
        chave = TextInput(label="Chave Pix", placeholder="Sua chave")
        qr = TextInput(label="Link do QR Code (URL)", required=False)
        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)

        async def callback(interaction: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode, partidas_feitas) VALUES (?,?,?,?, (SELECT partidas_feitas FROM pix WHERE user_id=?))", 
                       (interaction.user.id, nome.value, chave.value, qr.value, interaction.user.id))
            await interaction.response.send_message("✅ Pix configurado!", ephemeral=True)
        
        modal.on_submit = callback
        await it.response.send_modal(modal)

    @discord.ui.button(label="Ver Minha Chave Pix", style=discord.ButtonStyle.gray, emoji="🔍", custom_id="v17_ver")
    async def ver(self, it: discord.Interaction, b: Button):
        r = buscar_mediador(it.user.id)
        if not r: return await it.response.send_message("❌ Sem cadastro.", ephemeral=True)
        e = discord.Embed(title="💠 Seus Dados", description=f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`", color=0x3498db)
        if r[2]: e.set_image(url=r[2])
        await it.response.send_message(embed=e, ephemeral=True)

# ==============================================================================
#                           INTERFACE DA FILA (.mediar)
# ==============================================================================

class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        txt = ""
        for i, uid in enumerate(fila_mediadores):
            r = buscar_mediador(uid)
            txt += f"**{i+1} •** {r[0] if r else 'Mediador'} (<@{uid}>)\n"
        return discord.Embed(title="🛡️ Fila de Mediadores Online", description=txt or "Ninguém online.", color=0x2b2d31)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, custom_id="v17_in")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, custom_id="v17_out")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                         PROCESSAMENTO DE PARTIDAS
# ==============================================================================

class ViewConfirmar(View):
    def __init__(self, p1, p2, med, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.valor, self.modo = p1, p2, med, valor, modo
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def ok(self, it, b):
        if it.user.id not in [self.p1, self.p2]: return
        self.conf.add(it.user.id)
        if len(self.conf) == 2:
            await it.channel.purge(limit=5)
            r = buscar_mediador(self.med)
            v = self.valor.replace('R$', '').replace(',', '.')
            final = f"{(float(v) + 0.10):.2f}".replace('.', ',')
            e = discord.Embed(title="💸 PAGAMENTO", color=0xF1C40F)
            e.add_field(name="👤 Titular", value=r[0] if r else "Pendente")
            e.add_field(name="💠 Chave", value=f"`{r[1]}`" if r else "Pendente")
            e.add_field(name="💰 Valor", value=f"R$ {final}")
            if r and r[2]: e.set_image(url=r[2])
            await it.channel.send(content=f"🔔 <@{self.med}> | <@{self.p1}> <@{self.p2}>", embed=e)

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogs, self.msg = modo, valor, [], None

    def embed(self):
        e = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        e.add_field(name="💰 Valor", value=self.valor, inline=False)
        e.add_field(name="🏆 Modo", value=self.modo, inline=False)
        l = "\n".join([f"👤 {j['m']} - `{j['g']}`" for j in self.jogs]) or "Vazia"
        e.add_field(name="⚡ Jogadores", value=l, inline=False)
        e.set_image(url=BANNER_URL)
        return e

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def gn(self, it, b): await self.add(it, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def gi(self, it, b): await self.add(it, "Gelo Infinito")

    async def add(self, it, g):
        if any(j['id'] == it.user.id for j in self.jogs): return
        self.jogs.append({'id': it.user.id, 'm': it.user.mention, 'g': g})
        await it.response.send_message("✅ Entrou!", ephemeral=True)
        await self.msg.edit(embed=self.embed())

        if len(self.jogs) == 2:
            if not fila_mediadores: return await it.channel.send("❌ Sem mediadores!")
            j1, j2 = self.jogs; m_id = fila_mediadores.pop(0); fila_mediadores.append(m_id)
            c_id = pegar_config("canal_th")
            th = await bot.get_channel(int(c_id)).create_thread(name=f"Partida-{self.valor}", type=discord.ChannelType.public_thread)
            
            # Tópico Formal com @ no mediador
            re = buscar_mediador(m_id)
            et = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            et.add_field(name="👑 Modo:", value=self.modo, inline=False)
            et.add_field(name="⚡ Jogadores:", value=f"{j1['m']} - {j1['g']}\n{j2['m']} - {j2['g']}", inline=False)
            et.add_field(name="💸 Valor:", value=f"R$ {self.valor}", inline=False)
            et.add_field(name="👮 Mediador:", value=f"{re[0] if re else 'Mediador'} (<@{m_id}>)", inline=False)
            et.set_thumbnail(url=FOTO_BONECA)

            await th.send(content=f"🔔 <@{m_id}> | {j1['m']} {j2['m']}", embed=et, view=ViewConfirmar(j1['id'], j2['id'], m_id, self.valor, self.modo))
            partidas_ativas[th.id] = {'med': m_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            self.jogs = []; await self.msg.edit(embed=self.embed())

# ==============================================================================
#                               COMANDOS
# ==============================================================================

@bot.command()
async def Pix(ctx):
    await ctx.send(embed=discord.Embed(title="⚙️ CONFIGURAÇÃO PIX", color=0x2b2d31), view=ViewPix())

@bot.command()
async def mediar(ctx):
    if ctx.author.guild_permissions.manage_messages:
        await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo, valor):
    if ctx.author.guild_permissions.administrator:
        v = ViewFila(modo, valor); m = await ctx.send(embed=v.embed(), view=v); v.msg = m

@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); s = ChannelSelect()
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(s.values[0].id)))
        await it.response.send_message("✅ Canal Salvo!", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Selecione o canal das threads:", view=v)

@bot.command()
async def logs(ctx):
    if not ctx.author.guild_permissions.administrator: return
    db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_logs", str(ctx.channel.id)))
    await ctx.send("✅ Este canal agora receberá logs de erro e sistema.")

# ==============================================================================
#                             GERENCIAMENTO DE ERROS
# ==============================================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return # Ignora se o comando não existir
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você não tem permissão para usar este comando.", delete_after=5)
    else:
        print(f"⚠️ Erro detectado: {error}")
        await log_sistema("ERRO DE COMANDO", f"Usuário: {ctx.author}\nErro: {error}", 0xe74c3c)

# ==============================================================================
#                               EVENTOS
# ==============================================================================

@bot.event
async def on_message(message):
    if message.author.bot: return
    # Lógica de ID e SENHA da sala
    if message.channel.id in partidas_ativas:
        d = partidas_ativas[message.channel.id]
        if message.author.id == d['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete(); await message.channel.send("✅ ID salvo! Mande a senha.", delete_after=2)
            else:
                s = message.content; i = temp_dados_sala.pop(message.channel.id); await message.delete()
                e = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                e.description = f"**ID:** {i}\n**Senha:** {s}\n**Modo:** {d['modo']}"; e.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=e)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db()
    # Tenta registrar as views para persistência
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    print(f"✅ WS APOSTAS ONLINE EM: {bot.user}")
    await log_sistema("BOT ONLINE", "O bot foi iniciado e os comandos estão ativos.", 0x2ecc71)

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ ERRO: Token não encontrado nas variáveis de ambiente.")
        
