import discord
import os
import asyncio
import datetime
import traceback
import random
from discord.ext import commands
from discord import app_commands

TOKEN = os.getenv("DISCORD_TOKEN")
DONO_ID = 1461858587080130663

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- SISTEMA DE DADOS (MEMÓRIA) ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Suporte": None, "Reembolso": None, "Evento": None, "Vagas": None, "Filas": []},
    "economia": {}, # {user_id: coins}
    "loja": {},     # {nome: {valor, desc}}
    "blacklist": [] # [user_id]
}
tickets_abertos = []

# ==============================================================================
# 1. SISTEMA DE LOBBY / FILA INTERATIVA (COM VISUAL DE ESCOLHA)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, limite: int, modo: str, valor: str):
        super().__init__(timeout=None)
        self.limite = limite
        self.modo = modo
        self.valor = valor
        self.jogadores = [] # Lista de IDs
        self.dados_jogadores = {} # {id: "Nome | Escolha"}
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        # Se for 1v1 (2 pessoas), botões de Gelo (CINZAS)
        if self.limite == 2:
            self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, emoji="🧊", custom_id=f"join_normal_{self.modo}"))
            self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, emoji="♾️", custom_id=f"join_infinito_{self.modo}"))
        else:
            # Se for 2v2+, botão Entrar (CINZA)
            self.add_item(discord.ui.Button(label="Entrar na Fila", style=discord.ButtonStyle.secondary, emoji="✅", custom_id=f"join_geral_{self.modo}"))
        
        # Botão Sair (VERMELHO)
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="✖️", custom_id=f"leave_{self.modo}"))

    async def atualizar_embed(self, interaction):
        # Monta a lista visual: "@Fulano | Gelo Infinito"
        if not self.jogadores:
            lista_texto = "Nenhum jogador na fila"
        else:
            lista_texto = ""
            for uid in self.jogadores:
                info = self.dados_jogadores.get(uid, "Entrou")
                lista_texto += f"👤 {info}\n"

        embed = interaction.message.embeds[0]
        # Atualiza o campo de jogadores
        embed.set_field_at(2, name="👥 | Jogadores", value=f"{lista_texto}\n\n**Status:** {len(self.jogadores)}/{self.limite}", inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_partida(self, interaction):
        canais = configuracao["canais"].get("Filas", [])
        canal_destino = random.choice(canais) if canais else interaction.channel
        
        await interaction.channel.send(f"✅ **Fila Cheia!** Abrindo ticket em {canal_destino.mention}...", delete_after=5)
        
        thread = await canal_destino.create_thread(name=f"MATCH-{self.modo}-{len(tickets_abertos)}", type=discord.ChannelType.private_thread)
        
        mencoes = ""
        for uid in self.jogadores:
            u = interaction.guild.get_member(uid)
            if u:
                await thread.add_user(u)
                mencoes += f"{u.mention} "
                tickets_abertos.append(uid)
        
        for c in configuracao["cargos"]["ver"]: mencoes += f"{c.mention} "

        embed = discord.Embed(title="🔥 PARTIDA INICIADA", description=f"**Modo:** {self.modo}\n**Valor:** {self.valor}\n\nValidem o pagamento abaixo.", color=discord.Color.green())
        await thread.send(content=mencoes, embed=embed, view=MatchControlView())
        
        # Reseta
        self.jogadores = []
        self.dados_jogadores = {}
        await self.atualizar_embed(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = interaction.data["custom_id"]
        uid = interaction.user.id
        nome = interaction.user.display_name

        if "leave" in cid:
            if uid in self.jogadores:
                self.jogadores.remove(uid)
                del self.dados_jogadores[uid]
                await interaction.response.defer()
                await self.atualizar_embed(interaction)
            else:
                await interaction.response.send_message("❌ Você não está na fila.", ephemeral=True)
            return True

        if uid in self.jogadores:
            return await interaction.response.send_message("❌ Você já está na fila!", ephemeral=True)
        
        if len(self.jogadores) >= self.limite:
            return await interaction.response.send_message("❌ Fila cheia!", ephemeral=True)

        # Define a escolha baseada no botão clicado
        escolha = ""
        if "normal" in cid: escolha = "🧊 Gel Normal"
        elif "infinito" in cid: escolha = "♾️ Gel Infinito"
        else: escolha = "✅ Entrou"

        self.jogadores.append(uid)
        self.dados_jogadores[uid] = f"{interaction.user.mention} | {escolha}" # Salva com a escolha
        
        await interaction.response.defer()
        await self.atualizar_embed(interaction)

        if len(self.jogadores) >= self.limite:
            await self.iniciar_partida(interaction)
        return True

class CriarFilaModal(discord.ui.Modal, title="Criar Fila"):
    nome = discord.ui.TextInput(label="Nome (Ex: 1v1 | Mobile)", placeholder="Digite o modo...")
    valor = discord.ui.TextInput(label="Valor (Ex: R$ 5,00)", placeholder="Digite o valor...")
    qtd = discord.ui.TextInput(label="Jogadores (2 ou 4)", placeholder="2", max_length=1)

    async def on_submit(self, interaction):
        try:
            lim = int(self.qtd.value)
            if lim < 2: return await interaction.response.send_message("Mínimo 2.", ephemeral=True)
            
            await interaction.response.defer(ephemeral=True)
            embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
            embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
            embed.add_field(name="💸 | Valor", value=self.valor.value, inline=False)
            embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            
            view = FilaLobbyView(lim, self.nome.value, self.valor.value)
            await interaction.channel.send(embed=embed, view=view)
            await interaction.followup.send("✅ Fila criada!", ephemeral=True)
        except: pass

# ==============================================================================
# 2. CONTROLES DE TICKET (SUPORTE E MATCH)
# ==============================================================================

class MatchControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_v_pay")
    async def v(self, i, b):
        if i.user.guild_permissions.manage_messages or i.user.id == DONO_ID:
            await i.response.send_message(f"✅ **Validado por {i.user.mention}!**", ephemeral=False)
    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_c_match")
    async def c(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.channel.delete()

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Finalizar", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_fin_t")
    async def f(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.channel.delete()
    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_ass_t")
    async def a(self, i, b): await i.channel.send(f"{i.user.mention} assumiu!"); await i.response.send_message("Ok", ephemeral=True)
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_out_t")
    async def s(self, i, b): await i.channel.remove_user(i.user)
    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_stf_t")
    async def st(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.response.send_message("Menu Staff", view=StaffActionsView(), ephemeral=True)

# ==============================================================================
# 3. PAINEL STAFF (MENU DROPDOWN)
# ==============================================================================
class RenomearModal(discord.ui.Modal, title="Renomear"):
    nome = discord.ui.TextInput(label="Novo Nome")
    async def on_submit(self, i): await i.channel.edit(name=self.nome.value); await i.response.send_message("Feito!", ephemeral=True)

class AddUserModal(discord.ui.Modal, title="Add User"):
    uid = discord.ui.TextInput(label="ID")
    async def on_submit(self, i): 
        try: u = await i.guild.fetch_member(int(self.uid.value)); await i.channel.add_user(u); await i.response.send_message("Add!", ephemeral=True)
        except: await i.response.send_message("Erro ID", ephemeral=True)

class StaffActionsDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Renomear Ticket", emoji="📝"),
            discord.SelectOption(label="Adicionar Membro", emoji="👤"),
            discord.SelectOption(label="Notificar", emoji="🔔")
        ]
        super().__init__(placeholder="Selecione", options=options)
    async def callback(self, i):
        if self.values[0] == "Renomear Ticket": await i.response.send_modal(RenomearModal())
        elif self.values[0] == "Adicionar Membro": await i.response.send_modal(AddUserModal())
        elif self.values[0] == "Notificar": await i.channel.send(f"{i.user.mention} chamando! @here"); await i.response.send_message("Ok", ephemeral=True)

class StaffActionsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60); self.add_item(StaffActionsDropdown())

# ==============================================================================
# 4. PAINEL TICKET PRINCIPAL
# ==============================================================================
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Suporte", emoji="🛠️"), discord.SelectOption(label="Reembolso", emoji="💰"),
                   discord.SelectOption(label="Evento", emoji="💫"), discord.SelectOption(label="Vagas", emoji="👑")]
        super().__init__(placeholder="Selecione", options=options, custom_id="main_drop")
    async def callback(self, i):
        cat = self.values[0]
        ch = configuracao["canais"].get(cat) or i.channel
        th = await ch.create_thread(name=f"{cat}-{i.user.name}", type=discord.ChannelType.private_thread)
        await th.add_user(i.user); tickets_abertos.append(i.user.id)
        
        embed = discord.Embed(description="Aguarde.", color=discord.Color.dark_grey())
        men = f"{i.user.mention} " + " ".join([c.mention for c in configuracao["cargos"]["ver"]])
        await th.send(men, embed=embed, view=TicketControlView())
        await i.response.send_message(f"Ticket: <#{th.id}>", ephemeral=True)

class MainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketDropdown())

