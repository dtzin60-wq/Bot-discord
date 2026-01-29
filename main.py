import discord
from discord.ext import commands
import asyncio
import os

# Configurações de Intenções
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

# Variável global simulando o mediador da imagem
mediador_exemplo = "@ADM CAPONE"

# --- VIEW DO TÓPICO (Aparece após clicar em Gel Normal/Infinito) ---
class PainelPartida(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Lógica da imagem
        embed = discord.Embed(
            title="✅ | Partida Confirmada",
            description=f"{interaction.user.mention} confirmou a aposta!\n\u21aa O outro jogador precisa confirmar para continuar.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Aposta recusada. O tópico será deletado...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary)
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=discord.Color.blue())
        embed.description = "• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra não existir no regulamento, tire print do acordo."
        await interaction.response.send_message(embed=embed, ephemeral=False)

# --- VIEW DA FILA PRINCIPAL (.fila) ---
class FilaControl(discord.ui.View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor

    async def iniciar_topico(self, interaction, gel_tipo):
        thread = await interaction.channel.create_thread(
            name=f"Aposta-{self.valor}-{interaction.user.name}",
            type=discord.ChannelType.public_thread
        )
        
        # Embed baseada na imagem
        embed = discord.Embed(title="Partida Confirmada", color=0x2b2d31)
        embed.add_field(name="🎮 Estilo de Jogo", value=f"{self.modo} | Gel {gel_tipo}", inline=False)
        embed.add_field(name="💰 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
        embed.add_field(name="👤 Mediador", value=mediador_exemplo, inline=False)
        embed.add_field(name="👥 Jogadores", value=f"{interaction.user.mention}\n@Aguardando...", inline=False)
        
        await thread.send(embed=embed, view=PainelPartida())
        await interaction.response.send_message(f"✅ Tópico criado: {thread.mention}", ephemeral=True)

    @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
    async def normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_topico(interaction, "Normal")

    @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
    async def infinito(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.iniciar_topico(interaction, "Infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Você saiu da fila.", ephemeral=True)

# --- COMANDOS ---

@bot.command()
async def fila(ctx, modo="1v1", valor="0,00", plataforma="MOBILE"):
    # Estilo da imagem
    embed = discord.Embed(title=f"{modo} | SPACE APOSTAS 5K", color=discord.Color.blue())
    embed.add_field(name="👑 Modo", value=f"{modo} {plataforma.upper()}", inline=False)
    embed.add_field(name="💎 Valor", value=f"R$ {valor}", inline=False)
    embed.add_field(name="⚡ Jogadores", value="Nenhum jogador na fila", inline=False)
    embed.set_image(url="https://i.imgur.com/8NnO8Z1.png") # Coloque o link da sua imagem aqui
    
    await ctx.send(embed=embed, view=FilaControl(modo, valor))

@bot.command()
async def mediar(ctx):
    # Estilo da imagem
    embed = discord.Embed(title="Painel da fila controladora", description="Entre na fila para mediar", color=0x4b0082)
    embed.add_field(name="Mediadores:", value=f"• {mediador_exemplo}")
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢"))
    view.add_item(discord.ui.Button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴"))
    view.add_item(discord.ui.Button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️"))
    view.add_item(discord.ui.Button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️"))
    
    await ctx.send(embed=embed, view=view)

@bot.command()
async def pix(ctx):
    # Estilo da imagem
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", color=0x2f3136)
    embed.description = "Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo."
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠"))
    view.add_item(discord.ui.Button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍"))
    view.add_item(discord.ui.Button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="🔍"))
    
    await ctx.send(embed=embed, view=view)

@bot.command()
async def aux(ctx):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Dar Vitória", style=discord.ButtonStyle.success))
    view.add_item(discord.ui.Button(label="Vitória por W.O", style=discord.ButtonStyle.primary))
    
    btn_fechar = discord.ui.Button(label="Finalizar Aposta", style=discord.ButtonStyle.danger)
    async def fechar_callback(interaction):
        if isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Tópico finalizado!")
            await asyncio.sleep(2)
            await interaction.channel.delete()
    btn_fechar.callback = fechar_callback
    view.add_item(btn_fechar)
    
    await ctx.send("🛠️ **Painel Auxiliar de Partida**", view=view)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

# Railway usa a variável TOKEN
bot.run(os.getenv("TOKEN"))
                              
