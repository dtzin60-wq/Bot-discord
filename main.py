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

# Memória de Configuração (Salva na RAM)
configuracao = {
    "cargos": {
        "ver": [],       
        "finalizar": []  
    },
    "canais": {
        "Suporte": None,
        "Reembolso": None,
        "Receber Evento": None,
        "Vagas de Mediador": None
    }
}

# --- 1. VIEW DE CONTROLE (DENTRO DO TICKET) - BLINDADA ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Timeout None é vital para não parar de funcionar

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar_persistente")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Recupera cargos (ou lista vazia se perdeu a config)
            cargos_finalizar = configuracao["cargos"].get("finalizar", [])
            user = interaction.user
            
            # Verificação de Permissão Blindada
            e_staff = False
            if user.id == DONO_ID or user.guild_permissions.administrator:
                e_staff = True
            elif cargos_finalizar: # Se a lista não estiver vazia
                for cargo in cargos_finalizar:
                    if cargo in user.roles:
                        e_staff = True
                        break
            
            # Se a config foi perdida (reinício), libera para Admins por segurança
            if not cargos_finalizar and user.guild_permissions.administrator:
                e_staff = True

            if e_staff:
                await interaction.response.send_message("🚨 **Fechando ticket em 5 segundos...**", ephemeral=True)
                await asyncio.sleep(5)
                if interaction.channel: # Verifica se o canal ainda existe
                    await interaction.channel.delete()
            else:
                await interaction.response.send_message("❌ Você não tem permissão (ou o bot reiniciou e perdeu os cargos configurados).", ephemeral=True)
        except Exception as e:
            print(f"Erro ao finalizar: {e}")
            try: await interaction.response.send_message("❌ Erro ao processar. Tente novamente.", ephemeral=True)
            except: pass

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_assumir_persistente")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu este atendimento!")
        await interaction.response.send_message("Atendimento assumido!", ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_staff_persistente")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Ferramentas da Staff (Em breve)", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sair_persistente")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.channel.remove_user(interaction.user)
            await interaction.response.send_message("👋 Você saiu do ticket.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Erro ao sair. Talvez eu não tenha permissão.", ephemeral=True)

# --- 2. MENU DE SELEÇÃO - BLINDADO ---
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️", description="Clique aqui caso precisa de algum suporte"),
            discord.SelectOption(label="Reembolso", emoji="💰", description="Clique aqui caso deseja fazer um reembolso"),
            discord.SelectOption(label="Receber Evento", emoji="💫", description="Clique aqui caso queira receber algum evento"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑", description="Clique aqui caso queira alguma vaga de mediador na ORG"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="select_menu_persistente")

    async def callback(self, interaction: discord.Interaction):
        # Defesa contra Interaction Failed: Responde rápido ou avisa erro
        try:
            escolha = self.values[0]
            canal_destino = configuracao["canais"].get(escolha)

            # BLINDAGEM: Se o bot reiniciou, ele perde a config. Avisa o usuário.
            if not canal_destino:
                await interaction.response.send_message(
                    f"⚠️ **Atenção:** O bot foi reiniciado recentemente e perdeu a configuração temporária.\n"
                    f"Por favor, peça ao Dono (<@{DONO_ID}>) para usar o comando `/configurar_topicos` novamente.", 
                    ephemeral=True
                )
                return

            # Cria o Tópico
            thread = await canal_destino.create_thread(
                name=f"{escolha}-{interaction.user.name}",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            
            await thread.add_user(interaction.user)
            
            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
            
            await interaction.response.send_message(content=f"✅ Seu ticket foi aberto!", view=view_jump, ephemeral=True)

            # Mensagem interna
            embed = discord.Embed(
                description="Seja bem-vindo(a) ao painel de atendimento. Informamos que, dependendo do horário em que este ticket foi aberto, o tempo de resposta pode variar.",
                color=discord.Color.dark_grey()
            )
            agora = datetime.datetime.now()
            embed.add_field(name="Horário de Abertura:", value=f"<t:{int(agora.timestamp())}:F>")
            
            # Recuperação segura de menções
            mencao = f"{interaction.user.mention}"
            cargos_ver = configuracao["cargos"].get("ver", [])
            cargos_fin = configuracao["cargos"].get("finalizar", [])

            if cargos_ver:
                for cargo in cargos_ver:
                    mencao += f" {cargo.mention}"
            
            if cargos_fin:
                for cargo in cargos_fin:
                    if cargo not in cargos_ver:
                        mencao += f" {cargo.mention}"

            # Envia a View de Controle (também persistente)
            await thread.send(content=mencao, embed=embed, view=TicketControlView())

        except Exception as e:
            print(f"Erro no callback: {e}")
            try:
                await interaction.response.send_message("❌ Ocorreu um erro ao tentar criar o ticket. Tente novamente em instantes.", ephemeral=True)
            except:
                pass

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Timeout None para ser persistente
        self.add_item(TicketDropdown())

# --- EVENTO ON_READY (A MÁGICA DA BLINDAGEM) ---
@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user}")
    
    # ISSO AQUI EVITA O "INTERACTION FAILED" DEPOIS DE REINICIAR
    # O bot reconecta aos botões antigos que têm o mesmo custom_id
    bot.add_view(MainView())
    bot.add_view(TicketControlView())
    
    await bot.tree.sync()
    print("✅ Views persistentes carregadas e comandos sincronizados.")

# --- COMANDOS ---

@bot.tree.command(name="configurar_topicos", description="🎟️ Define onde cada ticket será criado")
async def configurar_topicos(interaction: discord.Interaction, canal_suporte: discord.TextChannel, canal_reembolso: discord.TextChannel, canal_evento: discord.TextChannel, canal_vagas: discord.TextChannel):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)
    configuracao["canais"].update({"Suporte": canal_suporte, "Reembolso": canal_reembolso, "Receber Evento": canal_evento, "Vagas de Mediador": canal_vagas})
    await interaction.response.send_message("✅ Canais configurados com sucesso!", ephemeral=True)

@bot.tree.command(name="criar_painel", description="💸 Envia o painel WS TICKET (Configure os cargos)")
@app_commands.describe(
    staff_1="Cargo principal de suporte", finalizar_1="Cargo principal para finalizar",
    staff_2="[Opcional]", staff_3="[Opcional]", staff_4="[Opcional]",
    finalizar_2="[Opcional]", finalizar_3="[Opcional]", finalizar_4="[Opcional]"
)
async def criar_painel(interaction: discord.Interaction, staff_1: discord.Role, finalizar_1: discord.Role, staff_2: discord.Role = None, staff_3: discord.Role = None, staff_4: discord.Role = None, finalizar_2: discord.Role = None, finalizar_3: discord.Role = None, finalizar_4: discord.Role = None):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono!", ephemeral=True)
    
    c_ver = [c for c in [staff_1, staff_2, staff_3, staff_4] if c]
    c_fin = [c for c in [finalizar_1, finalizar_2, finalizar_3, finalizar_4] if c]
    
    configuracao["cargos"]["ver"] = c_ver
    configuracao["cargos"]["finalizar"] = c_fin

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
    await interaction.response.send_message(f"✅ Painel configurado! ({len(c_ver)} staffs, {len(c_fin)} finalizadores)", ephemeral=True)

@bot.tree.command(name="quem_pode_usar", description="💸 Quem pode usar os comandos do bot?")
async def quem_pode_usar(interaction: discord.Interaction):
    embed = discord.Embed(title="💸 Permissões do Bot", color=discord.Color.gold())
    embed.description = f"👑 **Dono Supremo:** <@{DONO_ID}>\n👮 **Staff:** Pode finalizar tickets."
    await interaction.response.send_message(embed=embed)

if TOKEN: bot.run(TOKEN)
                                 
