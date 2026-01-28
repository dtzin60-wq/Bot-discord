import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents)

# ===== CONFIG =====
config = {
    "cargo_analista": None,
    "cargo_mediador": None,
    "canal_topico": None
}

pix_db = {}
fila_mediadores = []
filas = {}
partidas = {}

# ===== UTIL =====
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
    qrcode = TextInput(label="Link do QR Code")

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qrcode": self.qrcode.value
        }
        await interaction.response.send_message("✅ Pix salvo!", ephemeral=True)

class PixView(View):
    @discord.ui.button(label="Adicionar Pix", style=discord.ButtonStyle.green)
    async def add(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

    @discord.ui.button(label="Ver meu Pix", style=discord.ButtonStyle.blurple)
    async def ver(self, interaction: discord.Interaction, button: Button):
        pix = pix_db.get(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você não cadastrou Pix.", ephemeral=True)

        embed = discord.Embed(title="💰 Seu Pix", color=0x00ff00)
        embed.add_field(name="Nome", value=pix["nome"], inline=False)
        embed.add_field(name="Chave", value=pix["chave"], inline=False)
        embed.set_image(url=pix["qrcode"])
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command()
async def chavepix(ctx):
    await ctx.send("💳 Painel Pix", view=PixView())

# ================= PAINEL CONFIG =================
class PainelView(View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.add_item(CargoSelect(guild, "Analista"))
        self.add_item(CargoSelect(guild, "Mediador"))
        self.add_item(CanalSelect(guild))

class CargoSelect(Select):
    def __init__(self, guild, tipo):
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in guild.roles]
        super().__init__(placeholder=f"Escolher cargo {tipo}", options=options)
        self.tipo = tipo

    async def callback(self, interaction: discord.Interaction):
        cid = int(self.values[0])
        if self.tipo == "Analista":
            config["cargo_analista"] = cid
        else:
            config["cargo_mediador"] = cid
        await interaction.response.send_message(f"✅ Cargo {self.tipo} configurado.", ephemeral=True)

class CanalSelect(Select):
    def __init__(self, guild):
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in guild.text_channels]
        super().__init__(placeholder="Escolher canal do tópico", options=options, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        config["canal_topico"] = int(self.values[0])
        await interaction.response.send_message("✅ Canal configurado.", ephemeral=True)

@bot.command()
async def painel(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Só administrador.")
    await ctx.send("⚙️ Configuração", view=PainelView(ctx.guild))

# ================= FILA MEDIADOR =================
class MediadorView(View):
    async def atualizar(self, interaction):
        texto = "\n".join([f"{i+1}º - {m.mention}" for i,m in enumerate(fila_mediadores)]) or "Nenhum"
        embed = discord.Embed(title="🧑‍⚖️ Fila Mediador", color=0xffaa00)
        embed.add_field(name="Ordem", value=texto)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if not tem_cargo(interaction.user, config["cargo_mediador"]):
            return await interaction.response.send_message("❌ Você não é mediador.", ephemeral=True)
        if interaction.user not in fila_mediadores:
            fila_mediadores.append(interaction.user)
        await self.atualizar(interaction)
        await interaction.response.defer()

@bot.command()
async def filamediador(ctx):
    embed = discord.Embed(title="🧑‍⚖️ Fila Mediador", color=0xffaa00)
    embed.add_field(name="Ordem", value="Nenhum")
    await ctx.send(embed=embed, view=MediadorView())

# ================= FILA APOSTA =================
class FilaView(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.limite = 2

    async def atualizar(self, interaction):
        fila = filas[self.modo]
        if fila:
            texto = "\n".join([f"{u.mention} — {tipo}" for u, tipo in fila.items()])
        else:
            texto = "Nenhum"

        embed = discord.Embed(title="🎮 ws apostas", color=0x00ff99)
        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=texto, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="🧊 Gelo normal", style=discord.ButtonStyle.blurple)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "Gelo normal")

    @discord.ui.button(label="❄️ Gelo infinito", style=discord.ButtonStyle.green)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "Gelo infinito")

    @discord.ui.button(label="❌ Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        fila = filas[self.modo]
        fila.pop(interaction.user, None)
        await self.atualizar(interaction)
        await interaction.response.defer()

    async def entrar(self, interaction, tipo):
        fila = filas[self.modo]

        if interaction.user in fila:
            return await interaction.response.send_message("Você já escolheu.", ephemeral=True)

        if len(fila) >= self.limite:
            return await interaction.response.send_message("Fila cheia.", ephemeral=True)

        fila[interaction.user] = tipo
        await self.atualizar(interaction)

        if len(fila) == 2:
            await self.criar_topico()

        await interaction.response.defer()

    async def criar_topico(self):
        canal = bot.get_channel(config["canal_topico"])
        if not canal:
            return

        jogadores = list(filas[self.modo].items())
        filas[self.modo].clear()

        mediador = fila_mediadores.pop(0) if fila_mediadores else None

        topico = await canal.create_thread(
            name=f"partida-{formatar_valor(self.valor)}",
            type=discord.ChannelType.public_thread
        )

        partidas[topico.id] = {
            "jogadores": jogadores,
            "valor": self.valor,
            "modo": self.modo,
            "mediador": mediador,
            "confirmados": []
        }

        embed = discord.Embed(
            title="⚔️ PARTIDA CRIADA",
            description="Jogadores acalmem, conversem e cliquem em confirmar!",
            color=0x3498db
        )

        jogadores_txt = "\n".join([f"{u.mention} — {tipo}" for u, tipo in jogadores])

        embed.add_field(name="Modo", value=self.modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)
        embed.add_field(name="Jogadores", value=jogadores_txt, inline=False)
        embed.add_field(name="Mediador", value=mediador.mention if mediador else "Nenhum", inline=False)

        await topico.send(embed=embed, view=ConfirmacaoView())

# ================= CONFIRMA =================
class RegrasModal(Modal, title="Combinar Regras"):
    regras = TextInput(label="Digite as regras", style=discord.TextStyle.long)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.send(f"📜 Regras combinadas:\n{self.regras.value}")
        await interaction.response.defer()

class ConfirmacaoView(View):
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(interaction.channel.id)
        if not dados:
            return

        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)

        if len(dados["confirmados"]) == 2:
            mediador = dados["mediador"]
            pix = pix_db.get(mediador.id) if mediador else None

            embed = discord.Embed(title="💰 PIX DO MEDIADOR", color=0x00ff00)
            if pix:
                embed.add_field(name="Nome", value=pix["nome"], inline=False)
                embed.add_field(name="Chave Pix", value=pix["chave"], inline=False)
                embed.set_image(url=pix["qrcode"])
            else:
                embed.description = "Mediador não cadastrou Pix."

            await interaction.channel.send(embed=embed)

        await interaction.response.defer()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def recusar(self, interaction: discord.Interaction, button: Button):
        await interaction.channel.send(f"❌ {interaction.user.mention} recusou a partida.")
        await interaction.response.defer()

    @discord.ui.button(label="Combinar regras", style=discord.ButtonStyle.gray)
    async def regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(RegrasModal())

# ================= COMANDO FILA =================
@bot.command()
async def fila(ctx, modo: str, valor_txt: str):
    if not tem_cargo(ctx.author, config["cargo_analista"]):
        return await ctx.send("❌ Sem permissão.")

    valor = float(valor_txt.replace("valor:", "").replace(",", "."))

    filas[modo] = {}

    embed = discord.Embed(title="🎮 ws apostas", color=0x00ff99)
    embed.add_field(name="Modo", value=modo, inline=False)
    embed.add_field(name="Valor", value=f"R$ {formatar_valor(valor)}", inline=False)
    embed.add_field(name="Jogadores", value="Nenhum", inline=False)

    await ctx.send(embed=embed, view=FilaView(modo, valor))

# ================= START =================
bot.run(TOKEN)
