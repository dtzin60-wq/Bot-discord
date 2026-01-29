import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3, os, random, asyncio
from datetime import datetime, timedelta

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

# ================= BANCO DE DADOS (EXTENDIDO) =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS permissoes (funcao TEXT PRIMARY KEY, role_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS validade (guild_id INTEGER PRIMARY KEY, data_expiracao TEXT)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    con = sqlite3.connect("dados.db")
    con.execute(q, p)
    con.commit()
    con.close()

def salvar_config(ch, v):
    db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", (ch, str(v)))

def pegar_config(ch):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

# ================= SISTEMA DE VALIDADE E PERMISSÃO =================

def checar_validade(guild_id):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT data_expiracao FROM validade WHERE guild_id=?", (guild_id,)).fetchone()
    con.close()
    if not r: return False
    exp = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")
    return datetime.now() < exp

async def tem_permissao(ctx, funcao):
    if ctx.author.guild_permissions.administrator: return True
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT role_id FROM permissoes WHERE funcao=?", (funcao,)).fetchone()
    con.close()
    if not r: return False
    role = ctx.guild.get_role(r[0])
    return role in ctx.author.roles

# ================= VIEWS PERSISTENTES (BLINDAGEM) =================

class VPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persistent_pix:cadastrar")
    async def cadastrar(self, it, b):
        if not checar_validade(it.guild.id):
            return await it.response.send_message("❌ Renove o bot para pode usar os comandos!", ephemeral=True)
        
        class MPix(Modal, title="Cadastrar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo")
            c = TextInput(label="Chave PIX", placeholder="Sua chave")
            q = TextInput(label="Link do QR Code", placeholder="Link da imagem", required=False)
            async def on_submit(self, i):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
                await i.response.send_message("✅ Chave cadastrada com sucesso!", ephemeral=True)
        await it.response.send_modal(MPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="persistent_pix:ver_sua")
    async def ver_sua(self, it, b):
        con = sqlite3.connect("dados.db")
        r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
        if not r: return await it.response.send_message("❌ Você não tem chave cadastrada.", ephemeral=True)
        emb = discord.Embed(title="Sua Chave PIX", description=f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

class VMed(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    def gerar_embed(self):
        txt = ""
        if not fila_mediadores:
            txt = "A fila está vazia no momento."
        else:
            for i, uid in enumerate(fila_mediadores, 1):
                txt += f"{i} • <@{uid}> {uid}\n"
        emb = discord.Embed(title="Painel da fila controladora", description=f"__**Fila Ativa**__\n\n{txt}", color=0x2b2d31)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persistent_med:entrar")
    async def entrar(self, it, b):
        if not checar_validade(it.guild.id):
            return await it.response.send_message("❌ Renove o bot para pode usar os comandos!", ephemeral=True)
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persistent_med:sair")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

# ================= COMANDO .BOTCONFIG (SISTEMA DE GESTÃO) =================

class ViewConfig(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Permissões", style=discord.ButtonStyle.primary, custom_id="cfg:perms")
    async def perms(self, it, b):
        opts = [
            discord.SelectOption(label="Comandos Gerais", value="cmd_geral"),
            discord.SelectOption(label="Fila de Mediador", value="ser_med"),
            discord.SelectOption(label="Cadastrar Pix", value="cad_pix"),
            discord.SelectOption(label="Usar .aux", value="cmd_aux")
        ]
        s = Select(placeholder="Escolha a função para dar cargo", options=opts)
        async def s_cb(i):
            rs = RoleSelect(placeholder="Selecione o cargo")
            async def r_cb(i2):
                db_execute("INSERT OR REPLACE INTO permissoes VALUES (?,?)", (s.values[0], rs.values[0].id))
                await i2.response.send_message(f"✅ Cargo para {s.values[0]} configurado!", ephemeral=True)
            rs.callback = r_cb; v = View(); v.add_item(rs); await i.response.send_message("Selecione o cargo:", view=v, ephemeral=True)
        s.callback = s_cb; v = View(); v.add_item(s); await it.response.send_message("Escolha a função:", view=v, ephemeral=True)

    @discord.ui.button(label="Validade/Licença", style=discord.ButtonStyle.success, custom_id="cfg:validade")
    async def validade(self, it, b):
        class MVal(Modal, title="Configurar Validade"):
            d = TextInput(label="Quantidade", placeholder="Ex: 30")
            t = TextInput(label="Tipo (minutos, horas, dias, meses)", placeholder="Ex: dias")
            async def on_submit(self, i):
                qtd = int(self.d.value)
                tipo = self.t.value.lower()
                now = datetime.now()
                if "minuto" in tipo: exp = now + timedelta(minutes=qtd)
                elif "hora" in tipo: exp = now + timedelta(hours=qtd)
                elif "dia" in tipo: exp = now + timedelta(days=qtd)
                elif "mes" in tipo or "mês" in tipo: exp = now + timedelta(days=qtd*30)
                db_execute("INSERT OR REPLACE INTO validade VALUES (?,?)", (i.guild.id, exp.strftime("%Y-%m-%d %H:%M:%S")))
                await i.response.send_message(f"✅ Licença definida até: {exp.strftime('%d/%m/%Y %H:%M')}", ephemeral=True)
        await it.response.send_modal(MVal())

    @discord.ui.button(label="Identidade do Bot", style=discord.ButtonStyle.secondary, custom_id="cfg:identity")
    async def identity(self, it, b):
        class MId(Modal, title="Mudar Nome/Foto"):
            n = TextInput(label="Novo Nome", required=False)
            p = TextInput(label="Link da Nova Foto", required=False)
            async def on_submit(self, i):
                if self.n.value: await bot.user.edit(username=self.n.value)
                if self.p.value:
                    import requests
                    r = requests.get(self.p.value); await bot.user.edit(avatar=r.content)
                await i.response.send_message("✅ Identidade atualizada!", ephemeral=True)
        await it.response.send_modal(MId())

# ================= CLASSE DO BOT =================

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        self.add_view(VPix())
        self.add_view(VMed())
        self.add_view(ViewConfig())
        init_db()

bot = MyBot()
fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 

# ================= COMANDOS PROTEGIDOS =================

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    await ctx.send("⚙️ **Painel de Controle WS**", view=ViewConfig())

@bot.command()
async def Pix(ctx):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot para pode usar os comandos!")
    if not await tem_permissao(ctx, "cad_pix"): return await ctx.send("❌ Sem permissão!")
    await ctx.send(embed=discord.Embed(title="Configurar Pix", color=0x2b2d31), view=VPix())

@bot.command()
async def mediar(ctx):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    if not await tem_permissao(ctx, "ser_med"): return await ctx.send("❌ Sem permissão!")
    await ctx.send(embed=VMed().gerar_embed(), view=VMed())

@bot.command()
async def fila(ctx, modo, valor):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    if not await tem_permissao(ctx, "cmd_geral"): return await ctx.send("❌ Sem permissão!")
    await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

# ================= LÓGICA DE PARTIDA (ID/SENHA) =================

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        d = partidas_ativas[message.channel.id]
        if message.author.id == d['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados:
                temp_dados[message.channel.id] = message.content; await message.delete()
                await message.channel.send("✅ ID recebido.", delete_after=1)
            else:
                s = message.content; id_s = temp_dados.pop(message.channel.id); await message.delete()
                v_num = float(d['valor'].replace(',', '.'))
                await message.channel.edit(name=f"pagar-{(v_num * 2):.2f}".replace('.', ','))
                emb = discord.Embed(title="🚀 DADOS DA PARTIDA", color=0x2ecc71)
                emb.description = f"**ID:** `{id_s}`\n**Senha:** `{s}`"; emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=emb)
    await bot.process_commands(message)

# ================= RESTANTE DO CÓDIGO (TOPICO/FILA) =================

class ViewTopico(View):
    def __init__(self, p1, p2, med, val, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.modo = p1, p2, med, val, modo
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        if it.user.id not in [self.p1, self.p2] or it.user.id in self.conf: return
        self.conf.add(it.user.id)
        await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=3)
        if len(self.conf) == 2:
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            emb = discord.Embed(title="💸 PAGAMENTO", color=0xF1C40F)
            emb.add_field(name="Chave Pix", value=f"`{r[1]}`" if r else "N/A")
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(embed=emb)

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.users = modo, valor, []

    def gerar_embed(self):
        txt = "\n".join([u.mention for u in self.users]) if self.users else "Vazio"
        return discord.Embed(title="🎮 FILA", description=f"Valor: {self.valor}\n{txt}", color=0x3498DB)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.secondary)
    async def entrar_f(self, it, b):
        if any(u.id == it.user.id for u in self.users): return
        self.users.append(it.user)
        if len(self.users) == 2:
            p1, p2 = self.users[0], self.users[1]; self.users = []
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            c_id = pegar_config("canal_1"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name="confirmacao", type=discord.ChannelType.public_thread)
            partidas_ativas[th.id] = {'modo': self.modo, 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            await th.send(view=ViewTopico(p1.id, p2.id, med_id, self.valor, self.modo))
        await it.response.edit_message(embed=self.gerar_embed())

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i): salvar_config("canal_1", sel.values[0].id); await i.response.send_message("✅ OK!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal:", view=v)

bot.run(TOKEN)
        
