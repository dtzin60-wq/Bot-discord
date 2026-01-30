import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3, os, random, asyncio

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Memória global da fila e monitoramento
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
        print(f"Erro no DB: {e}")

def pegar_config(ch):
    con = sqlite3.connect("dados.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

# ================= SISTEMA .Pix (VISUAL ORIGINAL) =================
class MPix(Modal, title="Cadastrar Chave PIX"):
    n = TextInput(label="Nome do Titular", placeholder="Digite o nome completo")
    c = TextInput(label="Chave PIX", placeholder="Sua chave (CPF, Email, Telefone, etc)")
    q = TextInput(label="Link do QR Code", placeholder="Opcional: link da imagem do QR Code", required=False)
    
    async def on_submit(self, i: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, self.n.value, self.c.value, self.q.value))
        await i.response.send_message("✅ **Sucesso!** Sua chave PIX foi salva e será usada nas suas mediações.", ephemeral=True)

class VPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persistent:cad_pix")
    async def cadastrar(self, it: discord.Interaction, b):
        await it.response.send_modal(MPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="persistent:ver_pix")
    async def ver_sua(self, it: discord.Interaction, b):
        con = sqlite3.connect("dados.db")
        r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
        if not r: return await it.response.send_message("❌ Você não tem chave cadastrada.", ephemeral=True)
        
        emb = discord.Embed(title="Sua Chave PIX", description=f"**Titular:** `{r[0]}`\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

# ================= SISTEMA .mediar (VISUAL ORIGINAL + NUMERADO) =================
class VMed(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    def gerar_embed(self):
        if not fila_mediadores:
            desc = "A fila está vazia no momento."
        else:
            # Lista numerada exata: 1 • @Usuário
            desc = "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
            
        emb = discord.Embed(
            title="Painel da fila controladora", 
            description=f"__**Entre na fila para começar a mediar**__\n\n{desc}", 
            color=0x2b2d31
        )
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persistent:entrar_fila")
    async def e(self, it: discord.Interaction, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persistent:sair_fila")
    async def s(self, it: discord.Interaction, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

# ================= TÓPICO (CONFIRMAÇÃO + LIMPEZA + PIX AUTO) =================
class ViewTopico(View):
    def __init__(self, p1, p2, med, val, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.modo = p1, p2, med, val, modo
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it: discord.Interaction, b):
        if it.user.id not in [self.p1, self.p2]: 
            return await it.response.send_message("❌ Apenas os jogadores podem confirmar.", ephemeral=True)
        
        self.conf.add(it.user.id)
        await it.response.send_message(f"✅ <@{it.user.id}> confirmou!", delete_after=3)
        
        if len(self.conf) == 2:
            await asyncio.sleep(1)
            await it.channel.purge(limit=25) # LIMPEZA AUTOMÁTICA DO CHAT
            
            con = sqlite3.connect("dados.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            
            # Cálculo de taxa 0.10 automático
            try: v_f = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            except: v_f = self.val

            emb_p = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_p.add_field(name="👤 Titular", value=r[0] if r else "Não cadastrado", inline=True)
            emb_p.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Não cadastrada", inline=True)
            emb_p.add_field(name="💰 Valor Total", value=f"R$ {v_f}", inline=False)
            emb_p.set_footer(text="Envie o comprovante para o mediador liberar os dados da sala.")
            if r and r[2]: emb_p.set_image(url=r[2])
            
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_p)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def r(self, it: discord.Interaction, b):
        if it.user.id not in [self.p1, self.p2]: return
        await it.response.send_message(f"❌ Partida cancelada por {it.user.mention}. Deletando tópico...")
        await asyncio.sleep(3); await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def rules(self, it: discord.Interaction, b):
        await it.response.send_message("📝 Usem este espaço para combinar as regras (Gelo, Armas, etc).", ephemeral=True)

# ================= FILA DE APOSTAS COM ROTAÇÃO =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.p = modo, valor, []

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u in self.p): return
        self.p.append(it.user)
        
        if len(self.p) == 2:
            if not fila_mediadores: 
                self.p = []
                return await it.response.send_message("❌ Não há mediadores na fila!", ephemeral=True)
            
            # --- LÓGICA DE ROTAÇÃO: Chama o 1º e joga ele pro final ---
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)
            
            c_id = pegar_config("canal_1"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name=f"aposta-{self.valor}", type=discord.ChannelType.public_thread)
            
            partidas_ativas[th.id] = {'med': med_id, 'p1': self.p[0].id, 'p2': self.p[1].id, 'val': self.valor, 'modo': f"{self.modo} | {gelo}"}
            
            emb = discord.Embed(title="Aguardando Confirmações", color=0x2b2d31)
            emb.description = f"**👑 Modo:** {self.modo} | {gelo}\n**💸 Valor:** R$ {self.valor}\n**👮 Mediador:** <@{med_id}>\n\n**Jogadores:** <@{self.p[0].id}> e <@{self.p[1].id}>"
            
            await th.send(content=f"<@{self.p[0].id}> <@{self.p[1].id}>", embed=emb, view=ViewTopico(self.p[0].id, self.p[1].id, med_id, self.valor, self.modo))
            self.p = []
            await it.response.send_message("✅ Partida criada! Vá para o tópico.", ephemeral=True)
        else: await it.response.send_message("✅ Você entrou na fila de espera!", ephemeral=True)

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gelo Normal")
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gelo Infinito")

# ================= COMANDOS E EVENTOS =================
@bot.command()
async def Pix(ctx):
    emb = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie sua chave PIX para receber pagamentos de mediação automaticamente.", color=0x2b2d31)
    emb.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=emb, view=VPix())

@bot.command()
async def mediar(ctx):
    view = VMed()
    await ctx.send(embed=view.gerar_embed(), view=view)

@bot.command()
async def fila(ctx, modo, valor):
    emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    emb.add_field(name="💰 Valor", value=f"R$ {valor}"); emb.add_field(name="🏆 Modo", value=modo)
    emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i): 
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_1", str(sel.values[0].id)))
        await i.response.send_message("✅ Canal configurado com sucesso!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal onde os tópicos serão criados:", view=v)

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
                await message.channel.send("✅ **ID registrado.** Envie a **Senha** agora.", delete_after=2)
            else:
                senha = message.content; id_sala = temp_dados.pop(tid)
                await message.delete()
                try: 
                    v_num = float(dados['val'].replace(',', '.'))
                    await message.channel.edit(name=f"pagar-{(v_num * 2):.2f}".replace('.', ','))
                except: pass
                emb = discord.Embed(title="🚀 DADOS DA PARTIDA", color=0x2ecc71)
                emb.description = f"**Modo :** {dados['modo']}\n**Valor :** R$ {dados['val']}\n**ID:** `{id_sala}`\n**Senha:** `{senha}`"
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db()
    bot.add_view(VPix())
    bot.add_view(VMed())
    print(f"✅ Bot Online: {bot.user}")

bot.run(TOKEN)
        
