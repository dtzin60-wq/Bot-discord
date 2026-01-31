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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Estados Globais
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}
manutencao_ativa = False

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            chave TEXT,
            qrcode TEXT,
            partidas_feitas INTEGER DEFAULT 0
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS blacklist (
            user_id INTEGER PRIMARY KEY,
            motivo TEXT,
            data TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def usuario_banido(user_id):
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT 1 FROM blacklist WHERE user_id=?", (user_id,)).fetchone()
        return True if r else False

def pegar_config(chave):
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

def buscar_mediador(user_id):
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (user_id,)).fetchone()

# ==============================================================================
#                      NOVO VISUAL DO COMANDO .Pix (CONFORME IMAGEM)
# ==============================================================================
class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="v21_cad")
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        if manutencao_ativa: return await interaction.response.send_message("🚧 Bot em manutenção!", ephemeral=True)
        
        modal = Modal(title="Configurar Chave PIX")
        nome = TextInput(label="Nome do Titular", placeholder="Nome que aparece no banco")
        chave = TextInput(label="Chave Pix", placeholder="Sua chave")
        qr = TextInput(label="Link do QR Code (URL)", required=False)
        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)

        async def on_submit(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode, partidas_feitas) VALUES (?,?,?,?, (SELECT partidas_feitas FROM pix WHERE user_id=?))", 
                       (it.user.id, nome.value, chave.value, qr.value, it.user.id))
            await it.response.send_message(f"✅ Chave de **{nome.value}** cadastrada com sucesso!", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="v21_sua")
    async def sua_chave(self, interaction: discord.Interaction, button: Button):
        r = buscar_mediador(interaction.user.id)
        if not r: return await interaction.response.send_message("❌ Você não cadastrou uma chave ainda!", ephemeral=True)
        
        emb = discord.Embed(title="💠 Sua Chave PIX", color=0x2ecc71)
        emb.description = f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`"
        if r[2]: emb.set_image(url=r[2])
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.gray, emoji="🔍", custom_id="v21_ver_med")
    async def ver_mediador(self, interaction: discord.Interaction, button: Button):
        # Esta função abre um modal para buscar por ID ou menção
        modal = Modal(title="Buscar Chave de Mediador")
        alvo = TextInput(label="ID do Mediador", placeholder="Insira o ID do mediador que deseja ver")
        modal.add_item(alvo)

        async def buscar(it: discord.Interaction):
            try:
                uid = int(alvo.value.strip())
                r = buscar_mediador(uid)
                if not r: return await it.response.send_message("❌ Mediador não encontrado no sistema.", ephemeral=True)
                
                emb = discord.Embed(title=f"💠 Chave de Mediador", color=0x3498db)
                emb.description = f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`"
                if r[2]: emb.set_image(url=r[2])
                await it.response.send_message(embed=emb, ephemeral=True)
            except:
                await it.response.send_message("❌ ID inválido. Insira apenas números.", ephemeral=True)

        modal.on_submit = buscar
        await interaction.response.send_modal(modal)

# ==============================================================================
#                          VISUAL DO COMANDO .mediar
# ==============================================================================
class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        lista = ""
        if fila_mediadores:
            for i, u_id in enumerate(fila_mediadores):
                r = buscar_mediador(u_id)
                nome_formatado = r[0] if r else "Membro"
                lista += f"**{i+1} •** {nome_formatado} (<@{u_id}>)\n"
        else: lista = "*Nenhum mediador disponível.*"
        return discord.Embed(title="🛡️ Painel da Fila Controladora", description=lista, color=0x2b2d31)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="v21_in")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴", custom_id="v21_out")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                          LÓGICA DE FILA E TÓPICOS
