import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os

TOKEN = os.getenv("TOKEN")
CARGO_AUTORIZADO = "Mediador"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}
canal_topico = None  # canal escolhido no comando .canal

# ================= UTIL =================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_cargo(member):
    return discord.utils.get(member.roles, name=CARGO_AUTORIZADO)

def validar_modo(modo):
    try:
        a, b = modo.lower().split("v")
        a, b = int(a), int(b)
        if a == b and 1 <= a <= 4:
            return a * 2
        return None
    except:
        return None

# ================= ESCOLHER CANAL =================
class CanalSelect(Select):
    def __init__(self, canais):
        options = [
            discord.SelectOption(label=canal.name, value=str(canal.id))
            for canal in canais
        ]
        super().__init__(placeholder="Escolha o canal onde serão criados os tópicos", options=options)

    async def callback(self, interaction: discord.Interaction):
        global canal_topico
        canal_topico = int(self.values[0])
        await interaction.response.send_message("✅ Canal definido com sucesso!", ephemeral=True)

class CanalView(View):
    def __init__(self, canais):
        super().__init__(timeout=60)
        self.add_item(CanalSelect(canais))

@bot.command()
async def canal(ctx):
    if not tem_cargo(ctx.author):
        return await ctx.send("❌ Sem permissão.")

    canais = [c for c in ctx.guild.text_channels]
    await ctx.send("📌 Escolha o canal para criar os tópicos:", view=CanalView(canais))

# ================= FILA MEDIADOR =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, interaction):
        lista = "\n".join([f"{i+1}º - {m.mention}" for i, m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(title="🧑‍⚖️ Fila de Mediadores", color=0xf1c40f)
        embed.add_field(name="Ordem", value=lista)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user):
            return await interaction.response.send_message("❌ Você não é mediador.", ephemeral=True)
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

@bot.command()
async def filamediador(ctx):
    if not tem_cargo(ctx.author):
        return await ctx.send("❌ Sem permissão.")
    embed = discord.Embed(title="🧑‍⚖️ Fila de Mediadores", color=0xf1c40f)
    embed.add_field(name="Ordem", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

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

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]

        if interaction.user in fila:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= self.limite:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(interaction.user)
        await self.atualizar(interaction)

        if len(fila) == self.limite:
            await self.criar_topico(interaction)

        await interaction.response.defer()

    async def criar_topico(self, interaction):
        global canal_topico
        if canal_topico is None:
            return await interaction.followup.send("❌ Use .canal primeiro para definir onde criar os tópicos.", ephemeral=True)

        canal_base = interaction.guild.get_channel(canal_topico)

        jogadores = filas[self.modo]["jogadores"].copy()
        filas[self.modo]["jogadores"].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        topico = await canal_base.create_thread(
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

        embed = discord.Embed(title="Confirmação da Partida", color=0x3498db)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in jogadores]), inline=False)
        embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

        await topico.send(embed=embed, view=ConfirmacaoView())

# ================= CONFIRMAÇÃO =================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)
            await interaction.channel.send(f"✅ {interaction.user.mention} confirmou!")

        if len(dados["confirmados"]) == 2:
            if not dados["taxa_aplicada"]:
                dados["valor"] += 0.10
                dados["taxa_aplicada"] = True

            await interaction.channel.edit(name=f"partida-{formatar_valor(dados['valor'])}")

            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="✅ Partida Confirmada", color=0x2ecc71)
            embed.add_field(name="Modo", value=dados["modo"], inline=False)
            embed.add_field(name="Valor", value=f"R$ {formatar_valor(dados['valor'])}", inline=False)
            embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in dados["jogadores"]]), inline=False)
            embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

            if pix:
                embed.add_field(name="Chave Pix", value=pix["chave"], inline=False)
                embed.set_image(url=pix["qrcode"])

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not tem_cargo(ctx.author):
        return await ctx.send("❌ Sem permissão.")

    limite = validar_modo(modo)
    if not limite:
        return await ctx.send("❌ Use apenas 1v1, 2v2, 3v3 ou 4v4.")

    if not valor_txt.lower().startswith("valor:"):
        return await ctx.send("Use: .fila 2v2 valor:2,50")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    filas[modo] = {"jogadores": []}

    embed = discord.Embed(title="🎮 Fila de Aposta", color=0x2ecc71)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(modo, valor, limite))

# ================= START =================
bot.run(TOKEN)
