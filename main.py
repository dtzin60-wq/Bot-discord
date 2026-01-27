import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

intents = discord.Intents.default()
intents.message_toggle = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

CARGO_PERMITIDO = "Xoxota"
CARGO_MEDIADOR = "Mediador"

fila_jogadores = []
fila_mediadores = []
pix_mediadores = {}

painel_fila_msg = None
painel_mediador_msg = None

def tem_cargo(user, nome):
    return discord.utils.get(user.roles, name=nome)

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome do titular")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_mediadores[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value
        }
        await interaction.response.send_message("✅ Pix cadastrado!", ephemeral=True)

# ================= FILA JOGADORES =================
class FilaView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in fila_jogadores:
            fila_jogadores.append(interaction.user)
        await atualizar_fila(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_jogadores:
            fila_jogadores.remove(interaction.user)
        await atualizar_fila(interaction)

# ================= FILA MEDIADORES =================
class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user, CARGO_MEDIADOR):
            await interaction.response.send_message("❌ Você não é mediador", ephemeral=True)
            return
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await atualizar_mediador(interaction)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in fila_mediadores:
            fila_mediadores.remove(interaction.user)
        await atualizar_mediador(interaction)

# ================= ATUALIZAR =================
async def atualizar_fila(interaction):
    global painel_fila_msg

    embed = discord.Embed(title="Aguardando Jogadores", color=0x2ecc71)
    jogadores = "\n".join([j.mention for j in fila_jogadores]) or "Nenhum"
    embed.add_field(name="Jogadores", value=jogadores)

    if painel_fila_msg:
        await painel_fila_msg.edit(embed=embed, view=FilaView())
    else:
        painel_fila_msg = await interaction.channel.send(embed=embed, view=FilaView())

    if len(fila_jogadores) >= 2 and len(fila_mediadores) >= 1:
        await criar_partida(interaction.guild)

async def atualizar_mediador(interaction):
    global painel_mediador_msg

    embed = discord.Embed(title="Fila de Mediadores", color=0xf1c40f)
    mediadores = "\n".join([m.mention for m in fila_mediadores]) or "Nenhum"
    embed.add_field(name="Mediadores", value=mediadores)

    if painel_mediador_msg:
        await painel_mediador_msg.edit(embed=embed, view=MediadorView())
    else:
        painel_mediador_msg = await interaction.channel.send(embed=embed, view=MediadorView())

# ================= PARTIDA =================
async def criar_partida(guild):
    jogadores = fila_jogadores[:2]
    mediador = fila_mediadores[0]

    fila_jogadores.clear()
    fila_mediadores.pop(0)

    categoria = discord.utils.get(guild.categories, name="PARTIDAS")
    if not categoria:
        categoria = await guild.create_category("PARTIDAS")

    canal = await guild.create_text_channel(f"partida-{jogadores[0].name}-vs-{jogadores[1].name}", category=categoria)

    embed = discord.Embed(title="Partida Confirmada", color=0x3498db)
    embed.add_field(name="Jogadores", value=f"{jogadores[0].mention}\n{jogadores[1].mention}")
    embed.add_field(name="Mediador", value=mediador.mention)

    await canal.send(embed=embed, view=ConfirmarView(jogadores, mediador))

# ================= CONFIRMAR =================
class ConfirmarView(View):
    def __init__(self, jogadores, mediador):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.mediador = mediador
        self.confirmados = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.jogadores:
            await interaction.response.send_message("❌ Você não é jogador", ephemeral=True)
            return

        if interaction.user not in self.confirmados:
            self.confirmados.append(interaction.user)

        await interaction.channel.purge(limit=10)

        embed = discord.Embed(title="Confirmações", color=0x2ecc71)
        embed.add_field(name="Confirmados", value="\n".join([u.mention for u in self.confirmados]))

        if len(self.confirmados) == 2:
            pix = pix_mediadores.get(self.mediador.id)
            if pix:
                embed.add_field(
                    name="Pix do Mediador",
                    value=f"Nome: {pix['nome']}\nChave: {pix['chave']}\nQR: {pix['qr']}"
                )

        await interaction.channel.send(embed=embed, view=self)

# ================= COMANDOS =================
@bot.command()
async def fila(ctx):
    global painel_fila_msg
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return

    embed = discord.Embed(title="Aguardando Jogadores", color=0x2ecc71)
    embed.add_field(name="Jogadores", value="Nenhum")
    painel_fila_msg = await ctx.send(embed=embed, view=FilaView())

@bot.command()
async def filamediador(ctx):
    global painel_mediador_msg
    if not tem_cargo(ctx.author, CARGO_PERMITIDO):
        return

    embed = discord.Embed(title="Fila de Mediadores", color=0xf1c40f)
    embed.add_field(name="Mediadores", value="Nenhum")
    painel_mediador_msg = await ctx.send(embed=embed, view=MediadorView())

@bot.command()
async def pix(ctx):
    if not tem_cargo(ctx.author, CARGO_MEDIADOR):
        return
    await ctx.send_modal(PixModal())

# ================= TOKEN =================
bot.run("SEU_TOKEN_AQUI")