# ==============================================================================
# 5. COMANDOS RESTAURADOS (ECONOMIA, LOJA, MODERAÇÃO)
# ==============================================================================

@bot.tree.command(name="darcoin", description="💰 Adiciona coins")
async def darcoin(i: discord.Interaction, user: discord.User, qtd: int):
    if i.user.id != DONO_ID: return
    atual = configuracao["economia"].get(user.id, 0)
    configuracao["economia"][user.id] = atual + qtd
    await i.response.send_message(f"✅ Dei {qtd} coins para {user.mention}", ephemeral=True)

@bot.tree.command(name="perfil", description="👤 Ver perfil")
async def perfil(i: discord.Interaction, user: discord.User = None):
    target = user or i.user
    coins = configuracao["economia"].get(target.id, 0)
    embed = discord.Embed(title=f"Perfil de {target.name}", color=discord.Color.gold())
    embed.add_field(name="💰 Coins", value=str(coins))
    await i.response.send_message(embed=embed)

@bot.tree.command(name="addproduto", description="🛠️ Add produto na loja")
async def addproduto(i: discord.Interaction, nome: str, valor: int, desc: str):
    if i.user.id != DONO_ID: return
    configuracao["loja"][nome] = {"valor": valor, "desc": desc}
    await i.response.send_message(f"✅ Produto {nome} adicionado!", ephemeral=True)

