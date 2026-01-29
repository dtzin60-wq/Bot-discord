import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3, os, random, asyncio
from datetime import datetime, timedelta

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

# ================= BANCO DE DADOS =================
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

def pegar_config(ch):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

def checar_validade(guild_id):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT data_expiracao FROM validade WHERE guild_id=?", (guild_id,)).fetchone()
    con.close()
    if not r: return False
    exp = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")
    return datetime.now() < exp

# ================= VIEWS PERSISTENTES (PIX, MEDIADOR E CONFIG) =================

class VPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persist:cad_pix")
    async def cadastrar(self, it, b):
        if not checar_validade(it.guild.id):
            return await it.response.send_message("❌ Renove o bot pra pode usar os comandos!", ephemeral=True)
        
        class MPix(Modal, title="Cadastrar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo")
            c = TextInput(label="Chave PIX", placeholder="Sua chave")
            q = TextInput(label="Link do QR Code", placeholder="Link da imagem", required=False)
            async def on_submit(self, i):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
                await i.response.send_message("✅ Chave cadastrada com sucesso!", ephemeral=True)
        await it.response.send_modal(MPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="persist:ver_pix")
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
        txt = "\n".join([f"{i+1} • <@{u}> {u}" for i, u in enumerate(fila_mediadores, 1)]) if fila_mediadores else "A fila está vazia no momento."
        emb = discord.Embed(title="Painel da fila controladora", description=f"__**Entre na fila para começar a mediar suas filas**__\n\n{txt}", color=0x2b2d31)
        if bot.user: emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persist:med_in")
    async def entrar(self, it, b):
        if not checar_validade(it.guild.id):
            return await it.response.send_message("❌ Renove o bot pra pode usar os comandos!", ephemeral=True)
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persist:med_out")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

