import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")
CARGO_AUTORIZADO = "Mediador"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}
mensagens_fila = {}

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

class PixView(View):
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        await interaction.response.send_modal(PixModal())

@bot.command()
async def cadastrarpix(ctx):
    if not tem_cargo(ctx.author):
        return await ctx.send("❌ Sem permissão.")
    await ctx.send("💰 Painel Pix", view=PixView())

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

# ================= FILA APOSTA =================
class FilaView(View):
    def __init__(self, modo):
        super().__init__(timeout=None)
        self.modo = modo

    async def atualizar(self, interaction):
        dados = filas[self.modo]
        fila = dados["jogadores"]

        nomes = "\n".join(u.mention for u in fila) or "Nenhum"

        embed = discord.Embed(title="🎮 Fila de Aposta", color=0x2ecc71)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(dados['valor'])}", inline=False)
        embed.add_field(name="Jogadores", value=nomes, inline=False)

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        dados = filas[self.modo]
        fila = dados["jogadores"]

        if interaction.user in fila:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        fila.append(interaction.user)
        await self.atualizar(interaction)

        if len(fila) == dados["limite"]:
            await self.criar_canal(interaction)

        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        dados = filas[self.modo]
        fila = dados["jogadores"]

        if interaction.user in fila:
            fila.remove(interaction.user)
            await self.atualizar(interaction)

        await interaction.response.defer()

    async def criar_canal(self, interaction):
        guild = interaction.guild
        dados = filas[self.modo]
        jogadores = dados["jogadores"].copy()
        dados["jogadores"].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        canal = await guild.create_text_channel(f"partida-{self.modo}")

        partidas[canal.id] = {
            "jogadores": jogadores,
            "valor": dados["valor"],
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": []
        }

        embed = discord.Embed(title="Confirmação da Partida", color=0x3498db)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(dados['valor'])}", inline=False)
        embed.add_field(name="Jogadores", value=" x ".join(j.mention for j in jogadores), inline=False)
        embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

        await canal.send(embed=embed, view=ConfirmacaoView())

# ================= CONFIRMAÇÃO =================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            await interaction.channel.purge()
            valor = dados["valor"]

            await interaction.channel.edit(name=f"partida-{formatar_valor(valor)}")

            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="✅ Partida Confirmada", color=0x2ecc71)
            embed.add_field(name="Modo", value=dados["modo"], inline=False)
            embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
            embed.add_field(name="Jogadores", value=" x ".join(j.mention for j in dados["jogadores"]), inline=False)
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
        return await ctx.send("❌ Use apenas 1v1 até 4v4.")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    if modo in mensagens_fila:
        try:
            await mensagens_fila[modo].delete()
        except:
            pass

    filas[modo] = {
        "jogadores": [],
        "valor": valor,
        "limite": limite
    }

    embed = discord.Embed(title="🎮 Fila de Aposta", color=0x2ecc71)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    msg = await ctx.send(embed=embed, view=FilaView(modo))
    mensagens_fila[modo] = msg

# ================= START =================
bot.run(TOKEN)
