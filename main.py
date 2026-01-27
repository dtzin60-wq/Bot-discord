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
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        data = pix_db.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)

        await interaction.response.send_message(
            f"Nome: {data['nome']}\nChave: {data['chave']}",
            ephemeral=True
        )

@bot.command()
async def cadastrarpix(ctx):
    await ctx.send(
        "💰 **Cadastre sua chave Pix aqui**\n\n"
        "Selecione uma das opções abaixo:",
        view=PixView()
    )

# ================= FILA MEDIADOR =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await interaction.response.send_message("Você entrou na fila.", ephemeral=True)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await interaction.response.send_message("Você saiu da fila.", ephemeral=True)

@bot.command()
async def filamediador(ctx):
    await ctx.send(
        "👨‍⚖️ **Entre na fila e seja chamado**",
        view=MediadorView()
    )

# ================= FILA JOGO =================
class FilaView(View):
    def __init__(self, modo):
        super().__init__(timeout=None)
        self.modo = modo

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]

        if interaction.user in fila:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= filas[self.modo]["limite"]:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(interaction.user)
        await interaction.response.defer()
        await atualizar_fila(self.modo, interaction.message)

        if len(fila) == filas[self.modo]["limite"]:
            await criar_canal(interaction.guild, self.modo)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        if interaction.user in fila:
            fila.remove(interaction.user)

        await interaction.response.defer()
        await atualizar_fila(self.modo, interaction.message)

async def atualizar_fila(modo, message):
    fila = filas[modo]["jogadores"]

    if fila:
        jogadores = "\n".join(u.mention for u in fila)
    else:
        jogadores = "Nenhum"

    texto = (
        f"Fila {modo}\n\n"
        f"Modo\n{modo}\n\n"
        f"Valor\nR$ {formatar_valor(filas[modo]['valor'])}\n\n"
        f"Jogadores\n{jogadores}"
    )

    await message.edit(content=texto, view=FilaView(modo))

async def criar_canal(guild, modo):
    canal = await guild.create_text_channel(f"partida-{modo}")
    jogadores = filas[modo]["jogadores"]

    mediador = random.choice(fila_mediadores) if fila_mediadores else None

    partidas[canal.id] = {
        "jogadores": jogadores,
        "valor": filas[modo]["valor"],
        "modo": modo,
        "mediador": mediador,
        "confirmados": [],
        "id_partida": None,
        "senha": None
    }

    await canal.send(
        f"💬 **Conversem e se resolvam. Quando decidir, aperte em confirmar!**\n\n"
        f"Modo: {modo}\n"
        f"Valor: R$ {formatar_valor(filas[modo]['valor'])}\n"
        f"Jogadores: {jogadores[0].mention} x {jogadores[1].mention}",
        view=ConfirmacaoView()
    )

class ConfirmacaoView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        await interaction.response.defer()

        if len(dados["confirmados"]) == 2:
            await interaction.channel.purge()

            mediador = dados["mediador"]
            if not mediador or mediador.id not in pix_db:
                return await interaction.channel.send("❌ Mediador sem Pix cadastrado.")

            pix = pix_db[mediador.id]

            await interaction.channel.send(
                "⚠️ **Aguardem o ADM chegar para pagar!**\n\n"
                f"Modo: {dados['modo']}\n"
                f"Valor: R$ {formatar_valor(dados['valor'])}\n"
                f"Jogadores: {dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}\n\n"
                f"Pix ADM:\n"
                f"Nome: {pix['nome']}\n"
                f"Chave: {pix['chave']}"
            )

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Você saiu.", ephemeral=True)

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Conversem e combinem as regras.", ephemeral=True)

# ================= ID E SENHA =================
class CopiarIDView(View):
    def __init__(self, id_partida):
        super().__init__(timeout=None)
        self.id_partida = id_partida

    @discord.ui.button(label="Copiar ID", style=discord.ButtonStyle.green)
    async def copiar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"ID da partida: `{self.id_partida}`",
            ephemeral=True
        )

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
                f"Jogadores: {dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}\n\n"
                f"ID da partida: {idp}\n"
                f"Senha: {senha}",
                view=CopiarIDView(idp)
            )

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not valor_txt.lower().startswith("valor:"):
        return await ctx.send("Use: .fila 1v1 valor:2,50")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    limite = 2 if "2v2" not in modo else 4

    filas[modo] = {"jogadores": [], "valor": valor, "limite": limite}

    texto = (
        f"Fila {modo}\n\n"
        f"Modo\n{modo}\n\n"
        f"Valor\nR$ {formatar_valor(valor)}\n\n"
        f"Jogadores\nNenhum"
    )

    await ctx.send(texto, view=FilaView(modo))

# ================= START =================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
