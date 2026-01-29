import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect, Select, RoleSelect
import sqlite3, os, asyncio

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        # Registro de Views Persistentes (Blindagem Anti-Erro)
        self.add_view(VPix())
        self.add_view(VMed())
        self.add_view(PersistentFila())
        self.add_view(VConfig())
        print("✅ Sistema Blindado: Comandos persistentes carregados.")

bot = MyBot()
fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 
espera_jogadores = {}

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS bot_config (funcao TEXT PRIMARY KEY, role_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS perfil (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0, consecutivas INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit(); con.close()

def db_execute(q, p=()):
    con = sqlite3.connect("dados.db"); con.execute(q, p); con.commit(); con.close()

def get_profile(uid):
    con = sqlite3.connect("dados.db")
    res = con.execute("SELECT vitorias, derrotas, consecutivas, coins FROM perfil WHERE user_id=?", (uid,)).fetchone()
    con.close()
    if not res:
        db_execute("INSERT INTO perfil (user_id) VALUES (?)", (uid,))
        return (0, 0, 0, 0)
    return res

def check_perm(it, funcao):
    if it.user.guild_permissions.administrator: return True
    con = sqlite3.connect("dados.db")
    res = con.execute("SELECT role_id FROM bot_config WHERE funcao=?", (funcao,)).fetchone()
    con.close()
    if not res: return True
    role_ids = [r.id for r in it.user.roles]
    return res[0] in role_ids

# ================= COMANDO .BOTCONFIG (BLINDADO) =================
class VConfig(View):
    def __init__(self): super().__init__(timeout=None)

    async def salvar_cargo(self, it, label, slug):
        view = View(); sel = RoleSelect(placeholder=f"Cargo para: {label}")
        async def cb(i):
            db_execute("INSERT OR REPLACE INTO bot_config VALUES (?,?)", (slug, sel.values[0].id))
            await i.response.send_message(f"✅ Permissão '{label}' configurada com sucesso!", ephemeral=True)
        sel.callback = cb; view.add_item(sel)
        await it.response.send_message(f"Selecione o cargo para {label}:", view=view, ephemeral=True)

    @discord.ui.button(label="Novas Filas", style=discord.ButtonStyle.secondary, custom_id="cfg_f")
    async def b1(self, it, b): await self.salvar_cargo(it, "Criar Filas", "cmd_fila")
    @discord.ui.button(label="Usar .aux", style=discord.ButtonStyle.secondary, custom_id="cfg_a")
    async def b2(self, it, b): await self.salvar_cargo(it, "Usar Auxiliar", "cmd_aux")
    @discord.ui.button(label="Fila Mediador", style=discord.ButtonStyle.secondary, custom_id="cfg_m")
    async def b3(self, it, b): await self.salvar_cargo(it, "Ser Mediador", "ser_med")
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.secondary, custom_id="cfg_p")
    async def b4(self, it, b): await self.salvar_cargo(it, "Cadastrar Pix", "cad_pix")

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    await ctx.send("⚙️ **Painel de Controle de Permissões**", view=VConfig())

# ================= COMANDO .P (PERFIL) =================
@bot.command()
async def p(ctx, membro: discord.Member = None):
    membro = membro or ctx.author
    v, d, c, coins = get_profile(membro.id)
    emb = discord.Embed(title=f"👤 Status de {membro.display_name}", color=0x3498DB)
    emb.add_field(name="🏆 Vitórias:", value=f"`{v}`", inline=True)
    emb.add_field(name="💀 Partidas perdidas:", value=f"`{d}`", inline=True)
    emb.add_field(name="🔥 Vitórias consecutivas:", value=f"`{c}`", inline=True)
    emb.add_field(name="💰 Coins:", value=f"`{coins}`", inline=False)
    emb.set_thumbnail(url=membro.display_avatar.url)
    await ctx.send(embed=emb)

# ================= FILA DE MEDIADORES (ROTAÇÃO) =================
class VMed(View):
    def __init__(self): super().__init__(timeout=None)
    def ge(self):
        txt = "\n".join([f"{i+1} • <@{u}>" for i, u in enumerate(fila_mediadores)]) if fila_mediadores else "Fila vazia."
        return discord.Embed(title="Fila de Mediadores", description=f"__**Gerencie a fila de controle**__\n\n{txt}", color=0x2ecc71)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, custom_id="med_in")
    async def e(self, it, b):
        if not check_perm(it, "ser_med"): return await it.response.send_message("❌ Sem permissão.", ephemeral=True)
        if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
        await it.response.edit_message(embed=self.ge())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, custom_id="med_out")
    async def s(self, it, b):
        if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
        await it.response.edit_message(embed=self.ge())

