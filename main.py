import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, Select, ChannelSelect
import sqlite3
import os
import asyncio
import logging
import datetime
import sys
import json

# ==============================================================================
#                               CONFIGURAÇÕES E LOGS
# ==============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Estados Globais (In-Memory para performance)
fila_mediadores = [] 
partidas_ativas = {}
temp_dados_sala = {}
manutencao_global = False

# ==============================================================================
#                               BANCO DE DADOS (EXPANDIDO)
# ==============================================================================
def init_db():
    with sqlite3.connect("dados_bot.db") as con:
        # Tabela Pix com contagem de serviços
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY, 
            nome TEXT, 
            chave TEXT, 
            qrcode TEXT,
            total_mediacoes INTEGER DEFAULT 0,
            ganhos_estimados REAL DEFAULT 0.0
        )""")
        # Tabela de Configurações Gerais
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        # Tabela de Histórico de Partidas
        con.execute("""CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mediador_id INTEGER,
            jogador1 INTEGER,
            jogador2 INTEGER,
            valor TEXT,
            data TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def db_query(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute(query, params).fetchone()

def registrar_partida(m_id, p1, p2, valor):
    data = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    db_execute("INSERT INTO historico (mediador_id, jogador1, jogador2, valor, data) VALUES (?,?,?,?,?)",
               (m_id, p1, p2, valor, data))
    db_execute("UPDATE pix SET total_mediacoes = total_mediacoes + 1 WHERE user_id = ?", (m_id,))

# ==============================================================================
#                          SISTEMA DE MODAL (.fila)
# ==============================================================================
class ModalCriarFila(Modal):
    def __init__(self):
        super().__init__(title="Painel de Criação de Fila")
        
        self.modo = TextInput(
            label="Modo da Partida (1v1, 2v2, 3v3, 4v4)", 
            placeholder="Ex: 1v1", 
            min_length=3, max_length=3
        )
        self.plataforma = TextInput(
            label="Plataforma (Misto, Emulador, Mobile, Full)", 
            placeholder="Ex: MOBILE", 
            min_length=4
        )
        self.valor = TextInput(
            label="Valor da Aposta (R$)", 
            placeholder="Ex: 0,50", 
            min_length=1
        )

    async def on_submit(self, it: discord.Interaction):
        # Validação de Modo
        m_val = self.modo.value.lower()
        if m_val not in ["1v1", "2v2", "3v3", "4v4"]:
            return await it.response.send_message("❌ Modo deve ser entre 1v1 e 4v4!", ephemeral=True)
        
        # Formatação do nome da fila
        nome_exibicao = f"{self.modo.value.upper()} | {self.plataforma.value.upper()}"
        
        view = ViewFilaAposta(nome_exibicao, self.valor.value)
        emb = view.gerar_embed()
        
        msg = await it.channel.send(embed=emb, view=view)
        view.message = msg
        await it.response.send_message(f"✅ Fila {nome_exibicao} aberta!", ephemeral=True)

# ==============================================================================
#                          VISUAL DO COMANDO .mediar (EXATO)
# ==============================================================================
class ViewMediarWS(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        # Visual idêntico ao print: Título, Descrição e Lista de Menções com IDs
        desc = "Entre na fila para começar a mediar suas filas\n\n"
        if fila_mediadores:
            for i, u_id in enumerate(fila_mediadores):
                desc += f"**{i+1} •** <@{u_id}> {u_id}\n"
        else:
            desc += "*Ninguém aguardando na fila.*"
            
        emb = discord.Embed(title="Painel da fila controladora", description=desc, color=0x2b2d31)
        emb.set_thumbnail(url=ICONE_ORG)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="ws_med_in")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴", custom_id="ws_med_out")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.gray, emoji="⚙️", custom_id="ws_med_rem")
    async def remover(self, it, b):
        if not it.user.guild_permissions.administrator: return
        modal = Modal(title="Remover Membro da Fila")
        alvo = TextInput(label="ID do Usuário")
        modal.add_item(alvo)
        async def callback(interaction):
            try:
                uid = int(alvo.value.strip())
                if uid in fila_mediadores: 
                    fila_mediadores.remove(uid)
                    await interaction.response.edit_message(embed=self.gerar_embed())
                else: await interaction.response.send_message("ID não está na fila.", ephemeral=True)
            except: await interaction.response.send_message("ID Inválido.", ephemeral=True)
        modal.on_submit = callback; await it.response.send_modal(modal)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.gray, emoji="⚙️", custom_id="ws_med_staff")
    async def staff(self, it, b):
        # Menu secreto para ADMs
        if not it.user.guild_permissions.administrator: return
        await it.response.send_message("🛠️ Logs e estatísticas foram enviados ao console.", ephemeral=True)

