import discord
from discord.ext import commands
from discord import app_commands
import logging

# Configuração de logs para debug
logging.basicConfig(level=logging.INFO)

class BotMediação(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        # Registra as views para persistência
        self.add_view(TicketLauncher())
        await self.tree.sync()
        print("Bot sincronizado com sucesso.")

bot = BotMediação()

# --- 1. Botão de Lançamento ---
class TicketLauncher(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Intermédio", style=discord.ButtonStyle.danger, custom_id="abrir_ticket")
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Imagem 2: Mensagem Ephemeral
        await interaction.response.send_message("✅ | Seu middleman foi aberto. CLIQUE AQUI para encontrá-lo.", ephemeral=True)
        
        # Criação do canal privado
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        channel = await guild.create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites)
        
        # Embed dentro do ticket
        embed = discord.Embed(title="Mediação Manual iniciada", description="Bem-vindo ao nosso sistema de middleman! Selecione o usuário abaixo.")
        await channel.send(embed=embed, view=UserSelectView())

# --- 2. Seleção de Usuário (Correção do Erro) ---
class UserSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(UserSelectMenu())

class UserSelectMenu(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o usuário que você está mediando", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        # Ação após selecionar o usuário
        user_selected = self.values[0]
        await interaction.response.send_message(f"✅ Usuário {user_selected.mention} selecionado para a mediação.")
        
        # Aqui você adicionaria o comando para dar permissão ao usuário no canal
        await interaction.channel.set_permissions(user_selected, read_messages=True, send_messages=True)

# --- 3. Comando de Configuração ---
@bot.tree.command(name="bot_config", description="Configuração do sistema")
@app_commands.checks.has_permissions(administrator=True)
async def bot_config(interaction: discord.Interaction, foto_interface: str, logo_final: str):
    # Lógica para salvar links (pode ser enviada para um arquivo JSON)
    await interaction.response.send_message(f"Configurações recebidas.\nInterface: {foto_interface}\nLogo: {logo_final}", ephemeral=True)

# --- 4. Sistema de Finalização (Lógica de Logs) ---
class FinalizarView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar Mediação", style=discord.ButtonStyle.success)
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Referência 4: Lógica para enviar para canal de logs
        await interaction.response.send_message("Mediação finalizada com sucesso!")
        # Implementar deleção ou arquivamento do canal aqui

bot.run("MTUyMTkyNzA1MDU2OTU4MDc4NQ.GDgV1s.h077bzqnavOJey3LG1kbOY2CQWGcQw05oxVpWI")
