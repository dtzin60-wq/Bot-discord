import discord
from discord import app_commands
from discord.ext import commands

# Configuração dos Intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Armazenamento simples das configurações (em memória)
config = {
    "embed_image": "https://link_da_imagem_1.png",
    "final_logo": "https://link_da_logo_4.png"
}

# 1. Interface de Abertura (Botão)
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Intermédio", style=discord.ButtonStyle.danger, custom_id="btn_abrir")
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Mensagem Ephemeral (só o usuário vê - Referência 1000038019.jpg)
        await interaction.response.send_message(f"✅ | {interaction.user.mention}, Seu middleman foi aberto. CLIQUE AQUI para encontrá-lo.", ephemeral=True)
        
        # Criação do ticket
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites)
        
        # Embed dentro do ticket (Referência 1000038020.jpg)
        embed = discord.Embed(title="Mediação Manual iniciada", description="Pedido de Middleman criado com sucesso. Selecione o usuário abaixo.")
        await channel.send(embed=embed, view=UserSelectView())

# 2. Menu de Seleção de Usuário
class UserSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.user_select(placeholder="Selecione o usuário que você está mediando")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        await interaction.response.send_message(f"Usuário {select.values[0].mention} selecionado.")

# 3. Comando de Configuração (/bot_config)
@bot.tree.command(name="bot_config", description="Configurar o sistema de intermediação")
async def bot_config(interaction: discord.Interaction, foto_interface: str, logo_final: str):
    config["embed_image"] = foto_interface
    config["final_logo"] = logo_final
    await interaction.response.send_message("Configurações salvas com sucesso!", ephemeral=True)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online como {bot.user}")

bot.run("MTUyMTkyNzA1MDU2OTU4MDc4NQ.GDgV1s.h077bzqnavOJey3LG1kbOY2CQWGcQw05oxVpWI")
