import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= VARIÁVEIS =================
pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}
CANAL_TOPICOS = None

# ================= UTIL =================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_permissao(member):
    return member.guild_permissions.administrator

def validar_modo(modo):
    try:
        a, b = modo.lower().split("v")
        a, b = int(a), int(b)
        if a == b and 1 <= a <= 4:
            return a * 2
    except:
        pass
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

@bot.command()
async def cadastrarpix(ctx):
    if not tem_permissao(ctx.author):
        return await ctx.send("❌ Sem permissão.")
    await ctx.send("💰 Cadastre seu Pix:", view=View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green, custom_id="pix")))

@bot.event
async def on_interaction(interaction):
    if interaction.data and interaction.data.get("custom_id") == "pix":
        await interaction.response.send_modal(PixModal())

# ================= CANAL =================
@bot.command()
async def canal(ctx):
    global CANAL_TOPICOS
    if not tem_permissao(ctx.author):
        return await ctx.send("❌ Sem permissão.")
    CANAL_TOPICOS = ctx.channel
    await ctx.send(f"✅ Canal definido: {ctx.channel.mention}")

# ================= MEDIADOR =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar(self, interaction):
        texto = "\n".join([f"{i+1}º - {m.mention}" for i, m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(title="🧑‍⚖️ Fila de Mediadores", color=0xf1c40f)
        embed.add_field(name="Ordem", value=texto)
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
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}")
        embed.add_field(name="Jogadores", value=nomes, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        if interaction.user not in fila and len(fila) < self.limite:
            fila.append(interaction.user)
        await self.atualizar(interaction)

        if len(fila) == self.limite:
            await self.criar_topico(interaction)

        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]["jogadores"]
        if interaction.user in fila:
            fila.remove(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

    async def criar_topico(self, interaction):
        global CANAL_TOPICOS
        if not CANAL_TOPICOS:
            return await interaction.followup.send("❌ Use .canal primeiro.", ephemeral=True)

        jogadores = filas[self.modo]["jogadores"].copy()
        filas[self.modo]["jogadores"].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        topico = await CANAL_TOPICOS.create_thread(
            name=f"partida-{formatar_valor(self.valor)}",
            type=discord.ChannelType.public_thread
        )

        partidas[topico.id] = {
            "jogadores": jogadores,
            "valor": self.valor,
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": [],
            "taxa": False
        }

        embed = discord.Embed(title="🔔 Confirmação da Partida", color=0x3498db)
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}")
        embed.add_field(name="Jogadores", value=" x ".join(j.mention for j in jogadores))
        embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum")

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

        if len(dados["confirmados"]) == 2:
            if not dados["taxa"]:
                dados["valor"] += 0.10
                dados["taxa"] = True

            await interaction.channel.edit(name=f"partida-{formatar_valor(dados['valor'])}")

            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="✅ PARTIDA CONFIRMADA", color=0x00ff99)
            embed.add_field(name="👥 Jogadores", value=" x ".join(j.mention for j in dados["jogadores"]), inline=False)
            embed.add_field(name="🧑‍⚖️ Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

            if pix:
                embed.add_field(name="💳 Chave Pix", value=pix["chave"], inline=False)
                embed.add_field(name="📛 Nome", value=pix["nome"], inline=False)
                embed.set_image(url=pix["qrcode"])

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not tem_permissao(ctx.author):
        return await ctx.send("❌ Sem permissão.")

    limite = validar_modo(modo)
    if not limite:
        return await ctx.send("Use: .fila 1v1 valor:5")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    filas[modo] = {"jogadores": []}

    embed = discord.Embed(title="🎮 Fila de Aposta", color=0x2ecc71)
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum")

    await ctx.send(embed=embed, view=FilaView(modo, valor, limite))

# ================= START =================
bot.run(TOKEN)
