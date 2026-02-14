import discord
import os
from discord.ext import commands

# Configuração para pegar o Token das "Variáveis" da Railway
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True # Importante ativar isso no Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", description="Clique aqui caso precise de algum suporte", emoji="🛠️"),
            discord.SelectOption(label="Reembolso", description="Clique aqui caso deseja fazer um reembolso", emoji="💰"),
            discord.SelectOption(label="Receber Evento", description="Clique aqui caso queira receber algum evento", emoji="💫"),
            discord.SelectOption(label="Vagas de Mediador", description="Clique aqui para vagas na ORG", emoji="👑"),
        ]
        super().__init__(placeholder="Selecione uma função", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        
        # Lógica de criação do canal
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="TICKETS")
        
        if not category:
            category = await guild.create_category("TICKETS")

        # Verifica se o usuário já tem ticket aberto (opcional, mas recomendado)
        channel_name = f"{escolha.lower()}-{interaction.user.name}".replace(" ", "-").lower()
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        
        if existing_channel:
            await interaction.response.send_message(f"Você já possui um ticket aberto em: {existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )
        
        await interaction.response.send_message(f"Você selecionou **{escolha}**. Criando seu canal...", ephemeral=True)
        await ticket_channel.send(f"{interaction.user.mention} criou um ticket de **{escolha}**. Aguarde a equipe.")

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

@bot.event
async def on_ready():
    print(f'Bot logado como {bot.user} - Pronto para criar tickets!')

@bot.command()
async def setup(ctx):
    embed = discord.Embed(
        title="SPACE TICKET",
        description="👉 Abra ticket com o que você precisa abaixo com as informações de guia.",
        color=discord.Color.from_rgb(20, 20, 20) # Cor escura estilo Space
    )
    # Coloque a URL da sua imagem aqui
    embed.set_image(url="LINK_DA_SUA_IMAGEM_AQUI")
    
    await ctx.send(embed=embed, view=TicketView())

if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: A variável DISCORD_TOKEN não foi encontrada.")
        