# ================= FILA PERSISTENTE =================
class PersistentFila(View):
    def __init__(self): super().__init__(timeout=None)

    async def entrar(self, it, gelo):
        emb = it.message.embeds[0]
        val = emb.fields[0].value.replace("R$ ", ""); modo = emb.fields[1].value
        chave = f"{val}:{modo}"

        if chave not in espera_jogadores: espera_jogadores[chave] = []
        if any(u.id == it.user.id for u, g in espera_jogadores[chave]): return
        
        espera_jogadores[chave].append((it.user, gelo))

        if len(espera_jogadores[chave]) == 2:
            p1, p2 = espera_jogadores[chave][0][0], espera_jogadores[chave][1][0]
            espera_jogadores[chave] = []

            if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores online!", ephemeral=True)

            # ROTAÇÃO CIRCULAR: O Mediador número 1 sai, vai pro fim, e o 2 assume.
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)

            con = sqlite3.connect("dados.db"); c_id = con.execute("SELECT valor FROM config WHERE chave='canal_1'").fetchone(); con.close()
            canal = bot.get_channel(int(c_id[0])) if c_id else it.channel
            th = await canal.create_thread(name=f"partida-{val}", type=discord.ChannelType.public_thread)
            partidas_ativas[th.id] = {'modo': modo, 'valor': val, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            
            await th.send(content=f"<@{med_id}> Mediador escalado! | {p1.mention} vs {p2.mention}", view=ViewTopico(p1.id, p2.id, med_id, val, modo))
        
        await it.response.edit_message(embed=self.att(it.message.embeds[0], chave))

    def att(self, emb, chave):
        jogs = espera_jogadores.get(chave, [])
        txt = "\n".join([f"👤 {u.mention}" for u, g in jogs]) if jogs else "Vazio"
        emb.set_field_at(2, name="Jogadores", value=txt, inline=False); return emb

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, custom_id="f_gn")
    async def b1(self, it, b): await self.entrar(it, "Normal")
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, custom_id="f_gi")
    async def b2(self, it, b): await self.entrar(it, "Infinito")

# ================= COMANDO .AUX (VITÓRIA E COINS) =================
class ViewAux(View):
    def __init__(self, dados, thread):
        super().__init__(timeout=None)
        self.dados, self.thread = dados, thread

    @discord.ui.button(label="Escolher vencedor", style=discord.ButtonStyle.green, emoji="🏆")
    async def vencedor(self, it, b):
        opt = [
            discord.SelectOption(label="Jogador 1", value=f"{self.dados['p1']}:{self.dados['p2']}"),
            discord.SelectOption(label="Jogador 2", value=f"{self.dados['p2']}:{self.dados['p1']}")
        ]
        s = Select(options=opt)
        async def cb(i):
            ganhou, perdeu = map(int, i.data['values'][0].split(":"))
            db_execute("UPDATE perfil SET vitorias=vitorias+1, consecutivas=consecutivas+1, coins=coins+1 WHERE user_id=?", (ganhou,))
            db_execute("UPDATE perfil SET derrotas=derrotas+1, consecutivas=0 WHERE user_id=?", (perdeu,))
            await i.response.send_message(f"🏆 <@{ganhou}> venceu! Recebeu **1 Coin** e subiu no ranking.")
        s.callback = cb; v = View(); v.add_item(s)
        await it.response.send_message("Selecione o vencedor da partida:", view=v, ephemeral=True)

    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.danger, emoji="🔒")
    async def finalizar(self, it, b):
        await it.response.send_message("🔒 Finalizando... Tópico deletado."); await asyncio.sleep(3); await self.thread.delete()

