import discord
import os
import datetime
import asyncio
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
DONO_ID = 1461858587080130663  # Seu ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- MEMÓRIA (Cargos e Canais de Destino) ---
# Aqui guardamos onde cada ticket deve ser criado
configuracao = {
    "cargos": {"ver": None, "finalizar": None},
    "canais": {
        "Suporte": None,
        "Reembolso": None,
        "Receber Evento": None,
        "Vagas de Mediador": None
    }
}

# --- VIEW: Botões de Controle DENTRO do Tópico ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica permissão
        roles = interaction.user.roles
        cargo_finalizar = configuracao["cargos"]["finalizar"]
        tem_permissao = interaction.user.id == DONO_ID or interaction.user.guild_permissions.administrator or (cargo_finalizar in roles if cargo_finalizar else False)

        if tem_permissao:
            await interaction.response.send_message("🚨 **Este tópico será excluído em 5 segundos...**", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete() # Deleta o tópico
        else:
            await interaction.response.send_message("❌ Sem permissão para finalizar.", ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_assumir")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu este atendimento!")
        await interaction.response.send_message("Atendimento assumido!", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove o usuário do tópico (Thread)
        await interaction.channel.remove_user(interaction.user)
        await interaction.response.send_message("👋 Você saiu do ticket.", ephemeral=True)

# --- VIEW: Confirmação para Criar o Tópico ---
class ConfirmCreateView(discord.ui.View):
    def __init__(self, escolha):
        super().__init__(timeout=60)
        self.escolha = escolha

    @discord.ui.button(label="Criar Tópico", style=discord.ButtonStyle.primary, emoji="📩")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        canal_destino = configuracao["canais"].get(self.escolha)

        if not canal_destino:
            await interaction.response.send_message("❌ Erro: O canal para esta categoria não foi configurado pelo dono. Use /configurar_topicos.", ephemeral=True)
            return

        try:
            # Cria um TÓPICO PRIVADO (Thread) dentro do canal configurado
            thread = await canal_destino.create_thread(
                name=f"{self.escolha}-{interaction.user.name}",
                type=discord.ChannelType.private_thread, # Tópico Privado
                invitable=False # Apenas mods podem convidar
            )
            
            # Adiciona o usuário ao tópico
            await thread.add_user(interaction.user)
            
            # Adiciona quem tem o cargo de ver (se configurado)
            cargo_ver = configuracao["cargos"]["ver"]
            # Nota: Em threads privadas, não dá pra adicionar um cargo inteiro automaticamente pela API simples,
            # mas os admins e mods geralmente conseguem ver threads privadas.
            # O bot envia a mensagem marcando o cargo para notificar.

            # Link para ir ao tópico
            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Acessar Tópico", url=thread.jump_url, emoji="🔗"))
            
            await interaction.response.edit_message(content=f"✅ Tópico criado com sucesso em {thread.mention}!", view=view_jump)

            # Mensagem Inicial dentro do Tópico
            embed = discord.Embed(
                description=f"Olá {interaction.user.mention}, descreva seu problema abaixo.",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Space Apostas • Suporte")
            
            mencao = f"{interaction.user.mention}"
            if cargo_ver: mencao += f" {cargo_ver.mention}"

            await thread.send(content=mencao, embed=embed, view=TicketControlView())

        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao criar tópico. Verifique se tenho permissão no canal {canal_destino.mention}. Erro: {e}", ephemeral=True)

# --- VIEW: Menu Principal ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️", description="Dúvidas e ajuda geral"),
            discord.SelectOption(label="Reembolso", emoji="💰", description="Problemas com pagamentos"),
            discord.SelectOption(label="Receber Evento", emoji="💫", description="Resgate de prêmios"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑", description="Recrutamento da equipe"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="main_select")

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        # Mensagem de confirmação (Double Check)
        await interaction.response.send_message(
            content=f"Você escolheu **{escolha}**. Clique abaixo para confirmar e criar o tópico.",
            view=ConfirmCreateView(escolha),
            ephemeral=True
        )

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user}")
    await bot.tree.sync()

# --- COMANDO 1: Cria o Painel (Configura Cargos e Envia Mensagem) ---
@bot.tree.command(name="criar_painel", description="💸 Envia o painel e configura os cargos")
@app_commands.describe(cargo_ver="Quem vê os tickets?", cargo_finalizar="Quem finaliza os tickets?")
async def criar_painel(interaction: discord.Interaction, cargo_ver: discord.Role, cargo_finalizar: discord.Role):
    if interaction.user.id != DONO_ID:
        return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)
    
    configuracao["cargos"]["ver"] = cargo_ver
    configuracao["cargos"]["finalizar"] = cargo_finalizar

    embed = discord.Embed(title="SPACE TICKET", description="Selecione uma categoria abaixo para abrir um tópico de atendimento.", color=discord.Color.from_rgb(20, 20, 20))
    # Coloque sua imagem aqui
    embed.set_image(url="https://i.imgur.com/SEU_LINK_AQUI.png") 
    
    await interaction.channel.send(embed=embed, view=MainView())
    await interaction.response.send_message("✅ Painel enviado e cargos configurados!", ephemeral=True)

# --- COMANDO 2: Configura os CANAIS DE DESTINO (O que você pediu) ---
@bot.tree.command(name="configurar_topicos", description="🎟️ Define em qual canal cada tópico será criado")
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

    # Salva os canais na memória
    configuracao["canais"]["Suporte"] = canal_suporte
    configuracao["canais"]["Reembolso"] = canal_reembolso
    configuracao["canais"]["Receber Evento"] = canal_evento
    configuracao["canais"]["Vagas de Mediador"] = canal_vagas

    texto_resposta = (
        "✅ **Configuração de Canais Atualizada!**\n\n"
        f"🛠️ **Suporte** -> {canal_suporte.mention}\n"
        f"💰 **Reembolso** -> {canal_reembolso.mention}\n"
        f"💫 **Evento** -> {canal_evento.mention}\n"
        f"👑 **Vagas** -> {canal_vagas.mention}\n\n"
        "Agora, quando alguém abrir um ticket, um **Tópico Privado** será criado dentro desses canais."
    )
    
    await interaction.response.send_message(texto_resposta, ephemeral=True)

bot.run(TOKEN)
