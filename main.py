import discord
from discord.ext import commands
from discord.ui import View, Button
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ====== CONFIG ======
CANAL_TOPICO = None
BANNER_URL = "https://i.imgur.com/7QK4H6y.png"  # troque se quiser

filas = {}  # modo -> [(user, gelo)]
partidas = {}

# ===== UTIL =====
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ===== VIEW DA FILA =====
class FilaView(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor

    async def atualizar(self, message):
        fila = filas[self.modo]
        texto = ""
        for u, gelo in fila:
            texto += f"{u.mention} - {gelo}\n"
        if not texto:
            texto = "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await message.edit(embed=embed, view=self)

    async def entrar(self, interaction, gelo):
        fila = filas[self.modo]

        if any(u == interaction.user for u, _ in fila):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append((interaction.user, gelo))
        await self.atualizar(interaction.message)

        # só cria se os dois escolherem o mesmo gelo
        if len(fila) == 2:
            (_, g1), (_, g2) = fila
            if g1 == g2:
                await criar_topico(self.modo, self.valor)

        await interaction.response.defer()

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "Gelo infinito")

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "Gelo normal")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        filas[self.modo] = [x for x in filas[self.modo] if x[0] != interaction.user]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

# ===== CRIAR TÓPICO =====
async def criar_topico(modo, valor):
    global filas

    canal = bot.get_channel(CANAL_TOPICO)
    if not canal:
        return

    jogadores = filas[modo].copy()
    filas[modo].clear()

    nome = f"partida-{formatar_valor(valor)}"

    topico = await canal.create_thread(
        name=nome,
        type=discord.ChannelType.public_thread
    )

    embed = discord.Embed(title="⚔️ PARTIDA CRIADA", color=0x3498db)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(
        name="Jogadores",
        value=f"{jogadores[0][0].mention} x {jogadores[1][0].mention}",
        inline=False
    )

    await topico.send(embed=embed)

# ===== COMANDO FILA =====
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not valor_txt.lower().startswith("valor:"):
        return await ctx.send("Use: `.fila 1v1 valor:10`")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    filas[modo] = []

    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(modo, valor))

# ===== DEFINIR CANAL DOS TÓPICOS =====
@bot.command()
async def canal(ctx):
    global CANAL_TOPICO
    CANAL_TOPICO = ctx.channel.id
    await ctx.send("✅ Este canal agora cria os tópicos das partidas.")

# ===== START =====
bot.run(TOKEN)
