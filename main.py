import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

filas = {}
partidas = {}
pix_db = {}

CANAIS_TOPICO = []
canal_index = 0

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ================= MODAL PIX =================
class PixModal(Modal, title="Cadastrar chave Pix"):
    nome = TextInput(label="Nome da conta")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("✅ Chave Pix cadastrada!", ephemeral=True)

# ================= VIEW PIX =================
class PixView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar sua chave Pix", style=discord.ButtonStyle.gray)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

# ================= MODAL REGRAS =================
class RegrasModal(Modal, title="Combinar regras"):
    regras = TextInput(label="Digite as regras", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(f"📜 **Regras combinadas:**\n{self.regras.value}")
        await interaction.response.defer()

# ================= VIEW TÓPICO =================
class TopicoView(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas[self.thread_id]

        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não é jogador.", ephemeral=True)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)
            await interaction.channel.send(f"✅ {interaction.user.mention} confirmou.")

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recusar(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send("❌ Partida recusada.")
        await interaction.response.defer()

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def combinar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RegrasModal())

# ================= VIEW FILA =================
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

        # não deixa entrar duas vezes
        if any(u.id == interaction.user.id for u, _ in fila):
            return await interaction.response.send_message(
                "Você já está na fila.", ephemeral=True
            )

        # adiciona mantendo ordem de chegada
        fila.append((interaction.user, escolha))
        await self.atualizar(interaction.message)

        # só cria tópico se tiver 2 jogadores
        if len(fila) == 2:
            (j1, m1), (j2, m2) = fila

            # ✅ só cria se escolherem o MESMO modo
            if m1 == m2:
                await criar_topico(interaction.guild, j1, j2, m1, self.valor)

                # remove apenas esses dois
                filas[self.chave] = []
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
async def criar_topico(guild, j1, j2, modo, valor):
    global canal_index
    canal = bot.get_channel(CANAIS_TOPICO[canal_index])
    canal_index = (canal_index + 1) % len(CANAIS_TOPICO)

    thread = await canal.create_thread(name=f"partida - {formatar_valor(valor)}")

    partidas[thread.id] = {
        "jogadores": [j1, j2],
        "confirmados": []
    }

    embed = discord.Embed(title="⚔️ PARTIDA", color=0x3498db)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)

    await thread.send(embed=embed, view=TopicoView(thread.id))

# ================= COMANDOS =================
@bot.command()
async def canal(ctx, *canais: discord.TextChannel):
    if len(canais) < 1:
        return await ctx.send("❌ Use: .canal #canal1 #canal2")

    global CANAIS_TOPICO
    CANAIS_TOPICO = [c.id for c in canais]
    await ctx.send("✅ Canais definidos para criar tópicos!")

@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    chave = f"{modo}_{valor}"
    filas[chave] = []

    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(chave, modo, valor))

@bot.command()
async def pix(ctx):
    embed = discord.Embed(title="💰 CHAVE PIX", description="Cadastre sua chave Pix abaixo")
    await ctx.send(embed=embed, view=PixView())

# ================= START =================
bot.run(TOKEN)
