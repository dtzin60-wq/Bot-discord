import discord
import os
import asyncio
import datetime
import traceback
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
DONO_ID = 1461858587080130663

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- MEMÓRIA ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {
        "Suporte": None, 
        "Reembolso": None, 
        "Receber Evento": None, 
        "Vagas de Mediador": None,
        "Filas": None
    }
}
tickets_abertos = []

# ==============================================================================
# SISTEMA DE MODALS (CAIXINHAS DE TEXTO DA STAFF)
# ==============================================================================

class RenomearModal(discord.ui.Modal, title="Renomear Ticket"):
    novo_nome = discord.ui.TextInput(label="Novo Nome", placeholder="Ex: atendimento-finalizado")
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.edit(name=self.novo_nome.value)
        await interaction.response.send_message(f"✅ Ticket renomeado para **{self.novo_nome.value}**", ephemeral=True)

class AdicionarMembroModal(discord.ui.Modal, title="Adicionar Membro"):
    user_id = discord.ui.TextInput(label="ID do Usuário", placeholder="Cole o ID aqui...")
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = await interaction.guild.fetch_member(int(self.user_id.value))
            await interaction.channel.add_user(user)
            await interaction.response.send_message(f"✅ {user.mention} adicionado ao ticket.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Usuário não encontrado ou ID inválido.", ephemeral=True)

class RemoverMembroModal(discord.ui.Modal, title="Remover Membro"):
    user_id = discord.ui.TextInput(label="ID do Usuário", placeholder="Cole o ID aqui...")
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = await interaction.guild.fetch_member(int(self.user_id.value))
            await interaction.channel.remove_user(user)
            await interaction.response.send_message(f"👋 {user.mention} removido do ticket.", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Usuário não encontrado ou ID inválido.", ephemeral=True)

# ==============================================================================
# SISTEMA DO MENU STAFF (DROPDOWN)
# ==============================================================================

class StaffActionsDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Renomear Ticket", emoji="📝", description="Altera o nome do ticket atual"),
            discord.SelectOption(label="Notificar Membro", emoji="🔔", description="Menciona o membro para avisá-lo"),
            discord.SelectOption(label="Adicionar Usuário", emoji="👤", description="Adiciona um usuário ao ticket"),
            discord.SelectOption(label="Remover Usuário", emoji="🚫", description="Remove um usuário do ticket"),
        ]
        super().__init__(placeholder="Selecione uma ação", options=options)

    async def callback(self, interaction: discord.Interaction):
        acao = self.values[0]

        if acao == "Renomear Ticket":
            await interaction.response.send_modal(RenomearModal())
        
        elif acao == "Notificar Membro":
            # Tenta achar o dono do ticket pelo nome do canal ou menciona todos
            await interaction.channel.send(f"🔔 **ATENÇÃO:** {interaction.user.mention} está aguardando uma resposta! @here")
            await interaction.response.send_message("✅ Notificação enviada.", ephemeral=True)
        
        elif acao == "Adicionar Usuário":
            await interaction.response.send_modal(AdicionarMembroModal())
        
        elif acao == "Remover Usuário":
            await interaction.response.send_modal(RemoverMembroModal())

class StaffActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(StaffActionsDropdown())

