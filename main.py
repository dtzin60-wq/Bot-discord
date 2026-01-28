import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ====== DADOS ======
fila = []  # [(user, modo)]
partidas = {}
CANAL_TOPICO = None
VALOR_ATUAL = 5.00  # você pode mudar depois

# ===== UTIL =====
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ===== MODAL REGRAS =====
class RegrasModal(Modal, title="Combinar Regras"):
    regras = TextInput(label="Digite as regras", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(f"📜 **Regras combinadas:**\n{self.regras.value}")
        await interaction.response.defer()

# ===== CONFIRMAÇÃO =====
class ConfirmacaoView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não está na partida.", ephemeral=True)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            valor_formatado = formatar_valor(dados["valor"])
            await interaction.channel.edit(name=f"partida - {valor_formatado}")
            await interaction.channel.send("✅ Ambos confirmaram! Partida iniciada.")

        await interaction.response.defer()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recusar(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send("❌ Partida recusada.")
        await interaction.response.defer()

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def combinar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RegrasModal())

# ===== FILA VIEW =====
class FilaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, message):
        texto = ""
        for u, modo in fila:
            texto += f"{u.mention} - {modo}\n"
        if not texto:
            texto = "Nenhum jogador"

        embed = discord.Embed(title="🎮 ws apostas", color=0x2ecc71)
        embed.add_field(name="Modo", value="1v1", inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await message.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        global fila
        fila = [x for x in fila if x[0] != interaction.user]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

    async def entrar(self, interaction, modo):
        if any(u == interaction.user for u, _ in fila):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append((interaction.user, modo))
        await self.atualizar(interaction.message)

        if len(fila) == 2:
            await criar_topico(interaction.guild)

        await interaction.response.defer()

# ===== CRIAR TÓPICO =====
async def criar_topico(guild):
    global fila
    canal = bot.get_channel(CANAL_TOPICO)
    if not canal:
        return

    (j1, m1), (j2, m2) = fila
    fila.clear()

    topico = await canal.create_thread(
        name="partida-criada",
        type=discord.ChannelType.public_thread
    )

    modo_texto = f"1v1 {m1}"

    partidas[topico.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "valor": VALOR_ATUAL
    }

    embed = discord.Embed(title="⚔️ PARTIDA", description="Conversem e confirmem", color=0x3498db)
    embed.add_field(name="Modo", value=modo_texto, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)

    await topico.send(embed=embed, view=ConfirmacaoView())

# ===== COMANDOS =====
@bot.command()
async def canal(ctx):
    global CANAL_TOPICO
    CANAL_TOPICO = ctx.channel.id
    await ctx.send("✅ Este canal foi definido para criar os tópicos.")

@bot.command()
async def fila(ctx):
    embed = discord.Embed(title="🎮 ws apostas", color=0x2ecc71)
    embed.add_field(name="Modo", value="1v1", inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView())

# ===== START =====
bot.run(TOKEN)
