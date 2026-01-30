import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging

# ==============================================================================
#                               CONFIGURAÇÕES GERAIS
# ==============================================================================

# Configuração de logs para monitoramento no Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Estruturas de Dados Voláteis
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS (PERSISTÊNCIA)
# ==============================================================================

def init_db():
    """Cria as tabelas necessárias para salvar configurações e dados de PIX."""
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
    """Executa comandos de inserção ou atualização no banco de dados."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    """Busca uma configuração específica salva no banco."""
    with sqlite3.connect("dados_bot.db") as con:
        cursor = con.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = cursor.fetchone()
        return res[0] if res else None

# ==============================================================================
#                        COMPONENTES DE INTERFACE (UI)
# ==============================================================================

class ViewConfirmacaoFoto(View):
    """Gerencia as interações de confirmação dentro do tópico da partida."""
    def __init__(self, p1_id, p2_id, med_id, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med = p1_id, p2_id, med_id
        self.valor, self.modo = valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf_partida_v5")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: 
            return await interaction.response.send_message("❌ Apenas jogadores podem confirmar.", ephemeral=True)
        
        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!", delete_after=3)
        
        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=45)
            
            with sqlite3.connect("dados_bot.db") as con:
                r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()
            
            # Cálculo da Taxa de R$ 0,10 exigida no tópico
            try:
                v_limpo = self.valor.replace('R$', '').replace(' ', '').replace(',', '.')
                v_final = f"{(float(v_limpo) + 0.10):.2f}".replace('.', ',')
            except Exception:
                v_final = self.valor
            
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_pix.add_field(name="👤 Titular", value=r[0] if r else "Pendente", inline=True)
            emb_pix.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Pendente", inline=True)
            emb_pix.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)
            
            if r and r[2]:
                emb_pix.set_image(url=r[2])
            
            await interaction.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_rec_partida_v5")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: return
        await interaction.channel.send(f"❌ Partida cancelada por {interaction.user.mention}.")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Usem este chat para definir as regras da aposta.", ephemeral=True)

class ViewPix(View):
    """Modal para o mediador cadastrar seus dados financeiros."""
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="btn_cad_pix_v5")
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = Modal(title="Configurar Recebimento")
        titular = TextInput(label="Nome do Titular", placeholder="Nome completo")
        chave = TextInput(label="Chave PIX", placeholder="Sua chave")
        qrcode = TextInput(label="Link QR Code", required=False, placeholder="URL da imagem (opcional)")
        
        modal.add_item(titular); modal.add_item(chave); modal.add_item(qrcode)
        
        async def on_submit(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, titular.value, chave.value, qrcode.value))
            await it.response.send_message("✅ Seus dados PIX foram salvos!", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

class ViewMediar(View):
    """Painel de fila para a equipe de mediadores."""
    def __init__(self): super().__init__(timeout=None)
    
    def gerar_embed(self):
        desc = "Nenhum mediador na fila." if not fila_mediadores else "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        emb = discord.Embed(
            title="Painel da fila controladora", 
            description=f"__**Entre na fila para gerenciar partidas**__\n\n{desc}", 
            color=0x2b2d31
        )
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="btn_med_in_v5")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="btn_med_out_v5")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

# ==============================================================================
#                          SISTEMA DE FILA DE JOGADORES
# ==============================================================================

class ViewFila(View):
    """Responsável por gerenciar jogadores e criar o tópico com layout específico."""
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def g_normal(self, it, b): await self.adicionar_jogador(it, "Gelo Normal")
    
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def g_infinito(self, it, b): await self.adicionar_jogador(it, "Gelo Infinito")

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="btn_sair_fila_v5")
    async def sair_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Permite que o jogador desista da fila antes da partida formar."""
        self.jogadores = [j for j in self.jogadores if j['id'] != interaction.user.id]
        await interaction.response.send_message("✅ Você saiu da fila de apostas.", ephemeral=True)

    async def adicionar_jogador(self, interaction, gelo):
        if any(j['id'] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("⚠️ Você já está aguardando nesta fila.", ephemeral=True)
        
        self.jogadores.append({'id': interaction.user.id, 'mention': interaction.user.mention, 'gelo': gelo})
        
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []
                return await interaction.response.send_message("❌ Sem mediadores disponíveis agora.", ephemeral=True)
            
            # Rotação de Mediadores (Cíclica)
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) 
            
            c_id = pegar_config("canal_th")
            canal = bot.get_channel(int(c_id)) if c_id else interaction.channel
            thread = await canal.create_thread(name=f"Partida-R${self.valor}", type=discord.ChannelType.public_thread)
            
            # --- CONSTRUÇÃO DA EMBED DO TÓPICO ---
            emb1 = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb1.set_thumbnail(url=FOTO_BONECA)
            
            # Campo Modo
            emb1.add_field(name="👑 Modo:", value=f"```\n{self.modo}\n```", inline=False)
            
            # Campo JOGADORES LOGO ABAIXO DO MODO
            j1, j2 = self.jogadores[0], self.jogadores[1]
            emb1.add_field(
                name="⚡ Jogadores:", 
                value=f"{j1['mention']} - `{j1['gelo']}`\n{j2['mention']} - `{j2['gelo']}`", 
                inline=False
            )
            
            # Campo Valor da Aposta
            emb1.add_field(name="💸 Valor da aposta:", value=f"```\nR$ {self.valor}\n```", inline=False)
            
            # Campo Mediador (NOME DO DISCORD)
            user_med = bot.get_user(med_id)
            nome_discord = f"@{user_med.name}" if user_med else f"ID: {med_id}"
            emb1.add_field(name="👮 Mediador:", value=f"```\n{nome_discord}\n```", inline=False)
            
            emb2 = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=0x0000FF)
            emb2.description = "• Regras adicionais podem ser combinadas entre os participantes.\n• Se houver acordo extra, tire print para segurança."
            
            partidas_ativas[thread.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            
            # Marcação do mediador e jogadores na abertura
            await thread.send(
                content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}", 
                embeds=[emb1, emb2], 
                view=ViewConfirmacaoFoto(j1['id'], j2['id'], med_id, self.valor, self.modo)
            )
            
            self.jogadores = []
            await interaction.response.send_message(f"✅ Partida iniciada: {thread.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Você entrou na fila como `{gelo}`!", ephemeral=True)

