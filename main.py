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

# --- MEMÓRIA DO BOT ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Suporte": None, "Reembolso": None, "Evento": None, "Vagas": None, "Filas": []},
    "economia": {},
    "loja": {},
    "blacklist": []
}
tickets_abertos = []

# ==============================================================================
# 1. SISTEMA DE FILA / LOBBY (VISUAL RESTAURADO COM ESCOLHA)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, limite: int, modo: str, valor: str):
        super().__init__(timeout=None)
        self.limite = limite
        self.modo = modo
        self.valor = valor
        self.jogadores = [] # Lista de IDs para contagem
        self.dados_visuais = {} # Dicionário {id: "Opção Escolhida"} para o visual
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        # Se for 1v1 (2 pessoas), mostra opções de Gelo (CINZAS)
        if self.limite == 2:
            self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, emoji="🧊", custom_id=f"join_normal"))
            self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, emoji="♾️", custom_id=f"join_infinito"))
        else:
            # Se for 2v2+ (Mais de 2), mostra Entrar (CINZA)
            self.add_item(discord.ui.Button(label="Entrar na Fila", style=discord.ButtonStyle.secondary, emoji="✅", custom_id=f"join_geral"))
        
        # Botão Sair (VERMELHO)
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="✖️", custom_id=f"leave_fila"))

    async def atualizar_embed(self, interaction):
        if not self.jogadores:
            texto_jogadores = "Nenhum jogador na fila"
        else:
            texto_jogadores = ""
            for uid in self.jogadores:
                # Pega a escolha salva (ex: "Gel Infinito") e monta a string
                escolha = self.dados_visuais.get(uid, "Entrou")
                texto_jogadores += f"<@{uid}> | {escolha}\n"

        embed = interaction.message.embeds[0]
        # Atualiza o campo "Jogadores" (Índice 2)
        embed.set_field_at(2, name="👥 | Jogadores", value=f"{texto_jogadores}\n\n**Status:** {len(self.jogadores)}/{self.limite}", inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_partida(self, interaction):
        # Sorteia canal
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

        embed = discord.Embed(
            title="🔥 PARTIDA INICIADA",
            description=f"**Modo:** {self.modo}\n**Valor:** {self.valor}\n\n👉 Enviem o PIX e comprovantes aqui.\nO Mediador irá validar.",
            color=discord.Color.green()
        )
        await thread.send(content=mencoes, embed=embed, view=MatchControlView())
        
        # Reseta fila
        self.jogadores = []
        self.dados_visuais = {}
        await self.atualizar_embed(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = interaction.data["custom_id"]
        uid = interaction.user.id

        # Lógica SAIR
        if cid == "leave_fila":
            if uid in self.jogadores:
                self.jogadores.remove(uid)
                if uid in self.dados_visuais: del self.dados_visuais[uid]
                await interaction.response.defer()
                await self.atualizar_embed(interaction)
            else:
                await interaction.response.send_message("❌ Você não está na fila.", ephemeral=True)
            return True

        # Lógica ENTRAR
        if uid in self.jogadores:
            return await interaction.response.send_message("❌ Você já está nesta fila!", ephemeral=True)
        
        if len(self.jogadores) >= self.limite:
            return await interaction.response.send_message("❌ Fila cheia!", ephemeral=True)

        # Define qual texto vai aparecer do lado do nome
        texto_escolha = ""
        if cid == "join_normal": texto_escolha = "🧊 Gel Normal"
        elif cid == "join_infinito": texto_escolha = "♾️ Gel Infinito"
        elif cid == "join_geral": texto_escolha = "✅ Entrou"

        self.jogadores.append(uid)
        self.dados_visuais[uid] = texto_escolha # Salva a escolha visualmente
        
        await interaction.response.defer()
        await self.atualizar_embed(interaction)

        if len(self.jogadores) >= self.limite:
            await self.iniciar_partida(interaction)
        return True

class CriarFilaModal(discord.ui.Modal, title="Criar Fila Personalizada"):
    nome = discord.ui.TextInput(label="Nome (Ex: 1v1 | Mobile)", placeholder="Digite o modo...")
    valor = discord.ui.TextInput(label="Valor (Ex: R$ 1,00)", placeholder="Digite o valor...")
    qtd = discord.ui.TextInput(label="Jogadores (2 ou 4)", placeholder="2", max_length=1)

    async def on_submit(self, interaction):
        try:
            lim = int(self.qtd.value)
            if lim < 2: return await interaction.response.send_message("Mínimo 2 jogadores.", ephemeral=True)
            
            await interaction.response.defer(ephemeral=True)
            
            # Embed Visual igual ao solicitado
            embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
            embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
            embed.add_field(name="💸 | Valor", value=self.valor.value, inline=False)
            embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
            
            # Imagem do Astronauta
            embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
            
            view = FilaLobbyView(lim, self.nome.value, self.valor.value)
            await interaction.channel.send(embed=embed, view=view)
            await interaction.followup.send("✅ Fila criada!", ephemeral=True)
        except: pass

# ==============================================================================
# 2. CONTROLES DE TICKET (BOTOES INTERNOS)
# ==============================================================================

class MatchControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_v_match")
    async def v(self, i, b):
        if i.user.guild_permissions.manage_messages or i.user.id == DONO_ID:
            await i.response.send_message(f"✅ **Pagamento Validado por {i.user.mention}!**", ephemeral=False)
    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_c_match")
    async def c(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.channel.delete()

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Finalizar", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_fin_main")
    async def f(self, i, b):
        # Verifica cargos configurados
        user = i.user
        permitido = user.id == DONO_ID or user.guild_permissions.manage_messages
        if not permitido:
            for cargo in configuracao["cargos"]["finalizar"]:
                if cargo in user.roles: permitido = True; break
        
        if permitido: await i.channel.delete()
        else: await i.response.send_message("❌ Sem permissão.", ephemeral=True)

    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.secondary, emoji="🛡️", custom_id="btn_ass_main")
    async def a(self, i, b): await i.channel.send(f"{i.user.mention} assumiu!"); await i.response.send_message("Ok", ephemeral=True)
    
    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="🛠️", custom_id="btn_stf_main")
    async def st(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.response.send_message("Menu Staff", view=StaffActionsView(), ephemeral=True)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_out_main")
    async def s(self, i, b): await i.channel.remove_user(i.user)

# ==============================================================================
# 3. PAINEL STAFF
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
        options = [discord.SelectOption(label="Renomear Ticket", emoji="📝"), discord.SelectOption(label="Adicionar Membro", emoji="👤"), discord.SelectOption(label="Notificar", emoji="🔔")]
        super().__init__(placeholder="Selecione", options=options)
    async def callback(self, i):
        if self.values[0] == "Renomear Ticket": await i.response.send_modal(RenomearModal())
        elif self.values[0] == "Adicionar Membro": await i.response.send_modal(AddUserModal())
        elif self.values[0] == "Notificar": await i.channel.send(f"{i.user.mention} chamando! @here"); await i.response.send_message("Ok", ephemeral=True)

class StaffActionsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=60); self.add_item(StaffActionsDropdown())