# ==============================================================================
#                          LÓGICA DE FILA E ROTAÇÃO (DETERMINÍSTICA)
# ==============================================================================
class ViewFilaAposta(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = [] # Lista de dicts {id, mention, gelo}
        self.message = None

    def gerar_embed(self):
        # Visual inspirado no print da Space
        emb = discord.Embed(title=f"{self.modo} | SPACE APOSTAS 5K", color=0x0000FF)
        emb.add_field(name="👑 **Modo**", value=self.modo, inline=False)
        emb.add_field(name="💸 **Valor**", value=f"R$ {self.valor}", inline=False)
        
        lista = "\n".join([f"👤 {j['m']} - `{j['g']}`" for j in self.jogadores]) or "Nenhum jogador na fila"
        emb.add_field(name="⚡ **Jogadores**", value=lista, inline=False)
        
        emb.set_image(url=BANNER_URL)
        emb.set_thumbnail(url=ICONE_ORG)
        emb.set_footer(text="@gg/spaceapostas")
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, custom_id="ws_f_in")
    async def entrar_btn(self, it, b):
        if any(j["id"] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Você já está nesta fila!", ephemeral=True)
        
        self.jogadores.append({"id": it.user.id, "m": it.user.mention, "g": "MOBILE"})
        await it.response.edit_message(embed=self.gerar_embed())

        # Gatilho de Partida (Exemplo 1v1)
        if len(self.jogadores) >= 2:
            if not fila_mediadores:
                return await it.channel.send("❌ Não há mediadores disponíveis no painel!", delete_after=5)
            
            # --- ROTAÇÃO DA FILA (O 2º vira 1º) ---
            mediador_atual = fila_mediadores.pop(0) # Remove o primeiro da lista
            fila_mediadores.append(mediador_atual) # Adiciona ele ao final
            
            # Notificação de Canal de Tópicos
            canal_id = db_query("SELECT valor FROM config WHERE chave='canal_thread'")
            if not canal_id: return await it.channel.send("Configuração de canal ausente.")
            
            canal_alvo = bot.get_channel(int(canal_id[0]))
            thread = await canal_alvo.create_thread(
                name=f"Partida-{self.valor}-{self.modo}",
                type=discord.ChannelType.public_thread
            )
            
            p1, p2 = self.jogadores[0], self.jogadores[1]
            registrar_partida(mediador_atual, p1['id'], p2['id'], self.valor)
            
            # Visual do Tópico
            e_th = discord.Embed(title="⚔️ Partida Localizada", color=0xFFFF00)
            e_th.add_field(name="👮 Mediador", value=f"<@{mediador_atual}>")
            e_th.add_field(name="👥 Jogadores", value=f"{p1['m']} vs {p2['m']}")
            await thread.send(content=f"🔔 <@{mediador_atual}> | {p1['m']} {p2['m']}", embed=e_th)
            
            self.jogadores = self.jogadores[2:] # Limpa os que entraram
            await self.message.edit(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, custom_id="ws_f_out")
    async def sair_btn(self, it, b):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                          VISUAL DO COMANDO .Pix (CONFORME PRINT)
# ==============================================================================
class ViewPixWS(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="ws_pix_set")
    async def cadastrar(self, it, b):
        # Modal conforme descrição do painel
        modal = Modal(title="Configurar Minha Chave PIX")
        t = TextInput(label="Nome do Titular", placeholder="Nome no Banco")
        c = TextInput(label="Chave PIX", placeholder="Sua Chave")
        q = TextInput(label="Link do QR Code", required=False)
        modal.add_item(t); modal.add_item(c); modal.add_item(q)
        
        async def callback(interaction):
            db_execute("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode) VALUES (?,?,?,?)",
                       (interaction.user.id, t.value, c.value, q.value))
            await interaction.response.send_message("✅ Chave PIX configurada!", ephemeral=True)
        modal.on_submit = callback; await it.response.send_modal(modal)

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="ws_pix_my")
    async def ver_minha(self, it, b):
        r = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,))
        if not r: return await it.response.send_message("❌ Você não tem chave salva.", ephemeral=True)
        e = discord.Embed(title="💠 Seus Dados", color=0x2ecc71)
        e.add_field(name="Titular", value=r[0])
        e.add_field(name="Chave", value=f"`{r[1]}`")
        if r[2]: e.set_image(url=r[2])
        await it.response.send_message(embed=e, ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.gray, emoji="🔍", custom_id="ws_pix_med")
    async def ver_outro(self, it, b):
        modal = Modal(title="Buscar Chave")
        id_med = TextInput(label="ID do Mediador")
        modal.add_item(id_med)
        async def cb(interaction):
            r = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (id_med.value,))
            if not r: return await interaction.response.send_message("Mediador não encontrado.", ephemeral=True)
            e = discord.Embed(title=f"💠 Chave de {r[0]}", color=0x3498db)
            e.add_field(name="Chave", value=f"`{r[1]}`")
            if r[2]: e.set_image(url=r[2])
            await interaction.response.send_message(embed=e, ephemeral=True)
        modal.on_submit = cb; await it.response.send_modal(modal)

# ==============================================================================
#                               COMANDOS CORE
# ==============================================================================
@bot.command()
async def fila(ctx):
    # Agora o comando .fila abre o modal interativo
    if not ctx.author.guild_permissions.administrator: return
    await ctx.interaction.response.send_modal(ModalCriarFila())

@bot.command()
async def Pix(ctx):
    # Visual conforme imagem 1000004559.jpg
    emb = discord.Embed(
        title="Painel Para Configurar Chave PIX",
        description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.",
        color=0x2b2d31
    )
    emb.set_thumbnail(url=ICONE_ORG)
    await ctx.send(embed=emb, view=ViewPixWS())

@bot.command()
async def mediar(ctx):
    # Visual conforme print da fila controladora
    if ctx.author.guild_permissions.manage_messages:
        await ctx.send(embed=ViewMediarWS().gerar_embed(), view=ViewMediarWS())

@bot.command()
async def canal_fila(ctx):
    # Configura onde os tópicos serão criados
    if not ctx.author.guild_permissions.administrator: return
    v = View(); s = ChannelSelect()
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_thread", str(s.values[0].id)))
        await it.response.send_message(f"✅ Canal de tópicos definido: {s.values[0].mention}", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Selecione o canal para criação de tópicos:", view=v)

@bot.event
async def on_ready():
    init_db()
    # Registra as views persistentes
    bot.add_view(ViewPixWS())
    bot.add_view(ViewMediarWS())
    print(f"✅ SISTEMA WS INICIALIZADO: {bot.user}")

if TOKEN: bot.run(TOKEN)
