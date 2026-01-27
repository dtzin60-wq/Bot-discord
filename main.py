import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

filas = {}
pix_keys = {}

class FilaView(discord.ui.View):
    def __init__(self, fila_id):
        super().__init__(timeout=None)
        self.fila_id = fila_id

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        fila = filas[self.fila_id]
        user = interaction.user

        if user in fila["jogadores"]:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)
            return

        fila["jogadores"].append(user)

        if len(fila["jogadores"]) == 2:
            jogadores = ", ".join([j.mention for j in fila["jogadores"]])
            await interaction.channel.send(
                f"⚠️ **Aguardem o ADM chegar para pagar!**\n\n"
                f"**Modo:** {fila['modo']}\n"
                f"**Valor:** R$ {fila['valor']}\n"
                f"**Jogadores:** {jogadores}"
            )

        await interaction.response.send_message("Você entrou na fila!", ephemeral=True)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        fila = filas[self.fila_id]
        user = interaction.user

        if user in fila["jogadores"]:
            fila["jogadores"].remove(user)
            await interaction.response.send_message("Você saiu da fila.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)


class PixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Envie sua chave Pix agora:", ephemeral=True)

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        msg = await bot.wait_for("message", check=check)
        pix_keys[interaction.user.id] = msg.content
        await interaction.followup.send("✅ Chave Pix cadastrada com sucesso!", ephemeral=True)

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        chave = pix_keys.get(interaction.user.id)
        if chave:
            await interaction.response.send_message(f"Sua chave Pix: `{chave}`", ephemeral=True)
        else:
            await interaction.response.send_message("Você ainda não cadastrou uma chave Pix.", ephemeral=True)


@bot.command()
async def fila(ctx, modo: str, *, valor_texto: str):
    if not valor_texto.lower().startswith("valor:"):
        await ctx.send("Use assim: `!fila 1v1 valor:10`")
        return

    valor = valor_texto.replace("valor:", "").strip()

    fila_id = len(filas) + 1

    filas[fila_id] = {
        "modo": modo,
        "valor": valor,
        "jogadores": []
    }

    embed = discord.Embed(title=f"Fila {modo}", color=discord.Color.green())
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {valor}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(fila_id))


@bot.command()
async def pix(ctx):
    embed = discord.Embed(title="💰 Painel Pix", description="Gerencie sua chave Pix", color=discord.Color.blue())
    await ctx.send(embed=embed, view=PixView())


@bot.event
async def on_ready():
    print("Bot ligado com sucesso!")


bot.run(os.getenv("TOKEN"))
