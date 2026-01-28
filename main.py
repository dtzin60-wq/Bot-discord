import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ================== CONFIG ==================
config = {
    "canal_topico": None,
    "cargo_admin": None,
    "cargo_mediador": None,
    "banner": "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
}

filas = {}  # {"1v1": [(user, tipo)]}
fila_mediadores = []
partidas = {}
pix_db = {}

# ================== UTIL ==================
def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

def tem_cargo(member, cargo):
    if member.guild_permissions.administrator:
        return True
    if not cargo:
        return False
    return any(r.id == cargo for r in member.roles)

# ================== PIX ==================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome da chave")
    chave = TextInput(label="Chave Pix")
    qrcode = TextInput(label="Link QR Code")

    async def on_submit(self, interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix salvo!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction, button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction, button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou.", ephemeral=True)
        embed = discord.Embed(title="💰 Seu Pix")
        embed.add_field(name="Nome", value=pix["nome"])
        embed.add_field(name="Chave", value=pix["chave"])
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Ver Pix mediadores", style=discord.ButtonStyle.gray)
    async def ver_med(self, interaction, button):
        texto = ""
        for uid, pix in pix_db.items():
            texto += f"<@{uid}> → {pix['chave']}\n"
        if not texto:
            texto = "Nenhum mediador cadastrou."
        await interaction.response.send_message(texto, ephemeral=True)

@bot.command()
async def chavepix(ctx):
    await ctx.send("💳 Para colocar sua chave Pix aperte no botão abaixo", view=PixView())

# ================== MEDIADOR ==================
class MediadorView(View):
    async def atualizar(self, msg):
        texto = "\n".join([f"{i+1}º - {m.mention}" for i, m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(title="🧑‍⚖️ Entre na fila mediadores pra ser chamado")
        embed.add_field(name="Fila", value=texto)
        await msg.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
    async def entrar(self, interaction, button):
        if not tem_cargo(interaction.user, config["cargo_mediador"]):
            return await interaction.response.send_message("❌ Você não é mediador.", ephemeral=True)
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await self.atualizar(interaction.message)
        await interaction.response.defer()

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction, button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await self.atualizar(interaction.message)
        await interaction.response.defer()

@bot.command()
async def filamediador(ctx):
    embed = discord.Embed(title="🧑‍⚖️ Entre na fila mediadores pra ser chamado")
    embed.add_field(name="Fila", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

# ================== CONFIRMA ==================
class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction, button):
        dados = partidas.get(interaction.channel.id)
        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não é da partida.", ephemeral=True)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            await interaction.channel.edit(name=f"partida-{formatar_valor(dados['valor'])}")
            med = dados["mediador"]
            pix = pix_db.get(med.id) if med else None

            embed = discord.Embed(title="💰 PIX DO MEDIADOR")
            embed.add_field(name="Mediador", value=med.mention if med else "Nenhum")
            if pix:
                embed.add_field(name="Nome", value=pix["nome"])
                embed.add_field(name="Chave Pix", value=pix["chave"])
                embed.set_image(url=pix["qrcode"])
            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

# ================== FILA ==================
class FilaView(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        if modo not in filas:
            filas[modo] = []

    async def atualizar(self, msg):
        fila = filas[self.modo]
        texto = "\n".join([f"{u.mention} - {t}" for u, t in fila]) or "Nenhum"
        embed = discord.Embed(title="WS APOSTAS")
        embed.set_image(url=config["banner"])
        embed.add_field(name="Modo", value=self.modo)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}")
        embed.add_field(name="Jogadores", value=texto, inline=False)
        await msg.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.secondary)
    async def normal(self, interaction, button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.secondary)
    async def infinito(self, interaction, button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, interaction, button):
        filas[self.modo] = [x for x in filas[self.modo] if x[0] != interaction.user]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

    async def entrar(self, interaction, tipo):
        fila = filas[self.modo]
        if any(u == interaction.user for u, _ in fila):
            return await interaction.response.send_message("Já está na fila.", ephemeral=True)

        fila.append((interaction.user, tipo))
        await self.atualizar(interaction.message)

        iguais = [x for x in fila if x[1] == tipo]
        if len(iguais) >= 2:
            j1, j2 = iguais[0][0], iguais[1][0]
            filas[self.modo] = [x for x in fila if x[0] not in (j1, j2)]
            await criar_topico(interaction.guild, j1, j2, tipo, self.valor)

        await interaction.response.defer()

# ================== TOPICO ==================
async def criar_topico(guild, j1, j2, tipo, valor):
    canal = bot.get_channel(config["canal_topico"])
    if not canal:
        return
    mediador = fila_mediadores.pop(0) if fila_mediadores else None

    topico = await canal.create_thread(name="partida", type=discord.ChannelType.public_thread)
    partidas[topico.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "valor": valor,
        "mediador": mediador
    }

    embed = discord.Embed(title="⚔️ PARTIDA")
    embed.add_field(name="Modo", value=f"{tipo}")
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}")
    embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum")

    await topico.send(embed=embed, view=ConfirmacaoView())

# ================== COMANDOS ==================
@bot.command()
async def canal(ctx):
    config["canal_topico"] = ctx.channel.id
    await ctx.send("✅ Canal configurado para criar tópicos.")

@bot.command()
async def painel(ctx):
    await ctx.send("⚙️ Painel em construção (banner, cargos e configs)")

@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    embed = discord.Embed(title="WS APOSTAS")
    embed.set_image(url=config["banner"])
    embed.add_field(name="Modo", value=modo)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}")
    embed.add_field(name="Jogadores", value="Nenhum")
    await ctx.send(embed=embed, view=FilaView(modo, valor))

bot.run(TOKEN)
