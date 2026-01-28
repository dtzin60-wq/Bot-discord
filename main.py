import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= CONFIG =================
config = {
    "cargo_fila": None,
    "cargo_ssmob": None,
    "canal_topico": None
}

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}

# ================= UTIL =================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_cargo(member, cargo_id):
    if not cargo_id:
        return False
    return discord.utils.get(member.roles, id=cargo_id)

def validar_modo(modo):
    try:
        a, b = modo.lower().split("v")
        a, b = int(a), int(b)
        if a == b and 1 <= a <= 4:
            return a * 2
    except:
        return None

# ================= PAINEL =================
class PainelModal(Modal, title="Configuração"):
    cargo_fila = TextInput(label="ID do cargo que pode criar fila")
    cargo_ssmob = TextInput(label="ID do cargo que pode usar .ssmob")

    async def on_submit(self, interaction: discord.Interaction):
        config["cargo_fila"] = int(self.cargo_fila.value)
        config["cargo_ssmob"] = int(self.cargo_ssmob.value)
        await interaction.response.send_message("✅ Configurado!", ephemeral=True)

@bot.command()
async def painel(ctx):
    await ctx.send_modal(PainelModal())

# ================= CANAL =================
class CanalSelect(Select):
    def __init__(self, canais):
        options = [
            discord.SelectOption(label=canal.name, value=str(canal.id))
            for canal in canais
        ]
        super().__init__(placeholder="Escolha o canal", options=options)

    async def callback(self, interaction: discord.Interaction):
        config["canal_topico"] = int(self.values[0])
        await interaction.response.send_message("✅ Canal definido!", ephemeral=True)

class CanalView(View):
    def __init__(self, canais):
        super().__init__()
        self.add_item(CanalSelect(canais))

@bot.command()
async def canal(ctx):
    canais = [c for c in ctx.guild.text_channels]
    await ctx.send("Escolha o canal:", view=CanalView(canais))

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

@bot.command()
async def cadastrarpix(ctx):
    await ctx.send_modal(PixModal())

# ================= FILA =================
class FilaView(View):
    def __init__(self, modo, valor, limite):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.limite = limite

    async def atualizar(self, interaction):
        fila = filas[self.modo]["jogadores"]
        nomes = "\n".join(u.mention for u in fila) or "Nenhum"

        embed = discord.Embed(title="🎮 Fila de Aposta", color=0x2ecc71)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=nomes, inline=False)

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.primary)
    async def gelo(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction)

    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.success)
    async def gelo_inf(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction)

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        if interaction.user in fila:
            fila.remove(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    async def entrar(self, interaction):
        fila = filas[self.modo]["jogadores"]

        if interaction.user in fila:
            return await interaction.response.send_message("Já está na fila.", ephemeral=True)

        if len(fila) >= self.limite:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(interaction.user)
        await self.atualizar(interaction)

        if len(fila) == self.limite:
            await self.criar_topico(interaction)

        await interaction.response.defer()

    async def criar_topico(self, interaction):
        canal = bot.get_channel(config["canal_topico"])
        jogadores = filas[self.modo]["jogadores"].copy()
        filas[self.modo]["jogadores"].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        topico = await canal.create_thread(
            name=f"partida-{formatar_valor(self.valor)}",
            type=discord.ChannelType.public_thread
        )

        partidas[topico.id] = {
            "jogadores": jogadores,
            "valor": self.valor,
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": [],
            "taxa_aplicada": False
        }

        embed = discord.Embed(title="Confirme a partida", color=0x3498db)
        embed.add_field(name="Jogadores", value=" x ".join(j.mention for j in jogadores))
        await topico.send(embed=embed, view=ConfirmacaoView())

# ================= CONFIRMAÇÃO =================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            if not dados["taxa_aplicada"]:
                dados["valor"] += 0.10
                dados["taxa_aplicada"] = True

            await interaction.channel.edit(
                name=f"partida-{formatar_valor(dados['valor'])}"
            )

            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="✅ Partida Confirmada", color=0x2ecc71)
            embed.add_field(name="Valor", value=f"R$ {formatar_valor(dados['valor'])}")

            if pix:
                embed.add_field(name="Pix", value=pix["chave"])
                embed.set_image(url=pix["qrcode"])

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================= COMANDOS =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not tem_cargo(ctx.author, config["cargo_fila"]):
        return await ctx.send("❌ Sem permissão.")

    limite = validar_modo(modo)
    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    filas[modo] = {"jogadores": []}

    embed = discord.Embed(title="🎮 Fila de Aposta", color=0x2ecc71)
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum")

    await ctx.send(embed=embed, view=FilaView(modo, valor, limite))

@bot.command()
async def ssmob(ctx):
    if not tem_cargo(ctx.author, config["cargo_ssmob"]):
        return await ctx.send("❌ Sem permissão.")
    await ctx.send("🚨 SS MOB CHAMADO!")

bot.run(TOKEN)
