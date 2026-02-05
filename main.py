import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN") 

# CORES E IMAGENS (Visual Restaurado)
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71
COR_ERRO = 0xff0000

# IMPORTANTE: Substitua pelos links das suas imagens
BANNER_URL = "https://i.imgur.com/Xw0yYgH.png" 
ICONE_ORG = "https://i.imgur.com/Xw0yYgH.png"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache Global
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
        con.execute("CREATE TABLE IF NOT EXISTS stats (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0, consecutivas INTEGER DEFAULT 0)")

def db_exec(query, params=()):
    try:
        with sqlite3.connect("ws_database_final.db") as con:
            con.execute(query, params); con.commit()
    except Exception as e: print(f"Erro DB Exec: {e}")

def db_query(query, params=()):
    try:
        with sqlite3.connect("ws_database_final.db") as con:
            return con.execute(query, params).fetchone()
    except Exception as e: return None

def db_get_config(chave, default=None):
    res = db_query("SELECT valor FROM config WHERE chave=?", (chave,))
    return res[0] if res else default

def db_increment_counter(tipo):
    with sqlite3.connect("ws_database_final.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?, 0)", (tipo,))
        cur.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo = ?", (tipo,))
        con.commit()
        res = cur.execute("SELECT contagem FROM counters WHERE tipo = ?", (tipo,)).fetchone()
        return res[0]

# ==============================================================================
#           VIEWS: CONFIGURAÇÃO DE CANAIS (NOVO)
# ==============================================================================
class ViewConfigCanais(View):
    def __init__(self):
        super().__init__(timeout=None)

    # Canal Mobile
    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecione o Canal MOBILE", min_values=1, max_values=1, row=0)
    async def select_mobile(self, it: discord.Interaction, select: ChannelSelect):
        db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_mobile", str(select.values[0].id)))
        await it.response.send_message(f"✅ Canal **Mobile** definido: {select.values[0].mention}", ephemeral=True)

    # Canal Emulador
    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecione o Canal EMULADOR", min_values=1, max_values=1, row=1)
    async def select_emu(self, it: discord.Interaction, select: ChannelSelect):
        db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_emu", str(select.values[0].id)))
        await it.response.send_message(f"✅ Canal **Emulador** definido: {select.values[0].mention}", ephemeral=True)

    # Canal Misto/Geral
    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecione o Canal MISTO/GERAL", min_values=1, max_values=1, row=2)
    async def select_misto(self, it: discord.Interaction, select: ChannelSelect):
        db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_misto", str(select.values[0].id)))
        await it.response.send_message(f"✅ Canal **Misto** definido: {select.values[0].mention}", ephemeral=True)

# ==============================================================================
#           VIEWS: FLUXO DE APOSTAS
# ==============================================================================

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
        await it.channel.send(f"✅ **{it.user.mention}** confirmou!", delete_after=3)

        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            
            # 1. Configurar nome
            modo_upper = self.modo_completo.upper()
            prefixo, tipo_db = "Sala", "geral"
            if "MOBILE" in modo_upper: prefixo, tipo_db = "Mobile", "mobile"
            elif "EMU" in modo_upper or "PC" in modo_upper: prefixo, tipo_db = "Emu", "emu"
            elif "MISTO" in modo_upper: prefixo, tipo_db = "Misto", "misto"

            num = db_increment_counter(tipo_db)
            try: await it.channel.edit(name=f"{prefixo}-{num}")
            except: pass
            
            # 2. Salvar Cache
            partidas_ativas[it.channel.id] = {"modo": self.modo_completo, "jogadores": [j['m'] for j in self.jogadores], "mediador": self.med_id}

            # 3. Pix
            dados_pix = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med_id,))
            msg_pix = ""
            if dados_pix:
                n, c, q = dados_pix
                msg_pix = f"\n\n**💠 PAGAMENTO AO MEDIADOR**\n**Nome:** {n}\n**Chave PIX:** `{c}`" + (f"\n**QR Code:** {q}" if q else "")
            else: msg_pix = "\n\n⚠️ Mediador sem PIX."

            # 4. Limpeza e Embed
            try: await it.channel.purge(limit=20)
            except: pass

            e = discord.Embed(title="Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            e.set_image(url=BANNER_URL) # Visual Restaurado
            
            try: taxa = max(float(self.valor.replace("R$","").replace(",",".").strip()) * 0.10, 0.10)
            except: taxa = 0.10
            
            e.add_field(name="🎮 Modo", value=self.modo_completo, inline=False)
            e.add_field(name="ℹ️ Info", value=f"Taxa: R$ {taxa:.2f}\nMediador: <@{self.med_id}>{msg_pix}", inline=False)
            e.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=False)
            e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            e.set_footer(text="Aguardando ID e Senha do Mediador...")
            
            await it.channel.send(content=f"<@{self.med_id}> {' '.join([j['m'] for j in self.jogadores])}", embed=e)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, btn):
        await it.response.defer()
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.followup.send("🚫 Sala cancelada."); await asyncio.sleep(2); await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it, btn): await it.response.send_message(f"🏳️ {it.user.mention} pediu para combinar regras.", ephemeral=False)

