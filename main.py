import discord
import os
import datetime
from discord.ext import commands
from discord import app_commands

# Tenta pegar o token do ambiente (Railway) ou use um fixo para teste local
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuração dos Intents (Permissões)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Necessário para gerenciar permissões de membros
bot = commands.Bot(command_prefix="!", intents=intents)

# Memória temporária para os cargos (Reseta se o bot reiniciar)
configuracao_cargos = {
    "ver": None,
    "finalizar": None
}

# --- VIEW 1: Botões de Controle DENTRO do Ticket (Para a Staff) ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="ticket_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        cargo_finalizar = configuracao_cargos.get("finalizar")
        
        # Verifica permissão: Se é Admin OU tem o cargo configurado
        user_roles = interaction.user.roles
        e_admin = interaction.user.guild_permissions.administrator
        tem_cargo = cargo_finalizar in user_roles if cargo_finalizar else False

        if e_admin or tem_cargo:
            await interaction.response.send_message("O ticket será fechado em 5 segundos...", ephemeral=True)
            await discord.utils.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ Você não tem permissão para finalizar este ticket.", ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="ticket_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🛡️ {interaction.user.mention} assumiu este atendimento!", allowed_mentions=discord.AllowedMentions(users=True))

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="ticket_staff")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚙️ Painel da Staff (Em desenvolvimento).", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="ticket_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.set_permissions(interaction.user, overwrite=None)
        await interaction.response.send_message(f"👋 {interaction.user.mention} saiu do ticket.", allowed_mentions=discord.AllowedMentions(users=True))


# --- VIEW 2: Menu de Seleção (O Painel Principal) ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", description="Clique aqui caso precise de algum suporte", emoji="🛠️"),
            discord.SelectOption(label="Reembolso", description="Clique aqui caso deseja fazer um reembolso", emoji="💰"),
            discord.SelectOption(label="Receber Evento", description="Clique aqui caso queira receber algum evento", emoji="💫"),
            discord.SelectOption(label="Vagas de Mediador", description="Clique aqui para vagas na ORG", emoji="👑"),
        ]
        super().__init__(placeholder="Selecione uma função", min_values=1, max_values=1, options=options, custom_id="ticket_menu_select")

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        guild = interaction.guild
        user = interaction.user

        # 1. Cria ou busca a categoria TICKETS
        category = discord.utils.get(guild.categories, name="TICKETS")
        if not category:
            category = await guild.create_category("TICKETS")

        # 2. Verifica se já tem ticket
        channel_name = f"{escolha.lower()}-{user.name}".replace(" ", "-").lower()
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        
        if existing_channel:
            await interaction.response.send_message(f"❌ Você já possui um ticket aberto: {existing_channel.mention}", ephemeral=True)
            return

        # 3. Define Permissões
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        # Adiciona permissão para os cargos configurados
        if configuracao_cargos["ver"]:
            overwrites[configuracao_cargos["ver"]] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        if configuracao_cargos["finalizar"]:
            overwrites[configuracao_cargos["finalizar"]] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # 4. Cria o Canal
        ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
        
        # 5. Resposta Efêmera com Botão de "Pular para o Ticket"
        view_link = discord.ui.View()
        view_link.add_item(discord.ui.Button(label="Ir para o Ticket", url=ticket_channel.jump_url, emoji="🔗"))
        
        await interaction.response.send_message(
            content=f"✅ | Seu ticket de **{escolha}** foi aberto com sucesso!",
            view=view_link,
            ephemeral=True
        )
        
        # 6. MENSAGEM DENTRO DO TICKET (Embed + Painel de Controle)
        embed_ticket = discord.Embed(
            description="Seja bem-vindo(a) ao painel de atendimento. Informamos que, dependendo do horário em que este ticket foi aberto, o tempo de resposta pode variar.",
            color=discord.Color.dark_grey()
        )
        # Timestamp atual
        agora = datetime.datetime.now()
        embed_ticket.add_field(name="Horário de Abertura:", value=f"<t:{int(agora.timestamp())}:F> (<t:{int(agora.timestamp())}:R>)")
        
        # Tenta colocar a logo (se não tiver link, remova esta linha)
        # embed_ticket.set_thumbnail(url="LINK_DA_LOGO_PEQUENA") 

        # Monta menções
        mencoes = f"{user.mention}"
        if configuracao_cargos["ver"]: mencoes += f" {configuracao_cargos['ver'].mention}"
        if configuracao_cargos["finalizar"] and configuracao_cargos["finalizar"] != configuracao_cargos["ver"]:
            mencoes += f" {configuracao_cargos['finalizar'].mention}"

        await ticket_channel.send(content=mencoes, embed=embed_ticket, view=TicketControlView())


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

@bot.event
async def on_ready():
    print("------------------------------------------------------")
    print(f"✅ BOT ONLINE! Logado como: {bot.user}")
    print(f"✅ ID: {bot.user.id}")
    print("------------------------------------------------------")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} Comandos Slash sincronizados!")
    except Exception as e:
        print(f"❌ Erro ao sincronizar: {e}")

# COMANDO SLASH CORRIGIDO (Nome sem emoji e minúsculo)
@bot.tree.command(name="criar_painel", description="💸 Cria o painel de tickets Space Apostas")
@app_commands.describe(
    cargo_ver="Quem pode ver os tickets?",
    cargo_finalizar="Quem pode finalizar os tickets?"
)
async def criar_painel(interaction: discord.Interaction, cargo_ver: discord.Role, cargo_finalizar: discord.Role):
    # Verifica se quem digitou é admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas administradores podem usar este comando.", ephemeral=True)
        return

    # Salva os cargos na memória
    configuracao_cargos["ver"] = cargo_ver
    configuracao_cargos["finalizar"] = cargo_finalizar

    embed = discord.Embed(
        title="SPACE TICKET",
        description="👉 Abra ticket com o que você precisa abaixo com as informações de guia.",
        color=discord.Color.from_rgb(20, 20, 20)
    )
    # COLOQUE AQUI O LINK DA IMAGEM DO ASTRONAUTA
    embed.set_image(url="https://i.imgur.com/SEU_LINK_AQUI.png") 
    
    await interaction.response.send_message(
        f"✅ Painel configurado!\n👀 **Visualizar:** {cargo_ver.mention}\n🔒 **Finalizar:** {cargo_finalizar.mention}",
        ephemeral=True
    )
    
    await interaction.channel.send(embed=embed, view=TicketView())

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ ERRO: Token não encontrado. Configure a variável DISCORD_TOKEN no Railway.")
            
