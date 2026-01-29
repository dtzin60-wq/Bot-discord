import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3
import os
import asyncio

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
# NOVO BANNER CONFIGURADO ABAIXO:
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1466311386173800638/1769666262790.png?ex=697c4865&is=697af6e5&hm=0934f98ad0d47a55315994c9c0af4bfd531c444a76ed5456e963ba1eaa003903&"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= BANCO DE DADOS (ECONOMIA E CONFIG) =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qr TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats 
                      (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, 
                       derrotas INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def db_execute(query, params=()):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = cursor.fetchone()
    conn.commit()
    conn.close()
    return res

def salvar_config(chave, valor):
    db_execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (chave, str(valor)))

def puxar_config(chave):
    res = db_execute("SELECT valor FROM config WHERE chave = ?", (chave,))
    return res[0] if res else None

def atualizar_vitoria(ganhador_id, perdedor_id):
    for uid in [ganhador_id, perdedor_id]:
        db_execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (uid,))
    
    # +1 Vitoria, +1 Coin, +1 Streak
    db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1, streak = streak + 1 WHERE user_id = ?", (ganhador_id,))
    # +1 Derrota, Streak Reset
    db_execute("UPDATE stats SET derrotas = derrotas + 1, streak = 0 WHERE user_id = ?", (perdedor_id,))

# ================= SISTEMA DE VITÓRIA (.AUX) =================

class ViewSelecionarVencedor(View):
    def __init__(self, jogadores, thread):
        super().__init__(timeout=60)
        self.jogadores = jogadores
        self.thread = thread
        options = [discord.SelectOption(label=j.display_name, value=str(j.id), emoji="🏆") for j in jogadores]
        select = Select(placeholder="Quem venceu a partida?", options=options)
        select.callback = self.vencedor_callback
        self.add_item(select)

    async def vencedor_callback(self, it: discord.Interaction):
        vencedor_id = int(it.data['values'][0])
        perdedor = [j for j in self.jogadores if j.id != vencedor_id]
        perdedor_id = perdedor[0].id if perdedor else None
        
        atualizar_vitoria(vencedor_id, perdedor_id)
        v_obj = await bot.fetch_user(vencedor_id)
        
        await it.response.send_message(f"🏆 **VITÓRIA CONFIRMADA!**\nVencedor: {v_obj.mention}\n💰 **1 Coin** adicionado ao saldo!")
        await asyncio.sleep(5)
        await self.thread.edit(locked=True, archived=True)

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    @discord.ui.button(label="🏆 Declarar Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        dados = partidas_ativas.get(self.thread.id)
        if not dados: return await it.response.send_message("❌ Jogadores não encontrados.", ephemeral=True)
        await it.response.send_message("Selecione o vencedor:", view=ViewSelecionarVencedor(dados["jogadores"], self.thread), ephemeral=True)

    @discord.ui.button(label="⚠️ Vitória por W.O", style=discord.ButtonStyle.red)
    async def wo(self, it, btn):
        await it.response.send_message("⚠️ Partida encerrada por W.O.")
        await asyncio.sleep(3)
        await self.thread.edit(locked=True, archived=True)

# ================= COMANDO DE PERFIL .P =================

@bot.command()
async def p(ctx, member: discord.Member = None):
    member = member or ctx.author
    res = db_execute("SELECT vitorias, derrotas, streak, coins FROM stats WHERE user_id = ?", (member.id,))
    v, d, s, c = res if res else (0, 0, 0, 0)

    embed = discord.Embed(title=f"📊 Perfil de {member.display_name}", color=0x2ecc71)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏆 Vitórias", value=f"`{v}`", inline=True)
    embed.add_field(name="❌ Derrotas", value=f"`{d}`", inline=True)
    embed.add_field(name="🔥 Consecutivas", value=f"`{s}`", inline=True)
    embed.add_field(name="💰 Coins", value=f"`{c}`", inline=True)
    await ctx.send(embed=embed)

# ================= FILA E PIX =================

class ViewPixMediador(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, it, button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in it.user.roles):
            return await it.response.send_message("❌ Apenas mediadores.", ephemeral=True)
        res = db_execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (it.user.id,))
        if not res: return await it.response.send_message("❌ Use `.pix`.", ephemeral=True)
        await it.response.defer(); await it.channel.purge(limit=2)
        embed = discord.Embed(title="🏦 PAGAMENTO", color=0x2ecc71)
        embed.add_field(name="👤 Titular:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"): embed.set_image(url=res[2])
        await it.channel.send(content="@everyone", embed=embed)

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None); self.chave = chave; self.valor = valor
    async def atualizar(self, message):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention}" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
        embed.add_field(name="Valor", value=f"R$ {self.valor:.2f}", inline=False)
        embed.add_field(name="Fila", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)
    async def entrar(self, it, submodo):
        c_id = puxar_config("canal_destino")
        if not c_id: return await it.response.send_message("❌ Use `.canal`.", ephemeral=True)
        await it.response.defer(ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        filas_partida[self.chave].append((it.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]
        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            thread = await bot.get_channel(int(c_id)).create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}")
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}
            await thread.send(content=f"{p1.mention} {p2.mention}", view=ViewConfirmarPartida(thread.id))
            await self.atualizar(it.message)
        else: await self.atualizar(it.message)
    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g_n(self, it, b): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g_i(self, it, b): await self.entrar(it, "gelo infinito")

class ViewConfirmarPartida(View):
    def __init__(self, tid): super().__init__(timeout=None); self.tid = tid
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        dados = partidas_ativas.get(self.tid)
        if it.user in dados["jogadores"] and it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!")
            if len(set(dados["confirmados"])) >= 2:
                await it.channel.send("💳 Pagamento:", view=ViewPixMediador())

# ================= COMANDOS ADM =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo .aux")
        async def s1(self, it, sel): salvar_config("cargo_aux_id", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Staff")
        async def s2(self, it, sel): salvar_config("cargo_staff_id", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Mediador (Pix)")
        async def s3(self, it, sel): salvar_config("cargo_mediador_id", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("Configuração de Cargos:", view=ConfigV())

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal tópicos")
        async def s(self, it, sel): salvar_config("canal_destino", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("Escolha o canal de tópicos:", view=CV())

@bot.command()
async def fila(ctx, v: str):
    val = float(v.replace(",", "."))
    await ctx.send(embed=discord.Embed(title="🎮 WS APOSTAS"), view=ViewFilaPartida(f"f_{val}", val))

@bot.command()
async def aux(ctx):
    c_id = puxar_config("cargo_aux_id")
    if c_id and any(r.id == int(c_id) for r in ctx.author.roles):
        await ctx.send(embed=discord.Embed(title="🛠️ PAINEL AUXILIAR"), view=ViewAuxiliar(ctx.channel))

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Meu Pix"):
        n = TextInput(label="Nome"); c = TextInput(label="Chave"); q = TextInput(label="Foto QR")
        async def on_submit(self, it):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            await it.response.send_message("✅ Pix Cadastrado!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM()); await ctx.send("Configure seu Pix:", view=v)

filas_partida = {}; partidas_ativas = {}
@bot.event
async def on_ready(): init_db(); print(f"✅ Bot Online como {bot.user}")

bot.run(TOKEN)
        
