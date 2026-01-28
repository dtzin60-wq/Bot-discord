
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================== DADOS ==================
config = {
    "cargo_analista": None,
    "cargo_mediador": None,
    "canais": []
}

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}

# ================== UTIL ==================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_analista(member):
    if not config["cargo_analista"]:
        return False
    return discord.utils.get(member.roles, id=config["cargo_analista"])

def validar_modo(modo):
    try:
        a, b = modo.lower().split("v")
        a, b = int(a), int(b)
        if a == b:
            return a * 2
    except:
        pass
    return None

# ================== MODAL PIX ==================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

# ================== PAINEL PIX ==================
class PixView(View):
    @discord.ui.button(label="Adicionar chave Pix", style=discord.ButtonStyle.green)
    async def addpix(self, interaction, button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def verpix(self, interaction, button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou Pix.", ephemeral=True)
        embed = discord.Embed(title="💳 Seu Pix")
        embed.add_field(name="Nome", value=pix["nome"])
        embed.add_field(name="Chave", value=pix["chave"])
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Ver Pix do mediador", style=discord.ButtonStyle.gray)
    async def verpixmediador(self, interaction, button):
        dados = partidas.get(interaction.channel.id)
        if not dados or not dados["mediador"]:
            return await interaction.response.send_message("❌ Sem mediador.", ephemeral=True)
        pix = pix_db.get(dados["mediador"].id)
        if not pix:
            return await interaction.response.send_message("❌ Mediador sem Pix.", ephemeral=True)
        embed = discord.Embed(title="💳 Pix do Mediador")
        embed.add_field(name="Nome", value=pix["nome"])
        embed.add_field(name="Chave", value=pix["chave"])
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================== PAINEL CONFIG ==================
class ConfigView(View):
    @discord.ui.button(label="Configurar cargo Analista", style=discord.ButtonStyle.green)
    async def analista(self, interaction, button):
        role = interaction.user.top_role
        config["cargo_analista"] = role.id
        await interaction.response.send_message(f"Cargo Analista definido: {role.name}", ephemeral=True)

    @discord.ui.button(label="Configurar cargo Mediador", style=discord.ButtonStyle.blurple)
    async def mediador(self, interaction, button):
        role = interaction.user.top_role
        config["cargo_mediador"] = role.id
        await interaction.response.send_message(f"Cargo Mediador definido: {role.name}", ephemeral=True)

    @discord.ui.button(label="Adicionar canal de tópicos", style=discord.ButtonStyle.gray)
    async def canal(self, interaction, button):
        if len(config["canais"]) >= 3:
            return await interaction.response.send_message("❌ Máx 3 canais.", ephemeral=True)
        config["canais"].append(interaction.channel.id)
        await interaction.response.send_message("Canal adicionado.", ephemeral=True)

# ================== FILA MEDIADOR ==================
class MediadorView(View):
    async def atualizar(self, interaction):
        lista = "\n".join(m.mention for m in fila_mediadores) or "Nenhum"
        embed = discord.Embed(title="Fila Mediadores")
        embed.add_field(name="Ordem", value=lista)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction, button):
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction, button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

# ================== FILA ==================
class FilaView(View):
    def __init__(self, modo, valor, limite):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.limite = limite

    async def atualizar(self, interaction):
        nomes = "\n".join(j.mention for j in filas[self.modo]) or "Nenhum"
        embed = discord.Embed(title="WS APOSTAS")
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}")
        embed.add_field(name="Jogadores", value=nomes, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction, button):
        fila = filas[self.modo]
        if interaction.user not in fila:
            fila.append(interaction.user)
        await self.atualizar(interaction)
        if len(fila) == self.limite:
            await self.criar_topico(interaction)
        await interaction.response.defer()

    async def criar_topico(self, interaction):
        canal = interaction.guild.get_channel(config["canais"][0])
        jogadores = filas[self.modo].copy()
        filas[self.modo].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None
        if mediador:
            fila_mediadores.append(mediador)

        topico = await canal.create_thread(name="ws-aposta")

        partidas[topico.id] = {
            "jogadores": jogadores,
            "modo": self.modo,
            "valor": self.valor,
            "mediador": mediador,
            "confirmados": []
        }

        embed = discord.Embed(title="Aguardando confirmação")
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}")
        embed.add_field(name="Jogadores", value=" x ".join(j.mention for j in jogadores))
        embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum")

        await topico.send("Jogadores acalmem, conversem e confirmem.")
        await topico.send(embed=embed, view=ConfirmView())
        await topico.send(view=PixView())

# ================== CONFIRMAÇÃO ==================
class ConfirmView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction, button):
        dados = partidas[interaction.channel.id]
        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            pix = pix_db.get(dados["mediador"].id)
            embed = discord.Embed(title="Pix do Mediador")
            embed.add_field(name="Nome", value=pix["nome"])
            embed.add_field(name="Chave Pix", value=pix["chave"])
            embed.set_image(url=pix["qrcode"])
            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================== COMANDOS ==================
@bot.command()
async def painel(ctx):
    await ctx.send("Painel de Configuração", view=ConfigView())

@bot.command()
async def filamediador(ctx):
    embed = discord.Embed(title="Fila Mediadores")
    embed.add_field(name="Ordem", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not tem_analista(ctx.author):
        return await ctx.send("❌ Sem permissão.")
    limite = validar_modo(modo)
    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    filas[modo] = []
    embed = discord.Embed(title="WS APOSTAS")
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum")
    await ctx.send(embed=embed, view=FilaView(modo, valor, limite))

bot.run(TOKEN)
