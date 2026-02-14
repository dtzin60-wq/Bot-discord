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

# --- CONFIGURAÇÃO ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    # CANAIS SEPARADOS:
    # 'Geral' guarda os canais fixos do painel principal (Suporte, Reembolso...)
    # 'Filas' guarda a lista de até 3 canais para as apostas (Sorteio)
    "canais": {
        "Suporte": None, 
        "Reembolso": None, 
        "Evento": None, 
        "Vagas": None,
        "Filas": [] 
    }
}
tickets_abertos = []

# ==============================================================================
# SISTEMA 1: LOBBY DE APOSTAS (FILAS)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, limite: int, modo: str, valor: str):
        super().__init__(timeout=None)
        self.limite = limite
        self.modo = modo
        self.valor = valor
        self.jogadores = []
        self.nomes = []
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        # Botões Cinzas (Secondary)
        if self.limite == 2: # 1v1
            self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id=f"join_n_{self.modo}"))
            self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, custom_id=f"join_i_{self.modo}"))
        else: # 2v2+
            self.add_item(discord.ui.Button(label="Entrar na Fila", style=discord.ButtonStyle.secondary, custom_id=f"join_g_{self.modo}"))
        
        # Botão Vermelho (Danger)
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id=f"leave_f_{self.modo}"))

    async def atualizar_embed(self, interaction):
        lista = "\n".join([f"👤 {n}" for n in self.nomes]) if self.nomes else "Nenhum jogador na fila"
        embed = interaction.message.embeds[0]
        # Atualiza campo de Jogadores (Índice 2)
        embed.set_field_at(2, name="👥 | Jogadores", value=f"{lista}\n\n**Status:** {len(self.jogadores)}/{self.limite}", inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_partida(self, interaction):
        # --- LÓGICA ALEATÓRIA (SÓ PARA FILAS) ---
        canais_filas = configuracao["canais"].get("Filas", [])
        
        if not canais_filas:
            # Se esqueceu de configurar, usa o atual
            canal_destino = interaction.channel
        else:
            # Sorteia 1 dos 3 canais configurados
            canal_destino = random.choice(canais_filas)
        
        await interaction.channel.send(f"✅ **Fila Cheia!** Abrindo ticket em {canal_destino.mention}...", delete_after=5)
        
        thread = await canal_destino.create_thread(
            name=f"MATCH-{self.modo}-{len(tickets_abertos)+1}", 
            type=discord.ChannelType.private_thread
        )
        
        mencoes = ""
        for uid in self.jogadores:
            u = interaction.guild.get_member(uid)
            if u:
                await thread.add_user(u)
                mencoes += f"{u.mention} "
                tickets_abertos.append(uid)
        
        # Marca a Staff
        for c in configuracao["cargos"]["ver"]: mencoes += f"{c.mention} "

        embed_match = discord.Embed(
            title="🔥 PARTIDA ENCONTRADA", 
            description=f"**Modo:** {self.modo}\n**Valor:** {self.valor}\n\n👉 Enviem os PIX e comprovantes aqui.\nO Mediador irá validar em breve.", 
            color=discord.Color.green()
        )
        await thread.send(content=mencoes, embed=embed_match, view=MatchControlView())
        
        # Limpa visualmente para a próxima
        self.jogadores = []
        self.nomes = []
        await self.atualizar_embed(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = interaction.data["custom_id"]
        
        # SAIR
        if "leave_f" in cid:
            if interaction.user.id in self.jogadores:
                idx = self.jogadores.index(interaction.user.id)
                self.jogadores.pop(idx); self.nomes.pop(idx)
                await interaction.response.defer(); await self.atualizar_embed(interaction)
            else:
                await interaction.response.send_message("❌ Você não está na fila.", ephemeral=True)
            return True

        # ENTRAR
        if interaction.user.id in self.jogadores:
            return await interaction.response.send_message("❌ Já está na fila!", ephemeral=True)
        if len(self.jogadores) >= self.limite:
            return await interaction.response.send_message("❌ Fila cheia!", ephemeral=True)

        self.jogadores.append(interaction.user.id)
        self.nomes.append(interaction.user.display_name)
        await interaction.response.defer(); await self.atualizar_embed(interaction)
        
        if len(self.jogadores) >= self.limite: await self.iniciar_partida(interaction)
        return True

class CriarFilaModal(discord.ui.Modal, title="Criar Fila Personalizada"):
    nome = discord.ui.TextInput(label="Nome da Fila", placeholder="Ex: 1v1 | Emulador")
    valor = discord.ui.TextInput(label="Valor", placeholder="Ex: R$ 5,00")
    limite = discord.ui.TextInput(label="Jogadores (2 ou 4)", placeholder="2", max_length=1)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            lim = int(self.limite.value)
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
# SISTEMA 2: TICKET GERAL (PAINEL PRINCIPAL)
# ==============================================================================

class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", emoji="🛠️"),
            discord.SelectOption(label="Reembolso", emoji="💰"),
            discord.SelectOption(label="Evento", emoji="💫"),
            discord.SelectOption(label="Vagas", emoji="👑")
        ]
        super().__init__(placeholder="Selecione", options=options, custom_id="main_drop")

    async def callback(self, i):
        # Mapeamento do nome da opção para a chave no dicionário de canais
        mapa = {"Suporte": "Suporte", "Reembolso": "Reembolso", "Evento": "Evento", "Vagas": "Vagas"}
        chave = mapa[self.values[0]]
        
        # Pega o canal fixo configurado
        canal = configuracao["canais"].get(chave)
        
        if not canal:
            return await i.response.send_message(f"⚠️ Canal de **{self.values[0]}** não configurado!", ephemeral=True)
            
        th = await canal.create_thread(name=f"{self.values[0]}-{i.user.name}", type=discord.ChannelType.private_thread)
        await th.add_user(i.user)
        tickets_abertos.append(i.user.id)
        
        await i.response.send_message(f"✅ Ticket aberto! <#{th.id}>", ephemeral=True)
        
        embed = discord.Embed(description="Aguarde o atendimento.", color=discord.Color.dark_grey())
        mencao = f"{i.user.mention}"
        for c in configuracao["cargos"]["ver"]: mencao += f" {c.mention}"
        
        await th.send(content=mencao, embed=embed, view=TicketControlView())

class MainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketDropdown())

