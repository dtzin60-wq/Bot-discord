import discord
from discord.ext import commands
from discord.ui import View, Button
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

filas = {}  # { "1v1_10": [ (user, "gelo normal"), (user, "gelo normal") ] }
CANAL_TOPICO = None

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ================= VIEW DA FILA =================
class FilaView(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.modo = modo
        self.valor = valor

    async def atualizar(self, msg):
        fila = filas[self.chave]
        texto = "\n".join([f"{u.mention} - {m}" for u, m in fila]) or "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await msg.edit(embed=embed, view=self)

    async def entrar(self, interaction, escolha):
        fila = filas[self.chave]

        if any(u.id == interaction.user.id for u, _ in fila):
            return await interaction.response.send_message("❌ Você já está na fila.", ephemeral=True)

        if len(fila) >= 2:
            return await interaction.response.send_message("❌ Fila cheia.", ephemeral=True)

        fila.append((interaction.user, escolha))
        await self.atualizar(interaction.message)

        # se tiver 2 jogadores
        if len(fila) == 2:
            (j1, m1), (j2, m2) = fila

            # só cria se for o MESMO modo
            if m1 == m2:
                await criar_topico(interaction.guild, j1, j2, m1, self.modo, self.valor)
                filas[self.chave].clear()
                await self.atualizar(interaction.message)

        await interaction.response.defer()

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        filas[self.chave] = [x for x in filas[self.chave] if x[0].id != interaction.user.id]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

# ================= CRIAR TÓPICO =================
async def criar_topico(guild, j1, j2, modo_escolhido, modo, valor):
    canal = bot.get_channel(CANAL_TOPICO)
    if not canal:
        return

    nome = f"partida - {formatar_valor(valor)}"

    topico = await canal.create_thread(
        name=nome,
        type=discord.ChannelType.public_thread
    )

    embed = discord.Embed(title="⚔️ PARTIDA CRIADA", color=0x3498db)
    embed.add_field(name="Modo", value=modo_escolhido, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)

    await topico.send(embed=embed)

# ================= COMANDOS =================
@bot.command()
async def canal(ctx):
    global CANAL_TOPICO
    CANAL_TOPICO = ctx.channel.id
    await ctx.send("✅ Este canal foi definido para criar os tópicos.")

@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    try:
        valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    except:
        return await ctx.send("❌ Use: `.fila 1v1 valor:10`")

    chave = f"{modo}_{valor}"

    filas[chave] = []

    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(chave, modo, valor))

# ================= START =================
bot.run(TOKEN)
