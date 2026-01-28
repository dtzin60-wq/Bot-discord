import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
import sqlite3
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)
tree = bot.tree

# ================== BANCO ==================
conn = sqlite3.connect("dados.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS config (
    guild_id INTEGER,
    cargo_analista INTEGER,
    cargo_mediador INTEGER,
    canal_topico INTEGER
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS pix (
    user_id INTEGER,
    nome TEXT,
    chave TEXT,
    qrcode TEXT
)""")
conn.commit()

# ================== VARIÁVEIS ==================
fila_mediadores = []
filas = {}
partidas = {}

BANNER_URL = "https://i.imgur.com/Z6Y0H7f.png"  # pode trocar

# ================== UTIL ==================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def get_config(guild_id):
    cursor.execute("SELECT cargo_analista, cargo_mediador, canal_topico FROM config WHERE guild_id=?", (guild_id,))
    return cursor.fetchone()

def set_config(guild_id, analista=None, mediador=None, canal=None):
    if get_config(guild_id):
        if analista:
            cursor.execute("UPDATE config SET cargo_analista=? WHERE guild_id=?", (analista, guild_id))
        if mediador:
            cursor.execute("UPDATE config SET cargo_mediador=? WHERE guild_id=?", (mediador, guild_id))
        if canal:
            cursor.execute("UPDATE config SET canal_topico=? WHERE guild_id=?", (canal, guild_id))
    else:
        cursor.execute("INSERT INTO config VALUES (?,?,?,?)", (guild_id, analista, mediador, canal))
    conn.commit()

def tem_cargo(member, cargo_id):
    if member.guild_permissions.administrator:
        return True
    return any(r.id == cargo_id for r in member.roles)

# ================== PIX ==================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link do QRCode")

    async def on_submit(self, interaction: discord.Interaction):
        cursor.execute("DELETE FROM pix WHERE user_id=?", (interaction.user.id,))
        cursor.execute("INSERT INTO pix VALUES (?,?,?,?)", (interaction.user.id, self.nome.value, self.chave.value, self.qrcode.value))
        conn.commit()
        await interaction.response.send_message("✅ Pix salvo!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Adicionar Pix", style=discord.ButtonStyle.green)
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver meu Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        cursor.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (interaction.user.id,))
        pix = cursor.fetchone()
        if not pix:
            return await interaction.response.send_message("❌ Você não tem Pix.", ephemeral=True)

        embed = discord.Embed(title="💰 Seu Pix", color=0x00ff00)
        embed.add_field(name="Nome", value=pix[0], inline=False)
        embed.add_field(name="Chave", value=pix[1], inline=False)
        embed.set_image(url=pix[2])
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="chavepix")
async def chavepix(interaction: discord.Interaction):
    await interaction.response.send_message("💳 Painel Pix", view=PixView(), ephemeral=True)

# ================== PAINEL CONFIG ==================
class PainelView(View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.add_item(CargoSelect(guild, "Analista"))
        self.add_item(CargoSelect(guild, "Mediador"))
        self.add_item(CanalSelect(guild))

class CargoSelect(Select):
    def __init__(self, guild, tipo):
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in guild.roles]
        super().__init__(placeholder=f"Escolher cargo {tipo}", options=options)
        self.tipo = tipo

    async def callback(self, interaction: discord.Interaction):
        if self.tipo == "Analista":
            set_config(interaction.guild.id, analista=int(self.values[0]))
        else:
            set_config(interaction.guild.id, mediador=int(self.values[0]))
        await interaction.response.send_message(f"✅ Cargo {self.tipo} configurado.", ephemeral=True)

class CanalSelect(Select):
    def __init__(self, guild):
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in guild.text_channels]
        super().__init__(placeholder="Escolher canal do tópico", options=options)

    async def callback(self, interaction: discord.Interaction):
        set_config(interaction.guild.id, canal=int(self.values[0]))
        await interaction.response.send_message("✅ Canal configurado.", ephemeral=True)

@tree.command(name="painel")
async def painel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Só admin.", ephemeral=True)
    await interaction.response.send_message("⚙️ Configuração", view=PainelView(interaction.guild), ephemeral=True)

# ================== FILA MEDIADOR ==================
class MediadorView(View):
    async def atualizar(self, msg):
        texto = "\n".join([f"{i+1}º - {m.mention}" for i,m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(title="🧑‍⚖️ Fila Mediador", color=0xffaa00)
        embed.add_field(name="Ordem", value=texto)
        await msg.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        cfg = get_config(interaction.guild.id)
        if not cfg or not tem_cargo(interaction.user, cfg[1]):
            return await interaction.response.send_message("❌ Não é mediador.", ephemeral=True)
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await self.atualizar(interaction.message)
        await interaction.response.defer()

@tree.command(name="filamediador")
async def filamediador(interaction: discord.Interaction):
    embed = discord.Embed(title="🧑‍⚖️ Fila Mediador", color=0xffaa00)
    embed.add_field(name="Ordem", value="Nenhum")
    await interaction.response.send_message(embed=embed, view=MediadorView())

# ================== FILA APOSTA ==================
class FilaView(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor

    async def atualizar(self, msg):
        fila = filas[self.modo]
        nomes = "\n".join(u.mention for u in fila) or "Nenhum"

        embed = discord.Embed(title="🎮 ws apostas", color=0x00ff99)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=nomes, inline=False)
        await msg.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]
        if interaction.user in fila:
            return await interaction.response.send_message("Já está.", ephemeral=True)
        if len(fila) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(interaction.user)
        await self.atualizar(interaction.message)

        if len(fila) == 2:
            await self.criar_topico(interaction.guild)

        await interaction.response.defer()

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]
        if interaction.user in fila:
            fila.remove(interaction.user)
        await self.atualizar(interaction.message)
        await interaction.response.defer()

    async def criar_topico(self, guild):
        cfg = get_config(guild.id)
        canal = bot.get_channel(cfg[2])

        jogadores = filas[self.modo].copy()
        filas[self.modo].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        topico = await canal.create_thread(
            name=f"partida-{formatar_valor(self.valor)}",
            type=discord.ChannelType.public_thread
        )

        partidas[topico.id] = {
            "jogadores": jogadores,
            "valor": self.valor + 0.10,
            "mediador": mediador,
            "confirmados": []
        }

        embed = discord.Embed(title="⚔️ PARTIDA", description="Confirmem!", color=0x3498db)
        embed.add_field(name="Jogadores", value=" x ".join(j.mention for j in jogadores))
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor+0.10)}")
        embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum")

        await topico.send(embed=embed, view=ConfirmacaoView())

# ================== CONFIRMA ==================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            cursor.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (dados["mediador"].id,))
            pix = cursor.fetchone()

            embed = discord.Embed(title="💰 PIX DO MEDIADOR", color=0x00ff00)
            if pix:
                embed.add_field(name="Nome", value=pix[0])
                embed.add_field(name="Chave Pix", value=pix[1])
                embed.set_image(url=pix[2])
            else:
                embed.description = "Mediador sem Pix."

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================== /fila ==================
@tree.command(name="fila")
@app_commands.describe(modo="Ex: x1", valor="Ex: 5.00")
async def fila(interaction: discord.Interaction, modo: str, valor: float):
    cfg = get_config(interaction.guild.id)
    if not tem_cargo(interaction.user, cfg[0]):
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    filas[modo] = []

    embed = discord.Embed(title="🎮 ws apostas", color=0x00ff99)
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum")

    await interaction.response.send_message(embed=embed, view=FilaView(modo, valor))

# ================== START ==================
@bot.event
async def on_ready():
    await tree.sync()
    print("BOT ONLINE")

bot.run(TOKEN)
