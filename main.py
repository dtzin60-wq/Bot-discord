import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= CONFIG =================
config = {
    "canal_topico": None,
    "cargo_mediador": None,
    "cargo_admin": None
}

fila_aposta = []   # [(user, modo)]
fila_mediadores = []
pix_db = {}
partidas = {}

VALOR = 5.00
BANNER_URL = "https://i.imgur.com/zYxDCQT.png"

# ================= UTIL =================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_cargo(member, cargo_id):
    if member.guild_permissions.administrator:
        return True
    if not cargo_id:
        return False
    return any(r.id == cargo_id for r in member.roles)

# ================= MODAL PIX =================
class PixModal(Modal, title="Cadastrar chave Pix"):
    nome = TextInput(label="Nome do titular")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou Pix.", ephemeral=True)
        embed = discord.Embed(title="💰 Seu Pix", color=0x00ff00)
        embed.add_field(name="Nome", value=pix["nome"], inline=False)
        embed.add_field(name="Chave", value=pix["chave"], inline=False)
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Ver chave Pix de mediadores", style=discord.ButtonStyle.gray)
    async def ver_mediadores(self, interaction: discord.Interaction, button: Button):
        texto = ""
        for m in fila_mediadores:
            pix = pix_db.get(m.id)
            if pix:
                texto += f"{m.mention} - {pix['chave']}\n"
        if not texto:
            texto = "Nenhum mediador com Pix."
        await interaction.response.send_message(texto, ephemeral=True)

# ================= FILA MEDIADORES =================
class MediadorView(View):
    async def atualizar(self, interaction):
        texto = "\n".join([f"{i+1}º - {m.mention}" for i, m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(
            title="🧑‍⚖️ Fila de Mediadores",
            description="Entre na fila mediadores pra ser chamado",
            color=0xffaa00
        )
        embed.add_field(name="Ordem", value=texto)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar na fila de mediador", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user, config["cargo_mediador"]):
            return await interaction.response.send_message("❌ Você não é mediador.", ephemeral=True)
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    @discord.ui.button(label="Sair da fila de mediador", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    @discord.ui.button(label="Remover alguém da fila mediador", style=discord.ButtonStyle.gray)
    async def remover(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user, config["cargo_admin"]):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        if fila_mediadores:
            fila_mediadores.pop(0)
        await self.atualizar(interaction)
        await interaction.response.defer()

# ================= FILA APOSTA =================
class FilaView(View):
    async def atualizar(self, message):
        texto = "\n".join([f"{u.mention} - {modo}" for u, modo in fila_aposta]) or "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value="1v1", inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await message.edit(embed=embed, view=self)

    async def entrar(self, interaction, modo):
        if any(u == interaction.user for u, _ in fila_aposta):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)
        if len(fila_aposta) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila_aposta.append((interaction.user, modo))
        await self.atualizar(interaction.message)

        if len(fila_aposta) == 2:
            await criar_topico(interaction.guild)

        await interaction.response.defer()

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        global fila_aposta
        fila_aposta = [x for x in fila_aposta if x[0] != interaction.user]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

# ================= CONFIRMAÇÃO =================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="💰 PIX DO MEDIADOR", color=0x00ff00)
            embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

            if pix:
                embed.add_field(name="Nome da chave Pix do mediador", value=pix["nome"], inline=False)
                embed.add_field(name="Chave Pix do mediador", value=pix["chave"], inline=False)
                embed.set_image(url=pix["qrcode"])

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================= CRIAR TÓPICO =================
async def criar_topico(guild):
    canal = bot.get_channel(config["canal_topico"])
    if not canal:
        return

    (j1, m1), (j2, m2) = fila_aposta
    fila_aposta.clear()

    mediador = fila_mediadores.pop(0) if fila_mediadores else None

    topico = await canal.create_thread(name=f"partida - {formatar_valor(VALOR)}")

    partidas[topico.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "mediador": mediador
    }

    embed = discord.Embed(title="⚔️ PARTIDA", description="Conversem e confirmem", color=0x3498db)
    embed.add_field(name="Modo", value=f"1v1 {m1}", inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)
    embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

    await topico.send(embed=embed, view=ConfirmacaoView())

# ================= PAINEL CONFIG =================
class PainelView(View):
    def __init__(self, guild):
        super().__init__()
        self.add_item(CargoSelect(guild, "Mediador"))
        self.add_item(CargoSelect(guild, "Admin"))
        self.add_item(CanalSelect(guild))

class CargoSelect(Select):
    def __init__(self, guild, tipo):
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in guild.roles]
        super().__init__(placeholder=f"Escolher cargo {tipo}", options=options)
        self.tipo = tipo

    async def callback(self, interaction: discord.Interaction):
        if self.tipo == "Mediador":
            config["cargo_mediador"] = int(self.values[0])
        else:
            config["cargo_admin"] = int(self.values[0])
        await interaction.response.send_message("✅ Cargo configurado.", ephemeral=True)

class CanalSelect(Select):
    def __init__(self, guild):
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in guild.text_channels]
        super().__init__(placeholder="Escolher canal dos tópicos", options=options)

    async def callback(self, interaction: discord.Interaction):
        config["canal_topico"] = int(self.values[0])
        await interaction.response.send_message("✅ Canal configurado.", ephemeral=True)

# ================= COMANDOS =================
@bot.command()
async def painel(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Sem permissão.")
    await ctx.send("⚙️ Painel de Configuração", view=PainelView(ctx.guild))

@bot.command()
async def canal(ctx):
    await ctx.send("Escolha o canal para criar os tópicos:", view=CanalSelect(ctx.guild))

@bot.command()
async def fila(ctx):
    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value="1v1", inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)
    await ctx.send(embed=embed, view=FilaView())

@bot.command()
async def mediador(ctx):
    embed = discord.Embed(title="🧑‍⚖️ Fila de Mediadores", description="Entre na fila mediadores pra ser chamado", color=0xffaa00)
    embed.add_field(name="Ordem", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

@bot.command()
async def chavepix(ctx):
    await ctx.send("Para colocar sua chave Pix aperta no botão em baixo:", view=PixView())

bot.run(TOKEN)
