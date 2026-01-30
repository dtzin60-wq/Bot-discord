import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3, os, asyncio

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1466833663361548389/Screenshot_2026-01-30-13-32-38-096_com.openai.chatgpt-edit.jpg?ex=697e2ecd&is=697cdd4d&hm=6b49552a201219d4b6fc1048ab8993d5c889675163cca6a58a46bbe5c1a063a5&"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Memória Temporária
fila_mediadores = [] 
partidas_ativas = {} 
temp_dados_sala = {} 

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect("dados_bot.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    con = sqlite3.connect("dados_bot.db")
    con.execute(q, p)
    con.commit()
    con.close()

def pegar_config(ch):
    con = sqlite3.connect("dados_bot.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

# ================= VISUAL ORIGINAL: .Pix =================
class ModalPix(Modal, title="Cadastrar Chave PIX"):
    n = TextInput(label="Nome do Titular", placeholder="Digite o nome completo do titular")
    c = TextInput(label="Chave PIX", placeholder="Sua chave (CPF, Email, Telefone, etc)")
    q = TextInput(label="Link do QR Code", placeholder="Opcional: link da imagem do QR Code", required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (interaction.user.id, self.n.value, self.c.value, self.q.value))
        await interaction.response.send_message("✅ **Sucesso!** Sua chave PIX foi configurada.", ephemeral=True)

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persistent:pix_cad_orig")
    async def cadastrar(self, it: discord.Interaction, b):
        await it.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="persistent:pix_ver_orig")
    async def ver(self, it: discord.Interaction, b):
        con = sqlite3.connect("dados_bot.db")
        r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
        if not r: return await it.response.send_message("❌ Você não tem chave cadastrada.", ephemeral=True)
        emb = discord.Embed(title="Sua Chave PIX", description=f"**Titular:** `{r[0]}`\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

# ================= VISUAL ORIGINAL: .mediar / .mediat =================
class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    def gerar_embed(self):
        if not fila_mediadores:
            desc = "A fila está vazia no momento."
        else:
            # Lista numerada exata: 1 • @User
            desc = "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        
        emb = discord.Embed(
            title="Painel da fila controladora", 
            description=f"__**Entre na fila para começar a mediar**__\n\n{desc}", 
            color=0x2b2d31
        )
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persistent:med_e_orig")
    async def entrar(self, it: discord.Interaction, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persistent:med_s_orig")
    async def sair(self, it: discord.Interaction, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

# ================= FILA DE APOSTAS (GELO NO NOME) =================
class ViewMatchmaking(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.p = modo, valor, []

    def gerar_embed(self):
        txt = "Aguardando..." if not self.p else "\n".join([f"👤 {d['u'].mention} - `{d['g']}`" for d in self.p])
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Fila de Espera", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if any(d['u'].id == it.user.id for d in self.p): return await it.response.send_message("⚠️ Já está na fila!", ephemeral=True)
        self.p.append({'u': it.user, 'g': gelo})
        
        if len(self.p) == 2:
            if not fila_mediadores:
                self.p = []
                return await it.response.send_message("❌ Sem mediadores na fila!", ephemeral=True)
            
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id) # Rotação
            c_id = pegar_config("canal_th"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            thread = await canal.create_thread(name=f"Aposta-{self.valor}", type=discord.ChannelType.public_thread)
            
            partidas_ativas[thread.id] = {
                'med': med_id, 'p1': self.p[0]['u'].id, 'p2': self.p[1]['u'].id,
                'modo': f"{self.modo} ({self.p[0]['g']} vs {self.p[1]['g']})"
            }
            
            emb_th = discord.Embed(title="Aguardando Confirmações", color=0x2b2d31)
            emb_th.description = f"**Modo:** {self.modo}\n**Valor:** R$ {self.valor}\n**Mediador:** <@{med_id}>"
            await thread.send(content=f"<@{self.p[0]['u'].id}> <@{self.p[1]['u'].id}>", 
                             embed=emb_th, view=ViewConfirm(self.p[0]['u'].id, self.p[1]['u'].id, med_id, self.valor))
            self.p = []
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def n(self, it, b): await self.entrar(it, "Gelo Normal")
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def i(self, it, b): await self.entrar(it, "Gelo Infinito")
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="🚪")
    async def s(self, it, b):
        self.p = [d for d in self.p if d['u'].id != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

# ================= CONFIRMAÇÃO + LIMPEZA + TAXA =================
class ViewConfirm(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val = p1, p2, med, val
        self.conf = set()

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green)
    async def c(self, it: discord.Interaction, b):
        if it.user.id not in [self.p1, self.p2]: return
        self.conf.add(it.user.id)
        await it.response.send_message(f"✅ <@{it.user.id}> confirmou!", delete_after=2)
        if len(self.conf) == 2:
            await asyncio.sleep(1); await it.channel.purge(limit=50) # LIMPEZA
            con = sqlite3.connect("dados_bot.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            try: v_total = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            except: v_total = self.val
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_pix.add_field(name="👤 Titular", value=r[0] if r else "N/A", inline=True)
            emb_pix.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "N/A", inline=True)
            emb_pix.add_field(name="💰 Valor (Com Taxa)", value=f"R$ {v_total}", inline=False)
            if r and r[2]: emb_pix.set_image(url=r[2])
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_pix)

# ================= COMANDOS =================
@bot.command()
async def Pix(ctx):
    # Visual original: Embed descritiva com botões verdes
    emb = discord.Embed(
        title="Painel Para Configurar Chave PIX", 
        description="Configure sua chave para receber pagamentos automaticamente nas mediações.", 
        color=0x2b2d31
    )
    await ctx.send(embed=emb, view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo, valor):
    await ctx.send(embed=ViewMatchmaking(modo, valor).gerar_embed(), view=ViewMatchmaking(modo, valor))

@bot.command()
async def set_canal(ctx):
    v = View(); sel = ChannelSelect(placeholder="Selecione o canal para tópicos")
    async def cb(i):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await i.response.send_message("✅ Canal configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Configuração:", view=v)

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            cid = message.channel.id
            if cid not in temp_dados_sala:
                temp_dados_sala[cid] = message.content; await message.delete()
                await message.channel.send("✅ ID OK. Envie a **Senha**.", delete_after=2)
            else:
                senha = message.content; id_s = temp_dados_sala.pop(cid); await message.delete()
                emb = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                emb.description = f"**ID:** `{id_s}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db(); bot.add_view(ViewPix()); bot.add_view(ViewMediar())
    print(f"✅ Bot Online: {bot.user.name}")

# INICIALIZAÇÃO PARA RAILWAY
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: TOKEN não encontrado nas variáveis de ambiente.")
            
