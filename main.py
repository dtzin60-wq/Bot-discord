import discord
from discord.ext import commands

TOKEN = "SEU_TOKEN_AQUI"

CARGO_PERMITIDO = "Apostador"
CARGO_MEDIADOR = "Mediador"
CATEGORIA_APOSTAS = "APOSTAS"

fila_apostas = []
fila_mediadores = []
confirmacoes = {}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("Bot ligado!")

def embed_fila_apostas():
    jogadores = "\n".join([m.mention for m in fila_apostas]) if fila_apostas else "Nenhum jogador na fila"
    embed = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x2f3136)
    embed.add_field(name="Modo", value="1v1 MOBILE", inline=False)
    embed.add_field(name="Valor", value="R$ 0,25", inline=False)
    embed.add_field(name="Jogadores", value=jogadores, inline=False)
    embed.set_image(url="https://i.imgur.com/4M34hi2.png")  # banner
    return embed

def embed_fila_mediadores():
    mediadores = "\n".join([m.mention for m in fila_mediadores]) if fila_mediadores else "Nenhum"
    embed = discord.Embed(title="⚖️ FILA DE MEDIADORES", color=0x2f3136)
    embed.add_field(name="Ordem", value=mediadores, inline=False)
    embed.set_image(url="https://i.imgur.com/4M34hi2.png")
    return embed

class PainelApostas(discord.ui.View):
    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if CARGO_PERMITIDO not in [r.name for r in interaction.user.roles]:
            return await interaction.response.send_message("Você não pode usar.", ephemeral=True)

        if interaction.user in fila_apostas:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila_apostas) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila_apostas.append(interaction.user)
        await interaction.message.edit(embed=embed_fila_apostas(), view=self)
        await interaction.response.defer()

        if len(fila_apostas) == 2:
            await criar_canal(interaction.guild)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in fila_apostas:
            fila_apostas.remove(interaction.user)
            await interaction.message.edit(embed=embed_fila_apostas(), view=self)
        await interaction.response.defer()

class PainelMediadores(discord.ui.View):
    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if CARGO_MEDIADOR not in [r.name for r in interaction.user.roles]:
            return await interaction.response.send_message("Você não é mediador.", ephemeral=True)

        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
            await interaction.message.edit(embed=embed_fila_mediadores(), view=self)
        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
            await interaction.message.edit(embed=embed_fila_mediadores(), view=self)
        await interaction.response.defer()

async def criar_canal(guild):
    categoria = discord.utils.get(guild.categories, name=CATEGORIA_APOSTAS)
    jogador1, jogador2 = fila_apostas
    mediador = fila_mediadores.pop(0) if fila_mediadores else None

    fila_apostas.clear()

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        jogador1: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        jogador2: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    if mediador:
        overwrites[mediador] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    canal = await guild.create_text_channel("aguardando-confirmacao", overwrites=overwrites, category=categoria)

    confirmacoes[canal.id] = []

    embed = discord.Embed(title="⏳ Aguardando Confirmações", color=0x2f3136)
    embed.add_field(name="Modo", value="1v1 Normal", inline=False)
    embed.add_field(name="Valor", value="R$ 0,25", inline=False)
    embed.add_field(name="Jogadores", value=f"{jogador1.mention}\n{jogador2.mention}", inline=False)
    embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

    await canal.send(embed=embed, view=PainelConfirmacao(mediador))

class PainelConfirmacao(discord.ui.View):
    def __init__(self, mediador):
        super().__init__(timeout=None)
        self.mediador = mediador

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal = interaction.channel
        if interaction.user not in fila_apostas and interaction.user not in confirmacoes[canal.id]:
            confirmacoes[canal.id].append(interaction.user)

        if len(confirmacoes[canal.id]) == 2:
            await canal.purge()

            embed = discord.Embed(title="✅ Aposta Confirmada", color=0x00ff00)
            embed.add_field(name="Modo", value="1v1 Normal", inline=False)
            embed.add_field(name="Valor", value="R$ 0,25", inline=False)
            embed.add_field(name="Jogadores", value="\n".join([u.mention for u in confirmacoes[canal.id]]), inline=False)
            embed.add_field(name="Mediador", value=self.mediador.mention if self.mediador else "Nenhum", inline=False)
            embed.add_field(name="PIX", value="SEU PIX AQUI", inline=False)

            await canal.send(embed=embed)

        await interaction.response.defer()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.gray)
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Combinem as regras no chat.", ephemeral=True)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

@bot.command()
async def painel(ctx):
    if CARGO_PERMITIDO not in [r.name for r in ctx.author.roles]:
        return

    await ctx.send(embed=embed_fila_apostas(), view=PainelApostas())
    await ctx.send(embed=embed_fila_mediadores(), view=PainelMediadores())

bot.run(TOKEN)
