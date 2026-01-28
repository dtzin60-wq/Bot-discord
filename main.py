import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

TOKEN = "SEU_TOKEN_AQUI"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

filas = {}
pix_db = {}
partidas = {}
CANAIS_TOPICO = []
canal_index = 0

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

class PixView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

# ================= TÓPICO =================
class TopicoView(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas[self.thread_id]

        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não é da partida.", ephemeral=True)

        if interaction.user in dados["confirmados"]:
            return await interaction.response.send_message("Você já confirmou.", ephemeral=True)

        dados["confirmados"].append(interaction.user)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!")

        if len(dados["confirmados"]) == 2:
            j1, j2 = dados["jogadores"]
            pix1 = pix_db.get(j1.id)
            pix2 = pix_db.get(j2.id)

            embed = discord.Embed(title="💰 PAGAMENTO", color=0x2ecc71)

            if pix1:
                embed.add_field(name=j1.name, value=f"{pix1['nome']}\n{pix1['chave']}\n{pix1['qr']}", inline=False)
            else:
                embed.add_field(name=j1.name, value="❌ Sem Pix", inline=False)

            if pix2:
                embed.add_field(name=j2.name, value=f"{pix2['nome']}\n{pix2['chave']}\n{pix2['qr']}", inline=False)
            else:
                embed.add_field(name=j2.name, value="❌ Sem Pix", inline=False)

            await interaction.channel.send(embed=embed)

# ================= FILA =================
class FilaView(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.modo = modo
        self.valor = valor

    def ordenar_fila(self):
        # prioridade: gelo infinito em cima
        prioridade = {"gelo infinito": 0, "gelo normal": 1}
        filas[self.chave].sort(key=lambda x: prioridade.get(x[1], 2))

    async def atualizar(self, interaction):
        self.ordenar_fila()
        fila = filas[self.chave]
        texto = "\n".join([f"{u.mention} - {m}" for u, m in fila]) or "Nenhum"

        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {self.valor:.2f}".replace(".", ","), inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)

        await interaction.response.edit_message(embed=embed, view=self)

    async def entrar(self, interaction, modo_escolhido):
        fila = filas[self.chave]

        if any(u.id == interaction.user.id for u, _ in fila):
            return await interaction.response.send_message("Você já está na fila.", ephemeral=True)

        fila.append((interaction.user, modo_escolhido))

        if len(fila) == 2:
            (j1, m1), (j2, m2) = fila

            # só cria se os dois escolherem o mesmo modo
            if m1 == m2:
                await criar_topico(interaction.guild, j1, j2, m1, self.valor)
                filas[self.chave] = []
                return await self.atualizar(interaction)

        await self.atualizar(interaction)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        filas[self.chave] = [x for x in filas[self.chave] if x[0].id != interaction.user.id]
        await self.atualizar(interaction)

# ================= CRIAR TÓPICO =================
async def criar_topico(guild, j1, j2, modo, valor):
    global canal_index
    canal = bot.get_channel(CANAIS_TOPICO[canal_index])
    canal_index = (canal_index + 1) % len(CANAIS_TOPICO)

    thread = await canal.create_thread(name=f"partida-{valor}")

    partidas[thread.id] = {
        "jogadores": [j1, j2],
        "confirmados": []
    }

    embed = discord.Embed(title="⚔️ PARTIDA", color=0x3498db)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {valor:.2f}".replace(".", ","), inline=False)
    embed.add_field(name="Jogadores", value=f"{j1.mention} x {j2.mention}", inline=False)

    await thread.send(embed=embed, view=TopicoView(thread.id))

# ================= COMANDOS =================
@bot.command()
async def canal(ctx, *canais: discord.TextChannel):
    global CANAIS_TOPICO
    CANAIS_TOPICO = [c.id for c in canais]
    await ctx.send("✅ Canais configurados!")

@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    valor = float(valor_txt.replace("valor:", "").replace(",", "."))
    chave = f"{modo}_{valor}"
    filas[chave] = []

    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {valor:.2f}".replace(".", ","), inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(chave, modo, valor))

@bot.command()
async def pix(ctx):
    await ctx.send("Cadastre seu Pix:", view=PixView())

# ================= START =================
bot.run(TOKEN)
