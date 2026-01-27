import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os
import random

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

# ================= FILA APOSTA =================
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
            "confirmados": []
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
            mediador_nome = mediador.mention if mediador else "Nenhum"

            embed = discord.Embed(title="Partida Confirmada", color=0x00ff00)
            embed.add_field(name="Modo", value=dados["modo"], inline=False)
            embed.add_field(name="Valor", value=f"R$ {formatar_valor(dados['valor'])}", inline=False)
            embed.add_field(
                name="Jogadores",
                value=f"{dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}",
                inline=False
            )
            embed.add_field(name="Mediador", value=mediador_nome, inline=False)

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Você saiu da partida.", ephemeral=True)

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("💬 Podem combinar as regras no chat.")

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not valor_txt.lower().startswith("valor:"):
        return await ctx.send("Use: .fila 1v1 valor:2,50")

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
