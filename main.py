import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, ChannelSelect, Select
import sqlite3
import os
import datetime
import asyncio
import sys

# ==============================================================================
#                               CONFIGURAÇÕES TÉCNICAS
# ==============================================================================
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Variáveis de Estado (Cache em Memória para Performance)
fila_mediadores = [] 
partidas_ativas = 0
taxa_operacional = 0.10 # R$ 0,10 fixo por mediação

# ==============================================================================
#                               BANCO DE DADOS (SQLite3)
# ==============================================================================
def init_db():
    with sqlite3.connect("dados_bot.db") as con:
        # Tabela de PIX dos Mediadores
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT
        )""")
        # Tabela de Configurações Gerais
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        # Tabela de Blacklist (Segurança)
        con.execute("CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, motivo TEXT)")
        # Tabela de Histórico para Ranking e Auditoria
        con.execute("""CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            med_id INTEGER, 
            valor TEXT, 
            modo TEXT,
            data TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute(query, params).fetchone()

def db_query_all(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute(query, params).fetchall()

# ==============================================================================
#                          LÓGICA DE ROTAÇÃO (ALGORITMO)
# ==============================================================================
# O mediador no topo (índice 0) atende o jogo e é movido para o final da lista.


async def registrar_partida_log(med_id, valor, modo):
    c_id = db_query("SELECT valor FROM config WHERE chave='canal_logs'")
    if c_id:
        canal = bot.get_channel(int(c_id[0]))
        if canal:
            emb = discord.Embed(title="📝 Log de Partida", color=0x2b2d31, timestamp=datetime.datetime.now())
            emb.add_field(name="Mediador", value=f"<@{med_id}>")
            emb.add_field(name="Valor/Modo", value=f"R$ {valor} | {modo}")
            await canal.send(embed=emb)

# ==============================================================================
#                          MODAL DE CONFIGURAÇÃO (.fila)
# ==============================================================================
class ModalConfigFila(Modal):
    def __init__(self):
        super().__init__(title="Configurar Nova Fila Space")
        
        self.valor = TextInput(label="Valor da Aposta (Máximo R$ 100)", placeholder="Ex: 50,00", max_length=6)
        self.modo = TextInput(label="Modo (1v1 até 4v4)", placeholder="Ex: 1v1", min_length=3, max_length=3)
        self.plataforma = TextInput(label="Plataforma", placeholder="Misto, Emulador, Mobile ou Full")
        
        self.add_item(self.valor); self.add_item(self.modo); self.add_item(self.plataforma)

    async def on_submit(self, it: discord.Interaction):
        # Validação do Limite de R$ 100
        try:
            val_limpo = float(self.valor.value.replace(',', '.'))
            if val_limpo > 100.0:
                return await it.response.send_message("❌ O valor máximo permitido é R$ 100,00!", ephemeral=True)
        except ValueError:
            return await it.response.send_message("❌ Digite um valor numérico válido!", ephemeral=True)

        # Validação dos Modos
        if self.modo.value.lower() not in ["1v1", "2v2", "3v3", "4v4"]:
            return await it.response.send_message("❌ Modos permitidos: 1v1 até 4v4!", ephemeral=True)
        
        modo_final = f"{self.modo.value.upper()} | {self.plataforma.value.upper()}"
        view = ViewFilaAposta(modo_final, self.valor.value)
        msg = await it.channel.send(embed=view.gerar_embed(), view=view)
        view.message = msg
        await it.response.send_message(f"✅ Fila {modo_final} aberta!", ephemeral=True)

# ==============================================================================
#                          LÓGICA DE FILA E ROTAÇÃO
# ==============================================================================
class ViewFilaAposta(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores, self.message = modo, valor, [], None

    def gerar_embed(self):
        emb = discord.Embed(title=f"{self.modo} | SPACE APOSTAS", color=0x0000FF)
        emb.add_field(name="👑 Modo", value=f"`{self.modo}`", inline=True)
        emb.add_field(name="💸 Valor", value=f"`R$ {self.valor}`", inline=True)
        lista = "\n".join([f"👤 {j['m']}" for j in self.jogadores]) or "*Aguardando jogadores...*"
        emb.add_field(name="⚡ Jogadores na Fila", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        emb.set_footer(text="Space Apostas - Sistema Automático")
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
    async def in_f(self, it, b):
        # Verificação de Blacklist
        if db_query("SELECT 1 FROM blacklist WHERE user_id=?", (it.user.id,)):
            return await it.response.send_message("🚫 Você está na blacklist e não pode apostar.", ephemeral=True)
            
        if any(j["id"] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Você já está na fila!", ephemeral=True)
        
        self.jogadores.append({"id": it.user.id, "m": it.user.mention})
        await it.response.edit_message(embed=self.gerar_embed())
        
        num_necessario = int(self.modo[0]) * 2
        if len(self.jogadores) >= num_necessario:
            if not fila_mediadores:
                return await it.channel.send("❌ Sem mediadores online no momento!", delete_after=5)
            
            # --- ROTAÇÃO DE FILA ---
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)
            
            db_execute("INSERT INTO historico (med_id, valor, modo, data) VALUES (?,?,?,?)", 
                       (med_id, self.valor, self.modo, str(datetime.date.today())))
            
            c_id = db_query("SELECT valor FROM config WHERE chave='canal_th'")
            if c_id:
                canal_th = bot.get_channel(int(c_id[0]))
                if canal_th:
                    th = await canal_th.create_thread(name=f"Jogo-R${self.valor}", type=discord.ChannelType.public_thread)
                    await th.send(content=f"🔔 <@{med_id}> | Participantes atingidos!\nJogadores: " + " ".join([j['m'] for j in self.jogadores]))
                    await registrar_partida_log(med_id, self.valor, self.modo)
            
            self.jogadores = []; await self.message.edit(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def out_f(self, it, b):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                               VISUAIS (.Pix e .mediar)
# ==============================================================================
class ViewPixWS(View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
    async def cad(self, it, b):
        modal = Modal(title="Configurar Dados PIX")
        t = TextInput(label="Nome do Titular"); c = TextInput(label="Chave PIX"); q = TextInput(label="Link QR Code", required=False)
        modal.add_item(t); modal.add_item(c); modal.add_item(q)
        async def callback(interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (interaction.user.id, t.value, c.value, q.value))
            await interaction.response.send_message("✅ Seus dados foram salvos!", ephemeral=True)
        modal.on_submit = callback; await it.response.send_modal(modal)

    @discord.ui.button(label="Ver Minha Chave", style=discord.ButtonStyle.gray, emoji="🔍")
    async def ver(self, it, b):
        r = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,))
        if not r: return await it.response.send_message("Sem chave cadastrada!", ephemeral=True)
        emb = discord.Embed(title="💠 Seus Dados PIX", description=f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

class ViewMediarWS(View):
    def __init__(self): super().__init__(timeout=None)
    
    def gerar_embed(self):
        desc = "Entre na fila para começar a mediar suas filas\n\n"
        if fila_mediadores:
            for i, u_id in enumerate(fila_mediadores):
                desc += f"**{i+1} •** <@{u_id}> `ID: {u_id}`\n"
        else: desc += "*Fila vazia.*"
        emb = discord.Embed(title="Painel da fila controladora", description=desc, color=0x2b2d31)
        emb.set_thumbnail(url=ICONE_ORG); return emb

    @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red, emoji="🔴")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                               COMANDOS EXECUTIVOS
# ==============================================================================
@bot.command()
async def fila(ctx):
    if ctx.author.guild_permissions.administrator:
        class FilaLauncher(View):
            @discord.ui.button(label="Abrir Painel de Criação", style=discord.ButtonStyle.primary, emoji="🚀")
            async def open(self, it, b): await it.response.send_modal(ModalConfigFila())
        await ctx.send("⚙️ **Configuração de Partida:**", view=FilaLauncher())

@bot.command()
async def Pix(ctx):
    emb = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie a chave PIX utilizada nas suas filas.", color=0x2b2d31)
    emb.set_thumbnail(url=ICONE_ORG); await ctx.send(embed=emb, view=ViewPixWS())

@bot.command()
async def mediar(ctx):
    if ctx.author.guild_permissions.manage_messages:
        await ctx.send(embed=ViewMediarWS().gerar_embed(), view=ViewMediarWS())

@bot.command()
async def canal_th(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); s = ChannelSelect(placeholder="Selecione o canal de tópicos")
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(s.values[0].id),))
        await it.response.send_message(f"✅ Canal de Tópicos definido!", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Configuração:", view=v)

@bot.command()
async def canal_logs(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); s = ChannelSelect(placeholder="Selecione o canal de logs")
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES ('canal_logs', ?)", (str(s.values[0].id),))
        await it.response.send_message(f"✅ Canal de Logs definido!", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Configuração:", view=v)

@bot.command()
async def ban(ctx, user: discord.Member, *, motivo="Nenhum"):
    if ctx.author.guild_permissions.administrator:
        db_execute("INSERT OR REPLACE INTO blacklist VALUES (?,?)", (user.id, motivo))
        await ctx.send(f"🚫 {user.mention} foi banido do sistema de apostas.")

@bot.command()
async def ranking(ctx):
    dados = db_query_all("SELECT med_id, COUNT(*) as total FROM historico GROUP BY med_id ORDER BY total DESC LIMIT 5")
    emb = discord.Embed(title="🏆 Ranking de Mediadores", color=0xFFD700)
    for i, row in enumerate(dados):
        emb.add_field(name=f"{i+1}º Lugar", value=f"<@{row[0]}> - {row[1]} partidas", inline=False)
    await ctx.send(embed=emb)

@bot.event
async def on_ready():
    init_db()
    bot.add_view(ViewPixWS())
    bot.add_view(ViewMediarWS())
    print(f"✅ SISTEMA ONLINE: {bot.user.name} | LINHAS: 350+")

if TOKEN: bot.run(TOKEN)
            
