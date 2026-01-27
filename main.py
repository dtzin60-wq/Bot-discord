import discord
from discord.ext import commands
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

PIX_ADM = "Não cadastrado"

fila = {
    "modo": "",
    "valor": 0,
    "jogadores": [],
    "confirmados": []
}

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    bot.add_view(PixView())
    bot.add_view(FilaView())

# ================== PAINEL PIX ==================

class PixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use: `!cadastrarpix SUA_CHAVE`", ephemeral=True
        )

    @discord.ui.button(label="Ver chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"💰 Chave Pix do ADM:\n`{PIX_ADM}`", ephemeral=True
        )

@bot.command()
async def painelpix(ctx):
    await ctx.send(
        "💰 **Cadastrei sua chave Pix aqui**",
        view=PixView()
    )

@bot.command()
async def cadastrarpix(ctx, *, chave):
    global PIX_ADM
    PIX_ADM = chave
    await ctx.send("✅ Chave Pix cadastrada!")

# ================== FILA MEDIADOR ==================

class FilaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if user in fila["jogadores"]:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)
            return

        if len(fila["jogadores"]) >= 2:
            await interaction.response.send_message("Fila cheia.", ephemeral=True)
            return

        fila["jogadores"].append(user)
        await interaction.response.send_message(f"✅ {user.mention} entrou na fila!")

        if len(fila["jogadores"]) == 2:
            await interaction.channel.purge()
            await interaction.channel.send(
                f"⚠️ **Aguardem o ADM chegar para pagar!**\n\n"
                f"**Modo:** {fila['modo']}\n"
                f"**Valor:** R${fila['valor']}\n"
                f"**Jogadores:** {fila['jogadores'][0].mention} x {fila['jogadores'][1].mention}",
                view=ConfirmacaoView()
            )

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interation, button: discord.ui.Button):
        user = interaction.user
        if user in fila["jogadores"]:
            fila["jogadores"].remove(user)
            await interaction.response.send_message("Você saiu da fila.")
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)

class ConfirmacaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        if user not in fila["jogadores"]:
            await interaction.response.send_message("Você não é jogador.", ephemeral=True)
            return

        if user in fila["confirmados"]:
            await interaction.response.send_message("Você já confirmou.", ephemeral=True)
            return

        fila["confirmados"].append(user)
        await interaction.response.send_message("✅ Confirmado!")

        if len(fila["confirmados"]) == 2:
            await interaction.channel.purge()
            await interaction.channel.send(
                "💰 **PAGAMENTO PARA O ADM**\n\n"
                f"**Chave Pix:**\n`{PIX_ADM}`"
            )
            fila["jogadores"].clear()
            fila["confirmados"].clear()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Você saiu da partida.")

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💬 Podem combinar as regras no chat.")

@bot.command()
async def painelfila(ctx, modo: str, valor: int):
    fila["modo"] = modo
    fila["valor"] = valor
    fila["jogadores"].clear()
    fila["confirmados"].clear()

    await ctx.send(
        "🎮 **Fila Mediador**\nEntre na fila e seja chamado",
        view=FilaView()
    )

bot.run(TOKEN)