# ==============================================================================
# VIEWS DE CONTROLE (BOTÕES DENTRO DOS TICKETS)
# ==============================================================================

class MatchControlView(discord.ui.View): # Para as filas de aposta
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_val")
    async def v(self, i, b):
        if i.user.id == DONO_ID or i.user.guild_permissions.manage_messages:
            await i.response.send_message(f"✅ Validado por {i.user.mention}!", ephemeral=False)
    @discord.ui.button(label="Fechar", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_cl")
    async def c(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.channel.delete()

class TicketControlView(discord.ui.View): # Para o suporte geral
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Finalizar", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_fin")
    async def f(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.channel.delete()
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="✖️", custom_id="btn_out")
    async def s(self, i, b): await i.channel.remove_user(i.user)

# ==============================================================================
# COMANDOS DE CONFIGURAÇÃO (SEPARADOS)
# ==============================================================================

@bot.tree.command(name="configurar_tickets_gerais", description="Canais fixos do Painel Principal")
async def cfg_geral(i: discord.Interaction, suporte: discord.TextChannel, reembolso: discord.TextChannel, evento: discord.TextChannel, vagas: discord.TextChannel):
    if i.user.id != DONO_ID: return
    configuracao["canais"].update({"Suporte": suporte, "Reembolso": reembolso, "Evento": evento, "Vagas": vagas})
    await i.response.send_message("✅ Canais do Painel Principal configurados!", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="Escolha 3 canais aleatórios para as Apostas")
async def cfg_filas(i: discord.Interaction, canal_1: discord.TextChannel, canal_2: discord.TextChannel = None, canal_3: discord.TextChannel = None):
    if i.user.id != DONO_ID: return
    
    lista = [canal_1]
    if canal_2: lista.append(canal_2)
    if canal_3: lista.append(canal_3)
    
    configuracao["canais"]["Filas"] = lista
    nomes = ", ".join([c.mention for c in lista])
    await i.response.send_message(f"✅ **Canais de Aposta (Aleatórios):** {nomes}", ephemeral=True)

# ==============================================================================
# OUTROS COMANDOS
# ==============================================================================

@bot.tree.command(name="criarfila", description="Cria Lobby de Apostas")
async def criarfila(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    await i.response.send_modal(CriarFilaModal())

@bot.tree.command(name="criar_painel", description="Painel WS TICKET Principal")
async def criar_painel(i: discord.Interaction, staff_role: discord.Role):
    if i.user.id != DONO_ID: return
    configuracao["cargos"]["ver"] = [staff_role]
    embed = discord.Embed(title="WS TICKET", description="Abra seu ticket.", color=discord.Color.blue())
    embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
    await i.channel.send(embed=embed, view=MainView())
    await i.response.send_message("✅", ephemeral=True)

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
            
