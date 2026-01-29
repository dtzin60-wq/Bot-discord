import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3, asyncio, aiohttp, random, os

# --- CONFIGURAÇÕES DE AMBIENTE (RAILWAY) ---
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
THUMBNAIL_MED = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 

# Banco de dados persistente
DB_PATH = "dados.db"

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS stats (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0, consecutivas INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    con = sqlite3.connect(DB_PATH)
    con.execute(q, p)
    con.commit()
    con.close()

def salvar_config(ch, v): db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", (ch, str(v)))
def pegar_config(ch):
    con = sqlite3.connect(DB_PATH); r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone(); con.close()
    return r[0] if r else None

def ajustar_stats(u_id, v=0, d=0, c=1):
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (u_id,))
    if v > 0: cur.execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + ?, consecutivas = consecutivas + 1 WHERE user_id = ?", (c, u_id))
    if d > 0: cur.execute("UPDATE stats SET derrotas = derrotas + 1, consecutivas = 0 WHERE user_id = ?", (u_id,))
    con.commit(); con.close()

async def tem_permissao(ctx, chave_config):
    if ctx.author.guild_permissions.administrator: return True
    role_id = pegar_config(chave_config)
    if not role_id: return False
    return any(r.id == int(role_id) for r in ctx.author.roles)

# ================= GATILHO ID/SENHA + RENOMEAR TÓPICO =================
@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            tid = message.channel.id
            if tid not in temp_dados:
                temp_dados[tid] = message.content
                await message.delete()
                await message.channel.send("✅ **ID OK.** Envie a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados.pop(tid)
                await message.delete()
                await message.channel.edit(name=f"💰｜Pagar-{dados['valor']}")
                emb = discord.Embed(title="🚀 INÍCIO DE PARTIDA", color=0x2ecc71)
                emb.add_field(name="👑 Modo", value=dados['modo'], inline=True)
                emb.add_field(name="💎 Valor", value=f"R$ {dados['valor']}", inline=True)
                emb.add_field(name="🆔 ID", value=f"`{id_sala}`", inline=True)
                emb.add_field(name="🔑 Senha", value=f"`{senha}`", inline=True)
                await message.channel.send(embed=emb)
    await bot.process_commands(message)

# ================= COMANDO .BOTCONFIG =================
@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class VConfig(View):
        @discord.ui.button(label="Permissões", style=discord.ButtonStyle.blurple, emoji="🔑")
        async def perms(self, it, b):
            class VPerms(View):
                @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar .aux?")
                async def p1(self, i, s): salvar_config("perm_aux", s.values[0].id); await i.response.send_message("Permissão .aux configurada!", ephemeral=True)
                @discord.ui.select(cls=RoleSelect, placeholder="Quem entra na fila de controle?")
                async def p2(self, i, s): salvar_config("perm_med", s.values[0].id); await i.response.send_message("Permissão Fila configurada!", ephemeral=True)
                @discord.ui.select(cls=RoleSelect, placeholder="Quem pode cadastrar Pix?")
                async def p3(self, i, s): salvar_config("perm_pix", s.values[0].id); await i.response.send_message("Permissão Pix configurada!", ephemeral=True)
            await it.response.send_message("Selecione os cargos:", view=VPerms(), ephemeral=True)

        @discord.ui.button(label="Mudar Nome do Bot", style=discord.ButtonStyle.secondary, emoji="📝")
        async def mn(self, it, b):
            class M(Modal, title="Novo Nome"):
                n = TextInput(label="Nome"); async def on_submit(self, i): await bot.user.edit(username=self.n.value); await i.response.send_message("Nome alterado!", ephemeral=True)
            await it.response.send_modal(M())

        @discord.ui.button(label="Mudar Foto do Bot", style=discord.ButtonStyle.secondary, emoji="📸")
        async def mf(self, it, b):
            class M(Modal, title="Link da Foto"):
                u = TextInput(label="URL"); async def on_submit(self, i):
                    async with aiohttp.ClientSession() as s:
                        async with s.get(self.u.value) as r: d = await r.read(); await bot.user.edit(avatar=d)
                    await i.response.send_message("Foto alterada!", ephemeral=True)
            await it.response.send_modal(M())

    emb = discord.Embed(title="⚙️ Painel de Configuração ORG FIRE", description="Controle permissões e identidade visual.", color=0x2b2d31)
    await ctx.send(embed=emb, view=VConfig())

# ================= COMANDO .AUX =================
@bot.command()
async def aux(ctx):
    if not await tem_permissao(ctx, "perm_aux"): return
    if ctx.channel.id not in partidas_ativas: return
    dados = partidas_ativas[ctx.channel.id]
    class VAux(View):
        @discord.ui.button(label="Escolher Vencedor", style=discord.ButtonStyle.green, emoji="🏆")
        async def v(self, it, b):
            v_select = View(); sel = Select(options=[
                discord.SelectOption(label="Jogador 1", value="1"), 
                discord.SelectOption(label="Jogador 2", value="2")
            ])
            async def cb(i):
                venc = dados['p1'] if sel.values[0]=="1" else dados['p2']
                perd = dados['p2'] if sel.values[0]=="1" else dados['p1']
                ajustar_stats(venc, v=1, c=1); ajustar_stats(perd, d=1)
                await i.response.send_message(f"🏆 <@{venc}> venceu e ganhou **1 Coin**!"); self.stop()
            sel.callback = cb; v_select.add_item(sel); await it.response.send_message("Quem venceu a partida?", view=v_select, ephemeral=True)
        
        @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.blurple, emoji="🏳️")
        async def wo(self, it, b): await it.response.send_message(f"🏳️ W.O declarado entre <@{dados['p1']}> e <@{dados['p2']}>")
        
        @discord.ui.button(label="Finalizar Aposta", style=discord.ButtonStyle.danger, emoji="❌")
        async def f(self, it, b): await it.response.send_message("Tópico finalizado. Fechando em 3s..."); await asyncio.sleep(3); await it.channel.delete()
    await ctx.send("🛠️ **Painel Auxiliar do Mediador**", view=VAux())