class ViewConfig(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Permissões", style=discord.ButtonStyle.primary, custom_id="persist:cfg_perms")
    async def perms(self, it, b):
        opts = [
            discord.SelectOption(label="Comandos Gerais", value="cmd_geral"),
            discord.SelectOption(label="Fila de Mediador", value="ser_med"),
            discord.SelectOption(label="Cadastrar Pix", value="cad_pix"),
            discord.SelectOption(label="Usar .aux", value="cmd_aux")
        ]
        s = Select(placeholder="Escolha a função", options=opts)
        async def s_cb(i):
            rs = RoleSelect(placeholder="Selecione o cargo")
            async def r_cb(i2):
                db_execute("INSERT OR REPLACE INTO permissoes VALUES (?,?)", (s.values[0], rs.values[0].id))
                await i2.response.send_message(f"✅ Cargo para {s.values[0]} configurado!", ephemeral=True)
            rs.callback = r_cb; v = View(); v.add_item(rs); await i.response.send_message("Selecione o cargo:", view=v, ephemeral=True)
        s.callback = s_cb; v = View(); v.add_item(s); await it.response.send_message("Escolha a função:", view=v, ephemeral=True)

    @discord.ui.button(label="Validade", style=discord.ButtonStyle.success, custom_id="persist:cfg_val")
    async def validade(self, it, b):
        class MVal(Modal, title="Configurar Validade"):
            d = TextInput(label="Quantidade (Ex: 30)")
            t = TextInput(label="Tipo (minutos/horas/dias/meses)")
            async def on_submit(self, i):
                qtd = int(self.d.value); t = self.t.value.lower(); now = datetime.now()
                if "min" in t: exp = now + timedelta(minutes=qtd)
                elif "hor" in t: exp = now + timedelta(hours=qtd)
                elif "dia" in t: exp = now + timedelta(days=qtd)
                else: exp = now + timedelta(days=qtd*30)
                db_execute("INSERT OR REPLACE INTO validade VALUES (?,?)", (i.guild.id, exp.strftime("%Y-%m-%d %H:%M:%S")))
                await i.response.send_message(f"✅ Licença definida!", ephemeral=True)
        await it.response.send_modal(MVal())

    @discord.ui.button(label="Identidade", style=discord.ButtonStyle.secondary, custom_id="persist:cfg_id")
    async def identity(self, it, b):
        class MId(Modal, title="Mudar Nome/Foto"):
            n = TextInput(label="Novo Nome", required=False)
            p = TextInput(label="Link da Foto", required=False)
            async def on_submit(self, i):
                if self.n.value: await bot.user.edit(username=self.n.value)
                if self.p.value:
                    import requests
                    await bot.user.edit(avatar=requests.get(self.p.value).content)
                await i.response.send_message("✅ Identidade atualizada!", ephemeral=True)
        await it.response.send_modal(MId())

# ================= COMANDO .FILA E LÓGICA DE PARTIDA =================

class ViewTopico(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.c = p1, p2, med, val, set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def conf(self, it, b):
        if it.user.id in [self.p1, self.p2]:
            self.c.add(it.user.id)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=3)
        if len(self.c) == 2:
            con = sqlite3.connect("dados.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            v_f = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb.add_field(name="👤 Titular", value=r[0] if r else "N/A")
            emb.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "N/A")
            emb.add_field(name="💰 Valor Total", value=f"R$ {v_f}", inline=False)
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb)

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.users = modo, valor, []

    def gerar_embed(self):
        txt = "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users]) if self.users else "Vazio"
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Jogadores", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if not checar_validade(it.guild.id):
            return await it.response.send_message("❌ Renove o bot pra pode usar os comandos!", ephemeral=True)
        if any(u.id == it.user.id for u, g in self.users): return
        self.users.append((it.user, gelo))
        if len(self.users) == 2:
            p1, p2 = self.users[0][0], self.users[1][0]; self.users = []
            if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores!", ephemeral=True)
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            c_id = pegar_config("canal_1"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name="aguardando-confirmação", type=discord.ChannelType.public_thread)
            partidas_ativas[th.id] = {'modo': f"{self.modo} ({gelo})", 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            
            emb_w = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_w.add_field(name="👑 Modo:", value=f"{self.modo} | {gelo}", inline=False)
            emb_w.add_field(name="💸 Valor:", value=f"R$ {self.valor}", inline=False)
            emb_w.add_field(name="✨ Jogadores:", value=f"{p1.mention}\n{p2.mention}", inline=False)
            await th.send(content=f"{p1.mention} {p2.mention}", embed=emb_w, view=ViewTopico(p1.id, p2.id, med_id, self.valor))
        await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gelo Infinito")

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger)
    async def s(self, it, b):
        self.users = [u for u in self.users if u[0].id != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

# ================= CLASSE BOT E EVENTOS =================

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        init_db()
        self.add_view(VPix())
        self.add_view(VMed())
        self.add_view(ViewConfig())
        print("✅ Blindagem Ativa e Views Registradas!")

bot = MyBot()
fila_mediadores = []
partidas_ativas = {}
temp_dados = {}

@bot.command()
async def botconfig(ctx):
    if ctx.author.guild_permissions.administrator:
        await ctx.send("⚙️ **Painel de Controle WS**", view=ViewConfig())

@bot.command()
async def Pix(ctx):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    emb = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar ou visualizar sua chave PIX.", color=0x2b2d31)
    emb.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=emb, view=VPix())

@bot.command()
async def mediar(ctx):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    await ctx.send(embed=VMed().gerar_embed(), view=VMed())

@bot.command()
async def fila(ctx, modo, valor):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); sel = ChannelSelect()
    async def cb(i):
        db_execute("INSERT OR REPLACE INTO config VALUES ('canal_1', ?)", (sel.values[0].id,))
        await i.response.send_message("✅ Canal configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel)
    await ctx.send("Escolha o canal dos tópicos:", view=v)

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    if msg.channel.id in partidas_ativas:
        d = partidas_ativas[msg.channel.id]
        if msg.author.id == d['med'] and msg.content.isdigit():
            if msg.channel.id not in temp_dados:
                temp_dados[msg.channel.id] = msg.content; await msg.delete()
                await msg.channel.send("✅ ID recebido. Mande a **Senha**.", delete_after=2)
            else:
                s = msg.content; id_s = temp_dados.pop(msg.channel.id); await msg.delete()
                v_n = float(d['valor'].replace(',','.')) * 2
                await msg.channel.edit(name=f"pagar-{v_n:.2f}".replace('.',','))
                emb = discord.Embed(title="🚀 DADOS DA PARTIDA", color=0x2ecc71)
                emb.description = f"**ID:** `{id_s}`\n**Senha:** `{s}`"; emb.set_image(url=BANNER_URL)
                await msg.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=emb)
    await bot.process_commands(msg)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} pronto para uso!")

bot.run(TOKEN)
    
