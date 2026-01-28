import discord
from discord.ext import commands
from discord.ui import View, Button
import os

TOKEN = "SEU_TOKEN_AQUI"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

filas = {}

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg?ex=697aef4c&is=69799dcc&hm=b523772cd5b4467e3fedbab7f725c3a84a8c59fb63cfb99cd81747face0c5ccd&"

def formatar_valor(v):
    return f"{v:.2f}".replace(".", ",")

class FilaView(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = []
        self.confirmados = []

    async def atualizar_embed(self, interaction):
        embed = discord.Embed(title=f"{self.modo} SPACE APOSTAS", color=0x2b2d31)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="👑 Modo", value=self.modo, inline=False)
        embed.add_field(name="💰 Valor", value=f"R$ {formatar_valor(self.valor)}", inline=False)

        if self.jogadores:
            nomes = "\n".join([j.mention for j in self.jogadores])
        else:
            nomes = "Nenhum jogador na fila"

        embed.add_field(name="⚡ Jogadores", value=nomes, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    @Button(label="Gel Normal", style=discord.ButtonStyle.secondary)
    async def gel_normal(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.jogadores:
            self.jogadores.append(interaction.user)
            await self.atualizar_embed(interaction)
            await interaction.response.send_message("Você entrou na fila (Gel Normal).", ephemeral=True)
        else:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)

    @Button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
    async def gel_infinito(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.jogadores:
            self.jogadores.append(interaction.user)
            await self.atualizar_embed(interaction)
            await interaction.response.send_message("Você entrou na fila (Gel Infinito).", ephemeral=True)
        else:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)

    @Button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user not in self.jogadores:
            await interaction.response.send_message("Entre na fila primeiro.", ephemeral=True)
            return

        if interaction.user not in self.confirmados:
            self.confirmados.append(interaction.user)

        if len(self.confirmados) == 2:
            canal = interaction.channel
            await canal.edit(topic=f"partida - {formatar_valor(self.valor)}")
            await interaction.response.send_message("Partida confirmada! 🎮", ephemeral=False)
        else:
            await interaction.response.send_message("Confirmação registrada. Aguardando outro jogador.", ephemeral=True)

    @Button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user in self.jogadores:
            self.jogadores.remove(interaction.user)
            if interaction.user in self.confirmados:
                self.confirmados.remove(interaction.user)
            await self.atualizar_embed(interaction)
            await interaction.response.send_message("Você saiu da fila.", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)

@bot.command()
async def fila(ctx, modo: str, *, valor: str):
    if "valor:" not in valor:
        await ctx.send("Use assim: `.fila 1v1 valor:10`")
        return

    try:
        valor_num = float(valor.replace("valor:", "").replace(",", "."))
    except:
        await ctx.send("Valor inválido.")
        return

    embed = discord.Embed(title=f"{modo} SPACE APOSTAS", color=0x2b2d31)
    embed.set_image(url=BANNER_URL)
    embed.add_field(name="👑 Modo", value=modo, inline=False)
    embed.add_field(name="💰 Valor", value=f"R$ {formatar_valor(valor_num)}", inline=False)
    embed.add_field(name="⚡ Jogadores", value="Nenhum jogador na fila", inline=False)

    view = FilaView(modo, valor_num)
    await ctx.send(embed=embed, view=view)

bot.run(TOKEN)
