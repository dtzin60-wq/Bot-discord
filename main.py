import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3, os, random, asyncio

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
# URL da imagem que aparece no comando .fila e no resultado final
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Memória global para filas e gestão de partidas
fila_mediadores = [] 
partidas_ativas = {} 
temp_dados = {} 

# ================= BANCO DE DADOS (BLINDAGEM) =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    try:
        con = sqlite3.connect("dados.db")
        con.execute(q, p)
        con.commit()
        con.close()
    except Exception as e:
        print(f"Erro no Banco de Dados: {e}")

def pegar_config(ch):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

# ================= SISTEMA .Pix (VISUAL ORIGINAL) =================
class MPix(Modal, title="Configurar Chave PIX"):
    n = TextInput(label="Nome do Titular", placeholder="Nome completo do dono da conta")
    c = TextInput(label="Chave PIX", placeholder="CPF, Email, Telemóvel ou Chave Aleatória")
    q = TextInput(label="Link do QR Code", placeholder="Opcional: link da imagem (URL)", required=False)
    
    async def on_submit(self, i: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
        await i.response.send_message("✅ **Dados guardados!** A sua chave será enviada automaticamente nas mediações.", ephemeral=True)

class VPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persistent:pix_cad")
    async def cadastrar(self, it: discord.Interaction, b):
        await it.response.send_modal(MPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="persistent:pix_ver")
    async def ver_sua(self, it: discord.Interaction, b):
        con = sqlite3.connect("dados.db")
        r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
        if not r: return await it.response.send_message("❌ Não tens nenhuma chave registada.", ephemeral=True)
        
        emb = discord.Embed(title="Sua Chave PIX", color=0x2ecc71)
        emb.add_field(name="👤 Titular", value=f"`{r[0]}`")
        emb.add_field(name="💠 Chave", value=f"`{r[1]}`")
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

# ================= SISTEMA .mediar (VISUAL ORIGINAL + ROTAÇÃO) =================
class VMed(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    def gerar_embed(self):
        if not fila_mediadores:
            desc = "A fila está vazia no momento."
        else:
            # Visual da lista numerada: 1 • @User
            desc = "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        emb = discord.Embed(title="Painel da fila controladora", description=f"__**Entra na fila para começar a mediar**__\n\n{desc}", color=0x2b2d31)
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persistent:med_e")
    async def e(self, it: discord.Interaction, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Já estás na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persistent:med_s")
    async def s(self, it: discord.Interaction, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Não estás na fila.", ephemeral=True)

# ================= TÓPICO (LIMPEZA AUTOMÁTICA + PIX) =================
class ViewTopico(View):
    def __init__(self, p1, p2, med, val, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.modo = p1, p2, med, val, modo
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it: discord.Interaction, b):
        if it.user.id not in [self.p1, self.p2]: return await it.response.send_message("❌ Só jogadores podem confirmar!", ephemeral=True)
        self.conf.add(it.user.id)
        await it.response.send_message(f"✅ <@{it.user.id}> confirmou!", delete_after=2)
        
        if len(self.conf) == 2:
            await asyncio.sleep(1)
            # LIMPEZA DO CHAT APÓS CONFIRMAÇÃO
            await it.channel.purge(limit=30) 
            
            con = sqlite3.connect("dados.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            
            # Cálculo da taxa automática de 0.10
            try: v_f = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            except: v_f = self.val

            emb_p = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_p.add_field(name="👤 Titular", value=r[0] if r else "Não cadastrado", inline=True)
            emb_p.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Não cadastrada", inline=True)
            emb_p.add_field(name="💰 Valor Total", value=f"R$ {v_f}", inline=False)
            emb_p.set_footer(text="Enviem o comprovante para o mediador libertar a sala.")
            if r and r[2]: emb_p.set_image(url=r[2])
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_p)

# ================= FILA DE APOSTAS COM BOTÃO SAIR =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.p = modo, valor, []

    def gerar_embed(self):
        txt = "Aguardando jogadores..." if not self.p else "\n".join([f"👤 {u.mention}" for u in self.p])
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Fila de Espera", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u in self.p): return await it.response.send_message("⚠️ Já estás na fila!", ephemeral=True)
        self.p.append(it.user)
        
        if len(self.p) == 2:
            if not fila_mediadores: 
                self.p = []
                return await it.response.send_message("❌ Não há mediadores disponíveis agora!", ephemeral=True)
            
            # --- LÓGICA DE ROTAÇÃO: 1º da fila vai para o fim após ser chamado ---
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)
            
            c_id = pegar_config("canal_1"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name=f"partida-{self.valor}", type=discord.ChannelType.public_thread)
            
            partidas_ativas[th.id] = {'med': med_id, 'p1': self.p[0].id, 'p2': self.p[1].id, 'val': self.valor, 'modo': f"{self.modo} | {gelo}"}
            
            emb = discord.Embed(title="Aguardando Confirmações", color=0x2b2d31)
            emb.description = f"**👑 Modo:** {self.modo} | {gelo}\n**💸 Valor:** R$ {self.valor}\n**👮 Mediador:** <@{med_id}>\n\n**Jogadores:** <@{self.p[0].id}> e <@{self.p[1].id}>"
            await th.send(content=f"<@{self.p[0].id}> <@{self.p[1].id}>", embed=emb, view=ViewTopico(self.p[0].id, self.p[1].id, med_id, self.valor, self.modo))
            self.p = []
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def b1(self, it, b): await self.entrar(it, "Gelo Normal")
    
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def b2(self, it, b): await self.entrar(it, "Gelo Infinito")
    
    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪")
    async def sair(self, it: discord.Interaction, b):
        u = next((u for u in self.p if u.id == it.user.id), None)
        if u:
            self.p.remove(u)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Não estás na fila!", ephemeral=True)

# ================= COMANDOS DE CONFIGURAÇÃO =================
@bot.command()
async def Pix(ctx):
    await ctx.send(embed=discord.Embed(title="Painel de Configuração PIX", color=0x2b2d31), view=VPix())

@bot.command()
async def mediar(ctx):
    await ctx.send(embed=VMed().gerar_embed(), view=VMed())

@bot.command()
async def fila(ctx, modo, valor):
    # Exemplo: .fila Apostado 10,00
    await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i): 
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_1", str(sel.values[0].id)))
        await i.response.send_message("✅ Canal de tópicos configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha onde os tópicos de partida serão criados:", view=v)

# ================= SISTEMA DE ENTREGA DE DADOS =================
@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            tid = message.channel.id
            if tid not in temp_dados:
                temp_dados[tid] = message.content; await message.delete()
                await message.channel.send("✅ **ID OK.** Agora envie a **Senha** da sala.", delete_after=2)
            else:
                senha = message.content; id_sala = temp_dados.pop(tid); await message.delete()
                emb = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                emb.description = f"**ID:** `{id_sala}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    await bot.process_commands(message)

# ================= INICIALIZAÇÃO =================
@bot.event
async def on_ready():
    init_db()
    # Registar views persistentes para que funcionem após o bot reiniciar
    bot.add_view(VPix())
    bot.add_view(VMed())
    print(f"✅ Bot Online como {bot.user}")

bot.run(TOKEN)
    
