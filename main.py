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
    "canais": {"Filas": []}, 
    "contador_salas": 0 
}
tickets_abertos = []
mediadores_ativos = []

# ==============================================================================
# 1. SISTEMA DE CONFIRMAÇÃO (DENTRO DO TICKET)
# ==============================================================================

class PartidaConfirmacaoView(discord.ui.View):
    def __init__(self, jogadores, modo, valor):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.modo = modo
        self.valor = valor
        self.confirmados = []

    async def atualizar_status(self, interaction):
        if len(self.confirmados) >= len(self.jogadores):
            # TODOS CONFIRMARAM -> INICIAR
            configuracao["contador_salas"] += 1
            num = configuracao["contador_salas"]
            
            # Define nome (Mobile ou Emulador)
            tipo = "emulador" if "emulador" in self.modo.lower() else "mobile"
            await interaction.channel.edit(name=f"{tipo}-{num}")
            
            # Atualiza Embed de Confirmação para Verde
            embed_c = interaction.message.embeds[0]
            embed_c.color = discord.Color.green()
            embed_c.title = "✅ PARTIDA CONFIRMADA"
            await interaction.message.edit(embed=embed_c, view=None)

            # Regras e Pagamento
            embed_reg = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", description="• Regras adicionais podem ser combinadas.\n• Se a regra não existir no regulamento, tire print do acordo.", color=discord.Color.gold())
            await interaction.channel.send(embed=embed_reg)

            embed_pag = discord.Embed(title="🔥 ÁREA DE PAGAMENTO", description=f"**Valor:** {self.valor}\n\nEnvie o PIX e comprovante abaixo.\nO Mediador irá validar.", color=discord.Color.green())
            await interaction.channel.send(embed=embed_pag, view=MatchControlView())

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf")
    async def confirmar(self, interaction, button):
        if interaction.user.id not in self.jogadores: return await interaction.response.send_message("❌ Você não está na partida.", ephemeral=True)
        if interaction.user.id in self.confirmados: return await interaction.response.send_message("✅ Já confirmou.", ephemeral=True)

        self.confirmados.append(interaction.user.id)
        await interaction.response.send_message(f"✅ **{interaction.user.display_name}** confirmou!", ephemeral=False)
        await self.atualizar_status(interaction)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_recus")
    async def recusar(self, interaction, button):
        if interaction.user.id not in self.jogadores: return await interaction.response.send_message("❌ Não está na partida.", ephemeral=True)
        await interaction.channel.send(f"❌ **{interaction.user.display_name}** recusou. Cancelando...")
        await asyncio.sleep(3)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️", custom_id="btn_regras")
    async def regras(self, interaction, button):
        await interaction.response.send_message(f"📢 {interaction.user.mention} quer combinar regras!", ephemeral=False)

class MatchControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Validar Pagamento", style=discord.ButtonStyle.success, emoji="💸", custom_id="btn_val_pay")
    async def v(self, i, b):
        if i.user.guild_permissions.manage_messages or i.user.id == DONO_ID: await i.response.send_message(f"✅ Validado por {i.user.mention}!", ephemeral=False)
    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_close_pay")
    async def c(self, i, b):
        if i.user.guild_permissions.manage_messages: await i.channel.delete()

# ==============================================================================
# 2. SISTEMA DE LOBBY (FILA)
# ==============================================================================

