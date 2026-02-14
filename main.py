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

# --- MEMÓRIA ---
configuracao = {
    "cargos": {"ver": [], "finalizar": []},
    "canais": {"Filas": []}, # Apenas canais de aposta
    "economia": {},
    "loja": {},
    "blacklist": []
}
tickets_abertos = []
mediadores_ativos = [] 

# ==============================================================================
# 1. SISTEMA DE FILA / LOBBY (1v1)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, modo: str, valor: str):
        super().__init__(timeout=None)
        self.limite = 2 
        self.modo = modo
        self.valor = valor
        self.jogadores = [] 
        self.dados_visuais = {} 
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id=f"join_normal"))
        self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, emoji="♾️", custom_id=f"join_infinito"))
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="✖️", custom_id=f"leave_fila"))

    async def atualizar_embed(self, interaction):
        if not self.jogadores:
            texto_jogadores = "Nenhum jogador na fila"
        else:
            texto_jogadores = ""
            for uid in self.jogadores:
                escolha = self.dados_visuais.get(uid, "Entrou")
                texto_jogadores += f"<@{uid}> | {escolha}\n"

        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="👥 | Jogadores", value=f"{texto_jogadores}", inline=False)
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
        
        # Marca staff configurada (opcional, se houver)
        for c in configuracao["cargos"].get("ver", []): mencoes += f"{c.mention} "

        embed = discord.Embed(
            title="🔥 PARTIDA INICIADA",
            description=f"**Modo:** {self.modo}\n**Valor:** {self.valor}\n\n👉 Enviem o PIX e comprovantes aqui.\nO Mediador irá validar.",
            color=discord.Color.green()
        )
        await thread.send(content=mencoes, embed=embed, view=MatchControlView())
        
        self.jogadores = []
        self.dados_visuais = {}
        await self.atualizar_embed(interaction)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = interaction.data["custom_id"]
        uid = interaction.user.id

        if cid == "leave_fila":
            if uid in self.jogadores:
                self.jogadores.remove(uid)
                if uid in self.dados_visuais: del self.dados_visuais[uid]
                await interaction.response.defer()
                await self.atualizar_embed(interaction)
            else:
                await interaction.response.send_message("❌ Você não está na fila.", ephemeral=True)
            return True

        if uid in self.jogadores:
            return await interaction.response.send_message("❌ Você já está nesta fila!", ephemeral=True)
        if len(self.jogadores) >= self.limite:
            return await interaction.response.send_message("❌ Fila cheia!", ephemeral=True)

        texto_escolha = ""
        if cid == "join_normal": texto_escolha = "Gel Normal"
        elif cid == "join_infinito": texto_escolha = "♾️ Gel Infinito"

        self.jogadores.append(uid)
        self.dados_visuais[uid] = texto_escolha 
        
        await interaction.response.defer()
        await self.atualizar_embed(interaction)

        if len(self.jogadores) >= self.limite:
            await self.iniciar_partida(interaction)
        return True

class CriarFilaModal(discord.ui.Modal, title="Criar Fila (1v1)"):
    nome = discord.ui.TextInput(label="Nome (Ex: 1v1 | Mobile)", placeholder="Digite o modo...")
    valor = discord.ui.TextInput(label="Valor (Ex: R$ 1,00)", placeholder="Digite o valor...")

    async def on_submit(self, interaction):
        await interaction.response.defer(ephemeral=True)
        
        embed = discord.Embed(title=f"{self.nome.value} | WS APOSTAS", color=discord.Color.blue())
        embed.add_field(name="👑 | Modo", value=self.nome.value, inline=False)
        embed.add_field(name="💸 | Valor", value=self.valor.value, inline=False)
        embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
        
        embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
        
        view = FilaLobbyView(self.nome.value, self.valor.value)
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("Criando fila...", ephemeral=True)

# ==============================================================================
# 2. SISTEMA DE FILA DE MEDIADORES
# ==============================================================================

class RemoverMediadorModal(discord.ui.Modal, title="Remover Mediador"):
    user_id = discord.ui.TextInput(label="ID do Mediador", placeholder="Cole o ID aqui...")
    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value)
            if uid in mediadores_ativos:
                mediadores_ativos.remove(uid)
                view = MediadorQueueView()
                await view.atualizar_embed(interaction)
                await interaction.followup.send(f"✅ Mediador <@{uid}> removido da fila!", ephemeral=True)
            else: await interaction.response.send_message("❌ Esse ID não está na fila.", ephemeral=True)
        except: await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

class MediadorQueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢", custom_id="med_join"))
        self.add_item(discord.ui.Button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="med_leave"))
        self.add_item(discord.ui.Button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_kick"))
        self.add_item(discord.ui.Button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_staff"))

    async def enviar_confirmacao(self, interaction, entrou: bool):
        embed = discord.Embed(description=f"✅ **Ação realizada com sucesso!**\n\n{interaction.user.mention}, a sua operação foi concluída com êxito.\n↪ Você {'entrou na' if entrou else 'saiu da'} fila com sucesso.", color=discord.Color.from_rgb(43, 45, 49))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def atualizar_embed(self, interaction):
        if not mediadores_ativos: texto_lista = "Nenhum mediador na fila."
        else:
            texto_lista = ""
            for i, uid in enumerate(mediadores_ativos, 1): texto_lista += f"**{i}** • <@{uid}> `{uid}`\n"

        embed = interaction.message.embeds[0]
        embed.description = f"**Entre na fila para começar a mediar suas filas**\n\n{texto_lista}"
        if interaction.response.is_done(): await interaction.message.edit(embed=embed, view=self)
        else: await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = interaction.data["custom_id"]
        uid = interaction.user.id
        if cid == "med_join":
            if uid in mediadores_ativos: await interaction.response.send_message("❌ Você já está na fila.", ephemeral=True)
            else: mediadores_ativos.append(uid); await self.enviar_confirmacao(interaction, True); await self.atualizar_embed(interaction)
        elif cid == "med_leave":
            if uid in mediadores_ativos: mediadores_ativos.remove(uid); await self.enviar_confirmacao(interaction, False); await self.atualizar_embed(interaction)
            else: await interaction.response.send_message("❌ Você não está na fila.", ephemeral=True)
        elif cid == "med_kick":
            if interaction.user.id == DONO_ID or interaction.user.guild_permissions.administrator: await interaction.response.send_modal(RemoverMediadorModal())
            else: await interaction.response.send_message("❌ Apenas Admins.", ephemeral=True)
        elif cid == "med_staff":
            if interaction.user.guild_permissions.manage_messages: await interaction.response.send_message("Menu Staff", view=StaffActionsView(), ephemeral=True)
            else: await interaction.response.send_message("❌ Apenas Staff.", ephemeral=True)
        return False

# ==============================================================================
# 3. CONTROLES DE TICKET E STAFF
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

class RenomearModal(discord.ui.Modal, title="Renomear"):
    nome = discord.ui.TextInput(label="Novo Nome")
    async def on_submit(self, i): await i.channel.edit(name=self.nome.value); await i.response.send_message("Feito!", ephemeral=True)

class AddUserModal(discord.ui.Modal, title="Add User"):
    uid = discord.ui.TextInput(label="ID")
    async def on_submit(self, i): 
        try: u = await i.guild.fetch_member(int(self.uid.value)); await i.channel.add_user(u); await i.channel.send(f"Adicionado: {u.mention}"); await i.response.send_message("Add!", ephemeral=True)
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
# 5. COMANDOS
# ==============================================================================

@bot.tree.command(name="filamediador", description="Painel da Fila Controladora (Mediadores)")
async def filamediador(interaction: discord.Interaction):
    if interaction.user.id != DONO_ID: return await interaction.response.send_message("❌ Apenas o dono.", ephemeral=True)
    embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para começar a mediar suas filas**\n\nNenhum mediador na fila.", color=discord.Color.from_rgb(147, 112, 219)) 
    await interaction.channel.send(embed=embed, view=MediadorQueueView())
    await interaction.response.send_message("✅ Painel Mediador criado!", ephemeral=True)

@bot.tree.command(name="criarfila", description="Cria Lobby 1v1 (Fixo 2 Jogadores)")
async def criarfila(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    await i.response.send_modal(CriarFilaModal())

# OUTROS COMANDOS
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
    if message.is_system() and isinstance(message.channel, discord.Thread):
        try: await message.delete()
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
                
