import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

CANAL_TOPICO = None
BANNER_URL = "https://i.imgur.com/4M34hi2.png"

fila = []  # [(user, gelo)]
partidas = {}
pix_db = {}

MODO_ATUAL = "1v1"
VALOR_ATUAL = 5.0

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ===== MODAL BANNER =====
class BannerModal(Modal, title="Definir Banner"):
    link = TextInput(label="Link da imagem (URL)")

    async def on_submit(self, interaction: discord.Interaction):
        global BANNER_URL
        BANNER_URL = self.link.value
        await interaction.response.send_message("✅ Banner atualizado!", ephemeral=True)

# ===== PAINEL CONFIG =====
class PainelView(View):
    @discord.ui.button(label="Escolher banner da fila", style=discord.ButtonStyle.blurple)
    async def banner(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(BannerModal())

@bot.command()
async def painel(ctx):
    await ctx.send("⚙️ Painel de Configuração", view=PainelView())

# ===== PIX =====
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix salvo!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou Pix.", ephemeral=True)

        embed = discord.Embed(title="💰 Seu Pix", color=0x2ecc71)
        embed.add_field(name="Nome", value=pix["nome"], inline=False)
        embed.add_field(name="Chave", value=pix["chave"], inline=False)
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command()
async def pix(ctx):
    await ctx.send("💳 Para colocar sua chave Pix aperta no botão abaixo:", view=PixView())

# ===== FILA VIEW =====
class FilaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, message):
        texto = ""
        for u, modo in fila:
            texto += f"{u.mention} - {modo}\n"
        if not texto:
            texto = "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=MODO_ATUAL, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await message.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        global fila
        fila = [x for x in fila if x[0] != interaction.user]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

    async def entrar(self, interaction, modo):
        if any(u == interaction.user for u, _ in fila):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        fila.append((interaction.user, modo))
        await self.atualizar(interaction.message)

        if len(fila) == 2:
            (j1, m1), (j2, m2) = fila
            if m1 == m2:
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

    partidas[topico.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "valor": VALOR_ATUAL
    }

    embed = discord.Embed(title="⚔️ PARTIDA CRIADA", color=0x3498db)
    embed.add_field(name="Modo", value=f"{MODO_ATUAL} {m1}", inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)

    await topico.send(embed=embed, view=ConfirmacaoView())

# ===== CONFIRMAÇÃO =====
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            await interaction.channel.edit(
                name=f"partida - {formatar_valor(dados['valor'])}"
            )

        await interaction.response.defer()

# ===== COMANDOS =====
@bot.command()
async def canal(ctx):
    global CANAL_TOPICO
    CANAL_TOPICO = ctx.channel.id
    await ctx.send("✅ Canal definido para criar os tópicos.")

@bot.command()
async def fila(ctx, modo: str, valor: float):
    global MODO_ATUAL, VALOR_ATUAL
    MODO_ATUAL = modo
    VALOR_ATUAL = valor

    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView())

# ===== START =====
bot.run(TOKEN)
