import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= DADOS =================
config = {
    "canal_topico": None,
    "cargo_admin": None,
    "cargo_mediador": None
}

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

filas = {}  # modo -> [(user, tipo)]
fila_mediadores = []
pix_db = {}
partidas = {}

# ================= UTIL =================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_cargo(member, cargo_id):
    if member.guild_permissions.administrator:
        return True
    if not cargo_id:
        return False
    return any(r.id == cargo_id for r in member.roles)

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link QR Code")

    async def on_submit(self, interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction, button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction, button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou Pix.", ephemeral=True)

        embed = discord.Embed(title="💰 Seu Pix")
        embed.add_field(name="Nome", value=pix["nome"])
        embed.add_field(name="Chave", value=pix["chave"])
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Ver Pix dos mediadores", style=discord.ButtonStyle.gray)
    async def ver_mediadores(self, interaction, button):
        texto = ""
        for uid, pix in pix_db.items():
            membro = interaction.guild.get_member(uid)
            if membro and tem_cargo(membro, config["cargo_mediador"]):
                texto += f"{membro.mention} - {pix['chave']}\n"

        if not texto:
            texto = "Nenhum mediador com Pix."

        await interaction.response.send_message(texto, ephemeral=True)

@bot.command()
async def chavepix(ctx):
    await ctx.send("💳 Para colocar sua chave Pix aperta no botão em baixo:", view=PixView())

# ================= PAINEL CONFIG =================
class PainelView(View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.add_item(CargoSelect(guild, "Admin"))
        self.add_item(CargoSelect(guild, "Mediador"))

class CargoSelect(Select):
    def __init__(self, guild, tipo):
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in guild.roles]
        super().__init__(placeholder=f"Escolher cargo {tipo}", options=options)
        self.tipo = tipo

    async def callback(self, interaction):
        cid = int(self.values[0])
        if self.tipo == "Admin":
            config["cargo_admin"] = cid
        else:
            config["cargo_mediador"] = cid
        await interaction.response.send_message(f"✅ Cargo {self.tipo} configurado.", ephemeral=True)

@bot.command()
async def painel(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Sem permissão.")
    await ctx.send("⚙️ Painel WS APOSTAS", view=PainelView(ctx.guild))

# ================= CANAL =================
class CanalSelect(Select):
    def __init__(self, guild):
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in guild.text_channels]
        super().__init__(placeholder="Escolher canal dos tópicos", options=options)

    async def callback(self, interaction):
        config["canal_topico"] = int(self.values[0])
        await interaction.response.send_message("✅ Canal configurado.", ephemeral=True)

class CanalView(View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.add_item(CanalSelect(guild))

@bot.command()
async def canal(ctx):
    await ctx.send("📍 Escolha o canal onde os tópicos serão criados:", view=CanalView(ctx.guild))

# ================= FILA MEDIADOR =================
class MediadorView(View):
    async def atualizar(self, interaction):
        texto = "\n".join([f"{i+1}º - {m.mention}" for i, m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(title="🧑‍⚖️ Entre na fila mediadores pra ser chamado")
        embed.add_field(name="Ordem", value=texto)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction, button):
        if not tem_cargo(interaction.user, config["cargo_mediador"]):
            return await interaction.response.send_message("❌ Você não é mediador.", ephemeral=True)
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

@bot.command()
async def filamediador(ctx):
    embed = discord.Embed(title="🧑‍⚖️ Entre na fila mediadores pra ser chamado")
    embed.add_field(name="Ordem", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

# ================= FILA APOSTAS =================
class FilaView(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        filas[modo] = []

    async def atualizar(self, interaction):
        fila = filas[self.modo]
        texto = "\n".join([f"{u.mention} - {t}" for u,t in fila]) or "Nenhum jogador"
        embed = discord.Embed(title="WS APOSTAS", color=0x2b2d31)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}")
        embed.add_field(name="Jogadores", value=texto, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.secondary)
    async def normal(self, interaction, button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.secondary)
    async def infinito(self, interaction, button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, interaction, button):
        filas[self.modo] = [x for x in filas[self.modo] if x[0] != interaction.user]
        await self.atualizar(interaction)
        await interaction.response.defer()

    async def entrar(self, interaction, tipo):
        fila = filas[self.modo]
        if any(u == interaction.user for u,_ in fila):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        fila.append((interaction.user, tipo))
        await self.atualizar(interaction)

        iguais = [x for x in fila if x[1] == tipo]
        if len(iguais) == 2:
            await criar_topico(interaction.guild, iguais[0][0], iguais[1][0], tipo)

        await interaction.response.defer()

# ================= TOPICO =================
async def criar_topico(guild, j1, j2, tipo):
    canal = bot.get_channel(config["canal_topico"])
    if not canal:
        return

    filas.clear()

    mediador = fila_mediadores.pop(0) if fila_mediadores else None

    topico = await canal.create_thread(name="partida", type=discord.ChannelType.public_thread)

    partidas[topico.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "valor": 0,
        "mediador": mediador
    }

    embed = discord.Embed(title="⚔️ PARTIDA")
    embed.add_field(name="Modo", value=f"{tipo}")
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}")
    embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum")

    await topico.send(embed=embed, view=ConfirmacaoView())

# ================= CONFIRMA =================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction, button):
        dados = partidas.get(interaction.channel.id)
        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não está na partida.", ephemeral=True)

        dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            valor = 10
            await interaction.channel.edit(name=f"partida - {formatar_valor(valor)}")
            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="💰 PIX DO MEDIADOR")
            if pix:
                embed.add_field(name="Mediador", value=mediador.mention)
                embed.add_field(name="Nome", value=pix["nome"])
                embed.add_field(name="Chave Pix", value=pix["chave"])
                embed.set_image(url=pix["qrcode"])
            else:
                embed.description = "Mediador sem Pix cadastrado."

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recusar(self, interaction, button):
        await interaction.channel.send("❌ Partida recusada.")
        await interaction.response.defer()

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def regras(self, interaction, button):
        await interaction.response.send_message("📜 Digitem as regras no chat.", ephemeral=True)

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, *, valor_txt: str):
    if "valor:" not in valor_txt:
        return await ctx.send("Use: .fila 1v1 valor:10")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    embed = discord.Embed(title="WS APOSTAS", color=0x2b2d31)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(modo, valor))

bot.run(TOKEN)
