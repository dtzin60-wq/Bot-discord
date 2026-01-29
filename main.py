import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3, asyncio, aiohttp, os

# --- CONFIGURAÇÕES DE IDENTIDADE ---
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

# ================= COMANDO FILA (ATUALIZADO) =================
@bot.command()
async def fila(ctx, modo_input, valor):
    class VFila(View):
        def __init__(self):
            super().__init__(timeout=None)
            self.jogadores = [] # Lista de tuplas (user, tipo_gelo)

        def gerar_embed(self):
            # Lógica para mostrar "Vazio" ou o Jogador
            p1_txt = f"{self.jogadores[0][0].mention} - {self.jogadores[0][1]}" if len(self.jogadores) >= 1 else "Vazio"
            p2_txt = f"{self.jogadores[1][0].mention} - {self.jogadores[1][1]}" if len(self.jogadores) >= 2 else "Vazio"

            emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
            emb.add_field(name="👤 Jogador 1", value=p1_txt, inline=False)
            emb.add_field(name="👤 Jogador 2", value=p2_txt, inline=False)
            emb.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
            emb.add_field(name="🏆 Modo", value=modo_input, inline=True)
            emb.set_image(url=BANNER_URL)
            return emb

        async def entrar(self, it, tipo):
            if any(p[0].id == it.user.id for p in self.jogadores):
                return await it.response.send_message("Você já está na fila!", ephemeral=True)
            
            if len(self.jogadores) < 2:
                self.jogadores.append((it.user, tipo))
                await it.response.edit_message(embed=self.gerar_embed())
            
            if len(self.jogadores) == 2:
                p1, p2 = self.jogadores[0][0], self.jogadores[1][0]
                self.jogadores = [] # Reseta a fila local
                med = fila_mediadores.pop(0) if fila_mediadores else None
                
                if not med: 
                    return await it.channel.send("❌ Partida pronta, mas não há mediadores online para criar a sala!")
                
                c_id = pegar_config("canal_1")
                canal = bot.get_channel(int(c_id)) if c_id else ctx.channel
                th = await canal.create_thread(name="⌛｜aguardando-confirmaçao")
                
                partidas_ativas[th.id] = {'modo': modo_input, 'valor': valor, 'p1': p1.id, 'p2': p2.id, 'med': med}
                await th.send(f"⚔️ **Partida Encontrada:** {p1.mention} vs {p2.mention}", view=ViewTopico(p1.id, p2.id, med, valor))

        @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="🧊")
        async def b_normal(self, it, b):
            await self.entrar(it, "Gelo Normal")

        @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.primary, emoji="♾️")
        async def b_infinito(self, it, b):
            await self.entrar(it, "Gelo Infinito")

        @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪")
        async def b_sair(self, it, b):
            for p in self.jogadores:
                if p[0].id == it.user.id:
                    self.jogadores.remove(p)
                    return await it.response.edit_message(embed=self.gerar_embed())
            await it.response.send_message("Você não está na fila.", ephemeral=True)

    view = VFila()
    await ctx.send(embed=view.gerar_embed(), view=view)

# ================= COMANDO .AUX E OUTROS =================
@bot.command()
async def aux(ctx):
    if not await tem_permissao(ctx, "perm_aux"): return
    if ctx.channel.id not in partidas_ativas: return
    dados = partidas_ativas[ctx.channel.id]
    class VAux(View):
        @discord.ui.button(label="Escolher Vencedor", style=discord.ButtonStyle.green, emoji="🏆")
        async def v(self, it, b):
            v_select = View(); sel = Select(options=[discord.SelectOption(label="Jogador 1", value="1"), discord.SelectOption(label="Jogador 2", value="2")])
            async def cb(i):
                venc = dados['p1'] if sel.values[0]=="1" else dados['p2']; perd = dados['p2'] if sel.values[0]=="1" else dados['p1']
                ajustar_stats(venc, v=1, c=1); ajustar_stats(perd, d=1)
                await i.response.send_message(f"🏆 <@{venc}> venceu!"); self.stop()
            sel.callback = cb; v_select.add_item(sel); await it.response.send_message("Vencedor?", view=v_select, ephemeral=True)
        @discord.ui.button(label="Finalizar", style=discord.ButtonStyle.danger)
        async def f(self, it, b): await it.channel.delete()
    await ctx.send("🛠️ **Painel Mediador**", view=VAux())

class ViewTopico(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val = p1, p2, med, val
        self.conf = set()
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, emoji="✅")
    async def c(self, it, b):
        if it.user.id not in [self.p1, self.p2]: return
        self.conf.add(it.user.id)
        await it.response.send_message(f"✅ {it.user.mention} confirmou!")
        if len(self.conf) == 2:
            await asyncio.sleep(2); await it.channel.purge(limit=15)
            v_f = f"{(float(self.val.replace(',','.'))+0.10):.2f}".replace('.',',')
            con = sqlite3.connect(DB_PATH); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            emb = discord.Embed(title="💸 PAGAMENTO", color=0xF1C40F, description=f"**Total:** R$ {v_f}\n**Chave:** `{r[1] if r else 'N/A'}`")
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(embed=emb)

@bot.command()
async def Pix(ctx):
    if not await tem_permissao(ctx, "perm_pix"): return
    class MPix(Modal, title="Cadastro PIX"):
        n=TextInput(label="Nome Titular"); c=TextInput(label="Chave PIX"); q=TextInput(label="QR Code", required=False)
        async def on_submit(self, i):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
            await i.response.send_message("✅ Salvo!", ephemeral=True)
    class VPix(View):
        @discord.ui.button(label="Configurar Pix", style=discord.ButtonStyle.green)
        async def cp(self, it, b): await it.response.send_modal(MPix())
        @discord.ui.button(label="Ver Chave Pix", style=discord.ButtonStyle.secondary)
        async def vp(self, it, b):
            con = sqlite3.connect(DB_PATH); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
            if r: await it.response.send_message(f"Nome: {r[0]}\nChave: {r[1]}", ephemeral=True)
            else: await it.response.send_message("Sem chave!", ephemeral=True)
    await ctx.send("💠 Painel Pix", view=VPix())

@bot.command()
async def mediar(ctx):
    if not await tem_permissao(ctx, "perm_med"): return
    class VMed(View):
        def ge(self):
            txt = "\n".join([f"<@{u}>" for u in fila_mediadores]) if fila_mediadores else "Vazia"
            return discord.Embed(title="Fila Mediadores", description=txt, color=0x2b2d31).set_thumbnail(url=THUMBNAIL_MED)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
        async def e(self, it, b): 
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.ge())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.ge())
    await ctx.send(embed=VMed().ge(), view=VMed())

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i): salvar_config("canal_1", sel.values[0].id); await i.response.send_message("Canal OK!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal:", view=v)

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class VConfig(View):
        @discord.ui.button(label="Permissões", style=discord.ButtonStyle.blurple)
        async def perms(self, it, b):
            class VPerms(View):
                @discord.ui.select(cls=RoleSelect, placeholder="Cargos...")
                async def p(self, i, s): salvar_config("perm_med", s.values[0].id); await i.response.send_message("OK!", ephemeral=True)
            await it.response.send_message("Ajuste:", view=VPerms(), ephemeral=True)
    await ctx.send("⚙️ Configuração", view=VConfig())

@bot.event
async def on_ready(): init_db(); print("✅ Bot Online")
bot.run(TOKEN)
    