# ==============================================================================
class ViewConfirmacao(View):
    def __init__(self, p1, p2, med, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.valor, self.modo = p1, p2, med, valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, it: discord.Interaction, b: Button):
        if it.user.id not in [self.p1, self.p2]: return
        self.confirmados.add(it.user.id)
        if len(self.confirmados) == 2:
            await it.channel.purge(limit=5)
            r = buscar_mediador(self.med)
            try:
                v_calc = self.valor.replace('R$', '').replace(',', '.').strip()
                v_final = f"{(float(v_calc) + 0.10):.2f}".replace('.', ',')
            except: v_final = self.valor

            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb.add_field(name="👤 Titular", value=f"**{r[0] if r else 'Pendente'}**")
            emb.add_field(name="💠 Chave Pix", value=f"`{r[1] if r else 'Pendente'}`")
            emb.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(content=f"🔔 <@{self.med}> | <@{self.p1}> <@{self.p2}>", embed=emb)

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores, self.message = modo, valor, [], None

    def gerar_embed(self):
        emb = discord.Embed(color=0x3498DB)
        emb.set_author(name="🎮 FILA DE APOSTAS", icon_url=bot.user.display_avatar.url)
        emb.add_field(name="💰 **Valor**", value=self.valor, inline=False)
        emb.add_field(name="🏆 **Modo**", value=self.modo, inline=False)
        l = "\n".join([f"👤 {j['m']} - `{j['g']}`" for j in self.jogadores]) or "Fila vazia"
        emb.add_field(name="⚡ **Jogadores**", value=l, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    @discord.ui.button(label="Gelo Normal", emoji="❄️", style=discord.ButtonStyle.secondary)
    async def g_n(self, it, b): await self.add(it, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", emoji="♾️", style=discord.ButtonStyle.secondary)
    async def g_i(self, it, b): await self.add(it, "Gelo Infinito")

    async def add(self, it, gelo):
        if manutencao_ativa: return await it.response.send_message("🚧 Manutenção.", ephemeral=True)
        if usuario_banido(it.user.id): return await it.response.send_message("❌ Você está na blacklist!", ephemeral=True)
        if any(j["id"] == it.user.id for j in self.jogadores): return
        
        self.jogadores.append({"id": it.user.id, "m": it.user.mention, "g": gelo})
        await it.response.send_message("✅ Entrou!", ephemeral=True)
        await self.message.edit(embed=self.gerar_embed())

        if len(self.jogadores) == 2:
            if not fila_mediadores: return await it.channel.send("❌ Sem mediadores online!", delete_after=5)
            j1, j2 = self.jogadores; med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            c_id = pegar_config("canal_th")
            th = await bot.get_channel(int(c_id)).create_thread(name=f"Partida-R${self.valor}", type=discord.ChannelType.public_thread)
            
            r_med = buscar_mediador(med_id)
            emb_th = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_th.add_field(name="👑 **Modo:**", value=self.modo, inline=False)
            emb_th.add_field(name="⚡ **Jogadores:**", value=f"{j1['m']} - {j1['g']}\n{j2['m']} - {j2['g']}", inline=False)
            emb_th.add_field(name="💸 **Valor da aposta:**", value=f"R$ {self.valor}", inline=False)
            emb_th.add_field(name="👮 **Mediador:**", value=f"{r_med[0] if r_med else 'Mediador'} (<@{med_id}>)", inline=False)
            emb_th.set_thumbnail(url=FOTO_BONECA)

            await th.send(content=f"🔔 <@{med_id}> | {j1['m']} {j2['m']}", embed=emb_th, view=ViewConfirmacao(j1['id'], j2['id'], med_id, self.valor, self.modo))
            partidas_ativas[th.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            self.jogadores = []; await self.message.edit(embed=self.gerar_embed())

# ==============================================================================
#                               COMANDOS
# ==============================================================================
@bot.command()
async def Pix(ctx):
    # Visual e descrição idênticos aos da imagem enviada
    emb = discord.Embed(
        title="Painel Para Configurar Chave PIX",
        description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.",
        color=0x2b2d31
    )
    # Foto de perfil do bot ou ícone da org no canto direito (thumbnail)
    emb.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=emb, view=ViewPix())

@bot.command()
async def mediar(ctx):
    if ctx.author.guild_permissions.manage_messages:
        await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo, valor):
    if ctx.author.guild_permissions.administrator:
        v = ViewFila(modo, valor); msg = await ctx.send(embed=v.gerar_embed(), view=v); v.message = msg

@bot.command()
async def ban(ctx, usuario: discord.Member, *, motivo="Nenhum"):
    if not ctx.author.guild_permissions.administrator: return
    db_execute("INSERT OR REPLACE INTO blacklist VALUES (?,?,?)", (usuario.id, motivo, str(datetime.date.today())))
    await ctx.send(f"🚫 {usuario.mention} foi banido das apostas por: {motivo}")

@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); sel = ChannelSelect()
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await it.response.send_message("✅ Canal configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal alvo:", view=v)

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        d = partidas_ativas[message.channel.id]
        if message.author.id == d['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete(); await message.channel.send("✅ ID salvo!", delete_after=2)
            else:
                s = message.content; i = temp_dados_sala.pop(message.channel.id); await message.delete()
                e = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                e.description = f"**ID:** {i}\n**Senha:** {s}\n**Modo:** {d['modo']}"; e.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=e)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db(); bot.add_view(ViewPix()); bot.add_view(ViewMediar()); print(f"✅ WS Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
    
