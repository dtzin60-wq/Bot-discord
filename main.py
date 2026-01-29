import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3, os, random, asyncio

# Railway utiliza variáveis de ambiente - certifique-se de configurar no painel
TOKEN = os.getenv("TOKEN")

# URL do Banner das suas imagens
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Armazenamento temporário
fila_mediadores = []
filas = {}
partidas = {}

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

# Verificador de permissão baseado no .botconfig
async def tem_permissao(it, chave_config):
    if it.user.guild_permissions.administrator: return True
    cargo_id = pegar_config(chave_config)
    if cargo_id and any(role.id == int(cargo_id) for role in it.user.roles): return True
    return False

# ================= CONFIRMAÇÃO E CRIAÇÃO DE TÓPICO =================
class ViewConfirm(View):
    def __init__(self, p1, p2, med_id, modo, valor, gelo):
        super().__init__(timeout=None)
        self.p1 = p1; self.p2 = p2; self.med_id = med_id
        self.modo = modo; self.valor = valor; self.gelo = gelo
        self.ok = []

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green)
    async def conf(self, it, b):
        if it.user not in [self.p1, self.p2]:
            return await it.response.send_message("Você não está nesta partida.", ephemeral=True)
        if it.user in self.ok:
            return await it.response.send_message("Você já confirmou.", ephemeral=True)
        
        self.ok.append(it.user)

        if len(self.ok) < 2:
            return await it.response.send_message("⏳ Aguardando o outro jogador confirmar...", ephemeral=False)

        # Seleção de canal aleatório conforme configurado no .canal
        canais_ids = [pegar_config(f"canal_{i}") for i in range(1, 4)]
        validos = [int(c) for c in canais_ids if c]
        
        if not validos:
            return await it.channel.send("❌ Erro: Nenhum canal de tópicos configurado. Use `.canal`.")

        canal_alvo = bot.get_channel(random.choice(validos))
        thread = await canal_alvo.create_thread(name=f"Aposta R${self.valor}-{self.p1.name}", type=discord.ChannelType.public_thread)

        partidas[thread.id] = {"jogadores": [self.p1, self.p2], "med": self.med_id}

        # Embed de Partida Criada (Imagem 3)
        emb = discord.Embed(title="🎮 PARTIDA INICIADA", color=0x2ecc71)
        emb.add_field(name="Modo", value=self.modo, inline=True)
        emb.add_field(name="Gelo", value=self.gelo, inline=True)
        emb.add_field(name="Valor", value=f"R$ {self.valor}", inline=False)
        emb.add_field(name="Mediador", value=f"<@{self.med_id}>", inline=False)
        emb.set_image(url=BANNER_URL)

        await thread.send(f"{self.p1.mention} ⚔️ {self.p2.mention}")
        await thread.send(embed=emb)
        await it.response.send_message(f"✅ Tópico criado com sucesso: {thread.mention}")

# ================= AUXILIAR (IMAGEM 2) =================
class ViewAux(View):
    def __init__(self, tid):
        super().__init__(timeout=None)
        self.tid = tid

    def gerar_botoes_vitoria(self, tipo_vitoria):
        dados = partidas.get(self.tid)
        class VitoriaView(View):
            def __init__(self):
                super().__init__()
                for j in dados["jogadores"]:
                    btn = Button(label=f"Vitória para {j.name}", style=discord.ButtonStyle.blurple)
                    async def callback(i, vencedor=j):
                        await i.response.send_message(f"🏆 Partida Finalizada! Vitória {tipo_vitoria} para {vencedor.mention}")
                    btn.callback = callback
                    self.add_item(btn)
        return VitoriaView()

    @discord.ui.button(label="Dar Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, b):
        if not await tem_permissao(it, "perm_aux"): return await it.response.send_message("Sem permissão.", ephemeral=True)
        await it.response.send_message("Selecione o vencedor:", view=self.gerar_botoes_vitoria("Comum"), ephemeral=True)

    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.gray)
    async def wo(self, it, b):
        if not await tem_permissao(it, "perm_aux"): return await it.response.send_message("Sem permissão.", ephemeral=True)
        await it.response.send_message("Selecione quem ganhou por W.O:", view=self.gerar_botoes_vitoria("W.O"), ephemeral=True)

    @discord.ui.button(label="Finalizar Aposta", style=discord.ButtonStyle.red)
    async def fechar(self, it, b):
        await it.response.send_message("Encerrando tópico em 3 segundos...")
        await asyncio.sleep(3)
        await it.channel.delete()
        partidas.pop(self.tid, None)

