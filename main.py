import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging

# --- CONFIGURAÇÃO DE LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

# --- CONFIGURAÇÕES GERAIS ---
# Certifique-se de que a variável de ambiente no Railway é exatamente TOKEN
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# --- MEMÓRIA VOLÁTIL ---
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================

def init_db():
    """Inicializa as tabelas do banco de dados se não existirem."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS pix (
                user_id INTEGER PRIMARY KEY, 
                nome TEXT, 
                chave TEXT, 
                qrcode TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY, 
                valor TEXT
            )
        """)
        con.commit()

def db_execute(query, params=()):
    """Executa um comando de escrita no banco de dados."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    """Recupera uma configuração específica do banco."""
    with sqlite3.connect("dados_bot.db") as con:
        cursor = con.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = cursor.fetchone()
        return res[0] if res else None

# ==============================================================================
#                        SISTEMA DE PAGAMENTO (TÓPICO)
# ==============================================================================

class ViewConfirmacaoFoto(View):
    """View para gerenciar as confirmações dos jogadores dentro do tópico."""
    def __init__(self, p1_id, p2_id, med_id, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med = p1_id, p2_id, med_id
        self.valor, self.modo = valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf_partida")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: 
            return await interaction.response.send_message("Você não é um dos jogadores!", ephemeral=True)
        
        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!", delete_after=3)
        
        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=30)
            
            # Busca dados PIX do mediador escalado
            with sqlite3.connect("dados_bot.db") as con:
                r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()
            
            # Lógica da Taxa Adicional de R$ 0,10
            try:
                v_limpo = self.valor.replace('R$', '').replace(' ', '').replace(',', '.')
                v_final = f"{(float(v_limpo) + 0.10):.2f}".replace('.', ',')
            except:
                v_final = self.valor
            
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_pix.add_field(name="👤 Titular", value=r[0] if r else "Pendente", inline=True)
            emb_pix.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Pendente", inline=True)
            emb_pix.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)
            
            if r and r[2]:
                emb_pix.set_image(url=r[2])
            
            await interaction.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_rec_partida")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: return
        await interaction.channel.send(f"❌ Partida cancelada por {interaction.user.mention}. Deletando canal...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️", custom_id="btn_regras_partida")
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Usem este chat para definir os detalhes da partida.", ephemeral=True)

# ==============================================================================
#                             COMANDOS .Pix E .mediar
# ==============================================================================

class ViewPix(View):
    """Visual original para configuração de PIX."""
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="bt_cad_pix")
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = Modal(title="Cadastrar Chave PIX")
        nome = TextInput(label="Nome do Titular", placeholder="Nome completo")
        chave = TextInput(label="Chave PIX", placeholder="Sua chave aqui")
        qr = TextInput(label="Link QR Code", required=False, placeholder="URL da imagem (opcional)")
        
        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)
        
        async def on_submit(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, nome.value, chave.value, qr.value))
            await it.response.send_message("✅ PIX configurado com sucesso!", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

class ViewMediar(View):
    """Visual original para a fila de mediadores com lista numerada."""
    def __init__(self): super().__init__(timeout=None)
    
    def gerar_embed(self):
        if not fila_mediadores:
            desc = "A fila está vazia no momento."
        else:
            desc = "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        
        emb = discord.Embed(
            title="Painel da fila controladora", 
            description=f"__**Entre na fila para começar a mediar**__\n\n{desc}", 
            color=0x2b2d31
        )
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="bt_ent_fila")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="bt_sai_fila")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você não está na fila!", ephemeral=True)

# ==============================================================================
#                          SISTEMA DE FILA DE JOGADORES
# ==============================================================================

class ViewFila(View):
    """Gerencia a entrada de jogadores e a criação automática de tópicos."""
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def g_normal(self, it, b): await self.processar_entrada(it, "Gelo Normal")
    
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def g_infinito(self, it, b): await self.processar_entrada(it, "Gelo Infinito")

    async def processar_entrada(self, interaction, tipo_gelo):
        if any(j['id'] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("⚠️ Você já está nesta fila!", ephemeral=True)
        
        self.jogadores.append({'id': interaction.user.id, 'mention': interaction.user.mention, 'gelo': tipo_gelo})
        
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []
                return await interaction.response.send_message("❌ Nenhum mediador na fila!", ephemeral=True)
            
            # --- ROTAÇÃO CÍCLICA DE MEDIADORES ---
            # O primeiro da fila atende a partida e é movido para o final imediatamente
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) 
            
            # Busca canal de tópicos configurado
            c_config = pegar_config("canal_th")
            canal = bot.get_channel(int(c_config)) if c_config else interaction.channel
            
            thread = await canal.create_thread(
                name=f"Partida-R${self.valor}", 
                type=discord.ChannelType.public_thread
            )
            
            # --- CONSTRUÇÃO DO PAINEL DE TÓPICO ---
            
            # EMBED 1 (Verde - Dados)
            emb1 = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb1.set_thumbnail(url=FOTO_BONECA)
            emb1.add_field(name="👑 Modo:", value=f"```\n{self.modo}\n```", inline=False)
            emb1.add_field(name="💸 Valor da aposta:", value=f"```\nR$ {self.valor}\n```", inline=False)
            
            user_med = bot.get_user(med_id)
            tag_med = f"@{user_med.name}" if user_med else f"ID: {med_id}"
            emb1.add_field(name="👮 Mediador:", value=f"```\n{tag_med}\n```", inline=False)
            
            # Jogadores formatados conforme solicitado
            j1, j2 = self.jogadores[0], self.jogadores[1]
            emb1.add_field(name="⚡ Jogadores:", value=f"{j1['mention']} - `{j1['gelo']}`\n{j2['mention']} - `{j2['gelo']}`", inline=False)
            
            # EMBED 2 (Azul - Regras)
            emb2 = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=0x0000FF)
            emb2.description = (
                "• Regras adicionais podem ser combinadas entre os participantes.\n"
                "• Se a regra combinada não existir no regulamento oficial da organização, "
                "é obrigatório tirar print do acordo antes do início da partida."
            )
            
            partidas_ativas[thread.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            
            # Marca o mediador e os jogadores no tópico para notificação imediata
            await thread.send(
                content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}", 
                embeds=[emb1, emb2], 
                view=ViewConfirmacaoFoto(j1['id'], j2['id'], med_id, self.valor, self.modo)
            )
            
            self.jogadores = [] # Reseta a fila interna para a próxima dupla
            await interaction.response.send_message(f"✅ Partida criada: {thread.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Você entrou na fila de `{tipo_gelo}`!", ephemeral=True)

# ==============================================================================
#                               COMANDOS EXECUTÁVEIS
# ==============================================================================

@bot.command()
async def Pix(ctx):
    """Comando para configurar os dados de recebimento do mediador."""
    emb = discord.Embed(
        title="Painel Para Configurar Chave PIX", 
        description="Clique no botão abaixo para salvar seus dados de recebimento.", 
        color=0x2b2d31
    )
    await ctx.send(embed=emb, view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    """Comando para exibir e gerenciar a fila de mediadores."""
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo: str, valor: str):
    """Inicia um painel de fila para os jogadores entrarem."""
    emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    emb.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
    emb.add_field(name="🏆 Modo", value=modo, inline=True)
    emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    """Configura o canal onde os tópicos de partida serão criados."""
    v = View(); sel = ChannelSelect(placeholder="Escolha o canal de tópicos")
    async def callback(interaction):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await interaction.response.send_message(f"✅ Canal definido: {sel.values[0].mention}", ephemeral=True)
    sel.callback = callback; v.add_item(sel)
    await ctx.send("Selecione o canal para criação automática de partidas:", view=v)

# ==============================================================================
#                          EVENTOS E LOGICA DE SALA
# ==============================================================================

@bot.event
async def on_message(message):
    """Monitora o envio de ID e Senha pelos mediadores nos tópicos ativos."""
    if message.author.bot: return
    
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        # Apenas o mediador daquela partida pode enviar o ID e Senha
        if message.author.id == dados['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete()
                await message.channel.send("✅ **ID Salvo!** Envie a **Senha** agora.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados_sala.pop(message.channel.id)
                await message.delete()
                
                emb_sala = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                emb_sala.description = f"**ID:** `{id_sala}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                emb_sala.set_image(url=BANNER_URL)
                
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb_sala)
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    """Evento de inicialização do bot."""
    init_db()
    # Re-adiciona views persistentes para funcionarem após reinicializações
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    logger.info(f"✅ Bot Online como {bot.user.name}")

# --- EXECUÇÃO ---
if TOKEN:
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure:
        logger.error("ERRO: Token inválido ou não configurado corretamente no Railway.")
else:
    logger.error("ERRO: Variável de ambiente 'TOKEN' não encontrada.")
               
