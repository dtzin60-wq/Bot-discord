import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import random
import aiohttp # Para baixar emojis se necessário
from datetime import datetime

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN") 

# CORES
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71
COR_ERRO = 0xff0000
COR_BLACKLIST = 0x000000

# IMAGENS
BANNER_URL = "https://i.imgur.com/Xw0yYgH.png" 
ICONE_ORG = "https://i.imgur.com/Xw0yYgH.png"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache
fila_mediadores = []
partidas_ativas = {} 

# ==============================================================================
#                         BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0)")
        con.execute("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INTEGER DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS stats (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, motivo TEXT)")

def db_exec(query, params=()):
    try:
        with sqlite3.connect("ws_database_final.db") as con:
            con.execute(query, params); con.commit()
    except: pass

def db_query(query, params=()):
    try:
        with sqlite3.connect("ws_database_final.db") as con:
            return con.execute(query, params).fetchone()
    except: return None

def db_get_config(chave):
    res = db_query("SELECT valor FROM config WHERE chave=?", (chave,))
    return res[0] if res else None

def db_increment_counter(tipo):
    with sqlite3.connect("ws_database_final.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?, 0)", (tipo,))
        cur.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo = ?", (tipo,))
        con.commit()
        res = cur.execute("SELECT contagem FROM counters WHERE tipo = ?", (tipo,)).fetchone()
        return res[0]

def is_blacklisted(user_id):
    return db_query("SELECT user_id FROM blacklist WHERE user_id=?", (user_id,)) is not None

# ==============================================================================
#           VIEWS E LÓGICA
# ==============================================================================

class ViewConfigCanais(View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Canal Aleatório 1", min_values=1, max_values=1, row=0)
    async def s1(self, it, select):
        db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_1", str(select.values[0].id)))
        await it.response.send_message(f"✅ Canal 1 Salvo: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Canal Aleatório 2", min_values=1, max_values=1, row=1)
    async def s2(self, it, select):
        db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_2", str(select.values[0].id)))
        await it.response.send_message(f"✅ Canal 2 Salvo: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Canal Aleatório 3", min_values=1, max_values=1, row=2)
    async def s3(self, it, select):
        db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_3", str(select.values[0].id)))
        await it.response.send_message(f"✅ Canal 3 Salvo: {select.values[0].mention}", ephemeral=True)

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m=Modal(title="Cadastrar Pix"); n=TextInput(label="Nome"); c=TextInput(label="Chave"); q=TextInput(label="QR Code (Opcional)", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def sub(i): db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value)); await i.response.send_message("✅ Salvo.", ephemeral=True)
        m.on_submit=sub; await it.response.send_modal(m)
    @discord.ui.button(label="Ver Minha Chave", style=discord.ButtonStyle.primary, emoji="🔍")
    async def ver(self, it, b):
        d=db_query("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        await it.response.send_message(f"**Seus Dados:**\nNome: {d[1]}\nChave: `{d[2]}`" if d else "Sem dados.", ephemeral=True)

class ViewCopiarID(View):
    def __init__(self, id_sala): super().__init__(timeout=None); self.id_sala = id_sala
    @discord.ui.button(label="Copiar ID", style=discord.ButtonStyle.secondary, emoji="📋")
    async def copiar(self, it, b): await it.response.send_message(f"{self.id_sala}", ephemeral=True)

class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor, modo_completo):
        super().__init__(timeout=None)
        self.jogadores = jogadores; self.med_id = med_id; self.valor = valor; self.modo_completo = modo_completo
        self.confirms = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, it: discord.Interaction, btn: Button):
        await it.response.defer()
        if it.user.id not in [j['id'] for j in self.jogadores]: return await it.followup.send("Você não está nesta partida.", ephemeral=True)
        if it.user.id in self.confirms: return await it.followup.send("Você já confirmou.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            num = db_increment_counter("geral")
            try: await it.channel.edit(name=f"Sala-{num}")
            except: pass
            
            partidas_ativas[it.channel.id] = {"modo": self.modo_completo, "jogadores": [j['m'] for j in self.jogadores], "mediador": self.med_id}
            
            d = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med_id,))
            msg_pix = f"\n\n**💠 PAGAMENTO**\nNome: {d[0]}\nChave: `{d[1]}`" if d else "\n\n⚠️ Mediador sem PIX."

            try: await it.channel.purge(limit=20)
            except: pass

            e = discord.Embed(title="Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA); e.set_image(url=BANNER_URL)
            e.add_field(name="🎮 Modo", value=self.modo_completo, inline=False)
            e.add_field(name="ℹ️ Info", value=f"Mediador: <@{self.med_id}>{msg_pix}", inline=False)
            e.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=False)
            e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            e.set_footer(text="Aguardando ID e Senha...")
            
            await it.channel.send(content=f"<@{self.med_id}> {' '.join([j['m'] for j in self.jogadores])}", embed=e)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, btn): await it.channel.delete()

