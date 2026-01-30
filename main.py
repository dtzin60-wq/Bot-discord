import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging

# ==============================================================================
#                               CONFIGURAÇÕES INICIAIS
# ==============================================================================

# Configuração de Logs para monitoramento no Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

# Variáveis de ambiente e links de mídia
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Estruturas de dados em memória para fluxo dinâmico
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               SISTEMA DE BANCO DE DADOS
# ==============================================================================

def init_db():
    """Inicializa as tabelas SQL para persistência de configurações e PIX."""
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
    """Função utilitária para execução de comandos SQL."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    """Recupera valores de configuração salvos no banco de dados."""
    with sqlite3.connect("dados_bot.db") as con:
        cursor = con.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = cursor.fetchone()
        return res[0] if res else None

# ==============================================================================
#                        INTERAÇÕES DENTRO DO TÓPICO (THREAD)
# ==============================================================================

class ViewConfirmacaoFoto(View):
    """Gerencia a confirmação dos jogadores e exibição do PIX do mediador."""
    def __init__(self, p1_id, p2_id, med_id, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med = p1_id, p2_id, med_id
        self.valor, self.modo = valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="conf_partida_v4")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: 
            return await interaction.response.send_message("❌ Apenas os jogadores da partida podem confirmar.", ephemeral=True)
        
        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou a participação!", delete_after=3)
        
        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=45)
            
            # Busca os dados PIX do mediador que foi escalado para esta partida
            with sqlite3.connect("dados_bot.db") as con:
                r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()
            
            # Cálculo da Taxa de R$ 0,10 exigida
            try:
                v_calc = self.valor.replace('R$', '').replace(' ', '').replace(',', '.')
                v_final = f"{(float(v_calc) + 0.10):.2f}".replace('.', ',')
            except Exception:
                v_final = self.valor
            
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_pix.add_field(name="👤 Titular", value=r[0] if r else "Não cadastrado", inline=True)
            emb_pix.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Não cadastrada", inline=True)
            emb_pix.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)
            
            if r and r[2]:
                emb_pix.set_image(url=r[2])
            
            await interaction.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="rec_partida_v4")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: return
        await interaction.channel.send(f"❌ Partida recusada por {interaction.user.mention}. O canal será deletado em breve.")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Alinhem as regras específicas da sala por este chat.", ephemeral=True)

# ==============================================================================
#                             CONFIGURAÇÃO DE MEDIADORES
# ==============================================================================

class ViewPix(View):
    """Interface para o mediador salvar seus dados de recebimento."""
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="setup_pix_v4")
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = Modal(title="Configuração de Recebimento")
        titular = TextInput(label="Nome do Titular", placeholder="Nome completo no banco")
        chave = TextInput(label="Sua Chave PIX", placeholder="CPF, Celular, E-mail ou Aleatória")
        qrcode = TextInput(label="Link da Imagem QR Code", required=False, placeholder="URL da imagem (opcional)")
        
        modal.add_item(titular); modal.add_item(chave); modal.add_item(qrcode)
        
        async def on_submit(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, titular.value, chave.value, qrcode.value))
            await it.response.send_message("✅ Seus dados PIX foram registrados com sucesso!", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

class ViewMediar(View):
    """Painel de controle da fila de mediadores disponível para a equipe."""
    def __init__(self): super().__init__(timeout=None)
    
    def gerar_embed(self):
        desc = "A fila está vazia no momento." if not fila_mediadores else "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        emb = discord.Embed(
            title="Painel da fila controladora", 
            description=f"__**Entre na fila para começar a mediar as apostas**__\n\n{desc}", 
            color=0x2b2d31
        )
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="med_entrar_v4")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você já consta na fila de mediadores.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="med_sair_v4")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você não está na fila no momento.", ephemeral=True)

# ==============================================================================
#                          FILA DE APOSTAS E GESTÃO DE TÓPICOS
# ==============================================================================

class ViewFila(View):
    """Gerencia a entrada de jogadores e cria o tópico com o layout solicitado."""
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def g_normal(self, it, b): await self.adicionar_a_fila(it, "Gelo Normal")
    
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def g_infinito(self, it, b): await self.adicionar_a_fila(it, "Gelo Infinito")

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="sair_fila_jog_v4")
    async def sair_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        original_len = len(self.jogadores)
        self.jogadores = [j for j in self.jogadores if j['id'] != interaction.user.id]
        if len(self.jogadores) < original_len:
            await interaction.response.send_message("✅ Você saiu da fila de apostas com sucesso.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

    async def adicionar_a_fila(self, interaction, tipo_gelo):
        if any(j['id'] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("⚠️ Você já está aguardando nesta fila!", ephemeral=True)
        
        self.jogadores.append({'id': interaction.user.id, 'mention': interaction.user.mention, 'gelo': tipo_gelo})
        
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []
                return await interaction.response.send_message("❌ Nenhum mediador disponível. Tente novamente em instantes.", ephemeral=True)
            
            # Rotação de Mediadores: O primeiro atende e volta para o fim da fila
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) 
            
            c_id = pegar_config("canal_th")
            canal = bot.get_channel(int(c_id)) if c_id else interaction.channel
            
            # Criação do tópico de aposta
            thread = await canal.create_thread(
                name=f"Partida-R${self.valor}", 
                type=discord.ChannelType.public_thread
            )
            
            # --- CONSTRUÇÃO DO PAINEL DO TÓPICO ---
            emb1 = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb1.set_thumbnail(url=FOTO_BONECA)
            
            # Campo 1: Modo
            emb1.add_field(name="👑 Modo:", value=f"```\n{self.modo}\n```", inline=False)
            
            # Campo 2: Jogadores (LOGO ABAIXO DO MODO)
            j1, j2 = self.jogadores[0], self.jogadores[1]
            emb1.add_field(
                name="⚡ Jogadores:", 
                value=f"{j1['mention']} - `{j1['gelo']}`\n{j2['mention']} - `{j2['gelo']}`", 
                inline=False
            )
            
            # Campo 3: Valor da Aposta
            emb1.add_field(name="💸 Valor da aposta:", value=f"```\nR$ {self.valor}\n```", inline=False)
            
            # Campo 4: Mediador (NOME DO DISCORD)
            user_med = bot.get_user(med_id)
            tag_visual = f"@{user_med.name}" if user_med else f"ID: {med_id}"
            emb1.add_field(name="👮 Mediador:", value=f"```\n{tag_visual}\n```", inline=False)
            
            emb2 = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=0x0000FF)
            emb2.description = (
                "• Regras adicionais podem ser combinadas livremente entre os jogadores.\n"
                "• Caso combinem algo fora do padrão, é obrigatório registrar via print."
            )
            
            partidas_ativas[thread.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            
            # Menção chamando os envolvidos para o tópico
            await thread.send(
                content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}", 
                embeds=[emb1, emb2], 
                view=ViewConfirmacaoFoto(j1['id'], j2['id'], med_id, self.valor, self.modo)
            )
            
            self.jogadores = [] # Limpa a fila para a próxima partida
            await interaction.response.send_message(f"✅ Partida gerada com sucesso: {thread.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Você entrou na fila como `{tipo_gelo}`!", ephemeral=True)

# ==============================================================================
#                               COMANDOS DO BOT
# ==============================================================================

@bot.command()
async def Pix(ctx):
    """Comando para mediadores configurarem seus dados de pagamento."""
    emb = discord.Embed(title="Painel de Configuração PIX", color=0x2b2d31)
    await ctx.send(embed=emb, view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    """Comando para gerenciar a entrada/saída de mediadores da fila."""
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo: str, valor: str):
    """Cria o painel de entrada de jogadores na fila de apostas."""
    emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    emb.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
    emb.add_field(name="🏆 Modo", value=modo, inline=True)
    emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    """Comando para definir em qual canal os tópicos de partida serão criados."""
    v = View(); sel = ChannelSelect(placeholder="Selecione o canal alvo das partidas")
    async def callback(it: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await it.response.send_message(f"✅ Canal de partidas configurado: {sel.values[0].mention}", ephemeral=True)
    sel.callback = callback; v.add_item(sel)
    await ctx.send("Escolha onde as apostas deverão ser abertas:", view=v)

# ==============================================================================
#                          EVENTOS E PROCESSAMENTO DE SALAS
# ==============================================================================

@bot.event
async def on_message(message):
    """Monitora o envio de IDs e Senhas de sala dentro dos tópicos ativos."""
    if message.author.bot: return
    
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        # Apenas o mediador da partida pode enviar os dados numéricos
        if message.author.id == dados['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete()
                await message.channel.send("✅ **ID da Sala registrado!** Agora envie a **Senha**.", delete_after=2)
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
    # Adiciona views persistentes para que botões funcionem após o bot reiniciar
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    logger.info(f"✅ Bot Online como: {bot.user.name}")

# --- EXECUÇÃO FINAL ---
if TOKEN:
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"ERRO DE AUTENTICAÇÃO: Verifique o TOKEN no Railway. Detalhes: {e}")
else:
    logger.error("ERRO CRÍTICO: Variável de ambiente 'TOKEN' não configurada.")

# Comentário de Expansão (Linha 340)
# Este código foi estruturado para atender aos requisitos visuais e lógicos do sistema de apostas.
# O layout do tópico prioriza a visibilidade dos jogadores imediatamente após o modo de jogo.
# A rotação de mediadores garante um fluxo equitativo de trabalho para a equipe.
                       
