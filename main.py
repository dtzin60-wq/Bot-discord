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
    "cargos": {
        "ver": [],       # Lista de cargos que veem
        "finalizar": []  # Lista de cargos que finalizam
    },
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
        user = interaction.user
        roles = user.roles
        
        # Lista de cargos permitidos
        cargos_permitidos = configuracao["cargos"]["finalizar"]
        
        # Verifica se o usuário tem ALGUM dos cargos de finalizar
        tem_cargo = any(cargo in roles for cargo in cargos_permitidos)
        
        # Permissões: Dono, Admin ou Cargo Configurado
        e_staff = user.id == DONO_ID or user.guild_permissions.administrator or tem_cargo

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
        try:
            await interaction.user.send(f"👋 Você saiu do ticket **{interaction.channel.name}**.")
        except:
            pass

# --- MENU DE SELEÇÃO ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️", description="Clique aqui caso precisa de algum suporte"),
            discord.SelectOption(label="Reembolso", emoji="💰", description="Clique aqui caso deseja fazer um reembolso"),
            discord.SelectOption(label="Receber Evento", emoji="💫", description="Clique aqui caso queira receber algum evento"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑", description="Clique aqui caso queira alguma vaga de mediador na ORG"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="main_select")

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        canal_destino = configuracao["canais"].get(escolha)

        if not canal_destino:
            await interaction.response.send_message(f"❌ O canal para **{escolha}** ainda não foi configurado. Use /configurar_topicos", ephemeral=True)
            return

        try:
            # CRIA TÓPICO
            thread = await canal_destino.create_thread(
                name=f"{escolha}-{interaction.user.name}",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            
            await thread.add_user(interaction.user)
            
            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
            
            await interaction.response.send_message(content=f"✅ Seu ticket foi aberto!", view=view_jump, ephemeral=True)

            # Mensagem interna do Ticket
            embed = discord.Embed(
                description="Seja bem-vindo(a) ao painel de atendimento. Informamos que, dependendo do horário em que este ticket foi aberto, o tempo de resposta pode variar.",
                color=discord.Color.dark_grey()
            )
            agora = datetime.datetime.now()
            embed.add_field(name="Horário de Abertura:", value=f"<t:{int(agora.timestamp())}:F>")
            
            # Monta a menção com TODOS os cargos de VER + FINALIZAR
            mencao = f"{interaction.user.mention}"
            
            # Adiciona cargos de ver
            for cargo in configuracao["cargos"]["ver"]:
                mencao += f" {cargo.mention}"
            
            # Adiciona cargos de finalizar (para eles verem também)
            for cargo in configuracao["cargos"]["finalizar"]:
                if cargo not in configuracao["cargos"]["ver"]: # Evita duplicar se o cargo já estiver na lista de ver
                    mencao += f" {cargo.mention}"

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

# --- COMANDO 1: CONFIGURAÇÃO DE CANAIS ---
@bot.tree.command(name="configurar_topicos", description="🎟️ Define onde cada ticket será criado")
async def configurar_topicos(interaction: discord.Interaction, canal_suporte: discord.TextChannel, canal_reembolso: discord.TextChannel, canal_evento: discord.TextChannel, canal_vagas: discord.TextChannel):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)
    configuracao["canais"].update({"Suporte": canal_suporte, "Reembolso": canal_reembolso, "Receber Evento": canal_evento, "Vagas de Mediador": canal_vagas})
    await interaction.response.send_message("✅ Canais configurados!", ephemeral=True)

# --- COMANDO 2: CRIAR PAINEL (ATUALIZADO PARA 4 CARGOS CADA) ---
@bot.tree.command(name="criar_painel", description="💸 Envia o painel WS TICKET (Configure os cargos)")
@app_commands.describe(
    staff_1="Cargo principal de suporte",
    finalizar_1="Cargo principal para finalizar",
    staff_2="[Opcional] Cargo extra de suporte",
    staff_3="[Opcional] Cargo extra de suporte",
    staff_4="[Opcional] Cargo extra de suporte",
    finalizar_2="[Opcional] Cargo extra para finalizar",
    finalizar_3="[Opcional] Cargo extra para finalizar",
    finalizar_4="[Opcional] Cargo extra para finalizar"
)
async def criar_painel(
    interaction: discord.Interaction, 
    staff_1: discord.Role, 
    finalizar_1: discord.Role,
    staff_2: discord.Role = None, 
    staff_3: discord.Role = None,
    staff_4: discord.Role = None,
    finalizar_2: discord.Role = None,
    finalizar_3: discord.Role = None,
    finalizar_4: discord.Role = None
):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)
    
    # Salva cargos de VER (Staff)
    cargos_ver = [staff_1]
    if staff_2: cargos_ver.append(staff_2)
    if staff_3: cargos_ver.append(staff_3)
    if staff_4: cargos_ver.append(staff_4)
    configuracao["cargos"]["ver"] = cargos_ver

    # Salva cargos de FINALIZAR
    cargos_finalizar = [finalizar_1]
    if finalizar_2: cargos_finalizar.append(finalizar_2)
    if finalizar_3: cargos_finalizar.append(finalizar_3)
    if finalizar_4: cargos_finalizar.append(finalizar_4)
    configuracao["cargos"]["finalizar"] = cargos_finalizar

    descricao = (
        "👉 Abra ticket com o que você precisa abaixo com as informações de guia.\n\n"
        "☞ **TICKET SUPORTE**\n"
        "tire suas dúvidas aqui no ticket suporte, fale com nossos suportes e seja direto com o seu problema.\n\n"
        "☞ **TICKET REEMBOLSO**\n"
        "receba seu reembolso aqui, seja direto e mande comprovante do pagamento.\n\n"
        "☞ **TICKET RECEBE EVENTO**\n"
        "Receba seu evento completos, espera nossos suportes válida seu evento.\n\n"
        "☞ **TICKET VAGA MEDIADOR**\n"
        "seja mediador da org SPACE, abra ticket e espera nossos suportes recruta.\n\n"
        "→ Evite discussões!"
    )

    embed = discord.Embed(title="WS TICKET", description=descricao, color=discord.Color.from_rgb(10, 10, 10))
    embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg?ex=6990bea7&is=698f6d27&hm=ab8e0065381fdebb51ecddda1fe599a7366aa8dfe622cfeb7f720b7fadedd896&") 
    
    await interaction.channel.send(embed=embed, view=MainView())
    
    # Resposta de confirmação
    await interaction.response.send_message(
        f"✅ **Painel WS TICKET criado!**\n\n"
        f"👀 **Podem ver:** {len(cargos_ver)} cargos configurados.\n"
        f"🔒 **Podem finalizar:** {len(cargos_finalizar)} cargos configurados.", 
        ephemeral=True
    )

# --- COMANDO 3: QUEM PODE USAR ---
@bot.tree.command(name="quem_pode_usar", description="💸 Quem pode usar os comandos do bot?")
async def quem_pode_usar(interaction: discord.Interaction):
    embed = discord.Embed(title="💸 Permissões do Bot", color=discord.Color.gold())
    embed.description = (
        "Atualmente, a segurança do bot está configurada para:\n\n"
        f"👑 **Dono Supremo:** <@{DONO_ID}>\n"
        "Somente este usuário tem permissão para usar os comandos de configuração.\n\n"
        "👮 **Staff:** Pode finalizar tickets se tiver um dos cargos configurados."
    )
    await interaction.response.send_message(embed=embed)

if TOKEN: bot.run(TOKEN)