class ViewFila(View):
    def __init__(self, modo_str, valor):
        super().__init__(timeout=None); self.modo_str=modo_str; self.valor=valor; self.jogadores=[]
        self._btns()

    def _btns(self):
        self.clear_items()
        b=Button(label="/entrar na fila", style=discord.ButtonStyle.success); b.callback=lambda i: self.join(i); self.add_item(b)
        bs=Button(label="Sair da Fila", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)

    def emb(self):
        e = discord.Embed(title=f"Aposta | {self.modo_str}", color=COR_EMBED)
        e.set_author(name="SPACE APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jogadores]) or "*Aguardando...*", inline=False)
        e.set_image(url=BANNER_URL)
        return e

    async def join(self, it: discord.Interaction):
        await it.response.defer()
        if is_blacklisted(it.user.id): return await it.followup.send("🚫 Você está na Blacklist!", ephemeral=True)
        if any(j['id']==it.user.id for j in self.jogadores): return await it.followup.send("Já na fila.", ephemeral=True)
        
        self.jogadores.append({'id':it.user.id,'m':it.user.mention})
        await it.message.edit(embed=self.emb())
        
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        
        if len(self.jogadores)>=lim:
            if not fila_mediadores: 
                self.jogadores.pop(); await it.message.edit(embed=self.emb())
                return await it.followup.send("⚠️ Sem mediadores!", ephemeral=True)
            
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            
            canais = [db_get_config("canal_1"), db_get_config("canal_2"), db_get_config("canal_3")]
            validos = [c for c in canais if c]
            if not validos: return await it.followup.send("❌ Sem canais configurados no /canal!", ephemeral=True)
            
            try:
                ch = bot.get_channel(int(random.choice(validos)))
                th = await ch.create_thread(name="confirmando", type=discord.ChannelType.public_thread)

                async def limpar():
                    await asyncio.sleep(0.1)
                    async for msg in ch.history(limit=5):
                        if msg.type == discord.MessageType.thread_created:
                            try: await msg.delete()
                            except: pass
                            break
                bot.loop.create_task(limpar())

                ew = discord.Embed(title="Confirmar Partida", color=COR_VERDE)
                ew.add_field(name="Jogadores", value="\n".join([j['m'] for j in self.jogadores]))
                await th.send(content=f"<@{med_id}> " + " ".join([j['m'] for j in self.jogadores]), embed=ew, view=ViewConfirmacao(self.jogadores, med_id, self.valor, self.modo_str))
                
                self.jogadores=[]; await it.message.edit(embed=self.emb())
            except Exception as e: print(e)

    async def leave(self, it):
        await it.response.defer()
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]; await it.message.edit(embed=self.emb())

# ==============================================================================
#           COMANDOS DAS PRINTS (ADMIN & UTILITÁRIOS)
# ==============================================================================

