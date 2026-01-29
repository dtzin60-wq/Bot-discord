import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio

# --- CONFIGURAÇÕES ---
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
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

# ================= VIEWS PERSISTENTES (BLINDAGEM) =================

class VPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="persistent_pix:cadastrar")
    async def cadastrar(self, it, b):
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

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="persistent_pix:ver_med")
    async def ver_med(self, it, b):
        await it.response.send_message("🔍 Use este botão para consultar chaves de outros mediadores (Função em breve).", ephemeral=True)

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
        
        emb = discord.Embed(
            title="Painel da fila controladora",
            description=f"__**Entre na fila para começar a mediar suas filas**__\n\n{txt}",
            color=0x2b2d31
        )
        # Fallback caso o bot ainda não esteja carregado
        avatar = bot.user.display_avatar.url if bot.user else None
        if avatar: emb.set_thumbnail(url=avatar)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="persistent_med:entrar")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="persistent_med:sair")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("⚠️ Você não está na fila!", ephemeral=True)

    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="persistent_med:remover")
    async def remover(self, it, b):
        if not it.user.guild_permissions.manage_messages:
            return await it.response.send_message("❌ Você não tem permissão para remover outros mediadores.", ephemeral=True)
        fila_mediadores.clear()
        await it.response.edit_message(embed=self.gerar_embed())

# ================= CLASSE DO BOT COM SETUP HOOK =================

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=".", intents=intents)

    async def setup_hook(self):
        # Registro das Views Persistentes para evitar Erro de Interação
        self.add_view(VPix())
        self.add_view(VMed())
        print("✅ Views Persistentes carregadas.")

bot = MyBot()
fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 

# ================= COMANDO .PIX =================
@bot.command()
async def Pix(ctx):
    emb = discord.Embed(
        title="Painel Para Configurar Chave PIX",
        description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.",
        color=0x2b2d31
    )
    emb.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=emb, view=VPix())

# ================= COMANDO .MEDIAR =================
@bot.command()
async def mediar(ctx):
    view = VMed()
    await ctx.send(embed=view.gerar_embed(), view=view)

# ================= LÓGICA DE PARTIDA (ID/SENHA + RENOMEAR) =================
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
                await message.channel.send("✅ **ID recebido.** Envie a **Senha** agora.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados.pop(tid)
                await message.delete()
                
                v_num = float(dados['valor'].replace(',', '.'))
                novo_nome = f"pagar-{(v_num * 2):.2f}".replace('.', ',')
                await message.channel.edit(name=novo_nome)

                emb = discord.Embed(title="🚀 DADOS DA PARTIDA", color=0x2ecc71)
                emb.description = (
                    f"**Modo :** {dados['modo']}\n"
                    f"**Valor :** R$ {dados['valor']}\n"
                    f"**Jogadores :** <@{dados['p1']}> vs <@{dados['p2']}>\n"
                    f"**Mediador :** <@{dados['med']}>\n\n"
                    f"**Id da sala :** `{id_sala}`\n"
                    f"**Senha da sala:** `{senha}`"
                )
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    await bot.process_commands(message)

# ================= COMANDO .FILA E SETUP =================
class ViewTopico(View):
    def __init__(self, p1, p2, med, val, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val, self.modo = p1, p2, med, val, modo
        self.conf = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        if it.user.id not in [self.p1, self.p2]: return
        if it.user.id in self.conf: return
        self.conf.add(it.user.id)
        emb = discord.Embed(title="🟩 | Partida Confirmada", description=f"{it.user.mention} confirmou a aposta!\n╰👉 O outro jogador precisa confirmar para continuar.", color=0x2ecc71)
        await it.response.send_message(embed=emb)
        if len(self.conf) == 2:
            await asyncio.sleep(2); await it.channel.purge(limit=15)
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            v_f = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            emb_p = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_p.add_field(name="👤 Titular", value=r[0] if r else "N/A"); emb_p.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "N/A")
            emb_p.add_field(name="💰 Valor Total", value=f"R$ {v_f}", inline=False)
            if r and r[2]: emb_p.set_image(url=r[2])
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_p)

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.users = modo, valor, []

    def gerar_embed(self):
        txt = "Vazio" if not self.users else "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users])
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True); emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Jogadores", value=txt, inline=False); emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.users): return
        self.users.append((it.user, gelo))
        if len(self.users) == 2:
            p1, p2 = self.users[0][0], self.users[1][0]; self.users = []
            if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores!", ephemeral=True)
            med_id = fila_mediadores.pop(0)
            c_id = pegar_config("canal_1"); canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name="aguardando-confirmação", type=discord.ChannelType.public_thread)
            partidas_ativas[th.id] = {'modo': f"{self.modo} ({gelo})", 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            
            emb_wait = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_wait.add_field(name="👑 Modo:", value=f"{self.modo} | {gelo}", inline=False)
            emb_wait.add_field(name="💸 Valor da aposta:", value=f"R$ {self.valor}", inline=False)
            emb_wait.add_field(name="✨ Jogadores:", value=f"{p1.mention}\n{p2.mention}", inline=False)
            await th.send(content=f"{p1.mention} {p2.mention}", embed=emb_wait, view=ViewTopico(p1.id, p2.id, med_id, self.valor, self.modo))
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gelo Normal")
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gelo Infinito")
    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger)
    async def s(self, it, b): self.users = [u for u in self.users if u[0].id != it.user.id]; await it.response.edit_message(embed=self.gerar_embed())

@bot.command()
async def fila(ctx, modo, valor): await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect()
    async def cb(i): salvar_config("canal_1", sel.values[0].id); await i.response.send_message("✅ Canal OK!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal dos tópicos:", view=v)

@bot.event
async def on_ready(): 
    init_db()
    print(f"✅ Bot Online: {bot.user}")

bot.run(TOKEN)
    
