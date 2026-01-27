
import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

filas = {}
fila_mediadores = []
pix_db = {}

@bot.event
async def on_ready():
print(f"Bot ligado como {bot.user}")

================= BOTCONFIG =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx, modo: str):
filas[modo] = []

embed = discord.Embed(  
    title=f"Fila {modo}",  
    description="Clique para entrar ou sair da fila",  
    color=0x00ff00  
)  

view = FilaView(modo)  
await ctx.send(embed=embed, view=view)

class FilaView(View):
def init(self, modo):
super().init(timeout=None)
self.modo = modo

@discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)  
async def entrar(self, interaction: discord.Interaction, button: Button):  
    user = interaction.user  
    if user not in filas[self.modo]:  
        filas[self.modo].append(user)  

    await interaction.response.send_message(  
        f"Você entrou na fila {self.modo}. Jogadores: {len(filas[self.modo])}", ephemeral=True  
    )  

    limite = int(self.modo[0]) * 2  # 1v1=2, 2v2=4 etc  

    if len(filas[self.modo]) >= limite:  
        guild = interaction.guild  
        channel = await guild.create_text_channel(f"partida-{self.modo}")  

        mencoes = " ".join([u.mention for u in filas[self.modo]])  
        await channel.send(f"🎮 Partida criada!\n{mencoes}")  

        filas[self.modo].clear()  

@discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)  
async def sair(self, interaction: discord.Interaction, button: Button):  
    user = interaction.user  
    if user in filas[self.modo]:  
        filas[self.modo].remove(user)  
    await interaction.response.send_message("Você saiu da fila.", ephemeral=True)

================= MEDIADOR =================

@bot.command()
async def mediador(ctx):
embed = discord.Embed(title="Fila de Mediadores", color=0xffcc00)
view = MediadorView()
await ctx.send(embed=embed, view=view)

class MediadorView(View):
@discord.ui.button(label="Entrar na fila de mediador", style=discord.ButtonStyle.green)
async def entrar(self, interaction: discord.Interaction, button: Button):
user = interaction.user
if user not in fila_mediadores:
fila_mediadores.append(user)
await interaction.response.send_message(
f"Você entrou na fila de mediadores.\nFila: {', '.join([u.name for u in fila_mediadores])}",
ephemeral=True
)

================= PIX =================

@bot.command()
async def pix(ctx):
embed = discord.Embed(title="Painel Pix", color=0x00ffff)
view = PixView()
await ctx.send(embed=embed, view=view)

class PixView(View):
@discord.ui.button(label="Cadastrar chave Pix", style=discord.ButtonStyle.green)
async def cadastrar(self, interaction: discord.Interaction, button: Button):
await interaction.response.send_modal(PixModal())

@discord.ui.button(label="Ver minha chave Pix", style=discord.ButtonStyle.blurple)  
async def ver(self, interaction: discord.Interaction, button: Button):  
    user = interaction.user  
    if user.id in pix_db:  
        data = pix_db[user.id]  
        await interaction.response.send_message(  
            f"Nome: {data['nome']}\nChave: {data['chave']}\nQR Code: {data['qr']}",  
            ephemeral=True  
        )  
    else:  
        await interaction.response.send_message("Você não cadastrou Pix.", ephemeral=True)  

@discord.ui.button(label="Ver Pix dos mediadores", style=discord.ButtonStyle.gray)  
async def mediadores(self, interaction: discord.Interaction, button: Button):  
    texto = ""  
    for u in fila_mediadores:  
        if u.id in pix_db:  
            texto += f"{u.name}: {pix_db[u.id]['chave']}\n"  
    if texto == "":  
        texto = "Nenhum mediador com Pix cadastrado."  
    await interaction.response.send_message(texto, ephemeral=True)

class PixModal(Modal, title="Cadastrar Pix"):
nome = TextInput(label="Nome completo do titular")
chave = TextInput(label="Chave Pix")
qr = TextInput(label="Código QR Code")

async def on_submit(self, interaction: discord.Interaction):  
    pix_db[interaction.user.id] = {  
        "nome": self.nome.value,  
        "chave": self.chave.value,  
        "qr": self.qr.value  
    }  
    await interaction.response.send_message("Pix cadastrado com sucesso!", ephemeral=True)

================= TOKEN =================

bot.run("MTQ2NTU3OTE4MTIwMjA3OTc3NQ.GkUd5s.sQxmHAMPMR6uKKy_ZBismCyER27riZ-5RusbFg")