@bot.tree.command(name="criarloja", description="🏪 Mostra a loja")
async def criarloja(i: discord.Interaction):
    if not configuracao["loja"]: return await i.response.send_message("Loja vazia", ephemeral=True)
    embed = discord.Embed(title="🛒 LOJA WS", color=discord.Color.purple())
    for n, d in configuracao["loja"].items(): embed.add_field(name=f"{n} - {d['valor']} coins", value=d['desc'], inline=False)
    await i.channel.send(embed=embed)
    await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="clear", description="🧹 Limpa mensagens")
async def clear(i: discord.Interaction, qtd: int):
    if i.user.guild_permissions.manage_messages:
        await i.channel.purge(limit=qtd)
        await i.response.send_message(f"🧹 Limpei {qtd} mensagens.", ephemeral=True)

@bot.tree.command(name="ban", description="🚫 Banir usuário")
async def ban(i: discord.Interaction, user: discord.Member, motivo: str = "Sem motivo"):
    if i.user.guild_permissions.ban_members:
        await user.ban(reason=motivo)
        await i.response.send_message(f"🚫 {user.mention} banido!", ephemeral=True)

@bot.tree.command(name="blacklist", description="🚫 Adicionar a blacklist")
async def blacklist(i: discord.Interaction, user: discord.User):
    if i.user.id != DONO_ID: return
    configuracao["blacklist"].append(user.id)
    await i.response.send_message(f"🚫 {user.mention} na blacklist!", ephemeral=True)

@bot.tree.command(name="lock", description="🔒 Trancar canal")
async def lock(i: discord.Interaction):
    if i.user.guild_permissions.manage_channels:
        await i.channel.set_permissions(i.guild.default_role, send_messages=False)
        await i.response.send_message("🔒 Canal trancado.", ephemeral=True)

@bot.tree.command(name="unlock", description="🔓 Destrancar canal")
async def unlock(i: discord.Interaction):
    if i.user.guild_permissions.manage_channels:
        await i.channel.set_permissions(i.guild.default_role, send_messages=True)
        await i.response.send_message("🔓 Canal destrancado.", ephemeral=True)

# ==============================================================================
# 6. CONFIGURAÇÃO E START
# ==============================================================================

@bot.tree.command(name="criarfila", description="Cria Painel de Aposta")
async def criarfila(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    await i.response.send_modal(CriarFilaModal())

@bot.tree.command(name="criar_painel", description="Cria Painel Principal")
async def criar_painel(i: discord.Interaction, staff: discord.Role):
    if i.user.id != DONO_ID: return
    configuracao["cargos"]["ver"] = [staff]
    embed = discord.Embed(title="WS TICKET", description="Abra seu ticket.", color=discord.Color.blue())
    embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
    await i.channel.send(embed=embed, view=MainView())
    await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="configurar_tickets_gerais", description="Configura Suporte")
async def cfg_g(i: discord.Interaction, suporte: discord.TextChannel, reembolso: discord.TextChannel, evento: discord.TextChannel, vagas: discord.TextChannel):
    if i.user.id != DONO_ID: return
    configuracao["canais"].update({"Suporte": suporte, "Reembolso": reembolso, "Evento": evento, "Vagas": vagas})
    await i.response.send_message("✅ Configurado!", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="Configura Canais de Aposta (Aleatórios)")
async def cfg_f(i: discord.Interaction, c1: discord.TextChannel, c2: discord.TextChannel = None, c3: discord.TextChannel = None):
    if i.user.id != DONO_ID: return
    lista = [c1]
    if c2: lista.append(c2)
    if c3: lista.append(c3)
    configuracao["canais"]["Filas"] = lista
    await i.response.send_message(f"✅ Canais de aposta: {len(lista)} definidos.", ephemeral=True)

@bot.event
async def on_message(message):
    if message.is_system() and isinstance(message.channel, discord.Thread):
        try: await message.delete()
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
        