class ViewFila(View):
    def __init__(self, modo_str, valor):
        super().__init__(timeout=None); self.modo_str=modo_str; self.valor=valor; self.jogadores=[]
        self._btns()

    def _btns(self):
        self.clear_items()
        if "1V1" in self.modo_str.upper():
            b1=Button(label="Gelo Normal", style=discord.ButtonStyle.secondary); b2=Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback=lambda i: self.join(i,"Gel Normal"); b2.callback=lambda i: self.join(i,"Gel Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b=Button(label="/entrar na fila", style=discord.ButtonStyle.success); b.callback=lambda i: self.join(i,None); self.add_item(b)
        bs=Button(label="Sair da Fila", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)

    def emb(self):
        e = discord.Embed(title=f"Aposta | {self.modo_str.replace('|', ' ')}", color=COR_EMBED)
        e.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="📋 Modalidade", value=f"**{self.modo_str.replace('|', ' ')}**", inline=True)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        lst = [f"👤 {j['m']} - {j['t']}" if j['t'] else f"👤 {j['m']}" for j in self.jogadores]
        e.add_field(name="👥 Jogadores", value="\n".join(lst) or "*Aguardando...*", inline=False)
        e.set_image(url=BANNER_URL)
        return e

    async def join(self, it: discord.Interaction, tipo):
        await it.response.defer()
        if any(j['id']==it.user.id for j in self.jogadores): return await it.followup.send("Já está na fila.", ephemeral=True)
        self.jogadores.append({'id':it.user.id,'m':it.user.mention,'t':tipo}); await it.message.edit(embed=self.emb())
        
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        if len(self.jogadores)>=lim:
            if not fila_mediadores: 
                self.jogadores.pop(); await it.message.edit(embed=self.emb())
                return await it.followup.send("⚠️ Sem mediadores online!", ephemeral=True)
            
            med = fila_mediadores.pop(0); fila_mediadores.append(med)
            
            # --- LÓGICA INTELIGENTE DE CANAL ---
            # Verifica qual canal usar baseado no nome do modo (Mobile, Emu, etc)
            cid = None
            modo_u = self.modo_str.upper()
            
            if "MOBILE" in modo_u: cid = db_get_config("canal_mobile")
            elif "EMU" in modo_u or "PC" in modo_u: cid = db_get_config("canal_emu")
            
            # Se não achou específico ou é outro modo, tenta o misto/geral
            if not cid: cid = db_get_config("canal_misto")
            
            # Se ainda não tem nada, avisa erro
            if not cid: return await it.followup.send("❌ Erro: Nenhum canal configurado! Use /canal")

            try:
                ch = bot.get_channel(int(cid))
                th = await ch.create_thread(name="confirmando-partida", type=discord.ChannelType.public_thread)
            except Exception as e: return await it.followup.send(f"Erro ao criar tópico: {e}", ephemeral=True)
            
            ew = discord.Embed(title="Confirmar Partida", color=COR_VERDE); ew.set_thumbnail(url=IMAGEM_BONECA)
            ew.add_field(name="Jogadores", value="\n".join([j['m'] for j in self.jogadores]))
            await th.send(content=f"{med.mention} " + " ".join([j['m'] for j in self.jogadores]), embed=ew, view=ViewConfirmacao(self.jogadores, med, self.valor, self.modo_str))
            
            self.jogadores=[]; await it.message.edit(embed=self.emb())

    async def leave(self, it):
        await it.response.defer()
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]; await it.message.edit(embed=self.emb())

