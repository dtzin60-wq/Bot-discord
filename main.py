import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import random
import re

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

@bot.event
async def on_ready():
    print("Bot online:", bot.user)

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        data = pix_db.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)
        await interaction.response.send_message(f"Nome: {data['nome']}\nChave: {data['chave']}", ephemeral=True)

@bot.command()
async def cadastrarpix(ctx):
    await ctx.send("💰 **Painel Pix**", view=PixView())

# ================= FILA MEDIADOR =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, interaction):
        nomes = "\n".join(u.mention for u in fila_mediadores) or "Nenhum"

        embed = discord.Embed(title="Fila de Mediadores", color=0xffaa00)
        embed.add_field(name="Mediadores", value=nomes)

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
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
    embed = discord.Embed(title="Fila de Mediadores", color=0xffaa00)
    embed.add_field(name="Mediadores", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

# ================= FILA APOSTAS =================
class FilaView(View):
    def __init__(self, modo):
        super().__init__(timeout=None)
        self.modo = modo

    async def atualizar(self, interaction):
        fila = filas[self.modo]["jogadores"]
        nomes = "\n".join(u.mention for u in fila) or "Nenhum"

        embed = discord.Embed(title=f"Fila {self.modo}", color=0x00ff00)
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(filas[self.modo]['valor'])}")
        embed.add_field(name="Jogadores", value=nomes)

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
        jogadores = filas[self.modo]["jogadores"]

        canal = await guild.create_text_channel(f"partida-{self.modo}")

        mediador = random.choice(fila_mediadores) if fila_mediadores else None

        partidas[canal.id] = {
            "jogadores": jogadores.copy(),
            "valor": filas[self.modo]["valor"],
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": [],
            "id_partida": None,
            "senha": None
        }

        filas[self.modo]["jogadores"] = []

        await canal.send(
            "💬 **Conversem e se resolvam. Quando decidir, aperte em confirmar!**\n\n"
            f"Modo: {self.modo}\n"
            f"Valor: R$ {formatar_valor(filas[self.modo]['valor'])}\n"
            f"Jogadores: {jogadores[0].mention} x {jogadores[1].mention}",
            view=ConfirmacaoView()
        )

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
            mediador = dados["mediador"]
            if not mediador or mediador.id not in pix_db:
                return await interaction.channel.send("❌ Mediador sem Pix.")

            pix = pix_db[mediador.id]
            await interaction.channel.send(
                "⚠️ **Aguardem o pagamento**\n\n"
                f"Modo: {dados['modo']}\n"
                f"Valor: R$ {formatar_valor(dados['valor'])}\n"
                f"Jogadores: {dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}\n\n"
                f"Pix ADM:\nNome: {pix['nome']}\nChave: {pix['chave']}"
            )

        await interaction.response.defer()

# ================= COPIAR ID =================
class CopiarIDView(View):
    def __init__(self, id_partida):
        super().__init__(timeout=None)
        self.id_partida = id_partida

    @discord.ui.button(label="Copiar ID", style=discord.ButtonStyle.green)
    async def copiar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(f"`{self.id_partida}`", ephemeral=True)

# ================= ID + SENHA =================
@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id in partidas:
        match = re.match(r"(\d+)\s+(\d+)", message.content)
        if match:
            idp, senha = match.groups()
            dados = partidas[message.channel.id]

            await message.channel.send(
                f"⏳ **Em 3 a 5 minutos damos GO!**\n\n"
                f"Modo: {dados['modo']}\n"
                f"Valor: R$ {formatar_valor(dados['valor'])}\n"
                f"Jogadores: {dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}\n"
                f"ID da partida: {idp}\n"
                f"Senha: {senha}",
                view=CopiarIDView(idp)
            )

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not valor_txt.lower().startswith("valor:"):
        return await ctx.send("Use: .fila 2v2 valor:2,50")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    filas[modo] = {"jogadores": [], "valor": valor}

    embed = discord.Embed(title=f"Fila {modo}", color=0x00ff00)
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum")

    await ctx.send(embed=embed, view=FilaView(modo))

# ================= START =================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
