import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect
import sqlite3
import os
import asyncio

TOKEN = os.getenv("TOKEN")

COR_EMBED = 0x2b2d31
COR_VERDE = 0x2ecc71

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

fila_mediadores = []

# ===================== BANCO =====================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INTEGER DEFAULT 0)")

def db_exec(q, p=()):
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute(q, p)
        con.commit()

def db_query(q, p=()):
    with sqlite3.connect("ws_database_final.db") as con:
        return con.execute(q, p).fetchone()

def db_increment_counter(tipo):
    with sqlite3.connect("ws_database_final.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?,0)", (tipo,))
        cur.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo=?", (tipo,))
        con.commit()
        return cur.execute("SELECT contagem FROM counters WHERE tipo=?", (tipo,)).fetchone()[0]

# ===================== VIEW FILA =====================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = []

        self.add_item(Button(label="Entrar na Fila", emoji="🎮", style=discord.ButtonStyle.success, callback=self.join))
        self.add_item(Button(label="Sair da Fila", emoji="❌", style=discord.ButtonStyle.danger, callback=self.leave))

    def embed(self):
        e = discord.Embed(title=f"🎯 Aposta | {self.modo}", color=COR_EMBED)
        e.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        e.add_field(name="👥 Jogadores", value="\n".join(self.jogadores) or "*Aguardando...*", inline=False)
        e.set_image(url=BANNER_URL)
        return e

    async def join(self, it: discord.Interaction):
        if it.user.mention in self.jogadores:
            return await it.response.send_message("❌ Você já está na fila.", ephemeral=True)

        self.jogadores.append(it.user.mention)
        await it.response.edit_message(embed=self.embed(), view=self)

        if len(self.jogadores) >= 2:
            if not fila_mediadores:
                return await it.channel.send("⚠️ Sem mediadores disponíveis.")

            med = fila_mediadores.pop(0)
            fila_mediadores.append(med)

            canal_cfg = db_query("SELECT valor FROM config WHERE chave='canal_th'")
            if not canal_cfg:
                return await it.channel.send("❌ Canal de tópicos não configurado.")

            canal = bot.get_channel(int(canal_cfg[0]))
            thread = await canal.create_thread(name="🎮 aguardando-confirmacao")

            e = discord.Embed(title="✅ Partida Criada", color=COR_VERDE)
            e.add_field(name="Modo", value=self.modo)
            e.add_field(name="Valor", value=f"R$ {self.valor}")
            e.add_field(name="Jogadores", value="\n".join(self.jogadores))
            e.add_field(name="Mediador", value=f"<@{med}>")
            e.set_thumbnail(url=IMAGEM_BONECA)

            await thread.send(embed=e)
            self.jogadores = []
            await it.message.edit(embed=self.embed(), view=self)

    async def leave(self, it: discord.Interaction):
        if it.user.mention in self.jogadores:
            self.jogadores.remove(it.user.mention)
            await it.response.edit_message(embed=self.embed(), view=self)
        else:
            await it.response.send_message("Você não está na fila.", ephemeral=True)

# ===================== MODAL =====================
class ModalFila(Modal, title="🎮 Criar Filas"):
    modo = TextInput(label="Modo (ex: 1v1 Mobile)")
    valores = TextInput(label="Valores (separados por espaço)", placeholder="100,00 50,00 20,00")

    async def on_submit(self, it: discord.Interaction):
        vals = self.valores.value.split()
        vals = vals[:15]

        for v in vals:
            view = ViewFila(self.modo.value, v)
            await it.channel.send(embed=view.embed(), view=view)
            await asyncio.sleep(0.5)

        await it.response.send_message("✅ Filas criadas!", ephemeral=True)

# ===================== SLASH COMMANDS =====================

@bot.tree.command(name="fila", description="🎮 Criar filas de aposta")
async def fila(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas admins.", ephemeral=True)

    await interaction.response.send_modal(ModalFila())

@bot.tree.command(name="canal", description="📌 Definir canal dos tópicos")
async def canal(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas admins.", ephemeral=True)

    db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th',?)", (str(canal.id),))
    await interaction.response.send_message(f"✅ Canal definido: {canal.mention}", ephemeral=True)

@bot.tree.command(name="mediar", description="👑 Entrar na fila de mediadores")
async def mediar(interaction: discord.Interaction):
    if interaction.user.id not in fila_mediadores:
        fila_mediadores.append(interaction.user.id)
        await interaction.response.send_message("✅ Você entrou na fila de mediadores.", ephemeral=True)
    else:
        fila_mediadores.remove(interaction.user.id)
        await interaction.response.send_message("❌ Você saiu da fila de mediadores.", ephemeral=True)

# ===================== READY =====================
@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print("🔥 BOT ONLINE (SLASH)")

bot.run(TOKEN)