# ================= FILA PRINCIPAL (IMAGEM 1) =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo; self.valor = valor; self.users = []

    async def update_embed(self, msg):
        txt = "\n".join([f"{u.mention} - {g}" for u, g in self.users]) if self.users else "Nenhum jogador na fila"
        emb = discord.Embed(title="🎮 SPACE APOSTAS | FILA", color=discord.Color.blue())
        emb.add_field(name="👑 Modo", value=self.modo, inline=True)
        emb.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="⚡ Jogadores", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        await msg.edit(content=None, embed=emb, view=self)

    async def entrar(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.users):
            return await it.response.send_message("Você já está na fila.", ephemeral=True)
        
        self.users.append((it.user, gelo))
        
        if len(self.users) == 2:
            if not fila_mediadores:
                self.users.pop() # Remove para não travar a fila
                return await it.response.send_message("❌ Não há mediadores em serviço no momento!", ephemeral=True)
            
            med_id = fila_mediadores.pop(0)
            p1, g1 = self.users[0]
            p2, g2 = self.users[1]
            
            await it.response.send_message(f"⚔️ Partida encontrada entre {p1.mention} e {p2.mention}!", view=ViewConfirm(p1, p2, med_id, self.modo, self.valor, g2))
            self.users = [] # Reseta a fila
        else:
            await it.response.send_message("Você entrou na fila!", ephemeral=True)
            await self.update_embed(it.message)

    @discord.ui.button(label="Gel Normal", style=discord.ButtonStyle.secondary)
    async def b1(self, it, b): await self.entrar(it, "Gel Normal")

    @discord.ui.button(label="Gel Infinito", style=discord.ButtonStyle.secondary)
    async def b2(self, it, b): await self.entrar(it, "Gel Infinito")

# ================= COMANDOS PRINCIPAIS =================
@bot.command()
async def fila(ctx, modo: str, valor: str, tipo: str = "mobile"):
    modo_f = f"{modo}-{tipo}"
    v = ViewFila(modo_f, valor)
    msg = await ctx.send("Iniciando fila...", view=v)
    await v.update_embed(msg)

@bot.command()
async def mediar(ctx):
    class VMed(View):
        @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.send_message("Você agora é um mediador ativo.", ephemeral=True)

        @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            await it.response.send_message("Você saiu da fila de mediadores.", ephemeral=True)

    emb = discord.Embed(title="Painel da Fila Controladora", description="Clique abaixo para mediar as partidas.", color=0x4b0082)
    await ctx.send(embed=emb, view=VMed())

@bot.command()
async def Pix(ctx):
    class VPix(View):
        @discord.ui.button(label="Configurar Chave PIX", style=discord.ButtonStyle.green)
        async def p(self, it, b):
            class MPix(Modal, title="Cadastro de PIX"):
                n = TextInput(label="Nome Completo")
                c = TextInput(label="Chave PIX")
                async def on_submit(self, i):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (i.user.id, self.n.value, self.c.value))
                    await i.response.send_message("✅ Sua chave PIX foi salva com sucesso!", ephemeral=True)
            await it.response.send_modal(MPix())

    await ctx.send("💠 Gerencie suas chaves PIX para receber pagamentos:", view=VPix())

@bot.command()
async def botconfig(ctx):
    class VConf(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo que usa .aux")
        async def s1(self, it, s): 
            salvar_config("perm_aux", s.values[0].id)
            await it.response.send_message("Permissão .aux atualizada.", ephemeral=True)

    await ctx.send("⚙️ Configurações de Permissões:", view=VConf())

@bot.command()
async def canal(ctx):
    class VCanal(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal para Tópicos", min_values=1, max_values=1)
        async def c1(self, it, s): 
            salvar_config("canal_1", s.values[0].id)
            await it.response.send_message("Canal 1 configurado.", ephemeral=True)

    await ctx.send("📍 Configure onde as partidas (tópicos) serão criadas:", view=VCanal())

@bot.command()
async def aux(ctx):
    if not isinstance(ctx.channel, discord.Thread):
        return await ctx.send("❌ Este comando só pode ser usado dentro de um tópico de partida.")
    await ctx.send("🛠️ **Painel Auxiliar de Mediador**", view=ViewAux(ctx.channel.id))

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user.name} está online no Railway!")

if __name__ == "__main__":
    bot.run(TOKEN)
        