# --- ADMINISTRAÇÃO DE COINS ---
@bot.tree.command(name="darcoin", description="Adiciona Coins ao saldo de um usuário")
async def darcoin(it: discord.Interaction, user: discord.User, valor: float):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Sem permissão.", ephemeral=True)
    db_exec("INSERT OR IGNORE INTO pix_saldo (user_id, saldo) VALUES (?, 0)", (user.id,))
    db_exec("UPDATE pix_saldo SET saldo = saldo + ? WHERE user_id = ?", (valor, user.id))
    await it.response.send_message(f"✅ Adicionado **R$ {valor:.2f}** para {user.mention}.", ephemeral=True)

@bot.tree.command(name="removercoin", description="Remove Coins de um usuário")
async def removercoin(it: discord.Interaction, user: discord.User, valor: float):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Sem permissão.", ephemeral=True)
    db_exec("UPDATE pix_saldo SET saldo = MAX(0, saldo - ?) WHERE user_id = ?", (valor, user.id))
    await it.response.send_message(f"✅ Removido **R$ {valor:.2f}** de {user.mention}.", ephemeral=True)

# --- STATUS E PERFIL ---
@bot.tree.command(name="darvitoria", description="Adiciona vitórias ao perfil do usuário")
async def darvitoria(it: discord.Interaction, user: discord.User, quantidade: int):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Sem permissão.", ephemeral=True)
    db_exec("INSERT OR IGNORE INTO stats (user_id, vitorias, derrotas) VALUES (?, 0, 0)", (user.id,))
    db_exec("UPDATE stats SET vitorias = vitorias + ? WHERE user_id = ?", (quantidade, user.id))
    await it.response.send_message(f"✅ Adicionado **{quantidade} vitórias** para {user.mention}.", ephemeral=True)

@bot.tree.command(name="limparperfil", description="Reseta vitórias/derrotas de um usuário")
async def limparperfil(it: discord.Interaction, user: discord.User):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Sem permissão.", ephemeral=True)
    db_exec("UPDATE stats SET vitorias=0, derrotas=0 WHERE user_id=?", (user.id,))
    await it.response.send_message(f"♻️ Perfil de {user.mention} resetado.", ephemeral=True)

# --- BLACKLIST ---
@bot.tree.command(name="blacklist", description="Banir usuário de usar o bot")
async def blacklist(it: discord.Interaction, user: discord.User, motivo: str = "Sem motivo"):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Sem permissão.", ephemeral=True)
    db_exec("INSERT OR REPLACE INTO blacklist (user_id, motivo) VALUES (?, ?)", (user.id, motivo))
    await it.response.send_message(f"🚫 {user.mention} adicionado à Blacklist. Motivo: {motivo}", ephemeral=True)

@bot.tree.command(name="unblacklist", description="Remover usuário da Blacklist")
async def unblacklist(it: discord.Interaction, user: discord.User):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Sem permissão.", ephemeral=True)
    db_exec("DELETE FROM blacklist WHERE user_id=?", (user.id,))
    await it.response.send_message(f"✅ {user.mention} removido da Blacklist.", ephemeral=True)

# --- UTILITÁRIOS ---
@bot.tree.command(name="ping", description="Veja a latência do bot")
async def ping(it: discord.Interaction):
    await it.response.send_message(f"🏓 Pong! **{round(bot.latency * 1000)}ms**", ephemeral=True)

@bot.tree.command(name="embed", description="Crie uma mensagem bonita (Embed)")
async def criar_embed(it: discord.Interaction, titulo: str, descricao: str, cor_hex: str = "#2ecc71"):
    if not it.user.guild_permissions.manage_messages: return await it.response.send_message("Sem permissão.", ephemeral=True)
    try:
        cor = int(cor_hex.replace("#", ""), 16)
        embed = discord.Embed(title=titulo, description=descricao, color=cor)
        if it.channel: await it.channel.send(embed=embed)
        await it.response.send_message("✅ Embed enviado.", ephemeral=True)
    except:
        await it.response.send_message("❌ Cor inválida. Use Hex (ex: #ffffff).", ephemeral=True)

