import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os
import asyncio

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qr TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
    conn.commit()
    conn.close()

def salvar_config(chave, valor):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (chave, str(valor)))
    conn.commit()
    conn.close()

def puxar_config(chave):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE chave = ?", (chave,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# Checagem de permissão personalizada
def e_staff():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator: return True
        cargo_staff_id = puxar_config("cargo_staff_id")
        if cargo_staff_id and any(r.id == int(cargo_staff_id) for r in ctx.author.roles):
            return True
        return False
    return commands.check(predicate)

# ================= VIEWS (AUXILIAR E PIX) =================

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    @discord.ui.button(label="Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        await it.response.send_message("🏆 Vitória declarada pelo mediador.")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.red)
    async def wo(self, it, btn):
        await it.response.send_message("⚠️ Partida encerrada por W.O.")
        await self.thread.edit(locked=True, archived=True)

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, it: discord.Interaction, button: Button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in it.user.roles):
            return await it.response.send_message("❌ Você não tem o cargo de Mediador.", ephemeral=True)

        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (it.user.id,))
        res = cursor.fetchone(); conn.close()
        if not res: return await it.response.send_message("❌ Use `.pix` primeiro.", ephemeral=True)

        await it.response.defer()
        await it.channel.purge(limit=3)
        embed = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed.add_field(name="👤 Nome:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"): embed.set_image(url=res[2])
        await it.channel.send(content="@everyone", embed=embed)

# ================= FILA E TÓPICOS =================

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, it, button):
        dados = partidas_ativas.get(self.thread_id)
        if not dados or it.user not in dados["jogadores"]:
            return await it.response.send_message("❌ Você não é jogador aqui.", ephemeral=True)
        
        if it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!")

        if len(set(dados["confirmados"])) >= 2:
            await it.channel.send(embed=discord.Embed(title="💳 AGUARDANDO PAGAMENTO", color=0xf1c40f), view=ViewPixMediador())

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def btn_recusar(self, it, button):
        await it.response.send_message("❌ Partida recusada. Encerrando...")
        await it.channel.edit(locked=True, archived=True)

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.gray, emoji="📝")
    async def btn_regras(self, it, button):
        await it.response.send_message("📝 Usem este chat para combinar as regras.", ephemeral=True)

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave, self.valor = chave, valor

    async def atualizar(self, message):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention}" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Valor", value=f"R$ {valor_str(self.valor)}", inline=False)
        embed.add_field(name="Fila", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, it, submodo):
        canal_id = puxar_config("canal_destino")
        if not canal_id: return await it.response.send_message("❌ Use `.canal` primeiro.", ephemeral=True)
        
        await it.response.defer(ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        filas_partida[self.chave].append((it.user, submodo))
        
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]
        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}
            
            med = fila_atendimento[0].mention if fila_atendimento else "Sem mediador"
            await thread.send(content=f"{p1.mention} {p2.mention} {med}", embed=discord.Embed(title="Confirmações", color=0x2ecc71), view=ViewConfirmarPartida(thread.id))
            await self.atualizar(it.message)
        else:
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_n(self, it, btn): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_i(self, it, btn): await self.entrar(it, "gelo infinito")

# ================= COMANDOS ADMINISTRATIVOS =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar o painel .aux?")
        async def s_aux(self, it, sel):
            salvar_config("cargo_aux_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo de Auxiliar: {sel.values[0].mention}", ephemeral=True)
        
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode mandar o Pix?")
        async def s_med(self, it, sel):
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo de Mediador (Pix): {sel.values[0].mention}", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar os comandos do bot?")
        async def s_staff(self, it, sel):
            salvar_config("cargo_staff_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo de Staff (Comandos): {sel.values[0].mention}", ephemeral=True)

    await ctx.send("⚙️ **Configuração de Cargos**", view=ConfigV())

@bot.command()
@e_staff()
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal dos tópicos...", channel_types=[discord.ChannelType.text])
        async def s(self, it, sel):
            salvar_config("canal_destino", sel.values[0].id)
            await it.response.send_message("✅ Canal configurado!", ephemeral=True)
    await ctx.send("Onde as partidas serão criadas?", view=CV())

@bot.command()
@e_staff()
async def fila(ctx, v: str):
    val = float(v.replace(",", "."))
    await ctx.send(embed=discord.Embed(title="🎮 FILA"), view=ViewFilaPartida(f"f_{val}", val))

@bot.command()
@e_staff()
async def mediar(ctx):
    class VS(View):
        async def up(self, it):
            txt = "\n".join([m.mention for m in fila_atendimento]) if fila_atendimento else "Vazio"
            await it.message.edit(embed=discord.Embed(title="🎧 SUPORTE", description=txt), view=self)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user not in fila_atendimento: fila_atendimento.append(it.user)
            await it.response.defer(); await self.up(it)
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user in fila_atendimento: fila_atendimento.remove(it.user)
            await it.response.defer(); await self.up(it)
    await ctx.send(embed=discord.Embed(title="🎧 FILA DE SUPORTE"), view=VS())

@bot.command()
async def aux(ctx):
    c_id = puxar_config("cargo_aux_id")
    if c_id and any(r.id == int(c_id) for r in ctx.author.roles):
        await ctx.send(embed=discord.Embed(title="🛠️ PAINEL"), view=ViewAuxiliar(ctx.channel))

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Meu Pix"):
        n = TextInput(label="Nome")
        c = TextInput(label="Chave")
        q = TextInput(label="Link Foto QR")
        async def on_submit(self, it):
            conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Pix salvo!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM())
    await ctx.send("Configure seu Pix:", view=v)

def valor_str(v): return f"{v:.2f}".replace(".", ",")

@bot.event
async def on_ready():
    init_db(); print(f"✅ {bot.user} online")

bot.run(TOKEN)
    
