import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect, ChannelSelect
import sqlite3
import os
import asyncio

# === CONFIG ===
TOKEN = os.getenv("TOKEN")
COR_EMB = 0x2b2d31 
COR_OK = 0x2ecc71 
ICONE = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
BANNER = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
BONECA = "https://i.imgur.com/Xw0yYgH.png"
DB = "ws_database_final.db"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)
fila_mediadores = []

# === BANCO DE DADOS ===
def db_ex(q, p=()):
    with sqlite3.connect(DB) as c: c.execute(q, p); c.commit()
def db_get(q, p=()):
    with sqlite3.connect(DB) as c: return c.execute(q, p).fetchone()

def init_db():
    db_ex("CREATE TABLE IF NOT EXISTS pix (user_id INT PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    db_ex("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    db_ex("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INT PRIMARY KEY, saldo REAL DEFAULT 0)")
    db_ex("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INT DEFAULT 0)")
    db_ex("CREATE TABLE IF NOT EXISTS perfis (user_id INT PRIMARY KEY, vitorias INT DEFAULT 0, derrotas INT DEFAULT 0, consecutivas INT DEFAULT 0, total_partidas INT DEFAULT 0, coins INT DEFAULT 0)")

def inc_cnt(t): 
    with sqlite3.connect(DB) as c:
        c.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?, 0)", (t,))
        c.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo = ?", (t,))
        c.commit(); return c.execute("SELECT contagem FROM counters WHERE tipo = ?", (t,)).fetchone()[0]

# === LOGICA JOGO ===
def reg_win(u): 
    db_ex("INSERT OR IGNORE INTO perfis (user_id) VALUES (?)", (u,))
    db_ex("UPDATE perfis SET vitorias=vitorias+1, consecutivas=consecutivas+1, total_partidas=total_partidas+1, coins=coins+1 WHERE user_id=?", (u,))
def reg_loss(u): 
    db_ex("INSERT OR IGNORE INTO perfis (user_id) VALUES (?)", (u,))
    db_ex("UPDATE perfis SET derrotas=derrotas+1, consecutivas=0, total_partidas=total_partidas+1 WHERE user_id=?", (u,))

