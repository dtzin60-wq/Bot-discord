import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

filas = {}
partidas = {}
pix_db = {}  # user_id: {"nome":..., "chave":..., "qr":...}

CANAIS_TOPICO = []
canal_index = 0

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

# ================= MODAL PIX =================
class PixModal(Modal, title="Cadastrar chave Pix"):
    nome = TextInput(label="Nome da conta")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("✅ Chave Pix cadastrada!", ephemeral=True)

# ================= VIEW PIX =================
class PixView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar sua chave Pix", style=discord.ButtonStyle.gray)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.gray)
    async def ver_minha(self, interaction: discord.Interaction, button: Button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou Pix.", ephemeral=True)

        await interaction.response.send_message(
            f"👤 Nome: {pix['nome']}\n💰 Chave: {pix['chave']}\n📷 QR: {pix['qr']}",
            ephemeral=True
        )

    @discord.ui.button(label="Ver chave Pix de outros mediadores", style=discord.ButtonStyle.red)
    async def ver_outros(self, interaction: discord.Interaction, button: Button):
        if not pix_db:
            return await interaction.response.send_message("❌ Nenhum Pix cadastrado.", ephemeral=True)

        texto = ""
        for uid, pix in pix_db.items():
            user = bot.get_user(uid)
            texto += f"{user} - {pix['chave']}\n"

        await interaction.response.send_message(texto, ephemeral=True)

# ================= MODAL REGRAS =================
class RegrasModal(Modal, title="Combinar regras"):
    regras = TextInput(label="Digite as regras", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(f"📜 **Regras combinadas:**\n{self.regras.value}")
        await interaction.response.defer()

# ================= VIEW TÓPICO =================
class TopicoView(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas[self.thread_id]

        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não é jogador.", ephemeral=True)

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)
            await interaction.channel.send(f"✅ {interaction.user.mention} confirmou.")

        if len(dados["confirmados"]) == 2:
            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id)

            if pix:
                embed = discord.Embed(title="💰 PAGAMENTO", color=0x2ecc71)
                embed.add_field(name="Mediador", value=mediador.mention, inline=False)
                embed.add_field(name="Nome da conta", value=pix["nome"], inline=False)
                embed.add_field(name="Chave Pix", value=pix["chave"], inline=False)
                embed.add_field(name="QR Code", value=pix["qr"], inline=False)
                await interaction.channel.send(embed=embed)

        await interaction.response.defer()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recusar(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send("❌ Partida recusada.")
        await interaction.response.defer()

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.blurple)
    async def combinar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RegrasModal())

# ================= VIEW FILA =================
class FilaView(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.modo = modo
        self.valor = valor

    async def atualizar(self, msg):
        fila = filas[self.chave]
        texto = "\n".join([f"{u.mention} - {m}" for u, m in fila]) or "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await msg.edit(embed=embed, view=self)

    async def entrar(self, interaction, escolha):
        fila = filas[self.chave]

        if any(u.id == interaction.user.id for u, _ in fila):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        fila.append((interaction.user, escolha))
        await self.atualizar(interaction.message)

        if len(fila) == 2:
            (j1, m1), (j2, m2) = fila
            if m1 == m2:
                await criar_topico(interaction.guild, j1, j2, m1, self.valor)
                filas[self.chave].clear()
                await self.atualizar(interaction.message)

        await interaction.response.defer()

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        filas[self.chave] = [x for x in filas[self.chave] if x[0].id != interaction.user.id]
        await self.atualizar(interaction.message)
        await interaction.response.defer()

# ================= CRIAR TÓPICO =================
async def criar_topico(guild, j1, j2, modo, valor):
    global canal_index
    canal = bot.get_channel(CANAIS_TOPICO[canal_index])
    canal_index = (canal_index + 1) % len(CANAIS_TOPICO)

    nome = f"partida - {formatar_valor(valor)}"
    thread = await canal.create_thread(name=nome)

    mediador = guild.me

    partidas[thread.id] = {
        "jogadores": [j1, j2],
        "confirmados": [],
        "valor": valor,
        "mediador": mediador
    }

    embed = discord.Embed(title="⚔️ PARTIDA", color=0x3498db)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)

    await thread.send(embed=embed, view=TopicoView(thread.id))

# ================= COMANDOS =================
@bot.command()
async def canal(ctx, *canais: discord.TextChannel):
    if len(canais) < 3:
        return await ctx.send("❌ Use no mínimo 3 canais.")
    global CANAIS_TOPICO
    CANAIS_TOPICO = [c.id for c in canais]
    await ctx.send("✅ Canais definidos para criar tópicos!")

@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    chave = f"{modo}_{valor}"
    filas[chave] = []

    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(chave, modo, valor))

@bot.command()
async def pix(ctx):
    embed = discord.Embed(title="💰 CHAVE PIX", description="Cadastre sua chave Pix abaixo")
    await ctx.send(embed=embed, view=PixView())

# ================= START =================
bot.run(TOKEN)