# ==============================================================================
# 4. PAINEL PRINCIPAL (TICKET GERAL)
# ==============================================================================
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️"), 
            discord.SelectOption(label="Reembolso", emoji="💰"),
            discord.SelectOption(label="Receber Evento", emoji="💫"), 
            discord.SelectOption(label="Vagas de Mediador", emoji="👑")
        ]
        super().__init__(placeholder="Selecione uma função", options=options, custom_id="main_drop")
    async def callback(self, i):
        try:
            # Mapeamento para os nomes salvos na config
            mapa = {"Suporte": "Suporte", "Reembolso": "Reembolso", "Receber Evento": "Evento", "Vagas de Mediador": "Vagas"}
            chave = mapa[self.values[0]]
            canal = configuracao["canais"].get(chave) or i.channel
            
            th = await canal.create_thread(name=f"{chave}-{i.user.name}", type=discord.ChannelType.private_thread)
            await th.add_user(i.user); tickets_abertos.append(i.user.id)
            
            embed = discord.Embed(description="Aguarde o atendimento.", color=discord.Color.dark_grey())
            embed.add_field(name="Horário:", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>")
            
            mencao = f"{i.user.mention} "
            for c in configuracao["cargos"]["ver"]: mencao += f" {c.mention}"
            
            await th.send(mencao, embed=embed, view=TicketControlView())
            await i.response.send_message(f"Ticket aberto: <#{th.id}>", ephemeral=True)
        except: pass

class MainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketDropdown())

# ==============================================================================
# 5. COMANDOS (RESTAURADOS E COM 4 CARGOS)
# ==============================================================================

