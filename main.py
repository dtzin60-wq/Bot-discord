limport discord
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

# ================= PAINEL PIX =================
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
    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        data = pix_db.get(interaction.user.id)
        if not data:
            return await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)
        await interaction.response.send_message(f"Nome: {data['nome']}\nChave: {data['chave']}", ephemeral=True)

@bot.command()
async def cadastrarpix(ctx):
    await ctx.send("💰 **Cadastre sua chave Pix aqui**", view=PixView())

# ================= FILA MEDIADOR =================
class MediadorView(View):
    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await interaction.response.send_message("Você entrou na fila de mediadores.", ephemeral=True)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await interaction.response.send_message("Você saiu da fila de mediadores.", ephemeral=True)

@bot.command()
async def filamediador(ctx):
    await ctx.send("👨‍⚖️ **Entre na fila e seja chamado**", view=MediadorView())

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
        fila = filas[self.modo]["jogadores"]
        jogadores = "\n".join(u.mention for u in fila) or "Nenhum"

        embed = discord.Embed(title=f"Fila {self.modo}", color=0x00ff00)
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(filas[self.modo]['valor'])}")
        embed.add_field(name="Jogadores", value=jogadores)

        await interaction.message.edit(embed=embed, view=self)

    async def criar_canal(self, interaction):
        guild = interaction.guild
        canal = await guild.create_text_channel(f"partida-{self.modo}")
        jogadores = filas[self.modo]["jogadores"]
        mediador = random.choice(fila_mediadores) if fila_mediadores else None

        partidas[canal.id] = {
            "jogadores": jogadores,
            "valor": filas[self.modo]["valor"],
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": [],
            "id_partida": None,
            "senha": None
        }

        await canal.send(
            "💬 **Conversem e se resolvam. Quando decidir, aperte em confirmar!**\n\n"
            f"Modo: {self.modo}\n"
            f"Valor: R$ {formatar_valor(filas[self.modo]['valor'])}\n"
            f"Jogadores: {jogadores[0].mention} x {jogadores[1].mention}",
            view=ConfirmacaoView()
        )

class ConfirmacaoView(View):
    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

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
                f"Pix ADM:\nNome: {pix['nome']}\nChave: {pix['chave']}"
            )

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Você saiu da partida.", ephemeral=True)

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("💬 Combinação de regras liberada.")

# ================= ID PARTIDA =================
class CopiarIDView(View):
    def __init__(self, id_partida):
        super().__init__(timeout=None)
        self.id_partida = id_partida

    @discord.ui.button(label="Copiar ID", style=discord.ButtonStyle.green)
    async def copiar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(f"ID da partida: `{self.id_partida}`", ephemeral=True)

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    if message.channel.id in partidas:
        match = re.match(r"(\d+)\s+(\d+)", message.content)
        if match:
            idp, senha = match.groups()
            dados = partidas[message.channel.id]
            dados["id_partida"] = idp
            dados["senha"] = senha

            await message.channel.send(
                f"⏳ **Em 3 a 5 minutos damos GO!**\n\n"
                f"Modo: {dados['modo']}\n"
                f"Valor: R$ {formatar_valor(dados['valor'])}\n"
                f"Jogadores: {dados['jogadores'][0].mention} x {dados['jogadores'][1].mention}\n"
                f"ID da partida: {idp}\n"
                f"Senha: {senha}",
                view=CopiarIDView(idp)
            )

# ================= CRIAR FILA =================
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
