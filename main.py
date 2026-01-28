import discord
from discord.ext import commands
import qrcode
import io

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
pix_mediadores = {}

@bot.event
async def on_ready():
    print("WS APOSTAS ONLINE")

# ================= PAINEL PRINCIPAL =================

class PainelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def gelo_infinito(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} gelo infinito", ephemeral=False)

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def gelo_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} gelo normal", ephemeral=False)

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger)
    async def sair_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
            await interaction.response.send_message("Você saiu da fila.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)

# ================= PAINEL PIX =================

class PixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.success)
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Envie sua chave Pix:", ephemeral=True)

        msg = await bot.wait_for("message", check=lambda m: m.author == interaction.user)
        pix_mediadores[interaction.user.id] = msg.content
        await interaction.followup.send("Chave Pix cadastrada!", ephemeral=True)

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.primary)
    async def ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        pix = pix_mediadores.get(interaction.user.id)
        if pix:
            await interaction.response.send_message(f"Sua chave Pix: {pix}", ephemeral=True)
        else:
            await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)

    @discord.ui.button(label="Ver chave Pix de mediadores", style=discord.ButtonStyle.secondary)
    async def ver_mediadores(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not fila_mediadores:
            await interaction.response.send_message("Fila vazia.", ephemeral=True)
            return

        mediador = fila_mediadores[0]
        pix = pix_mediadores.get(mediador.id, "Não cadastrado")

        qr = qrcode.make(pix)
        buf = io.BytesIO()
        qr.save(buf)
        buf.seek(0)

        embed = discord.Embed(title="Mediador")
        embed.add_field(name="Nome da chave Pix", value=mediador.name)
        embed.add_field(name="Chave Pix", value=pix)

        file = discord.File(buf, filename="qrcode.png")
        embed.set_image(url="attachment://qrcode.png")

        await interaction.response.send_message(embed=embed, file=file)

# ================= PAINEL MEDIADORES =================

class MediadorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar na fila de mediador", style=discord.ButtonStyle.success)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
            await interaction.response.send_message("Você entrou na fila.", ephemeral=True)
        else:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila de mediador", style=discord.ButtonStyle.danger)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
            await interaction.response.send_message("Você saiu da fila.", ephemeral=True)

    @discord.ui.button(label="Remover alguém da fila mediador", style=discord.ButtonStyle.secondary)
    async def remover(self, interaction: discord.Interaction, button: discord.ui.Button):
        if fila_mediadores:
            removido = fila_mediadores.pop(0)
            await interaction.response.send_message(f"{removido.name} removido da fila.")

# ================= COMANDOS =================

@bot.command()
async def painel(ctx):
    embed = discord.Embed(title="WS APOSTAS", description="Modo\nValor\nJogadores")
    await ctx.send(embed=embed, view=PainelView())

    await ctx.send("Para colocar sua chave Pix aperta no botão em baixo", view=PixView())
    await ctx.send("Entre na fila mediadores pra ser chamado", view=MediadorView())

@bot.command()
async def canal(ctx):
    await ctx.send("Escolha onde criar o tópico:")

# ================= TOKEN =================

bot.run("SEU_TOKEN_AQUI")
