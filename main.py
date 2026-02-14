import discord
import os
import datetime
from discord.ext import commands
from discord import app_commands

# Configuração para pegar o Token
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuração dos Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Armazena os cargos na memória
configuracao_cargos = {
    "ver": None,
    "finalizar": None
}

# --- VIEW: Botões de Controle dentro do Ticket (Igual Foto 2) ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="ticket_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica se quem clicou tem permissão (cargo configurado ou admin)
        cargo_finalizar = configuracao_cargos.get("finalizar")
        
        user_roles = interaction.user.roles
        has_permission = interaction.user.guild_permissions.administrator or (cargo_finalizar in user_roles if cargo_finalizar else False)

        if has_permission:
            await interaction.response.send_message("O ticket será fechado em 5 segundos...", ephemeral=True)
            await discord.utils.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("Você não tem permissão para finalizar este ticket.", ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="ticket_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} assumiu este ticket!", allowed_mentions=discord.AllowedMentions(users=True))

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="ticket_staff")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Painel da Staff (Função extra a configurar)", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="ticket_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove a permissão do usuário que clicou
        await interaction.channel.set_permissions(interaction.user, overwrite=None)
        await interaction.response.send_message(f"{interaction.user.mention} saiu do ticket.", allowed_mentions=discord.AllowedMentions(users=True))


# --- VIEW: Menu de Seleção Inicial ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", description="Clique aqui caso precise de algum suporte", emoji="🛠️"),
            discord.SelectOption(label="Reembolso", description="Clique aqui caso deseja fazer um reembolso", emoji="💰"),
            discord.SelectOption(label="Receber Evento", description="Clique aqui caso queira receber algum evento", emoji="💫"),
            discord.SelectOption(label="Vagas de Mediador", description="Clique aqui para vagas na ORG", emoji="👑"),
        ]
        super().__init__(placeholder="Selecione uma função", min_values=1, max_values=1, options=options, custom_id="ticket_menu")

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        guild = interaction.guild
        
        category = discord.utils.get(guild.categories, name="TICKETS")
        if not category:
            category = await guild.create_category("TICKETS")

        channel_name = f"{escolha.lower()}-{interaction.user.name}".replace(" ", "-").lower()
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        
        if existing_channel:
            await interaction.response.send_message(f"Você já possui um ticket aberto em: {existing_channel.mention}", ephemeral=True)
            return

        # Define permissões
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        cargo_ver = configuracao_cargos.get("ver")
        if cargo_ver:
            overwrites[cargo_ver] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        cargo_finalizar = configuracao_cargos.get("finalizar")
        if cargo_finalizar:
            overwrites[cargo_finalizar] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Cria o canal
        ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        
        await interaction.response.send_message(f"Ticket criado: {ticket_channel.mention}", ephemeral=True)
        
        # --- MONTAGEM DA MENSAGEM DENTRO DO TICKET (IGUAL FOTO 2) ---
        
        # 1. Menções (Cargos + Dono do ticket)
        mencoes = f"{interaction.user.mention}"
        if cargo_ver: mencoes += f" {cargo_ver.mention}"
        if cargo_finalizar: mencoes += f" {cargo_finalizar.mention}"
        
        # 2. Embed
        embed_ticket = discord.Embed(
            description="Seja bem-vindo(a) ao painel de atendimento. Informamos que, dependendo do horário em que este ticket foi aberto, o tempo de resposta pode variar.",
            color=discord.Color.dark_grey()
        )
        # Timestamp dinâmico do Discord
        agora = datetime.datetime.now()
        timestamp_discord = f"<t:{int(agora.timestamp())}:F> (<t:{int(agora.timestamp())}:R>)"
        
        embed_ticket.add_field(name="Horário de Abertura:", value=timestamp_discord, inline=False)
        embed_ticket.set_thumbnail(url="LINK_DA_SUA_LOGO_AQUI") # Coloque o link da sua logo pequena aqui
        
        # 3. Envia com os botões
        await ticket_channel.send(content=mencoes, embed=embed_ticket, view=TicketControlView())


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

@bot.event
async def on_ready():
    # Esta mensagem aparecerá nos logs da Railway
    print("------------------------------------------------------")
    print(f"✅ BOT ONLINE! Logado como: {bot.user}")
    print(f"✅ ID do Bot: {bot.user.id}")
    print("✅ Logs da Railway funcionando corretamente.")
    print("------------------------------------------------------")
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Comandos Slash sincronizados: {len(synced)}")
    except Exception as e:
        print(f"❌ Erro ao sincronizar: {e}")

@bot.tree.command(name="painel_ticket", description="Configura e envia o painel de tickets")
@app_commands.describe(
    cargo_ver="💸 Qual cargo pode ver o ticket?",
    cargo_finalizar="🎟️ Qual cargo pode finalizar o ticket?"
)
async def painel_ticket(interaction: discord.Interaction, cargo_ver: discord.Role, cargo_finalizar: discord.Role):
    configuracao_cargos["ver"] = cargo_ver
    configuracao_cargos["finalizar"] = cargo_finalizar

    embed = discord.Embed(
        title="SPACE TICKET",
        description="👉 Abra ticket com o que você precisa abaixo com as informações de guia.",
        color=discord.Color.from_rgb(20, 20, 20)
    )
    # Substitua pelo link da sua imagem grande
    embed.set_image(url="LINK_DA_IMAGEM_GRANDE_DO_ASTRONAUTA")

    await interaction.response.send_message(
        f"Painel configurado! \n**Cargo que vê:** {cargo_ver.mention}\n**Cargo que finaliza:** {cargo_finalizar.mention}",
        ephemeral=True
    )
    
    await interaction.channel.send(embed=embed, view=TicketView())

if TOKEN:
    bot.run(TOKEN)
else:
    print("Erro: A variável DISCORD_TOKEN não foi encontrada.")
                                                                