# ==============================================================================
# VIEWS DE CONTROLE (BOTÕES DO TICKET)
# ==============================================================================

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_finalizar_geral")
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Lógica de Finalizar
        cargos_finalizar = configuracao["cargos"].get("finalizar", [])
        user = interaction.user
        e_staff = user.id == DONO_ID or user.guild_permissions.administrator
        if not e_staff and cargos_finalizar:
            for cargo in cargos_finalizar:
                if cargo in user.roles:
                    e_staff = True
                    break
        if not cargos_finalizar and user.guild_permissions.administrator: e_staff = True

        if e_staff:
            await interaction.response.send_message("🚨 **Fechando ticket em 5 segundos...**", ephemeral=True)
            await asyncio.sleep(5)
            if interaction.channel: await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ Você não tem permissão.", ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_assumir_geral")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu este atendimento!")
        await interaction.response.send_message("Atendimento assumido!", ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_staff_geral")
    async def staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verifica permissão básica
        e_staff = interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID
        if e_staff:
            # Envia o Menu Dropdown apenas para a staff ver (Ephemeral)
            await interaction.response.send_message("🔧 **Painel da Staff:**", view=StaffActionsView(), ephemeral=True)
        else:
            await interaction.response.send_message("❌ Apenas staff.", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sair_geral")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.user
            if user.id in tickets_abertos: tickets_abertos.remove(user.id)
            await interaction.channel.remove_user(user)
        except: pass

# --- VIEW FILAS ---
class FilaControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_validar_fila")
    async def validar(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.guild_permissions.manage_messages or user.id == DONO_ID:
            await interaction.response.send_message(f"✅ **Pagamento Validado por {user.mention}!** Boa sorte! 🍀")
        else:
            await interaction.response.send_message("❌ Apenas staff.", ephemeral=True)

    @discord.ui.button(label="Fechar Fila", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_fechar_fila")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID:
            await interaction.response.send_message("🚨 **Fechando...**", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

# ==============================================================================
# LÓGICA DE CRIAÇÃO (VIEWS PRINCIPAIS)
# ==============================================================================

class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️", description="Clique aqui caso precisa de algum suporte"),
            discord.SelectOption(label="Reembolso", emoji="💰", description="Clique aqui caso deseja fazer um reembolso"),
            discord.SelectOption(label="Receber Evento", emoji="💫", description="Clique aqui caso queira receber algum evento"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑", description="Clique aqui caso queira alguma vaga de mediador na ORG"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="select_menu_geral")

    async def callback(self, interaction: discord.Interaction):
        try:
            user = interaction.user
            if user.id in tickets_abertos:
                await interaction.response.send_message("Você já tem um ticket criado não pode criar outro❗", ephemeral=True)
                return

            escolha = self.values[0]
            canal_destino = configuracao["canais"].get(escolha)

            if not canal_destino:
                await interaction.response.send_message(f"⚠️ Erro: Canal para **{escolha}** não configurado. Use `/configurar_topicos`.", ephemeral=True)
                return

            thread = await canal_destino.create_thread(name=f"{escolha}-{user.name}", type=discord.ChannelType.private_thread, invitable=False)
            tickets_abertos.append(user.id)
            await thread.add_user(user)

            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
            await interaction.response.send_message(content="✅ | Seu ticket foi aberto com sucesso!", view=view_jump, ephemeral=True)

            embed = discord.Embed(description="Seja bem-vindo(a) ao painel de atendimento.", color=discord.Color.dark_grey())
            embed.add_field(name="Horário de Abertura:", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>")
            
            mencao = f"{user.mention}"
            for c in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"
            for c in configuracao["cargos"].get("finalizar", []): 
                if c not in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"

            await thread.send(content=mencao, embed=embed, view=TicketControlView())

        except Exception as e:
            if interaction.user.id in tickets_abertos: tickets_abertos.remove(interaction.user.id)
            print(f"Erro: {e}")

class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

class FilaBotaoIndividual(discord.ui.Button):
    def __init__(self, numero, valor):
        super().__init__(label=f"Fila {numero:02d} • R$ {valor}", style=discord.ButtonStyle.secondary, custom_id=f"btn_fila_{numero}_{valor}")
        self.valor_aposta = valor
        self.numero_fila = numero

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        if user.id in tickets_abertos:
            return await interaction.response.send_message("Você já tem uma fila aberta! Finalize a anterior.", ephemeral=True)

        canal_destino = configuracao["canais"].get("Filas") or interaction.channel 
        try:
            await interaction.response.defer(ephemeral=True)
            thread = await canal_destino.create_thread(name=f"Fila-{self.numero_fila:02d}-{user.name}", type=discord.ChannelType.private_thread, invitable=False)
            tickets_abertos.append(user.id)
            await thread.add_user(user)

            view_jump = discord.ui.View()
            view_jump.add_item(discord.ui.Button(label="Ir para a Fila", url=thread.jump_url, emoji="🔗"))
            await interaction.followup.send(content=f"✅ | Você entrou na **Fila {self.numero_fila:02d}** (Valor: R$ {self.valor_aposta})!", view=view_jump, ephemeral=True)
            
            embed = discord.Embed(title=f"💰 APOSTA: R$ {self.valor_aposta}", description=f"Olá {user.mention}, envie o PIX e o comprovante.", color=discord.Color.green())
            await thread.send(content=user.mention, embed=embed, view=FilaControlView())
        except:
            if user.id in tickets_abertos: tickets_abertos.remove(user.id)

class FilaButtonsView(discord.ui.View):
    def __init__(self, quantidade: int, valor: str):
        super().__init__(timeout=None)
        for i in range(1, quantidade + 1):
            self.add_item(FilaBotaoIndividual(numero=i, valor=valor))

class FilaConfigModal(discord.ui.Modal, title="Criar Filas de Apostas"):
    quantidade = discord.ui.TextInput(label="Quantidade de Filas (Max 15)", placeholder="Ex: 10", min_length=1, max_length=2, required=True)
    valor = discord.ui.TextInput(label="Valor da Aposta", placeholder="Ex: 100,00", min_length=1, max_length=10, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value)
            if qtd < 1 or qtd > 15: return await interaction.response.send_message("❌ Máximo 15 filas.", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            embed = discord.Embed(title=f"FILAS DE APOSTAS - VALOR: R$ {self.valor.value}", description=f"💲 **VALOR DA ENTRADA:** R$ {self.valor.value}\n\nClique em uma fila livre abaixo.", color=discord.Color.blue())
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            await interaction.channel.send(embed=embed, view=FilaButtonsView(qtd, self.valor.value))
            await interaction.followup.send("✅ Painel criado!", ephemeral=True)
        except: pass

# ==============================================================================
# EVENTOS (AQUI ESTÁ A MÁGICA DE APAGAR MENSAGENS)
# ==============================================================================

@bot.event
async def on_ready():
    print(f"✅ Bot Online: {bot.user}")
    bot.add_view(MainView())
    bot.add_view(TicketControlView())
    await bot.tree.sync()

@bot.event
async def on_message(message):
    # Verifica se a mensagem é de sistema (Join, Pin, etc) E se está dentro de um Ticket (Thread)
    if message.is_system() and isinstance(message.channel, discord.Thread):
        try:
            await message.delete() # Apaga imediatamente
        except:
            pass
    
    await bot.process_commands(message)

# ==============================================================================
# COMANDOS
# ==============================================================================

@bot.tree.command(name="configurar_topicos", description="Define os canais de tickets")
async def configurar_topicos(interaction: discord.Interaction, canal_suporte: discord.TextChannel, canal_reembolso: discord.TextChannel, canal_evento: discord.TextChannel, canal_vagas: discord.TextChannel, canal_filas: discord.TextChannel):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    configuracao["canais"].update({"Suporte": canal_suporte, "Reembolso": canal_reembolso, "Receber Evento": canal_evento, "Vagas de Mediador": canal_vagas, "Filas": canal_filas})
    await interaction.response.send_message("✅ Canais salvos!", ephemeral=True)

@bot.tree.command(name="criar_painel", description="Cria o painel WS TICKET Principal")
async def criar_painel(interaction: discord.Interaction, staff_1: discord.Role, finalizar_1: discord.Role, staff_2: discord.Role = None, staff_3: discord.Role = None, staff_4: discord.Role = None, finalizar_2: discord.Role = None, finalizar_3: discord.Role = None, finalizar_4: discord.Role = None):
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.user.id != DONO_ID: return await interaction.followup.send("❌ Apenas o dono pode usar isso.")
        
        c_ver = [c for c in [staff_1, staff_2, staff_3, staff_4] if c]
        c_fin = [c for c in [finalizar_1, finalizar_2, finalizar_3, finalizar_4] if c]
        configuracao["cargos"]["ver"] = c_ver
        configuracao["cargos"]["finalizar"] = c_fin

        # TEXTO CORRIGIDO: SPACE -> WS
        descricao = (
            "👉 Abra ticket com o que você precisa abaixo com as informações de guia.\n\n"
            "☞ **TICKET SUPORTE**\n"
            "tire suas dúvidas aqui no ticket suporte, fale com nossos suportes e seja direto com o seu problema.\n\n"
            "☞ **TICKET REEMBOLSO**\n"
            "receba seu reembolso aqui, seja direto e mande comprovante do pagamento.\n\n"
            "☞ **TICKET RECEBE EVENTO**\n"
            "Receba seu evento completos, espera nossos suportes válida seu evento.\n\n"
            "☞ **TICKET VAGA MEDIADOR**\n"
            "seja mediador da org WS, abra ticket e espera nossos suportes recruta.\n\n"
            "→ Evite discussões!"
        )
        
        embed = discord.Embed(title="WS TICKET", description=descricao, color=discord.Color.blue())
        embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg?ex=6990bea7&is=698f6d27&hm=ab8e0065381fdebb51ecddda1fe599a7366aa8dfe622cfeb7f720b7fadedd896&")
        
        await interaction.channel.send(embed=embed, view=MainView())
        await interaction.followup.send(f"✅ Painel enviado!", ephemeral=True)
    except Exception as e:
        traceback.print_exc()
        await interaction.followup.send(f"❌ Erro: `{str(e)}`", ephemeral=True)

@bot.tree.command(name="criar_filas", description="Cria painel de filas de apostas")
async def criar_filas(interaction: discord.Interaction):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    await interaction.response.send_modal(FilaConfigModal())

if TOKEN: bot.run(TOKEN)
    