@bot.tree.command(name="criar_painel", description="Cria o painel WS TICKET (Até 4 cargos)")
@app_commands.describe(
    staff_1="Cargo ver 1", staff_2="Cargo ver 2", staff_3="Cargo ver 3", staff_4="Cargo ver 4",
    finalizar_1="Cargo fim 1", finalizar_2="Cargo fim 2", finalizar_3="Cargo fim 3", finalizar_4="Cargo fim 4"
)
async def criar_painel(
    interaction: discord.Interaction, 
    staff_1: discord.Role, finalizar_1: discord.Role,
    staff_2: discord.Role = None, staff_3: discord.Role = None, staff_4: discord.Role = None,
    finalizar_2: discord.Role = None, finalizar_3: discord.Role = None, finalizar_4: discord.Role = None
):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id != DONO_ID: return await interaction.followup.send("❌ Apenas o dono.")
    
    # Salva listas de cargos
    configuracao["cargos"]["ver"] = [c for c in [staff_1, staff_2, staff_3, staff_4] if c]
    configuracao["cargos"]["finalizar"] = [c for c in [finalizar_1, finalizar_2, finalizar_3, finalizar_4] if c]

    # DESCRIÇÃO COMPLETA RESTAURADA
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
    embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
    
    await interaction.channel.send(embed=embed, view=MainView())
    await interaction.followup.send("✅ Painel completo enviado!", ephemeral=True)

@bot.tree.command(name="criarfila", description="Cria Lobby de Apostas")
async def criarfila(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    await i.response.send_modal(CriarFilaModal())

# Outros comandos
@bot.tree.command(name="darcoin", description="💰 Adiciona coins")
async def darcoin(i: discord.Interaction, user: discord.User, qtd: int):
    if i.user.id != DONO_ID: return
    val = configuracao["economia"].get(user.id, 0) + qtd
    configuracao["economia"][user.id] = val
    await i.response.send_message(f"✅ {qtd} coins para {user.mention}", ephemeral=True)

@bot.tree.command(name="perfil", description="👤 Ver saldo")
async def perfil(i: discord.Interaction, user: discord.User = None):
    t = user or i.user
    val = configuracao["economia"].get(t.id, 0)
    await i.response.send_message(embed=discord.Embed(title=f"Perfil {t.name}", description=f"💰 Coins: {val}", color=discord.Color.gold()))

@bot.tree.command(name="addproduto", description="Adicionar a loja")
async def addprod(i: discord.Interaction, nome: str, valor: int, desc: str):
    if i.user.id != DONO_ID: return
    configuracao["loja"][nome] = {"valor": valor, "desc": desc}
    await i.response.send_message("✅ Adicionado!", ephemeral=True)

@bot.tree.command(name="criarloja", description="Mostra loja")
async def criarloja(i: discord.Interaction):
    if not configuracao["loja"]: return await i.response.send_message("Vazia", ephemeral=True)
    e = discord.Embed(title="🛒 LOJA WS", color=discord.Color.purple())
    for n,d in configuracao["loja"].items(): e.add_field(name=f"{n} - {d['valor']}", value=d['desc'], inline=False)
    await i.channel.send(embed=e)
    await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="blacklist", description="Banir do bot")
async def blacklist(i: discord.Interaction, user: discord.User):
    if i.user.id != DONO_ID: return
    configuracao["blacklist"].append(user.id)
    await i.response.send_message(f"🚫 {user.mention} Blacklisted", ephemeral=True)

@bot.tree.command(name="configurar_tickets_gerais", description="Canais do Painel Principal")
async def cfg_g(i: discord.Interaction, suporte: discord.TextChannel, reembolso: discord.TextChannel, evento: discord.TextChannel, vagas: discord.TextChannel):
    if i.user.id != DONO_ID: return
    configuracao["canais"].update({"Suporte": suporte, "Reembolso": reembolso, "Evento": evento, "Vagas": vagas})
    await i.response.send_message("✅ Configurado!", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="3 Canais de Apostas (Sorteio)")
async def cfg_f(i: discord.Interaction, c1: discord.TextChannel, c2: discord.TextChannel=None, c3: discord.TextChannel=None):
    if i.user.id != DONO_ID: return
    l = [c1]
    if c2: l.append(c2)
    if c3: l.append(c3)
    configuracao["canais"]["Filas"] = l
    await i.response.send_message(f"✅ {len(l)} canais de fila definidos.", ephemeral=True)

@bot.event
async def on_message(message):
    # Apaga msg de sistema (Fulano entrou no ticket)
    if message.is_system() and isinstance(message.channel, discord.Thread):
        try: await message.delete()
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
        
