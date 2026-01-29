import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio, re, aiohttp

# Configurações
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
partidas_ativas = {} 
temp_dados = {} 

# ================= DATABASE =================
def init_db():
    con = sqlite3.connect("dados.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)")
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

# ================= COMANDO .BOTCONFIG (COMPLETO) =================
@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.send("❌ Apenas administradores.")

    class ViewConfig(View):
        def __init__(self):
            super().__init__(timeout=None)

        # Seleções de Cargos
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar os comandos?", custom_id="cfg_1")
        async def p1(self, it, s):
            salvar_config("role_geral", s.values[0].id)
            await it.response.send_message(f"✅ Permissão Geral: {s.values[0].name}", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode entrar na fila controladora?", custom_id="cfg_3")
        async def p3(self, it, s):
            salvar_config("role_mediador", s.values[0].id)
            await it.response.send_message(f"✅ Permissão Mediador: {s.values[0].name}", ephemeral=True)

        # Botões de Identidade
        @discord.ui.button(label="Mudar Nome do Bot", style=discord.ButtonStyle.secondary, emoji="📝")
        async def mudar_nome(self, it, b):
            class ModalNome(Modal, title="Alterar Nome do Bot"):
                novo_nome = TextInput(label="Novo Nome", min_length=2, max_length=32)
                async def on_submit(self, i):
                    await bot.user.edit(username=self.novo_nome.value)
                    await i.response.send_message(f"✅ Nome alterado para: **{self.novo_nome.value}**", ephemeral=True)
            await it.response.send_modal(ModalNome())

        @discord.ui.button(label="Mudar Foto do Bot", style=discord.ButtonStyle.secondary, emoji="🖼️")
        async def mudar_foto(self, it, b):
            class ModalFoto(Modal, title="Alterar Foto do Bot"):
                url_foto = TextInput(label="URL da Imagem", placeholder="https://link-da-imagem.png")
                async def on_submit(self, i):
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(self.url_foto.value) as resp:
                                if resp.status != 200: return await i.response.send_message("❌ Link inválido.", ephemeral=True)
                                data = await resp.read()
                                await bot.user.edit(avatar=data)
                                await i.response.send_message("✅ Foto de perfil alterada!", ephemeral=True)
                    except Exception as e:
                        await i.response.send_message(f"❌ Erro: {e}", ephemeral=True)
            await it.response.send_modal(ModalFoto())

    emb = discord.Embed(title="⚙️ Painel de Configuração Avançada", description="Configure as permissões de cargos e a identidade visual do bot abaixo.", color=0x2b2d31)
    await ctx.send(embed=emb, view=ViewConfig())

# ================= EVENTO GATILHO (ID E SENHA) =================
@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            thread_id = message.channel.id
            if thread_id not in temp_dados:
                temp_dados[thread_id] = message.content
                await message.delete()
                await message.channel.send(f"✅ ID `{message.content}` recebido. Envie a **Senha**.", delete_after=3)
            else:
                senha = message.content
                id_sala = temp_dados.pop(thread_id)
                await message.delete()
                emb = discord.Embed(title="🚀 INÍCIO DE PARTIDA", color=0x2ecc71)
                emb.add_field(name="👑 Modo", value=dados['modo'], inline=True)
                emb.add_field(name="💎 Valor", value=f"R$ {dados['valor']}", inline=True)
                emb.add_field(name="👥 Jogadores", value=f"<@{dados['p1']}>\n<@{dados['p2']}>", inline=False)
                emb.add_field(name="🆔 ID", value=f"`{id_sala}`", inline=True)
                emb.add_field(name="🔑 Senha", value=f"`{senha}`", inline=True)
                await message.channel.send(embed=emb)
    await bot.process_commands(message)

# ================= COMANDO .PIX (EMBED) =================
@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def p(self, it, b):
            class MPix(Modal, title="Configurar PIX"):
                n = TextInput(label="Nome Completo"); c = TextInput(label="Chave PIX")
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (i.user.id, self.n.value, self.c.value))
                    await i.response.send_message("✅ PIX Salvo!", ephemeral=True)
            await it.response.send_modal(MPix())
        @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.blurple, emoji="🔍")
        async def sc(self, it, b):
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
            await it.response.send_message(f"💠 {r[0]} | `{r[1]}`" if r else "Sem chave.", ephemeral=True)
    await ctx.send(embed=discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie sua chave para mediação.", color=0x4b0082), view=VPix())

# ================= COMANDO .MEDIAR =================
class ViewMed(View):
    def __init__(self): super().__init__(timeout=None)
    def gerar_embed(self):
        txt = "\n".join([f"🟢 <@{uid}>" for uid in fila_mediadores]) if fila_mediadores else "Vazia"
        return discord.Embed(title="Painel da fila controladora", description=txt, color=0x4b0082)
    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def e(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def s(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())

@bot.command()
async def mediar(ctx): await ctx.send(embed=ViewMed().gerar_embed(), view=ViewMed())

# ================= COMANDO .CANAL =================
@bot.command()
async def canal(ctx):
    class ViewCanais(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 1")
        async def c1(self, it, s): salvar_config("canal_1", s.values[0].id); await it.response.send_message("C1 ✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 2")
        async def c2(self, it, s): salvar_config("canal_2", s.values[0].id); await it.response.send_message("C2 ✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 3")
        async def c3(self, it, s): salvar_config("canal_3", s.values[0].id); await it.response.send_message("C3 ✅", ephemeral=True)
    await ctx.send("📍 Canais dos Tópicos:", view=ViewCanais())

# ================= LÓGICA DO TÓPICO =================
class ViewTopico(View):
    def __init__(self, p1_id, p2_id, med_id):
        super().__init__(timeout=None)
        self.p1_id = p1_id; self.p2_id = p2_id; self.med_id = med_id
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, it, b):
        if it.user.id not in [self.p1_id, self.p2_id]: return
        self.confirmados.add(it.user.id)
        if len(self.confirmados) == 2:
            await it.channel.purge(limit=5)
            con = sqlite3.connect("dados.db"); r = con.execute("SELECT nome, chave FROM pix WHERE user_id=?", (self.med_id,)).fetchone(); con.close()
            msg = f"**Nome:** {r[0]}\n**Chave:** `{r[1]}`" if r else "Sem PIX!"
            await it.channel.send(embed=discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", description=msg, color=0xF1C40F))
    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it, b): await it.channel.delete()

# ================= COMANDO .FILA =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo; self.valor = valor; self.users = []
    def gerar_embed(self):
        txt = "\n".join([f"👤 {u.mention} - **{g}**" for u, g in self.users]) if self.users else "Vazia"
        emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=0x3498DB)
        emb.add_field(name="👑 Modo", value=self.modo, inline=True)
        emb.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="⚡ Jogadores", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb
    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.users): return
        self.users.append((it.user, gelo))
        if len(self.users) == 2:
            p1, g1 = self.users[0]; p2, g2 = self.users[1]; self.users = []
            await it.message.edit(embed=self.gerar_embed())
            if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores!", ephemeral=True)
            med_id = fila_mediadores.pop(0)
            canais = [pegar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [int(i) for i in canais if i]
            canal_alvo = bot.get_channel(random.choice(validos)) if validos else it.channel
            thread = await canal_alvo.create_thread(name=f"Aposta-{self.valor}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {'modo': f"{self.modo} | {gelo}", 'valor': self.valor, 'p1': p1.id, 'p2': p2.id, 'med': med_id}
            emb_p = discord.Embed(title="Partida Confirmada", color=0x2b2d31)
            emb_p.add_field(name="🎮 Estilo", value=f"1v1 | {gelo}", inline=False)
            emb_p.add_field(name="ℹ️ Info", value=f"Valor Da Sala: R$ 0,10\nMediador: <@{med_id}>", inline=False)
            emb_p.add_field(name="💸 Valor", value=f"R$ {self.valor}", inline=False)
            emb_p.add_field(name="👥 Jogadores", value=f"{p1.mention}\n{p2.mention}", inline=False)
            await thread.send(embed=emb_p, view=ViewTopico(p1.id, p2.id, med_id))
            await it.response.send_message(f"✅ Tópico: {thread.mention}", ephemeral=True)
        else: await it.response.edit_message(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gel Normal")
    @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gel Infinito")
    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
    async def sair(self, it, b): self.users = [u for u in self.users if u[0].id != it.user.id]; await it.response.edit_message(embed=self.gerar_embed(), view=self)

@bot.command()
async def fila(ctx, modo: str, valor: str): await ctx.send(embed=ViewFila(modo, valor).gerar_embed(), view=ViewFila(modo, valor))

@bot.event
async def on_ready(): init_db(); print(f"✅ Bot: {bot.user.name}")

bot.run(TOKEN)
                                