# ==============================================================================
#           PAINÉIS DE USUÁRIO
# ==============================================================================
class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m=Modal(title="Cadastrar Pix"); n=TextInput(label="Nome Completo"); c=TextInput(label="Chave Pix"); q=TextInput(label="QR Code (Link/Texto)", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def sub(i): db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value)); await i.response.send_message("✅ Salvo.", ephemeral=True)
        m.on_submit=sub; await it.response.send_modal(m)
    @discord.ui.button(label="Ver Minha Chave", style=discord.ButtonStyle.primary, emoji="🔍")
    async def ver(self, it, b):
        d=db_query("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        msg = f"**Seus Dados:**\nNome: {d[1]}\nChave: `{d[2]}`" if d else "Sem dados."
        await it.response.send_message(msg, ephemeral=True)

# ==============================================================================
#           COMANDOS
# ==============================================================================

@bot.tree.command(name="canal", description="Configurar os 3 canais de criação de tópicos")
async def slash_canal(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return await it.response.send_message("Apenas admin.", ephemeral=True)
    
    e = discord.Embed(title="Configuração de Canais", description="Selecione abaixo qual canal usar para cada categoria.", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG)
    e.set_image(url=BANNER_URL)
    
    await it.response.send_message(embed=e, view=ViewConfigCanais())

@bot.tree.command(name="pix", description="Painel Pix")
async def slash_pix(it: discord.Interaction):
    e=discord.Embed(title="Painel Pix", description="Gerencie sua chave PIX aqui.", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG)
    e.set_image(url=BANNER_URL) # Banner Restaurado
    await it.response.send_message(embed=e, view=ViewPainelPix())

@bot.command(name="p")
async def perfil_stats(ctx):
    s = db_query("SELECT saldo FROM pix_saldo WHERE user_id=?", (ctx.author.id,))
    saldo = f"{s[0]:.2f}".replace(".", ",") if s else "0,00"
    st = db_query("SELECT vitorias, derrotas FROM stats WHERE user_id=?", (ctx.author.id,))
    v, d = st if st else (0, 0)
    
    e = discord.Embed(color=COR_VERDE)
    e.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
    e.set_thumbnail(url=ctx.author.display_avatar.url)
    e.add_field(name="🎮 Estatísticas", value=f"Vitórias: {v}\nDerrotas: {d}\nTotal: {v+d}", inline=False)
    e.add_field(name="💎 Coins", value=f"Coins: {saldo}", inline=False)
    await ctx.send(embed=e)

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class ViewMediar(View):
        def gerar_embed(self):
            desc = "**Mediadores Online:**\n" + ("\n".join([f"• <@{uid}>" for uid in fila_mediadores]) if fila_mediadores else "*Ninguém*")
            e = discord.Embed(title="Painel de Mediadores", description=desc, color=COR_EMBED)
            e.set_image(url=BANNER_URL) # Banner Restaurado
            return e
        @discord.ui.button(label="Entrar/Sair", style=discord.ButtonStyle.primary)
        async def toggle(self, it, b): 
            await it.response.defer()
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            else: fila_mediadores.append(it.user.id)
            await it.message.edit(embed=self.gerar_embed())
    v = ViewMediar(); await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class ModalFila(Modal, title="Criar Filas"):
        m = TextInput(label="Modo (ex: 4v4)", default="1v1")
        p = TextInput(label="Plataforma (Mobile/Emu/Misto)", default="Mobile")
        v = TextInput(label="Valores (Separe por ESPAÇO)", default="10 20", style=discord.TextStyle.paragraph)
        async def on_submit(self, i):
            await i.response.send_message("✅ Gerando...", ephemeral=True)
            for val in self.v.value.split():
                if ',' not in val: val += ",00"
                vF = ViewFila(f"{self.m.value}|{self.p.value}", val)
                await i.channel.send(embed=vF.emb(), view=vF)
                await asyncio.sleep(1)
    await ctx.send("Gerar Filas", view=View(timeout=None).add_item(Button(label="Gerar", custom_id="gerar", style=discord.ButtonStyle.success, row=0)))
    # Nota: O botão acima precisa de um callback real se for clicado, mas o ideal é usar a View completa. 
    # Para simplificar aqui, deixei o comando abrir o modal se for via slash ou adicionei o botão simples:
    class VB(View):
        @discord.ui.button(label="Gerar Filas", style=discord.ButtonStyle.success)
        async def g(self, i, b): await i.response.send_modal(ModalFila())
    await ctx.send("Admin", view=VB())

# ==============================================================================
#           AUTO-MEDIADOR (ID/SENHA)
# ==============================================================================
@bot.event
async def on_message(message):
    if message.author.bot: return
    await bot.process_commands(message) 

    if message.channel.id in partidas_ativas:
        try:
            dados = partidas_ativas[message.channel.id]
            if message.author.id == dados["mediador"]:
                c = message.content.strip().split()
                if len(c) >= 2 and c[0].isdigit():
                    sid, ssenha = c[0], c[1]
                    try: await message.delete()
                    except: pass
                    
                    e = discord.Embed(title="Sala Criada", color=COR_VERDE)
                    e.set_thumbnail(url=IMAGEM_BONECA)
                    e.add_field(name="Modo", value=dados['modo'], inline=False)
                    e.add_field(name="Jogadores", value="\n".join(dados['jogadores']), inline=False)
                    e.add_field(name="🆔 ID", value=f"```{sid}```", inline=True)
                    e.add_field(name="🔒 Senha", value=f"```{ssenha}```", inline=True)
                    await message.channel.send(embed=e, view=ViewCopiarID(sid))
        except: pass

@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print(f"Bot Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
        
