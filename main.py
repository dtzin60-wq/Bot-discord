import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os, qrcode, io

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

fila_jogadores = []  # [(user, modo)]
fila_mediadores = []
pix_mediadores = {}
partidas = {}
CANAL_TOPICO = None
VALOR_ATUAL = 5.00

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ================= MODAL PIX =================

class PixModal(Modal, title="Cadastrar chave Pix"):
    chave = TextInput(label="Digite sua chave Pix")

    async def on_submit(self, interaction: discord.Interaction):
        pix_mediadores[interaction.user.id] = self.chave.value
        await interaction.response.send_message("✅ Chave Pix cadastrada!", ephemeral=True)

# ================= CONFIRMAÇÃO =================

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
            mediador = dados["mediador"]
            pix = pix_mediadores.get(mediador.id, "Não cadastrado")

            qr = qrcode.make(pix)
            buf = io.BytesIO()
            qr.save(buf)
            buf.seek(0)

            embed = discord.Embed(title="🎯 PARTIDA INICIADA", color=0x2ecc71)
            embed.add_field(name="Mediador", value=mediador.mention, inline=False)
            embed.add_field(name="Nome da chave Pix", value=mediador.name, inline=False)
            embed.add_field(name="Chave Pix", value=pix, inline=False)

            file = discord.File(buf, filename="qrcode.png")
            embed.set_image(url="attachment://qrcode.png")

            await interaction.channel.send(embed=embed, file=file)

        await interaction.response.defer()

# ================= FILA JOGADORES =================

class FilaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, message):
        texto = ""
        for u, modo in fila_jogadores:
            texto += f"{u.mention} - {modo}\n"
        if not texto:
            texto = "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
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

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        global fila_jogadores
        fila_jogadores = [x for x in fila_jogadores if x[0] != interaction.user]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

    async def entrar(self, interaction, modo):
        if any(u == interaction.user for u, _ in fila_jogadores):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila_jogadores) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila_jogadores.append((interaction.user, modo))
        await self.atualizar(interaction.message)

        if len(fila_jogadores) == 2:
            await criar_topico(interaction.guild)

        await interaction.response.defer()

# ================= FILA MEDIADORES =================

class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar na fila mediador", style=discord.ButtonStyle.success)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
            await interaction.response.send_message("Você entrou na fila de mediadores.", ephemeral=True)
        else:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila mediador", style=discord.ButtonStyle.danger)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
            await interaction.response.send_message("Você saiu da fila.", ephemeral=True)

# ================= CRIAR TÓPICO =================

async def criar_topico(guild):
    global fila_jogadores
    canal = bot.get_channel(CANAL_TOPICO)
    if not canal:
        return

    (j1, m1), (j2, m2) = fila_jogadores
    fila_jogadores.clear()

    mediador = fila_mediadores.pop(0) if fila_mediadores else None

    topico = await canal.create_thread(name="partida-criada", type=discord.ChannelType.public_thread)

    partidas[topico.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "valor": VALOR_ATUAL,
        "mediador": mediador
    }

    embed = discord.Embed(title="⚔️ PARTIDA", description="Confirmem a partida", color=0x3498db)
    embed.add_field(name="Modo", value=f"{m1} x {m2}", inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)
    embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

    await topico.send(embed=embed, view=ConfirmacaoView())

# ================= COMANDOS =================

@bot.command()
async def canal(ctx):
    global CANAL_TOPICO
    CANAL_TOPICO = ctx.channel.id
    await ctx.send("✅ Este canal foi definido para criar os tópicos.")

@bot.command()
async def painel(ctx):
    embed = discord.Embed(title="🎮 WS APOSTAS", description="Entre na fila para jogar", color=0x2ecc71)
    embed.add_field(name="Modo", value="1v1", inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(VALOR_ATUAL)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView())
    await ctx.send("💳 Para colocar sua chave Pix aperta no botão em baixo", view=PixView())
    await ctx.send("👮 Entre na fila mediadores pra ser chamado", view=MediadorView())

class PixView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.success)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.primary)
    async def ver(self, interaction: discord.Interaction, button: Button):
        pix = pix_mediadores.get(interaction.user.id)
        if pix:
            await interaction.response.send_message(f"Sua chave Pix: {pix}", ephemeral=True)
        else:
            await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)

    @discord.ui.button(label="Ver chave Pix de mediadores", style=discord.ButtonStyle.secondary)
    async def ver_mediadores(self, interaction: discord.Interaction, button: Button):
        if not fila_mediadores:
            return await interaction.response.send_message("Nenhum mediador na fila.", ephemeral=True)
        mediador = fila_mediadores[0]
        pix = pix_mediadores.get(mediador.id, "Não cadastrado")
        await interaction.response.send_message(f"Mediador: {mediador.mention}\nPix: {pix}", ephemeral=True)

bot.run(TOKEN)
