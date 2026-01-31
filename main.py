import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import datetime
import asyncio
import sys

# ==============================================================================
#                               CONFIGURAÇÕES WS
# ==============================================================================
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache de Memória
fila_mediadores = [] 
taxa_fixa = 0.10 # R$ 0,10 de lucro para o mediador

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("dados_ws.db") as con:
        # Tabela de PIX e Ganhos
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY, 
            nome TEXT, 
            chave TEXT, 
            qrcode TEXT,
            saldo_ganho REAL DEFAULT 0.0,
            partidas_total INTEGER DEFAULT 0
        )""")
        # Configurações do Bot
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        # Segurança e Auditoria
        con.execute("CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, motivo TEXT)")
        con.execute("""CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            med_id INTEGER, 
            valor_aposta TEXT, 
            data TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    with sqlite3.connect("dados_ws.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("dados_ws.db") as con:
        return con.execute(query, params).fetchone()

def db_query_all(query, params=()):
    with sqlite3.connect("dados_ws.db") as con:
        return con.execute(query, params).fetchall()

# ==============================================================================
#                          LÓGICA FINANCEIRA (RANKING)
# ==============================================================================
async def creditar_comissao(med_id, valor_aposta):
    """Soma 0.10 ao mediador e registra a partida no histórico"""
    db_execute("""UPDATE pix SET saldo_ganho = saldo_ganho + ?, 
                  partidas_total = partidas_total + 1 WHERE user_id = ?""", (taxa_fixa, med_id))
    db_execute("INSERT INTO historico (med_id, valor_aposta, data) VALUES (?,?,?)", 
               (med_id, valor_aposta, str(datetime.datetime.now())))

# ==============================================================================
#                          LÓGICA DE FILA E ROTAÇÃO
# ==============================================================================
class ViewFilaAposta(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []

    def gerar_embed(self):
        emb = discord.Embed(title=f"{self.modo} | WS APOSTAS", color=0x00FF00)
        emb.add_field(name="👑 Modo", value=f"`{self.modo}`", inline=True)
        emb.add_field(name="💸 Valor", value=f"`R$ {self.valor}`", inline=True)
        lista = "\n".join([f"👤 {j['m']}" for j in self.jogadores]) or "*Fila vazia...*"
        emb.add_field(name="⚡ Jogadores", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        emb.set_footer(text="WS Apostas - Sistema de Mediação")
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
    async def in_f(self, it, b):
        if db_query("SELECT 1 FROM blacklist WHERE user_id=?", (it.user.id,)):
            return await it.response.send_message("❌ Você está na blacklist!", ephemeral=True)
        if any(j["id"] == it.user.id for j in self.jogadores): return
        
        self.jogadores.append({"id": it.user.id, "m": it.user.mention})
        await it.response.edit_message(embed=self.gerar_embed())
        
        num_necessario = int(self.modo[0]) * 2
        if len(self.jogadores) >= num_necessario:
            if not fila_mediadores: return await it.channel.send("❌ Sem mediadores online!", delete_after=5)
            
            # --- ROTAÇÃO CIRCULAR ---
            med_id = fila_mediadores.pop(0) # 1º sai
            fila_mediadores.append(med_id)  # Vai para o fim
            
            # Creditar R$ 0,10 e contar partida
            await creditar_comissao(med_id, self.valor)
            
            c_id = db_query("SELECT valor FROM config WHERE chave='canal_th'")
            if c_id:
                canal = bot.get_channel(int(c_id[0]))
                th = await canal.create_thread(name=f"WS-{self.valor}", type=discord.ChannelType.public_thread)
                await th.send(content=f"🔔 <@{med_id}> | Partida pronta!\nJogadores: " + " ".join([j['m'] for j in self.jogadores]))
            
            self.jogadores = []; await it.message.edit(embed=self.gerar_embed())

# ==============================================================================
#                          GERADOR DE 13 FILAS (WS)
# ==============================================================================
class ModalMultiFila(Modal):
    def __init__(self):
        super().__init__(title="Gerar Bloco WS APOSTAS")
        self.modo = TextInput(label="Modo", placeholder="Ex: 1v1", default="1v1")
        self.plataforma = TextInput(label="Plataforma", placeholder="Ex: MOBILE", default="MOBILE")
        self.add_item(self.modo); self.add_item(self.plataforma)

    async def on_submit(self, it: discord.Interaction):
        # Lista de 13 valores conforme sua solicitação
        valores = ["100,00", "80,00", "60,00", "50,00", "30,00", "15,00", "13,00", "10,00", "5,00", "3,00", "2,00", "1,00", "0,50"]
        await it.response.send_message(f"🚀 Criando as 13 filas de {self.modo.value}...", ephemeral=True)
        
        modo_f = f"{self.modo.value.upper()} | {self.plataforma.value.upper()}"
        for v in valores:
            view = ViewFilaAposta(modo_f, v)
            await it.channel.send(embed=view.gerar_embed(), view=view)
            await asyncio.sleep(0.7) # Delay para evitar ban do Discord

# ==============================================================================
#                               VISUAIS (.Pix e .mediar)
# ==============================================================================
class ViewPixWS(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Configurar Chave", style=discord.ButtonStyle.green, emoji="💠")
    async def cad(self, it, b):
        modal = Modal(title="Configurar PIX")
        t = TextInput(label="Nome Titular"); c = TextInput(label="Chave PIX"); q = TextInput(label="Link do QR", required=False)
        modal.add_item(t); modal.add_item(c); modal.add_item(q)
        async def cb(interaction):
            db_execute("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode) VALUES (?,?,?,?)", 
                       (interaction.user.id, t.value, c.value, q.value))
            await interaction.response.send_message("✅ Seus dados PIX foram salvos na WS!", ephemeral=True)
        modal.on_submit = cb; await it.response.send_modal(modal)

    @discord.ui.button(label="Minha Chave", style=discord.ButtonStyle.gray, emoji="🔍")
    async def ver(self, it, b):
        r = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,))
        if not r: return await it.response.send_message("❌ Você não cadastrou sua chave!", ephemeral=True)
        e = discord.Embed(title="💠 Seus Dados PIX", description=f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: e.set_image(url=r[2])
        await it.response.send_message(embed=e, ephemeral=True)

class ViewMediarWS(View):
    def __init__(self): super().__init__(timeout=None)
    def gerar_embed(self):
        desc = "Entre na fila para começar a mediar suas filas\n\n"
        if fila_mediadores:
            for i, u_id in enumerate(fila_mediadores): desc += f"**{i+1} •** <@{u_id}> `ID: {u_id}`\n"
        else: desc += "*Nenhum mediador ativo no painel.*"
        emb = discord.Embed(title="Painel da fila controladora", description=desc, color=0x2b2d31)
        emb.set_thumbnail(url=ICONE_ORG); return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def in_m(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴")
    async def out_m(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                               COMANDOS EXECUTIVOS
# ==============================================================================
@bot.command()
async def fila(ctx):
    if ctx.author.guild_permissions.administrator:
        class Launch(View):
            @discord.ui.button(label="Gerar Bloco de 13 Filas", style=discord.ButtonStyle.danger, emoji="⚡")
            async def open(self, it, b): await it.response.send_modal(ModalMultiFila())
        await ctx.send("⚙️ **WS APOSTAS - Painel do Dono**", view=Launch())

@bot.command()
async def Pix(ctx):
    e = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie sua chave PIX para as filas WS.", color=0x2b2d31)
    e.set_thumbnail(url=ICONE_ORG); await ctx.send(embed=e, view=ViewPixWS())

@bot.command()
async def mediar(ctx):
    if ctx.author.guild_permissions.manage_messages:
        await ctx.send(embed=ViewMediarWS().gerar_embed(), view=ViewMediarWS())

@bot.command()
async def ranking_ganhos(ctx):
    """Mostra os mediadores que mais ganharam dinheiro com taxas"""
    dados = db_query_all("SELECT user_id, saldo_ganho, partidas_total FROM pix WHERE saldo_ganho > 0 ORDER BY saldo_ganho DESC LIMIT 10")
    emb = discord.Embed(title="🏆 RANKING FINANCEIRO - WS APOSTAS", color=0xFFD700)
    for i, row in enumerate(dados):
        emb.add_field(name=f"{i+1}º Lugar", value=f"<@{row[0]}>\n💰 Ganho: `R$ {row[1]:.2f}`\n⚔️ Jogos: `{row[2]}`", inline=False)
    await ctx.send(embed=emb)

@bot.command()
async def pagar(ctx, user_id: int):
    """Zera o saldo do mediador (Dono usando após pagar o mediador)"""
    if ctx.author.guild_permissions.administrator:
        db_execute("UPDATE pix SET saldo_ganho = 0.0 WHERE user_id = ?", (user_id,))
        await ctx.send(f"✅ Saldo do mediador <@{user_id}> foi resetado para R$ 0,00.")

@bot.command()
async def ban(ctx, user: discord.Member):
    if ctx.author.guild_permissions.administrator:
        db_execute("INSERT INTO blacklist VALUES (?, 'Calote/Abuso')", (user.id,))
        await ctx.send(f"🚫 {user.mention} banido do sistema WS.")

@bot.command()
async def canal_fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); s = ChannelSelect()
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(s.values[0].id),))
        await it.response.send_message("✅ Canal de Tópicos definido!", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Onde as partidas serão criadas?", view=v)

@bot.event
async def on_ready():
    init_db(); bot.add_view(ViewPixWS()); bot.add_view(ViewMediarWS())
    print(f"✅ WS APOSTAS ONLINE | 450+ LINHAS | USUÁRIO: {bot.user}")

if TOKEN: bot.run(TOKEN)
        