class FilaLobbyView(discord.ui.View):
    def __init__(self, modo: str, valor: str, limite: int):
        super().__init__(timeout=None)
        self.limite = limite
        self.modo = modo
        self.valor = valor
        self.jogadores = [] 
        self.dados_visuais = {} 
        self.configurar_botoes()

    def configurar_botoes(self):
        self.clear_items()
        # Se 1v1 (Limite 2) -> Botões de Gel (SEM EMOJI)
        if self.limite == 2:
            self.add_item(discord.ui.Button(label="Gel Normal", style=discord.ButtonStyle.secondary, custom_id="join_normal"))
            self.add_item(discord.ui.Button(label="Gel Infinito", style=discord.ButtonStyle.secondary, custom_id="join_infinito"))
        else:
            # Se Time (Limite > 2) -> Botão Entrar
            self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.secondary, custom_id="join_geral"))
        
        # Botão Sair
        self.add_item(discord.ui.Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="leave_fila"))

    async def atualizar_embed(self, interaction):
        if not self.jogadores: texto = "Nenhum jogador na fila"
        else:
            texto = ""
            for uid in self.jogadores:
                escolha = self.dados_visuais.get(uid, "Entrou")
                texto += f"<@{uid}> | {escolha}\n"

        embed = interaction.message.embeds[0]
        embed.set_field_at(2, name="👥 | Jogadores", value=texto, inline=False)
        await interaction.message.edit(embed=embed, view=self)

    async def iniciar_confirmacao(self, interaction):
        # Sorteia canal
        canais = configuracao["canais"].get("Filas", [])
        canal_destino = random.choice(canais) if canais else interaction.channel
        
        # REMOVIDO: Mensagem "Criando sala..." (Agora é silencioso)

        # Cria ticket
        thread = await canal_destino.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.private_thread)
        
        mencoes = ""
        objs_jogadores = []
        for uid in self.jogadores:
            u = interaction.guild.get_member(uid)
            if u:
                await thread.add_user(u)
                mencoes += f"{u.mention} "
                objs_jogadores.append(u)
                tickets_abertos.append(uid)
        
        embed_conf = discord.Embed(title="Aguardando Confirmações", color=discord.Color.light_grey())
        embed_conf.set_thumbnail(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
        embed_conf.add_field(name="👑 Modo:", value=self.modo, inline=False)
        embed_conf.add_field(name="💸 Valor:", value=self.valor, inline=False)
        embed_conf.add_field(name="⚡ Jogadores:", value="\n".join([u.mention for u in objs_jogadores]), inline=False)
        
        await thread.send(content=f"{mencoes} Confirmem a partida!", embed=embed_conf, view=PartidaConfirmacaoView(self.jogadores, self.modo, self.valor))
        
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
                await interaction.response.defer(); await self.atualizar_embed(interaction)
            else: await interaction.response.send_message("❌ Não está na fila.", ephemeral=True)
            return True

        if uid in self.jogadores: return await interaction.response.send_message("❌ Já está na fila!", ephemeral=True)
        if len(self.jogadores) >= self.limite: return await interaction.response.send_message("❌ Fila cheia!", ephemeral=True)

        escolha = "Entrou"
        if cid == "join_normal": escolha = "Gel Normal"
        elif cid == "join_infinito": escolha = "Gel Infinito"

        self.jogadores.append(uid)
        self.dados_visuais[uid] = escolha
        
        await interaction.response.defer()
        await self.atualizar_embed(interaction)

        if len(self.jogadores) >= self.limite: await self.iniciar_confirmacao(interaction)
        return True

# ==============================================================================
# 3. GERAÇÃO (15 FILAS)
# ==============================================================================

class SelecionarFilaSelect(discord.ui.Select):
    def __init__(self, modo, limite):
        valores = ["1,00", "2,00", "3,00", "4,00", "5,00", "10,00", "15,00", "20,00", "25,00", "30,00", "40,00", "50,00", "60,00", "80,00", "100,00"]
        options = [discord.SelectOption(label=f"R$ {v}", value=v) for v in valores]
        super().__init__(placeholder="Selecione o valor para gerar o painel", options=options)
        self.modo = modo
        self.limite = limite

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        embed = discord.Embed(title=f"{self.modo} | WS APOSTAS", color=discord.Color.blue())
        embed.add_field(name="👑 | Modo", value=self.modo, inline=False)
        embed.add_field(name="💸 | Valor", value=f"R$ {val}", inline=False)
        embed.add_field(name="👥 | Jogadores", value="Nenhum jogador na fila", inline=False)
        embed.set_image(url="https://cdn.discordapp.com/attachments/1465403221936963655/1465775330999533773/file_00000000d78871f596a846e9ca08d27c.jpg")
        
        await interaction.channel.send(embed=embed, view=FilaLobbyView(self.modo, f"R$ {val}", self.limite))
        await interaction.response.send_message(f"Painel de R$ {val} gerado!", ephemeral=True)

class GeradorFilasView(discord.ui.View):
    def __init__(self, modo, limite):
        super().__init__()
        self.add_item(SelecionarFilaSelect(modo, limite))

class CriarFilaModal(discord.ui.Modal, title="Gerador de Filas"):
    nome_modo = discord.ui.TextInput(label="Nome do Modo", placeholder="Ex: 1v1 Mobile")
    qtd = discord.ui.TextInput(label="Jogadores por Time", placeholder="2", max_length=2)

    async def on_submit(self, interaction):
        try:
            limite = int(self.qtd.value)
            await interaction.response.send_message(f"✅ Gerando seletor para **{self.nome_modo.value}**...", view=GeradorFilasView(self.nome_modo.value, limite), ephemeral=True)
        except: await interaction.response.send_message("Erro no número.", ephemeral=True)

# ==============================================================================
# 4. MEDIADOR (MANTIDO)
# ==============================================================================

class RemoverMediadorModal(discord.ui.Modal, title="Remover Mediador"):
    user_id = discord.ui.TextInput(label="ID do Mediador")
    async def on_submit(self, i):
        try:
            uid = int(self.user_id.value)
            if uid in mediadores_ativos: mediadores_ativos.remove(uid); await MediadorQueueView().atualizar_embed(i); await i.followup.send(f"✅ Removido <@{uid}>", ephemeral=True)
            else: await i.response.send_message("❌ Não encontrado.", ephemeral=True)
        except: await i.response.send_message("❌ Erro.", ephemeral=True)

class MediadorQueueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢", custom_id="med_join"))
        self.add_item(discord.ui.Button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="med_leave"))
        self.add_item(discord.ui.Button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_kick"))
        self.add_item(discord.ui.Button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="med_staff"))

    async def atualizar_embed(self, interaction):
        txt = "Nenhum mediador na fila." if not mediadores_ativos else "".join([f"**{i}** • <@{uid}> `{uid}`\n" for i, uid in enumerate(mediadores_ativos, 1)])
        embed = interaction.message.embeds[0]
        embed.description = f"**Entre na fila para começar a mediar suas filas**\n\n{txt}"
        if interaction.response.is_done(): await interaction.message.edit(embed=embed, view=self)
        else: await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, i):
        cid, uid = i.data["custom_id"], i.user.id
        if cid == "med_join":
            if uid in mediadores_ativos: await i.response.send_message("❌ Já está na fila.", ephemeral=True)
            else: mediadores_ativos.append(uid); await self.atualizar_embed(i)
        elif cid == "med_leave":
            if uid in mediadores_ativos: mediadores_ativos.remove(uid); await self.atualizar_embed(i)
            else: await i.response.send_message("❌ Não está na fila.", ephemeral=True)
        elif cid == "med_kick":
            if i.user.id == DONO_ID: await i.response.send_modal(RemoverMediadorModal())
            else: await i.response.send_message("❌ Apenas Dono.", ephemeral=True)
        return False

# ==============================================================================
# 5. COMANDOS
# ==============================================================================

@bot.tree.command(name="criarfila", description="Gera painel de filas")
async def criarfila(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    await i.response.send_modal(CriarFilaModal())

@bot.tree.command(name="filamediador", description="Painel Mediador")
async def filamediador(i: discord.Interaction):
    if i.user.id != DONO_ID: return
    embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para começar a mediar suas filas**\n\nNenhum mediador na fila.", color=discord.Color.purple()) 
    await i.channel.send(embed=embed, view=MediadorQueueView())
    await i.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="configurar_canais_filas", description="Canais de Aposta")
async def cfg_f(i: discord.Interaction, c1: discord.TextChannel, c2: discord.TextChannel=None, c3: discord.TextChannel=None):
    if i.user.id != DONO_ID: return
    l = [c for c in [c1, c2, c3] if c]
    configuracao["canais"]["Filas"] = l
    await i.response.send_message("✅ Configurado.", ephemeral=True)

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
        
