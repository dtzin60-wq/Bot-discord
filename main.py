limport discord
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

# ================= PIX =================
@bot.command()
async def pix(ctx):
    await ctx.send("💳 Painel Pix", view=PixView())

class PixView(View):
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver meu Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        data = pix_db.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)

        await interaction.response.send_message(
            f"Nome: {data['nome']}\nChave: {data['chave']}\nQR Code: {data['qr']}",
            ephemeral=True
        )

class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome do titular")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("Pix cadastrado!", ephemeral=True)

# ================= FILA MEDIADOR =================
@bot.command()
async def mediador(ctx):
    embed = discord.Embed(title="Fila de Mediadores", color=0x00ff00)
    embed.add_field(name="Mediadores", value="Nenhum", inline=False)
    await ctx.send(embed=embed, view=MediadorView())

class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        fila_mediadores.append(interaction.user)
        await self.atualizar(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
            await self.atualizar(interaction)

    async def atualizar(self, interaction):
        nomes = "\n".join(u.mention for u in fila_mediadores) or "Nenhum"
        embed = discord.Embed(title="Fila de Mediadores", color=0x00ff00)
        embed.add_field(name="Mediadores", value=nomes, inline=False)
        await interaction.message.edit(embed=embed, view=self)

# ================= FILA NORMAL =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not valor_txt.startswith("valor:"):
        return await ctx.send("Use: !fila 1v1 valor:10")

    try:
        valor = float(valor_txt.replace("valor:", ""))
    except:
        return await ctx.send("Valor inválido.")

    filas[modo] = {"jogadores": [], "valor": valor}

    embed = discord.Embed(title=f"Fila {modo}", color=0x00ff00)
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

        if interaction.user in fila:
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        if len(fila) >= 2:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila.append(interaction.user)
        await self.atualizar(interaction)

        if len(fila) == 2:
            await self.criar_canal(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]

        if interaction.user in fila:
            fila.remove(interaction.user)
            await self.atualizar(interaction)

    async def atualizar(self, interaction):
        jogadores = "\n".join(u.mention for u in filas[self.modo]["jogadores"]) or "Nenhum"
        valor = filas[self.modo]["valor"]

        embed = discord.Embed(title=f"Fila {self.modo}", color=0x00ff00)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar(valor)}", inline=False)
        embed.add_field(name="Jogadores", value=jogadores, inline=False)

        await interaction.message.edit(embed=embed, view=self)

    async def criar_canal(self, interaction):
        guild = interaction.guild
        canal = await guild.create_text_channel(f"partida-{self.modo}")

        mediador = random.choice(fila_mediadores) if fila_mediadores else None

        confirmacoes[canal.id] = {
            "confirmados": [],
            "modo": self.modo,
            "valor": filas[self.modo]["valor"],
            "jogadores": filas[self.modo]["jogadores"],
            "mediador": mediador
        }

        await canal.send("Clique para confirmar:", view=ConfirmarView())

# ================= CONFIRMAR =================
class ConfirmarView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = confirmacoes.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user in dados["confirmados"]:
            return await interaction.response.send_message("Você já confirmou.", ephemeral=True)

        dados["confirmados"].append(interaction.user)
        await interaction.response.send_message("Confirmado!", ephemeral=True)

        if len(dados["confirmados"]) == 2:
            await interaction.channel.purge()

            jogadores = "\n".join(u.mention for u in dados["jogadores"])

            embed = discord.Embed(title="Aguardem o ADM chegar para pagar!", color=0x00ff00)
            embed.add_field(name="Modo", value=dados["modo"], inline=False)
            embed.add_field(name="Valor", value=f"R$ {formatar(dados['valor'])}", inline=False)
            embed.add_field(name="Jogadores", value=jogadores, inline=False)

            await interaction.channel.send(embed=embed)

            mediador = dados["mediador"]
            if not mediador or mediador.id not in pix_db:
                return await interaction.channel.send("Mediador sem Pix cadastrado.")

            pix = pix_db[mediador.id]

            embed_pix = discord.Embed(title="Pix do ADM", color=0x00ff00)
            embed_pix.add_field(name="Nome", value=pix["nome"], inline=False)
            embed_pix.add_field(name="Chave", value=pix["chave"], inline=False)
            embed_pix.add_field(name="QR Code", value=pix["qr"], inline=False)

            await interaction.channel.send(embed=embed_pix)

# ================= START =================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
