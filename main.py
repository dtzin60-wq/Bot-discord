import discord
from discord.ext import commands

TOKEN = "COLOQUE_SEU_TOKEN_AQUI"

PIX_ADM = "NÃO CADASTRADO"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

fila = {
    "modo": "1v1",
    "valor": 10,
    "jogadores": []
}

@bot.event
async def on_ready():
    print(f"Bot ligado como {bot.user}")

# ================= PAINEL PIX =================

class PixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use: `!cadastrarpix SUA_CHAVE`",
            ephemeral=True
        )

    @discord.ui.button(label="Ver chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"💰 Chave Pix: `{PIX_ADM}`",
            ephemeral=True
        )

@bot.command()
async def painelpix(ctx):
    await ctx.send("💰 **Cadastre sua chave Pix aqui**", view=PixView())

@bot.command()
async def cadastrarpix(ctx, *, chave):
    global PIX_ADM
    PIX_ADM = chave
    await ctx.send("✅ Chave Pix cadastrada com sucesso!")

# ================= FILA =================

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
        await interaction.response.send_message(f"{user.mention} entrou na fila!")

        if len(fila["jogadores"]) == 2:
            await interaction.channel.purge(limit=50)
            await interaction.channel.send(
                f"⚠️ **Aguardem o ADM chegar para pagar!**\n\n"
                f"**Modo:** {fila['modo']}\n"
                f"**Valor:** R${fila['valor']}\n"
                f"**Jogadores:** {fila['jogadores'][0].mention} x {fila['jogadores'][1].mention}",
                view=ConfirmacaoView()
            )

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
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
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Você confirmou presença.")

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

    await ctx.send(
        "🎮 **Fila Mediador**\nEntre na fila e seja chamado",
        view=FilaView()
    )

bot.run(TOKEN)
