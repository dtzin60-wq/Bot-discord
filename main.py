import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3, os, random, asyncio
from datetime import datetime, timedelta

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

# SEU ID PARA ACESSO EXCLUSIVO À VALIDADE
OWNER_ID = 1461858587080130663 

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS permissoes (funcao TEXT PRIMARY KEY, role_id INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS validade (guild_id INTEGER PRIMARY KEY, data_expiracao TEXT)")
    con.commit(); con.close()

def db_execute(q, p=()):
    con = sqlite3.connect("dados.db"); con.execute(q, p); con.commit(); con.close()

def pegar_config(ch):
    con = sqlite3.connect("dados.db"); r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone(); con.close()
    return r[0] if r else None

def checar_validade(guild_id):
    con = sqlite3.connect("dados.db"); r = con.execute("SELECT data_expiracao FROM validade WHERE guild_id=?", (guild_id,)).fetchone(); con.close()
    if not r: return False
    try:
        exp = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S")
        return datetime.now() < exp
    except: return False

# ================= VIEWS DO TÓPICO (CONFIRMAR/RECUSAR) =================

class ViewTopico(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val = p1, p2, med, val
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, emoji="✅")
    async def conf(self, it, b):
        if it.user.id not in [self.p1, self.p2]:
            return await it.response.send_message("❌ Você não está nesta partida!", ephemeral=True)
        
        self.confirmados.add(it.user.id)
        await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=5)
        
        if len(self.confirmados) == 2:
            con = sqlite3.connect("dados.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            v_f = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            
            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb.add_field(name="👤 Titular", value=r[0] if r else "Não cadastrado")
            emb.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Não cadastrada")
            emb.add_field(name="💰 Valor Total", value=f"R$ {v_f}", inline=False)
            if r and r[2]: emb.set_image(url=r[2])
            
            self.stop()
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def recusar(self, it, b):
        if it.user.id not in [self.p1, self.p2]:
            return await it.response.send_message("❌ Você não está nesta partida!", ephemeral=True)
        
        await it.response.send_message(f"⚠️ {it.user.mention} recusou a partida. O tópico será apagado em 5 segundos.")
        await asyncio.sleep(5)
        await it.channel.delete()

# ================= VIEWS DO SISTEMA =================

class VPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persist:cad_pix")
    async def cadastrar(self, it, b):
        if not checar_validade(it.guild.id): return await it.response.send_message("❌ Renove a licença!", ephemeral=True)
        class MPix(Modal, title="Cadastrar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo")
            c = TextInput(label="Chave PIX", placeholder="Sua chave")
            q = TextInput(label="Link do QR Code", placeholder="Link da imagem (opcional)", required=False)
            async def on_submit(self, i):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
                await i.response.send_message("✅ Chave PIX salva com sucesso!", ephemeral=True)
        await it.response.send_modal(MPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="persist:ver_pix")
    async def ver_sua(self, it, b):
        con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
        if not r: return await it.response.send_message("❌ Nenhuma chave cadastrada.", ephemeral=True)
        emb = discord.Embed(title="Sua Chave PIX", description=f"**Titular:** {r[0]}\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

class VMed(View):
    def __init__(self): super().__init__(timeout=None)
    def gerar_embed(self):
        txt = "\n".join([f"**{i+1} •** <@{u}> (`{u}`)" for i, u in enumerate(fila_mediadores, 0)]) if fila_mediadores else "Fila vazia."
        emb = discord.Embed(title="Painel da fila controladora", description=f"__**Entre na fila para mediar salas**__\n\n{txt}", color=0x2b2d31)
        if bot.user: emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persist:med_in")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persist:med_out")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None); self.modo, self.valor, self.users = modo, valor, []
    def gerar_embed(self):
        txt = "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users]) if self.users else "Vazio"
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True); emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Jogadores", value=txt, inline=False); emb.set_image(url=BANNER_URL)
        return emb
    async def entrar(self, it, gelo):
        if not checar_validade(it.guild.id): return await it.response.send_message("❌ Bot expirado!", ephemeral=True)
        if any(u.id == it.user.id for u, g in self.users): return
        self.users.append((it.user, gelo))
        if len(self.users) == 2:
            p1, p2 = self.users[0][0], self.users[1][0]; self.users = []
            if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores!", ephemeral=True)
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            c_id = pegar_config("canal_1"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name=f"confirmar-{self.valor}", type=discord.ChannelType.public_thread)
            partidas_ativas[th.id] = {'modo': f"{self.modo} ({gelo})", 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            emb_w = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_w.add_field(name="👑 Modo:", value=f"{self.modo} | {gelo}"); emb_w.add_field(name="💸 Valor:", value=f"R$ {self.valor}")
            emb_w.add_field(name="✨ Jogadores:", value=f"{p1.mention}\n{p2.mention}", inline=False)
            await th.send(content=f"{p1.mention} {p2.mention}", embed=emb_w, view=ViewTopico(p1.id, p2.id, med_id, self.valor))
        await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gelo Normal")
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gelo Infinito")
    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger)
    async def s(self, it, b): self.users = [u for u in self.users if u[0].id != it.user.id]; await it.response.edit_message(embed=self.gerar_embed())

