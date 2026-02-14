import discord
import os
import asyncio
import datetime
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
DONO_ID = 1461858587080130663  # Seu ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Memória de Configuração
configuracao = {
    "cargos": {"ver": None, "finalizar": None},
    "canais": {
        "Suporte": None,
        "Reembolso": None,
        "Receber Evento": None,
        "Vagas de Mediador": None
    }
}

# --- BOTÕES DE CONTROLE (DENTRO DO TICKET) ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica permissão
        roles = interaction.user.roles
        cargo_finalizar = configuracao["cargos"]["finalizar"]
        e_staff = interaction.user.id == DONO_ID or interaction.user.guild_permissions.administrator or (cargo_finalizar in roles if cargo_finalizar else False)

        if e_staff:
            await interaction.response.send_message("🚨 **Este tópico será excluído em 5 segundos...**", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ Você não tem permissão para finalizar.", ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu este atendimento!")
        await interaction.response.send_message("Atendimento assumido!", ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_staff")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Ferramentas da Staff (Em breve)", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.remove_user(interaction.user)
        await interaction.response.send_message("👋 Você saiu do ticket.", ephemeral=True)

# --- MENU DE SELEÇÃO (IDENTICO À IMAGEM) ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        # Descrições exatas da imagem enviada
        options = [
            discord.SelectOption(
                label="Suporte", 
                emoji="🛠️", 
                description="Clique aqui caso precisa de algum suporte"
            ),
            discord.SelectOption(
                label="Reembolso", 
                emoji="💰", 
                description="Clique aqui caso deseja fazer um reembolso"
            ),
            discord.SelectOption(
                label="Receber Evento", 
                emoji="💫", 
                description="Clique aqui caso queira receber algum evento"
            ),
            discord.SelectOption(
                label="Vagas de Mediador", 
                emoji="👑", 
                description="Clique aqui caso queira alguma vaga de mediador na ORG"
            ),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="main_select")

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        canal_destino = configuracao["canais"].get(escolha)

        # Verifica se o dono configurou os canais
        if not canal_destino:
            await interaction.response.send_message(f"❌ O canal para **{escolha}** ainda não foi configurado pelo dono. Use /configurar_topicos", ephemeral=True)
            return

        try:
            # CRIA O TÓPICO DIRETO (Sem confirmação)
            thread = await canal_destino.create_thread(
                name=f"{escolha}-{interaction.user.name}",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            
            await thread.add_user(interaction.user)
            
            # Botão para ir ao ticket
            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
            
            await interaction.response.send_message(content=f"✅ Seu ticket de **{escolha}** foi criado!", view=view_jump, ephemeral=True)

            # Mensagem DENTRO do Ticket (Igual Foto 2)
            embed = discord.Embed(
                description="Seja bem-vindo(a) ao painel de atendimento. Informamos que, dependendo do horário em que este ticket foi aberto, o tempo de resposta pode variar.",
                color=discord.Color.dark_grey()
            )
            agora = datetime.datetime.now()
            embed.add_field(name="Horário de Abertura:", value=f"<t:{int(agora.timestamp())}:F> (há poucos segundos)")
            
            # Tenta pegar link da logo se tiver
            # embed.set_thumbnail(url="LINK_DA_LOGO")

            mencao = f"{interaction.user.mention}"
            if configuracao["cargos"]["ver"]: mencao += f" {configuracao['cargos']['ver'].mention}"

            await thread.send(content=mencao, embed=embed, view=TicketControlView())

        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao criar tópico: {e}", ephemeral=True)

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user}")
    await bot.tree.sync()

# --- COMANDO 1: CONFIGURAR CANAIS (Obrigatório usar primeiro) ---
@bot.tree.command(name="configurar_topicos", description="🎟️ Define onde cada ticket será criado")
@app_commands.describe(
    canal_suporte="Canal para tickets de Suporte",
    canal_reembolso="Canal para tickets de Reembolso",
    canal_evento="Canal para tickets de Evento",
    canal_vagas="Canal para tickets de Vagas"
)
async def configurar_topicos(
    interaction: discord.Interaction, 
    canal_suporte: discord.TextChannel,
    canal_reembolso: discord.TextChannel,
    canal_evento: discord.TextChannel,
    canal_vagas: discord.TextChannel
):
    if interaction.user.id != DONO_ID:
        return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)

    configuracao["canais"]["Suporte"] = canal_suporte
    configuracao["canais"]["Reembolso"] = canal_reembolso
    configuracao["canais"]["Receber Evento"] = canal_evento
    configuracao["canais"]["Vagas de Mediador"] = canal_vagas

    await interaction.response.send_message("✅ Canais configurados com sucesso! Agora pode criar o painel.", ephemeral=True)

# --- COMANDO 2: CRIAR O PAINEL ---
@bot.tree.command(name="criar_painel", description="💸 Envia o painel de tickets")
async def criar_painel(interaction: discord.Interaction, cargo_ver: discord.Role, cargo_finalizar: discord.Role):
    if interaction.user.id != DONO_ID:
        return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)
    
    configuracao["cargos"]["ver"] = cargo_ver
    configuracao["cargos"]["finalizar"] = cargo_finalizar

    embed = discord.Embed(title="SPACE TICKET", description="👉 Abra ticket com o que você precisa abaixo com as informações de guia.", color=discord.Color.from_rgb(20, 20, 20))
    # Coloque o link da imagem do astronauta aqui
    embed.set_image(url="https://i.imgur.com/SEU_LINK_AQUI.png") 
    
    await interaction.channel.send(embed=embed, view=MainView())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

if TOKEN:
    bot.run(TOKEN)
                                  
