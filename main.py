import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import random
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

filas = {}
fila_mediadores = []
pix_db = {}
confirmacoes = {}

def formatar(valor):
    return f"{valor:.2f}".replace(".", ",")

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")
    bot.add_view(FilaView("1v1"))  # mantém botões vivos
    bot.add_view(ConfirmarView())

# ================= FILA MEDIADOR =================
@bot.command()
async def mediador(ctx):
    if ctx.author in fila_mediadores:
        await ctx.send("Você já está na fila de mediadores.")
    else:
        fila_mediadores.append(ctx.author)
        await ctx.send(f"{ctx.author.mention} entrou na fila de mediadores.")

# ================= PAINEL PIX =================
@bot.command()
async def pix(ctx):
    await ctx.send("💳 Painel Pix", view=PixView())

class PixView(View):
    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        data = pix_db.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)

        await interaction.response.send_message(
            f"Nome: {data['nome']}\n"
            f"Chave Pix: {data['chave']}\n"
            f"QR Code: {data['qr']}",
            ephemeral=True
        )

class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome do titular")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link da imagem do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("Pix cadastrado com sucesso!", ephemeral=True)

# ================= CRIAR FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not valor_txt.startswith("valor;"):
        return await ctx.send("Use: !fila 1v1 valor;10")

    try:
        valor = float(valor_txt.replace("valor;", ""))
    except:
        return await ctx.send("Valor inválido.")

    filas[modo] = {"jogadores": [], "valor": valor}

    embed = discord.Embed(title=f"ws aposta {modo}", color=0x00ff00)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(modo))

class FilaView(View):
    def __init__(self, modo):
        super().__init__(timeout=None)
        self.modo = modo

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        user = interaction.user

        if user in fila:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(user)
        await self.atualizar(interaction)

        if len(fila) == 2:
            await self.criar_canal(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        user = interaction.user

        if user in fila:
            fila.remove(user)
            await self.atualizar(interaction)

    async def atualizar(self, interaction):
        fila = filas[self.modo]["jogadores"]
        jogadores = "\n".join(u.mention for u in fila) or "Nenhum"
        valor = filas[self.modo]["valor"]

        embed = discord.Embed(title=f"ws aposta {self.modo}", color=0x00ff00)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar(valor)}", inline=False)
        embed.add_field(name="Jogadores", value=jogadores, inline=False)

        await interaction.message.edit(embed=embed, view=self)

    async def criar_canal(self, interaction):
        guild = interaction.guild
        canal = await guild.create_text_channel(f"partida-{self.modo}")

        jogadores = filas[self.modo]["jogadores"]
        mediador = random.choice(fila_mediadores) if fila_mediadores else None

        confirmacoes[canal.id] = {
            "confirmados": [],
            "valor": filas[self.modo]["valor"],
            "mediador": mediador
        }

        embed = discord.Embed(title="Partida criada", color=0x00ff00)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar(filas[self.modo]['valor'])}", inline=False)
        embed.add_field(name="Jogadores", value="\n".join(u.mention for u in jogadores), inline=False)

        await canal.send(embed=embed, view=ConfirmarView())

# ================= CONFIRMAR =================
class ConfirmarView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        canal_id = interaction.channel.id
        dados = confirmacoes.get(canal_id)

        if not dados:
            return

        if interaction.user in dados["confirmados"]:
            return await interaction.response.send_message("Você já confirmou.", ephemeral=True)

        dados["confirmados"].append(interaction.user)
        await interaction.response.send_message("Confirmado.", ephemeral=True)

        if len(dados["confirmados"]) == 2:
            valor = dados["valor"] + 0.10
            mediador = dados["mediador"]

            if not mediador or mediador.id not in pix_db:
                return await interaction.channel.send("Mediador sem Pix cadastrado.")

            pix = pix_db[mediador.id]

            embed = discord.Embed(title="Pagamento ao mediador", color=0x00ff00)
            embed.add_field(name="Nome", value=pix["nome"], inline=False)
            embed.add_field(name="Chave Pix", value=pix["chave"], inline=False)
            embed.add_field(name="Valor", value=f"R$ {formatar(valor)}", inline=False)
            embed.add_field(name="QR Code", value=pix["qr"], inline=False)

            await interaction.channel.send(embed=embed)

# ================= START =================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    print("ERRO: TOKEN não encontrado")
else:
    bot.run(TOKEN)