class ViewConfig(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Validade (Dono)", style=discord.ButtonStyle.success, custom_id="persist:cfg_val")
    async def validade(self, it, b):
        if it.user.id != OWNER_ID: return await it.response.send_message("⛔ Acesso Negado!", ephemeral=True)
        class MVal(Modal, title="Configurar Licença"):
            d = TextInput(label="Quantidade de Dias"); t = TextInput(label="Confirmar (digite 'dia')")
            async def on_submit(self, i):
                exp = datetime.now() + timedelta(days=int(self.d.value))
                db_execute("INSERT OR REPLACE INTO validade VALUES (?,?)", (i.guild.id, exp.strftime("%Y-%m-%d %H:%M:%S")))
                await i.response.send_message(f"✅ Válido até {exp.strftime('%d/%m/%Y %H:%M')}", ephemeral=True)
        await it.response.send_modal(MVal())

# ================= COMANDOS =================

class MyBot(commands.Bot):
    def __init__(self): super().__init__(command_prefix=".", intents=discord.Intents.all())
    async def setup_hook(self): init_db(); self.add_view(VPix()); self.add_view(VMed()); self.add_view(ViewConfig())

bot = MyBot(); fila_mediadores = []; partidas_ativas = {}; temp_dados = {}

@bot.command()
async def Pix(ctx):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    emb = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo.", color=0x2b2d31)
    emb.set_thumbnail(url=bot.user.display_avatar.url); await ctx.send(embed=emb, view=VPix())

@bot.command()
async def mediar(ctx):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    await ctx.send(embed=VMed().gerar_embed(), view=VMed())

@bot.command()
async def fila(ctx, modo, valor):
    if not checar_validade(ctx.guild.id): return await ctx.send("❌ Renove o bot!")
    await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

@bot.command()
async def botconfig(ctx):
    if ctx.author.id == OWNER_ID or ctx.author.guild_permissions.administrator:
        await ctx.send("⚙️ **Configurações Gerais**", view=ViewConfig())

@bot.command()
async def aux(ctx):
    emb = discord.Embed(title="📖 Guia de Operação", description="1. `.mediar` para entrar na fila.\n2. No tópico, confirme ou recuse.\n3. Envie ID e depois Senha no chat.", color=0x3498db)
    await ctx.send(embed=emb)

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    if msg.channel.id in partidas_ativas:
        d = partidas_ativas[msg.channel.id]
        if msg.author.id == d['med'] and msg.content.isdigit():
            if msg.channel.id not in temp_dados:
                temp_dados[msg.channel.id] = msg.content; await msg.delete()
                await msg.channel.send("✅ ID salvo. Envie a **Senha**.", delete_after=2)
            else:
                s = msg.content; id_s = temp_dados.pop(msg.channel.id); await msg.delete()
                v_n = float(d['valor'].replace(',','.')) * 2
                await msg.channel.edit(name=f"pagar-{v_n:.2f}".replace('.',','))
                emb = discord.Embed(title="🚀 DADOS DA PARTIDA", color=0x2ecc71); emb.description = f"**ID:** `{id_s}`\n**Senha:** `{s}`"; emb.set_image(url=BANNER_URL)
                await msg.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=emb)
    await bot.process_commands(msg)

bot.run(TOKEN)
                           