# ================= COMANDOS E EVENTOS FINAIS =================
@bot.command()
async def aux(ctx):
    if not check_perm(ctx, "cmd_aux"): return await ctx.send("❌ Sem permissão.")
    if ctx.channel.id in partidas_ativas:
        await ctx.send("🛠️ **Painel de Mediador**", view=ViewAux(partidas_ativas[ctx.channel.id], ctx.channel))

@bot.command()
async def fila(ctx, modo, valor):
    if not check_perm(ctx, "cmd_fila"): return await ctx.send("❌ Sem permissão.")
    emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    emb.add_field(name="💰 Valor", value=f"R$ {valor}"); emb.add_field(name="🏆 Modo", value=modo)
    emb.add_field(name="Jogadores", value="Vazio", inline=False); emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=PersistentFila())

@bot.command()
async def Pix(ctx):
    if not check_perm(ctx, "cad_pix"): return await ctx.send("❌ Sem permissão.")
    await ctx.send("💠 **Configuração de Pagamento**", view=VPix())

class VPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, custom_id="px_set")
    async def c(self, it, b):
        class M(Modal, title="Cadastro PIX"):
            n = TextInput(label="Nome do Titular"); k = TextInput(label="Chave PIX")
            async def on_submit(self, i):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (i.user.id, self.n.value, self.k.value))
                await i.response.send_message("✅ Chave PIX salva com sucesso!", ephemeral=True)
        await it.response.send_modal(M())

@bot.command()
async def mediar(ctx): await ctx.send(embed=VMed().ge(), view=VMed())

@bot.command()
async def canal(ctx):
    v = View(); s = ChannelSelect()
    async def cb(i): db_execute("INSERT OR REPLACE INTO config VALUES ('canal_1', ?)", (s.values[0].id,)); await i.response.send_message("✅ Canal configurado!", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Selecione o canal para os tópicos:", view=v)

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    if msg.channel.id in partidas_ativas:
        d = partidas_ativas[msg.channel.id]
        if msg.author.id == d['med'] and msg.content.isdigit():
            if msg.channel.id not in temp_dados:
                temp_dados[msg.channel.id] = msg.content; await msg.delete()
                await msg.channel.send("✅ ID Recebido. Envie a **Senha**.", delete_after=2)
            else:
                s = msg.content; id_s = temp_dados.pop(msg.channel.id); await msg.delete()
                emb = discord.Embed(title="🚀 DADOS DA SALA", description=f"**ID:** `{id_s}`\n**Senha:** `{s}`", color=0x2ecc71)
                emb.set_image(url=BANNER_URL); await msg.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=emb)
    await bot.process_commands(msg)

class ViewTopico(View):
    def __init__(self, p1, p2, med, val, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.conf = p1, p2, med, val, set()
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        if it.user.id in [self.p1, self.p2]: self.conf.add(it.user.id)
        if len(self.conf) == 2:
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            v_total = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            await it.channel.send(f"💸 **PAGAMENTO AO MEDIADOR:**\n💰 Valor Total: R$ {v_total}\n👤 Titular: {r[0] if r else 'N/A'}\n💠 Chave: `{r[1] if r else 'N/A'}`")

@bot.event
async def on_ready(): init_db(); print(f"✅ Bot Online: {bot.user}")
bot.run(TOKEN)
    