@bot.tree.command(name="partidasativas", description="Mostra quantas partidas estão rolando agora")
async def partidasativas(it: discord.Interaction):
    qtd = len(partidas_ativas)
    desc = "\n".join([f"• <#{cid}> - {d['modo']}" for cid, d in partidas_ativas.items()]) if qtd > 0 else "Nenhuma partida no momento."
    e = discord.Embed(title=f"Partidas Ativas ({qtd})", description=desc, color=COR_VERDE)
    await it.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="addemoji", description="Adiciona um emoji ao servidor via link")
async def addemoji(it: discord.Interaction, nome: str, url: str):
    if not it.user.guild_permissions.manage_emojis: return await it.response.send_message("Sem permissão.", ephemeral=True)
    await it.response.defer()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200: return await it.followup.send("Erro ao baixar imagem.")
                data = await resp.read()
                emoji = await it.guild.create_custom_emoji(name=nome, image=data)
                await it.followup.send(f"✅ Emoji adicionado: {emoji}")
    except Exception as e:
        await it.followup.send(f"Erro: {e}")

# ==============================================================================
#           COMANDOS PADRÃO (CANAL, PIX, FILA)
# ==============================================================================

@bot.tree.command(name="canal", description="Configurar 3 canais para sorteio aleatório")
async def slash_canal(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    e = discord.Embed(title="Canais de Criação Aleatória", description="Selecione os canais abaixo.", color=COR_EMBED)
    e.set_image(url=BANNER_URL)
    await it.response.send_message(embed=e, view=ViewConfigCanais(), ephemeral=True)

@bot.tree.command(name="pix", description="Painel Pix")
async def slash_pix(it: discord.Interaction):
    e=discord.Embed(title="Painel Pix", description="Gerencie sua chave PIX aqui.", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG); e.set_image(url=BANNER_URL)
    await it.response.send_message(embed=e, view=ViewPainelPix(), ephemeral=True)

@bot.tree.command(name="painelsuascoins", description="Veja seu saldo de coins")
async def painelsuascoins(it: discord.Interaction):
    s = db_query("SELECT saldo FROM pix_saldo WHERE user_id=?", (it.user.id,))
    saldo = s[0] if s else 0.0
    st = db_query("SELECT vitorias, derrotas FROM stats WHERE user_id=?", (it.user.id,))
    v, d = st if st else (0, 0)
    
    e = discord.Embed(title=f"Perfil de {it.user.name}", color=COR_EMBED)
    e.set_thumbnail(url=it.user.display_avatar.url)
    e.add_field(name="💰 Coins", value=f"R$ {saldo:.2f}", inline=False)
    e.add_field(name="🏆 Vitórias", value=str(v), inline=True)
    e.add_field(name="💀 Derrotas", value=str(d), inline=True)
    await it.response.send_message(embed=e, ephemeral=True)

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class ViewMediar(View):
        def gerar_embed(self):
            desc = "**Mediadores Online:**\n" + ("\n".join([f"• <@{uid}>" for uid in fila_mediadores]) if fila_mediadores else "*Ninguém*")
            e = discord.Embed(title="Painel de Mediadores", description=desc, color=COR_EMBED)
            e.set_image(url=BANNER_URL) 
            return e
        @discord.ui.button(label="Entrar/Sair", style=discord.ButtonStyle.primary)
        async def toggle(self, it, b): 
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            else: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
    v = ViewMediar(); await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class ModalFila(Modal, title="Criar Filas"):
        m = TextInput(label="Modo", default="4v4")
        v = TextInput(label="Valores (espaço)", default="10 20")
        async def on_submit(self, i):
            await i.response.send_message("✅ Feito.", ephemeral=True)
            for val in self.v.value.split():
                vF = ViewFila(self.m.value, val if "," in val else val+",00")
        