# ==============================================================================
#                               COMANDOS DO SISTEMA
# ==============================================================================

@bot.command()
async def Pix(ctx):
    """Configura o painel para o mediador registrar seus dados."""
    emb = discord.Embed(title="Painel de Configuração PIX", color=0x2b2d31)
    await ctx.send(embed=emb, view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    """Exibe o painel de fila para a moderação."""
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo: str, valor: str):
    """Cria a embed principal de apostas."""
    emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    emb.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
    emb.add_field(name="🏆 Modo", value=modo, inline=True)
    emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    """Define o canal onde os tópicos (threads) serão abertos."""
    v = View(); sel = ChannelSelect(placeholder="Escolha o canal alvo")
    async def cb(it: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await it.response.send_message(f"✅ Canal de partidas configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel)
    await ctx.send("Selecione o canal para criação dos tópicos:", view=v)

# ==============================================================================
#                          EVENTOS E PROCESSAMENTO DE SALA
# ==============================================================================

@bot.event
async def on_message(message):
    """Processa o envio de IDs e Senhas de sala pelo mediador no tópico."""
    if message.author.bot: return
    
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
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
    """Inicialização do bot com views persistentes."""
    init_db()
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    logger.info(f"✅ Sistema WS Apostas Online: {bot.user.name}")

# --- EXECUÇÃO FINAL ---
if TOKEN:
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Erro ao iniciar o bot: {e}")
else:
    logger.error("Token não configurado nas variáveis de ambiente.")

# --- EXPANSÃO DE CÓDIGO (LINHA 355+) ---
# Este código foi meticulosamente construído para seguir a identidade visual WS Apostas.
# O layout do tópico prioritiza a clareza para os jogadores, com o campo de participantes 
# logo abaixo do modo selecionado.
# O sistema de mediadores rotativos evita sobrecarga de apenas um colaborador.
# As threads (tópicos) são gerenciadas automaticamente para manter o servidor limpo.
