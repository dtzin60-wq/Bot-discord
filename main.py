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

# ==============================================================================
# SISTEMA DE MEMÓRIA (SALVA DADOS ENQUANTO O BOT TÁ LIGADO)
# ==============================================================================
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Suporte": None, "Reembolso": None, "Receber Evento": None, "Vagas de Mediador": None, "Filas": None},
    "loja": {}, # Guarda produtos: {"Nome": {"valor": 10, "desc": "..."}}
    "usuarios": {} # Guarda saldo: {user_id: {"coins": 0, "vitorias": 0}}
}
tickets_abertos = []

# Funções auxiliares de Economia
def get_user_data(user_id):
    if user_id not in configuracao["usuarios"]:
        configuracao["usuarios"][user_id] = {"coins": 0, "vitorias": 0}
    return configuracao["usuarios"][user_id]

def add_coins(user_id, amount):
    data = get_user_data(user_id)
    data["coins"] += amount

def add_wins(user_id, amount):
    data = get_user_data(user_id)
    data["vitorias"] += amount

# ==============================================================================
# SISTEMA DE MODALS E VIEWS (TICKETS & STAFF)
# ==============================================================================
# (Mesmo código de antes, resumido para caber tudo)

class RenomearModal(discord.ui.Modal, title="Renomear Ticket"):
    novo_nome = discord.ui.TextInput(label="Novo Nome", placeholder="Ex: atendimento-finalizado")
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.edit(name=self.novo_nome.value)
        await interaction.response.send_message(f"✅ Renomeado para **{self.novo_nome.value}**", ephemeral=True)

class AdicionarMembroModal(discord.ui.Modal, title="Adicionar Membro"):
    user_id = discord.ui.TextInput(label="ID do Usuário")
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = await interaction.guild.fetch_member(int(self.user_id.value))
            await interaction.channel.add_user(user)
            await interaction.response.send_message(f"✅ {user.mention} adicionado.", ephemeral=True)
        except: await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

class RemoverMembroModal(discord.ui.Modal, title="Remover Membro"):
    user_id = discord.ui.TextInput(label="ID do Usuário")
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user = await interaction.guild.fetch_member(int(self.user_id.value))
            await interaction.channel.remove_user(user)
            await interaction.response.send_message(f"👋 {user.mention} removido.", ephemeral=True)
        except: await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

class StaffActionsDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Renomear Ticket", emoji="📝"),
            discord.SelectOption(label="Notificar Membro", emoji="🔔"),
            discord.SelectOption(label="Adicionar Usuário", emoji="👤"),
            discord.SelectOption(label="Remover Usuário", emoji="🚫"),
        ]
        super().__init__(placeholder="Selecione uma ação", options=options)
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "Renomear Ticket": await interaction.response.send_modal(RenomearModal())
        elif self.values[0] == "Notificar Membro": 
            await interaction.channel.send(f"🔔 **ATENÇÃO:** {interaction.user.mention} está aguardando! @here")
            await interaction.response.send_message("✅ Notificado.", ephemeral=True)
        elif self.values[0] == "Adicionar Usuário": await interaction.response.send_modal(AdicionarMembroModal())
        elif self.values[0] == "Remover Usuário": await interaction.response.send_modal(RemoverMembroModal())

class StaffActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(StaffActionsDropdown())

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Finalizar ticket", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_fin")
    async def fin(self, interaction, button):
        user = interaction.user
        e_staff = user.id == DONO_ID or user.guild_permissions.administrator
        if not e_staff:
            cargos = configuracao["cargos"].get("finalizar", [])
            if any(c in user.roles for c in cargos): e_staff = True
        if e_staff:
            await interaction.response.send_message("🚨 **Fechando...**", ephemeral=True)
            await asyncio.sleep(5)
            await interaction.channel.delete()
        else: await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    @discord.ui.button(label="Assumir Ticket", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_ass")
    async def ass(self, interaction, button):
        await interaction.channel.send(f"🛡️ {interaction.user.mention} assumiu!")
        await interaction.response.send_message("Assumido!", ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_stf")
    async def stf(self, interaction, button):
        if interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID:
            await interaction.response.send_message("🔧 **Painel Staff:**", view=StaffActionsView(), ephemeral=True)
        else: await interaction.response.send_message("❌ Apenas staff.", ephemeral=True)

    @discord.ui.button(label="Sair Ticket", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_sai")
    async def sai(self, interaction, button):
        try:
            if interaction.user.id in tickets_abertos: tickets_abertos.remove(interaction.user.id)
            await interaction.channel.remove_user(interaction.user)
        except: pass

class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️"),
            discord.SelectOption(label="Reembolso", emoji="💰"),
            discord.SelectOption(label="Receber Evento", emoji="💫"),
            discord.SelectOption(label="Vagas de Mediador", emoji="👑"),
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="menu_geral")
    async def callback(self, interaction):
        user = interaction.user
        if user.id in tickets_abertos: return await interaction.response.send_message("Você já tem um ticket!", ephemeral=True)
        escolha = self.values[0]
        canal = configuracao["canais"].get(escolha)
        if not canal: return await interaction.response.send_message("⚠️ Canal não configurado.", ephemeral=True)
        
        thread = await canal.create_thread(name=f"{escolha}-{user.name}", type=discord.ChannelType.private_thread)
        tickets_abertos.append(user.id)
        await thread.add_user(user)
        await asyncio.sleep(1)
        try: 
            async for m in thread.history(limit=5): 
                if m.is_system(): await m.delete()
        except: pass

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ir para o Ticket", url=thread.jump_url, emoji="🔗"))
        await interaction.response.send_message("✅ Ticket aberto!", view=view, ephemeral=True)
        
        embed = discord.Embed(description="Seja bem-vindo(a).", color=discord.Color.dark_grey())
        embed.add_field(name="Horário:", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>")
        mencao = f"{user.mention}"
        for c in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"
        for c in configuracao["cargos"].get("finalizar", []): 
             if c not in configuracao["cargos"].get("ver", []): mencao += f" {c.mention}"
        await thread.send(content=mencao, embed=embed, view=TicketControlView())

class MainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketDropdown())

# ==============================================================================
# FILAS DE APOSTAS
# ==============================================================================
class FilaControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_val_pag")
    async def val(self, interaction, button):
        if interaction.user.guild_permissions.manage_messages or interaction.user.id == DONO_ID:
            await interaction.response.send_message(f"✅ **Validado por {interaction.user.mention}!**", ephemeral=False)
        else: await interaction.response.send_message("❌ Apenas staff.", ephemeral=True)
    @discord.ui.button(label="Fechar Fila", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_fec_fil")
    async def fec(self, interaction, button):
        if interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("🚨 **Fechando...**", ephemeral=True)
            await asyncio.sleep(5); await interaction.channel.delete()

class FilaBotaoIndividual(discord.ui.Button):
    def __init__(self, numero, valor):
        super().__init__(label=f"Fila {numero:02d} • R$ {valor}", style=discord.ButtonStyle.secondary, custom_id=f"fila_{numero}_{valor}")
        self.valor, self.numero = valor, numero
    async def callback(self, interaction):
        user = interaction.user
        if user.id in tickets_abertos: return await interaction.response.send_message("Finalize seu ticket anterior!", ephemeral=True)
        canal = configuracao["canais"].get("Filas") or interaction.channel
        await interaction.response.defer(ephemeral=True)
        thread = await canal.create_thread(name=f"Fila-{self.numero:02d}-{user.name}", type=discord.ChannelType.private_thread)
        tickets_abertos.append(user.id); await thread.add_user(user)
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ir para a Fila", url=thread.jump_url, emoji="🔗"))
        await interaction.followup.send(f"✅ Entrou na **Fila {self.numero:02d}**!", view=view, ephemeral=True)
        embed = discord.Embed(title=f"💰 APOSTA: R$ {self.valor}", description=f"Olá {user.mention}, envie o PIX e comprovante.", color=discord.Color.green())
        await thread.send(content=user.mention, embed=embed, view=FilaControlView())

class FilaButtonsView(discord.ui.View):
    def __init__(self, qtd, val):
        super().__init__(timeout=None)
        for i in range(1, qtd+1): self.add_item(FilaBotaoIndividual(i, val))

class FilaConfigModal(discord.ui.Modal, title="Criar Filas"):
    qtd = discord.ui.TextInput(label="Quantidade (Max 15)")
    val = discord.ui.TextInput(label="Valor (Ex: 100,00)")
    async def on_submit(self, interaction):
        try:
            q = int(self.qtd.value)
            if q < 1 or q > 15: return await interaction.response.send_message("❌ Max 15.", ephemeral=True)
            await interaction.response.defer(ephemeral=True)
            embed = discord.Embed(title=f"FILAS WS - R$ {self.val.value}", description=f"💲 **VALOR:** R$ {self.val.value}\nClique numa fila abaixo.", color=discord.Color.blue())
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            await interaction.channel.send(embed=embed, view=FilaButtonsView(q, self.val.value))
            await interaction.followup.send("✅ Criado!", ephemeral=True)
        except: pass

# ==============================================================================
# NOVOS COMANDOS (ECONOMIA E LOJA)
# ==============================================================================

@bot.tree.command(name="darcoin", description="💰 Adiciona Coins a um usuário")
async def darcoin(interaction: discord.Interaction, usuario: discord.User, quantidade: int):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    add_coins(usuario.id, quantidade)
    await interaction.response.send_message(f"✅ **{quantidade} Coins** adicionados para {usuario.mention}!", ephemeral=True)

@bot.tree.command(name="darvitoria", description="🏆 Adiciona Vitórias a um usuário")
async def darvitoria(interaction: discord.Interaction, usuario: discord.User, quantidade: int):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    add_wins(usuario.id, quantidade)
    await interaction.response.send_message(f"✅ **{quantidade} Vitórias** adicionadas para {usuario.mention}!", ephemeral=True)

@bot.tree.command(name="perfil", description="👤 Vê seu saldo e vitórias")
async def perfil(interaction: discord.Interaction, usuario: discord.User = None):
    target = usuario or interaction.user
    data = get_user_data(target.id)
    embed = discord.Embed(title=f"Perfil de {target.name}", color=discord.Color.gold())
    embed.add_field(name="💰 Coins", value=f"{data['coins']}", inline=True)
    embed.add_field(name="🏆 Vitórias", value=f"{data['vitorias']}", inline=True)
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="addproduto", description="🛠️ Adiciona um produto à loja")
async def addproduto(interaction: discord.Interaction, nome: str, valor: int, descricao: str):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    configuracao["loja"][nome] = {"valor": valor, "desc": descricao}
    await interaction.response.send_message(f"✅ Produto **{nome}** (R${valor}) adicionado à loja!", ephemeral=True)

@bot.tree.command(name="criarloja", description="🏪 Exibe a loja de produtos")
async def criarloja(interaction: discord.Interaction):
    if not configuracao["loja"]: return await interaction.response.send_message("❌ A loja está vazia. Use /addproduto.", ephemeral=True)
    
    embed = discord.Embed(title="🛒 LOJA WS", description="Confira nossos produtos disponíveis:", color=discord.Color.purple())
    for nome, dados in configuracao["loja"].items():
        embed.add_field(name=f"{nome} - R$ {dados['valor']}", value=dados['desc'], inline=False)
    
    embed.set_footer(text="Para comprar, abra um ticket de suporte.")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ Loja enviada!", ephemeral=True)

@bot.tree.command(name="blacklist", description="🚫 Bane um usuário do bot (Simulação)")
async def blacklist(interaction: discord.Interaction, usuario: discord.User):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    await interaction.response.send_message(f"🚫 {usuario.mention} foi adicionado à Blacklist!", ephemeral=True)

@bot.tree.command(name="addemoji", description="🎨 Adiciona um emoji (Simulação)")
async def addemoji(interaction: discord.Interaction, url: str, nome: str):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    await interaction.response.send_message(f"✅ Emoji **{nome}** adicionado com sucesso!", ephemeral=True)

# ==============================================================================
# COMANDOS PRINCIPAIS E EVENTOS
# ==============================================================================

@bot.tree.command(name="configurar_topicos", description="Define canais")
async def config_top(interaction: discord.Interaction, suporte: discord.TextChannel, reembolso: discord.TextChannel, evento: discord.TextChannel, vagas: discord.TextChannel, filas: discord.TextChannel):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    configuracao["canais"].update({"Suporte": suporte, "Reembolso": reembolso, "Receber Evento": evento, "Vagas de Mediador": vagas, "Filas": filas})
    await interaction.response.send_message("✅ Canais salvos!", ephemeral=True)

@bot.tree.command(name="criar_painel", description="Cria Painel WS Ticket")
async def criar_pnl(interaction: discord.Interaction, staff_1: discord.Role, finalizar_1: discord.Role, staff_2: discord.Role = None, staff_3: discord.Role = None, staff_4: discord.Role = None, finalizar_2: discord.Role = None, finalizar_3: discord.Role = None, finalizar_4: discord.Role = None):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id != DONO_ID: return await interaction.followup.send("❌ Apenas o dono.")
    
    configuracao["cargos"]["ver"] = [c for c in [staff_1, staff_2, staff_3, staff_4] if c]
    configuracao["cargos"]["finalizar"] = [c for c in [finalizar_1, finalizar_2, finalizar_3, finalizar_4] if c]

    desc = ("👉 Abra ticket com o que você precisa abaixo com as informações de guia.\n\n"
            "☞ **TICKET SUPORTE**\n"
            "tire suas dúvidas aqui no ticket suporte, fale com nossos suportes e seja direto com o seu problema.\n\n"
            "☞ **TICKET REEMBOLSO**\n"
            "receba seu reembolso aqui, seja direto e mande comprovante do pagamento.\n\n"
            "☞ **TICKET RECEBE EVENTO**\n"
            "Receba seu evento completos, espera nossos suportes válida seu evento.\n\n"
            "☞ **TICKET VAGA MEDIADOR**\n"
            "seja mediador da org WS, abra ticket e espera nossos suportes recruta.\n\n"
            "→ Evite discussões!")
    
    embed = discord.Embed(title="WS TICKET", description=desc, color=discord.Color.blue())
    embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
    await interaction.channel.send(embed=embed, view=MainView())
    await interaction.followup.send("✅ Painel enviado!", ephemeral=True)

@bot.tree.command(name="criar_filas", description="Cria Painel de Filas")
async def criar_fls(interaction: discord.Interaction):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    await interaction.response.send_modal(FilaConfigModal())

@bot.event
async def on_message(message):
    if message.is_system() and isinstance(message.channel, discord.Thread):
        try: await message.delete()
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"✅ Bot WS Online: {bot.user}")
    bot.add_view(MainView())
    bot.add_view(TicketControlView())
    await bot.tree.sync()

if TOKEN: bot.run(TOKEN)
    
