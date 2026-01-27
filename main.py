import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import random

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

NOME_CARGO_MEDIADOR = "Mediador"
CARGO_PERMITIDO = "Xoxota"

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}
paineis_fila = {}  # evita spam

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_cargo(user, nome):
    return discord.utils.get(user.roles, name=nome)

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome do titular")
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
        if not tem_cargo(interaction.user, NOME_CARGO_MEDIADOR):
            return await interaction.response.send_message("❌ Apenas mediadores.", ephemeral=True)
        await interaction.response.send_modal(PixModal())

@bot.command()
async def cadastrarpix(ctx):
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return
    await ctx.send("💰 Painel Pix", view=PixView())

# ================= FILA MEDIADOR =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, interaction):
        if fila_mediadores:
            texto = "\n".join(f"{i+1}º - {u.mention}" for i, u in enumerate(fila_mediadores))
        else:
            texto = "Nenhum"

        embed = discord.Embed(title="Fila de Mediadores", color=0xffaa00)
        embed.add_field(name="Ordem", value=texto)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user, NOME_CARGO_MEDIADOR):
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
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return

    embed = discord.Embed(title="Fila de Mediadores", color=0xffaa00)
    embed.add_field(name="Ordem", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

# ================= FILA APOSTA =================
class FilaView(View):
    def __init__(self, modo):
        super().__init__(timeout=None)
        self.modo = modo

    async def atualizar(self, interaction):
        fila = filas[self.modo]["jogadores"]
        nomes = "\n".join(u.mention for u in fila) or "Nenhum"

        embed = discord.Embed(title="Aguardando Jogadores", color=0x2ecc71)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(filas[self.modo]['valor'])}", inline=False)
        embed.add_field(name="Jogadores", value=nomes, inline=False)

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]

        if interaction.user in fila:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(interaction.user)
        await self.atualizar(interaction)

        if len(fila) == 2:
            await self.criar_canal(interaction)

        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        if interaction.user in fila:
            fila.remove(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    async def criar_canal(self, interaction):
        guild = interaction.guild
        jogadores = filas[self.modo]["jogadores"].copy()
        filas[self.modo]["jogadores"] = []
        paineis_fila.pop(self.modo)

        canal = await guild.create_text_channel(f"partida-{self.modo}")

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        partidas[canal.id] = {
            "jogadores": jogadores,
            "valor": filas[self.modo]["valor"],
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": []
        }

        embed = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(filas[self.modo]['valor'])}", inline=False)
        embed.add_field(name="Jogadores", value=f"{jogadores[0].mention} x {jogadores[1].mention}", inline=False)

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
            await interaction.channel.send(f"✅ {interaction.user.mention} confirmou!")

        if len(dados["confirmados"]) == 2:
            await interaction.channel.purge()

            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="✅ Partida Confirmada", color=0x00ff00)
            embed.add_field(name="Modo", value=dados["modo"], inline=False)
            embed.add_field(name="Valor", value=f"R$ {formatar_valor(dados['valor'])}", inline=False)
            embed.add_field(name="Jogadores", value=f"{dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}", inline=False)

            if mediador:
                texto_mediador = mediador.mention
                if pix:
                    texto_mediador += f"\nPix: {pix['chave']}"
                embed.add_field(name="Mediador", value=texto_mediador, inline=False)
                if pix:
                    embed.set_image(url=pix["qrcode"])
            else:
                embed.add_field(name="Mediador", value="Nenhum", inline=False)

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return

    if modo in paineis_fila:
        return await ctx.send("❌ Já existe uma fila desse modo ativa.")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    filas[modo] = {"jogadores": [], "valor": valor}

    embed = discord.Embed(title="Aguardando Jogadores", color=0x2ecc71)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    msg = await ctx.send(embed=embed, view=FilaView(modo))
    paineis_fila[modo] = msg.id

# ================= START =================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
