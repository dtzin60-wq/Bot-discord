import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import random

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

CARGO_PERMITIDO = "Xoxota"
CARGO_MEDIADOR = "Mediador"

fila_jogadores = []
fila_mediadores = []
pix_mediadores = {}
partidas = {}

def tem_cargo(user, nome):
    return discord.utils.get(user.roles, name=nome)

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome do titular")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_mediadores[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

# ================= FILA JOGADORES =================
class FilaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in fila_jogadores:
            fila_jogadores.append(interaction.user)
        await atualizar_fila(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_jogadores:
            fila_jogadores.remove(interaction.user)
        await atualizar_fila(interaction)

# ================= FILA MEDIADORES =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user, CARGO_MEDIADOR):
            return await interaction.response.send_message("❌ Você não é mediador", ephemeral=True)

        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await atualizar_mediador(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await atualizar_mediador(interaction)

# ================= ATUALIZAR =================
async def atualizar_fila(interaction):
    embed = discord.Embed(title="Aguardando Jogadores", color=0x2ecc71)
    jogadores = "\n".join(j.mention for j in fila_jogadores) or "Nenhum"
    embed.add_field(name="Jogadores", value=jogadores)

    await interaction.message.edit(embed=embed, view=FilaView())

    if len(fila_jogadores) >= 2 and len(fila_mediadores) >= 1:
        await criar_partida(interaction.guild)

async def atualizar_mediador(interaction):
    embed = discord.Embed(title="Fila de Mediadores", color=0xf1c40f)
    mediadores = "\n".join(m.mention for m in fila_mediadores) or "Nenhum"
    embed.add_field(name="Mediadores", value=mediadores)

    await interaction.message.edit(embed=embed, view=MediadorView())

# ================= PARTIDA =================
async def criar_partida(guild):
    jogadores = fila_jogadores[:2]
    mediador = fila_mediadores.pop(0)
    fila_jogadores.clear()

    canal = await guild.create_text_channel(f"partida-{jogadores[0].name}-vs-{jogadores[1].name}")

    partidas[canal.id] = {
        "jogadores": jogadores,
        "mediador": mediador,
        "confirmados": []
    }

    embed = discord.Embed(title="Aguardando Confirmação", color=0x3498db)
    embed.add_field(name="Jogadores", value=f"{jogadores[0].mention}\n{jogadores[1].mention}")
    embed.add_field(name="Mediador", value=mediador.mention)

    await canal.send(embed=embed, view=ConfirmarView())

# ================= CONFIRMAR =================
class ConfirmarView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não é jogador", ephemeral=True)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)
            await interaction.channel.send(f"✅ {interaction.user.mention} confirmou!")

        if len(dados["confirmados"]) == 2:
            mediador = dados["mediador"]
            pix = pix_mediadores.get(mediador.id)

            embed = discord.Embed(title="Partida Confirmada", color=0x2ecc71)
            embed.add_field(name="Jogadores", value=f"{dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}")
            embed.add_field(name="Mediador", value=mediador.mention)

            if pix:
                embed.add_field(name="Pix do Mediador", value=f"{pix['nome']}\n{pix['chave']}")
                embed.set_image(url=pix["qr"])

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================= COMANDOS =================
@bot.command()
async def fila(ctx):
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return

    embed = discord.Embed(title="Aguardando Jogadores", color=0x2ecc71)
    embed.add_field(name="Jogadores", value="Nenhum")
    await ctx.send(embed=embed, view=FilaView())

@bot.command()
async def filamediador(ctx):
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return

    embed = discord.Embed(title="Fila de Mediadores", color=0xf1c40f)
    embed.add_field(name="Mediadores", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

@bot.command()
async def pix(ctx):
    if not tem_cargo(ctx.author, CARGO_MEDIADOR):
        return
    await ctx.send_modal(PixModal())

# ================= START =================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