class ViewConf(View):
    def __init__(self, jog, med, val, modo):
        super().__init__(timeout=None); self.jog=jog; self.med=med; self.val=val; self.modo=modo; self.cnf=[]
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def c(self, it, b):
        if it.user.id not in [j['id'] for j in self.jog]: return await it.response.send_message("Não é sua partida.", ephemeral=True)
        if it.user.id in self.cnf: return await it.response.send_message("Já confirmou.", ephemeral=True)
        self.cnf.append(it.user.id); await it.channel.send(f"✅ **{it.user.mention}** confirmou!")
        if len(self.cnf)>=len(self.jog):
            self.stop()
            m=self.modo.upper(); p="Sala"; t="geral"
            if "MOBILE" in m: p="Mobile"; t="mobile"
            elif "MISTO" in m: p="Misto"; t="misto"
            elif "FULL" in m: p="Full"; t="full"
            elif "EMU" in m: p="Emu"; t="emu"
            try: await it.channel.edit(name=f"{p}-{inc_cnt(t)}")
            except: pass
            
            e=discord.Embed(title="Partida Confirmada", color=COR_OK); e.set_thumbnail(url=BONECA)
            e.add_field(name="🎮 Estilo", value=f"{self.modo.split('|')[0]} Gel Normal", inline=False)
            try: tx=f"R$ {max(float(self.val.replace('R$','').replace(',','.').strip())*0.1, 0.1):.2f}".replace('.',',')
            except: tx="R$ 0,10"
            e.add_field(name="ℹ️ Info", value=f"Taxa: {tx}\nMediador: <@{self.med}>", inline=False)
            e.add_field(name="💎 Valor", value=f"R$ {self.val}", inline=False)
            e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jog]), inline=False)
            await it.channel.send(content=f"<@{self.med}> {' '.join([j['m'] for j in self.jog])}", embed=e)
            db_ex("UPDATE pix_saldo SET saldo=saldo+0.10 WHERE user_id=?",(self.med,))
    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def r(self, it, b):
        if it.user.id in [j['id'] for j in self.jog]: await it.channel.send("🚫 Cancelada."); await asyncio.sleep(2); await it.channel.delete()
    @discord.ui.button(label="Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def rg(self, it, b): await it.response.send_message(f"🏳️ {it.user.mention} quer combinar regras.", ephemeral=False)

class ViewFila(View):
    def __init__(self, m, v): super().__init__(timeout=None); self.m=m; self.v=v; self.j=[]
        self.clear_items()
        if "1V1" in m.upper():
            b1=Button(label="Normal", style=discord.ButtonStyle.secondary); b2=Button(label="Infinito", style=discord.ButtonStyle.secondary)
            b1.callback=lambda i: self.join(i,"Normal"); b2.callback=lambda i: self.join(i,"Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b=Button(label="Entrar", style=discord.ButtonStyle.success); b.callback=lambda i: self.join(i,None); self.add_item(b)
        bs=Button(label="Sair", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)
    def emb(self):
        e=discord.Embed(title=f"Aposta | {self.m.replace('|',' ')}", color=COR_EMB); e.set_author(name="WS", icon_url=ICONE)
        e.add_field(name="📋 Modo", value=f"**{self.m}**", inline=True); e.add_field(name="💰 Valor", value=f"**R$ {self.v}**", inline=True)
        e.add_field(name="👥 Jogadores", value="\n".join([f"👤 {p['m']}" for p in self.j]) or "*Aguardando...*", inline=False)
        e.set_image(url=BANNER); return e
    async def join(self, it, t):
        if any(x['id']==it.user.id for x in self.j): return await it.response.send_message("Já está.", ephemeral=True)
        self.j.append({'id':it.user.id,'m':it.user.mention,'t':t}); await it.response.edit_message(embed=self.emb())
        lim=int(self.m[0])*2 if self.m[0].isdigit() else 2
        if len(self.j)>=lim:
            if not fila_mediadores: return await it.channel.send("⚠️ Sem mediadores!", delete_after=5)
            md=fila_mediadores.pop(0); fila_mediadores.append(md)
            cf=db_get("SELECT valor FROM config WHERE chave='canal_th'")
            if not cf: return await it.channel.send("❌ Configure /canal")
            ch=bot.get_channel(int(cf[0])); th=await ch.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.public_thread)
            ew=discord.Embed(title="Aguardando...", color=COR_OK); ew.set_thumbnail(url=BONECA)
            ew.add_field(name="Modo", value=self.m); ew.add_field(name="Valor", value=f"R$ {self.v}")
            ew.add_field(name="Jogadores", value="\n".join([x['m'] for x in self.j]))
            ew.add_field(name="\u200b", value="```Regras adicionais podem ser combinadas.```")
            await th.send(content=" ".join([x['m'] for x in self.j]), embed=ew, view=ViewConf(self.j, md, self.v, self.m))
            self.j=[]; await it.message.edit(embed=self.emb())
    async def leave(self, it): self.j=[x for x in self.j if x['id']!=it.user.id]; await it.response.edit_message(embed=self.emb())

# === VIEWS PAINEIS ===
class ViewPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠")
    async def c(self, it, b):
        m=Modal(title="Pix"); n=TextInput(label="Nome"); c=TextInput(label="Chave"); q=TextInput(label="QR", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def s(i): db_ex("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value)); await i.response.send_message("Salvo.", ephemeral=True)
        m.on_submit=s; await it.response.send_modal(m)
    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍")
    async def v(self, it, b):
        d=db_get("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        if d: await it.response.send_message(f"Nome: {d[1]}\nChave: `{d[2]}`\nQR: {d[3] or 'N/A'}", ephemeral=True)
        else: await it.response.send_message("Sem dados.", ephemeral=True)
    @discord.ui.button(label="Ver Chave Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def vm(self, it, b):
        v=View(); s=UserSelect()
        async def cb(i):
            d=db_get("SELECT * FROM pix WHERE user_id=?",(s.values[0].id,))
            if d: await i.response.send_message(f"Mediador: {s.values[0].mention}\nChave: `{d[2]}`", ephemeral=True)
            else: await i.response.send_message("Sem dados.", ephemeral=True)
        s.callback=cb; v.add_item(s); await it.response.send_message("Selecione:", view=v, ephemeral=True)

class ViewBotConfig(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Config Filas", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def f(self, it, b): await it.response.send_message("Use .fila", ephemeral=True)

# === COMANDOS SLASH ===
@bot.tree.command(name="perfil", description="Ver estatísticas")
async def pf(it: discord.Interaction, usuario: discord.Member=None):
    await it.response.defer(); alvo=usuario if usuario else it.user
    d=db_get("SELECT vitorias, derrotas, consecutivas, total_partidas, coins FROM perfis WHERE user_id=?",(alvo.id,))
    v,dt,c,t,co = d if d else (0,0,0,0,0)
    e=discord.Embed(color=COR_OK); e.set_author(name=alvo.name, icon_url=alvo.display_avatar.url)
    e.add_field(name="🎮 Estatísticas", value=f"Vitórias: {v}\nDerrotas: {dt}\nConsecutivas: {c}\nTotal: {t}", inline=False)
    e.add_field(name="💎 Coins", value=f"| Coins: {co}", inline=False); e.set_thumbnail(url=alvo.display_avatar.url)
    await it.followup.send(embed=e)

@bot.tree.command(name="gg", description="Registrar resultado (Staff)")
async def gg(it: discord.Interaction, vencedor: discord.Member, perdedor: discord.Member):
    if not it.user.guild_permissions.manage_messages: return await it.response.send_message("❌", ephemeral=True)
    reg_win(vencedor.id); reg_loss(perdedor.id)
    await it.response.send_message(embed=discord.Embed(title="✅ Registrado", description=f"🏆 {vencedor.mention}\n💀 {perdedor.mention}", color=COR_OK))

@bot.tree.command(name="pix", description="Painel Pix")
async def px(it: discord.Interaction):
    await it.response.defer(ephemeral=False); e=discord.Embed(title="Painel Para Configurar Chave PIX", color=COR_EMB); e.set_thumbnail(url=ICONE)
    e.description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX."
    await it.followup.send(embed=e, view=ViewPix())

@bot.tree.command(name="botconfig", description="Configurações")
async def bc(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    await it.response.defer(ephemeral=False); e=discord.Embed(title="Painel Config", color=COR_EMB); e.set_thumbnail(url=ICONE); await it.followup.send(embed=e, view=ViewBotConfig())

@bot.tree.command(name="canal", description="Definir canal")
async def cn(it: discord.Interaction, canal: discord.TextChannel):
    if not it.user.guild_permissions.administrator: return
    db_ex("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(canal.id),))
    await it.response.send_message(f"✅ Canal: {canal.mention}", ephemeral=True)

# === COMANDOS PREFIXO ===
@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class VM(View):
        def e(self): return discord.Embed(title="Painel Controlador", description="**Mediadores:**\n"+"\n".join([f"• <@{u}>" for u in fila_mediadores]), color=COR_EMB)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.success)
        async def en(self,i,b): 
            if i.user.id not in fila_mediadores: fila_mediadores.append(i.user.id); await i.response.edit_message(embed=self.e())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger)
        async def sa(self,i,b): 
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.edit_message(embed=self.e())
        @discord.ui.button(label="Remover", style=discord.ButtonStyle.secondary, emoji="⚙️")
        async def rm(self,i,b):
            v=View(); s=UserSelect(placeholder="Quem?")
            async def cb(ii): 
                if s.values[0].id in fila_mediadores: fila_mediadores.remove(s.values[0].id); await i.message.edit(embed=self.e()); await ii.response.send_message("Removido.", ephemeral=True)
            s.callback=cb; v.add_item(s); await i.response.send_message("Quem?", view=v, ephemeral=True)
    await ctx.send(embed=VM().e(), view=VM())

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class MF(Modal, title="Gerar Filas"):
        m=TextInput(label="Modo", default="1v1"); p=TextInput(label="Plat", default="Mobile")
        v=TextInput(label="Valores (Separe por ESPAÇO)", default="100,00 50,00 10,00")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True); vals=[x.strip()+",00" if "," not in x else x.strip() for x in self.v.value.split()][:15]
            for val in vals: await i.channel.send(embed=ViewFila(f"{self.m.value}|{self.p.value}", val).emb(), view=ViewFila(f"{self.m.value}|{self.p.value}", val)); await asyncio.sleep(0.1)
    class VB(View):
        @discord.ui.button(label="Gerar", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(MF())
    await ctx.send("Admin:", view=VB())

@bot.event
async def on_ready(): init_db(); await bot.tree.sync(); print(f"ON: {bot.user}")

if TOKEN: bot.run(TOKEN)
    