# ================= COMANDO .P (PERFIL) =================
@bot.command()
async def p(ctx, m: discord.Member = None):
    m = m or ctx.author
    con = sqlite3.connect(DB_PATH); r = con.execute("SELECT vitorias, derrotas, consecutivas, coins FROM stats WHERE user_id=?", (m.id,)).fetchone(); con.close()
    v, d, c, coins = r if r else (0,0,0,0)
    emb = discord.Embed(title=f"👤 Perfil de {m.name}", color=0x3498db)
    emb.description = f"**Vitórias:** `{v}`\n**Partidas perdidas:** `{d}`\n**Vitórias consecutivas:** `{c}`\n**Coins:** 💰 `{coins}`"
    emb.set_thumbnail(url=m.display_avatar.url)
    await ctx.send(embed=emb)

# ================= FILA E MEDIAR =================
class ViewTopico(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1=p1; self.p2=p2; self.med=med; self.val=val; self.conf=set()
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        if it.user.id not in [self.p1, self.p2]: return
        self.conf.add(it.user.id)
        await it.response.send_message(embed=discord.Embed(title="✅ Confirmado", color=0x2ecc71, description=f"{it.user.mention} confirmou!"))
        if len(self.conf) == 2:
            await asyncio.sleep(2); await it.channel.purge(limit=10)
            v_final = f"{(float(self.val.replace(',','.'))+0.10):.2f}".replace('.',',')
            con = sqlite3.connect(DB_PATH); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F, description=f"**Valor (+0,10 Sala):** R$ {v_final}\n\n**Nome:** {r[0] if r else 'N/A'}\n**Chave:** `{r[1] if r else 'N/A'}`")
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(embed=emb)

@bot.command()
async def mediar(ctx):
    if not await tem_permissao(ctx, "perm_med"): return
    class VMed(View):
        def ge(self):
            txt = "\n".join([f"{i+1} • <@{u}> `{u}`" for i,u in enumerate(fila_mediadores)]) if fila_mediadores else "Nenhum mediador em serviço"
            emb = discord.Embed(title="Painel da fila controladora", description=f"**Entre na fila para começar a mediar**\n\n{txt}", color=0x2b2d31); emb.set_thumbnail(url=THUMBNAIL_MED); return emb
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
        async def e(self, it, b): 
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.ge())
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.ge())
    await ctx.send(embed=VMed().ge(), view=VMed())

@bot.command()
async def Pix(ctx):
    if not await tem_permissao(ctx, "perm_pix"): return
    class MPix(Modal, title="Configurar Pix"):
        n=TextInput(label="Nome Completo"); c=TextInput(label="Chave Pix"); q=TextInput(label="Link QR Code (Opcional)", required=False)
        async def on_submit(self, i): db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value)); await i.response.send_message("Dados salvos!", ephemeral=True)
    view = View(); btn = Button(label="Cadastrar Chave", style=discord.ButtonStyle.green, emoji="💠"); btn.callback = lambda i: i.response.send_modal(MPix()); view.add_item(btn)
    await ctx.send("Clique para configurar seu Pix:", view=view)

@bot.command()
async def fila(ctx, modo, valor):
    class VFila(View):
        def __init__(self): super().__init__(timeout=None); self.u=[]
        @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
        async def b1(self, it, b):
            if any(x.id==it.user.id for x,_ in self.u): return
            self.u.append((it.user, "Normal"))
            if len(self.u)==2:
                p1, p2 = self.u[0][0], self.u[1][0]; self.u=[]; med = fila_mediadores.pop(0) if fila_mediadores else None
                if not med: return await it.response.send_message("Sem Mediadores online!", ephemeral=True)
                canal_id = pegar_config("canal_1")
                canal = bot.get_channel(int(canal_id)) if canal_id else ctx.channel
                th = await canal.create_thread(name="⌛｜aguardando-confirmaçao")
                partidas_ativas[th.id] = {'modo': modo, 'valor': valor, 'p1': p1.id, 'p2': p2.id, 'med': med}
                await th.send(f"⚔️ Partida Localizada: {p1.mention} vs {p2.mention}", view=ViewTopico(p1.id, p2.id, med, valor))
    await ctx.send(embed=discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB).set_image(url=BANNER_URL), view=VFila())

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect(); 
    async def cb(i): salvar_config("canal_1", sel.values[0].id); await i.response.send_message("Canal de tópicos configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Selecione o canal para criação de tópicos:", view=v)

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} pronto para ORG FIRE!")
bot.run(TOKEN)
    
