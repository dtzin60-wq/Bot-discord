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

# Variáveis globais
filas_partida = {}
partidas_ativas = {}
fila_atendimento = []

def formatar_real(valor):
    return f"{valor:.2f}".replace(".", ",")

# ================= VIEWS DE MEDIAÇÃO E AUXILIAR =================

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    @discord.ui.button(label="Dar vitória para jogador", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        await it.response.send_message("🏆 **Vitória confirmada!** Partida encerrada pelo mediador.")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.gray)
    async def finalizar(self, it, btn):
        await it.response.send_message("🏁 **Aposta Finalizada.**")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.red)
    async def wo(self, it, btn):
        await it.response.send_message("⚠️ **VITÓRIA POR W.O!**\nO mediador declarou vitória por ausência do adversário.")
        await self.thread.edit(locked=True, archived=True)

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, it: discord.Interaction, button: Button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in it.user.roles):
            return await it.response.send_message("❌ Apenas o cargo mediador pode enviar o Pix.", ephemeral=True)

        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (it.user.id,))
        res = cursor.fetchone(); conn.close()
        
        if not res: return await it.response.send_message("❌ Cadastre seu pix com `.pix` primeiro.", ephemeral=True)

        await it.response.defer() # Evita erro de interação
        await it.channel.purge(limit=2)
        embed = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed.add_field(name="👤 Nome:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"): embed.set_image(url=res[2])
        embed.set_footer(text=f"Mediador: {it.user.display_name}")
        await it.channel.send(content="@everyone", embed=embed)

# ================= INTERAÇÃO NO TÓPICO =================

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, it: discord.Interaction, button: Button):
        dados = partidas_ativas.get(self.thread_id)
        if not dados or it.user not in dados["jogadores"]:
            return await it.response.send_message("❌ Você não está nesta partida.", ephemeral=True)
        
        if it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!", color=0x00ff00)

        if len(set(dados["confirmados"])) >= 2:
            embed_ready = discord.Embed(title="💳 AGUARDANDO PAGAMENTO", color=0xf1c40f, description="Ambos confirmaram! Mediador, envie os dados abaixo.")
            await it.channel.send(embed=embed_ready, view=ViewPixMediador())

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def btn_recusar(self, it: discord.Interaction, button: Button):
        await it.response.send_message(f"❌ {it.user.mention} recusou. Tópico fechado.")
        await it.channel.edit(locked=True, archived=True)

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.gray, emoji="📝")
    async def btn_regras(self, it: discord.Interaction, button: Button):
        # Respondemos de forma efêmera para não dar erro
        await it.response.send_message("📝 Combinem as regras aqui no tópico antes de pagar.", ephemeral=True)

# ================= SISTEMA DE FILA 1V1 MOBILE =================

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave, self.valor = chave, valor

    async def atualizar(self, message):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - `{m.title()}`" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        embed.add_field(name="Valor", value=f"R$ {formatar_real(self.valor)}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, it: discord.Interaction, submodo):
        canal_id = puxar_config("canal_destino")
        if not canal_id: return await it.response.send_message("❌ Configure o canal com `.canal`.", ephemeral=True)

        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(u.id == it.user.id for u, _ in filas_partida[self.chave]):
            return await it.response.send_message("❌ Já está na fila!", ephemeral=True)

        await it.response.defer() # Essencial para evitar "Interação falhou" em filas
        filas_partida[self.chave].append((it.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]

        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}

            med_mencion = fila_atendimento[0].mention if fila_atendimento else "*Ninguém na fila*"
            emb = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb.add_field(name="👮 Mediador:", value=med_mencion, inline=False)
            emb.add_field(name="👑 Modo:", value=f"1v1 | {submodo.title()}", inline=False)
            emb.add_field(name="⚡ Jogadores:", value=f"{p1.mention}\n{p2.mention}", inline=False)
            
            mentions = f"{p1.mention} {p2.mention} {fila_atendimento[0].mention if fila_atendimento else ''}"
            await thread.send(content=mentions, embed=emb, view=ViewConfirmarPartida(thread.id))
            await self.atualizar(it.message)
        else:
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_n(self, it, btn): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_i(self, it, btn): await self.entrar(it, "gelo infinito")

# ================= COMANDOS =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Qual cargo pode dar Aux?")
        async def s_aux(self, it, sel):
            salvar_config("cargo_aux_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo {sel.values[0].mention} para .aux salvo!", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Qual cargo pode mandar Pix?")
        async def s_mediador(self, it, sel):
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo {sel.values[0].mention} para Mediador salvo!", ephemeral=True)
    await ctx.send("⚙️ Configurações do Bot:", view=ConfigV())

@bot.command()
async def aux(ctx):
    c_id = puxar_config("cargo_aux_id")
    if not c_id or not any(r.id == int(c_id) for r in ctx.author.roles):
        return await ctx.send("❌ Sem permissão de auxiliar.")
    if not isinstance(ctx.channel, discord.Thread):
        return await ctx.send("❌ Use apenas dentro dos tópicos.")
    await ctx.send(embed=discord.Embed(title="🛠️ AUXILIAR", color=0x3498db), view=ViewAuxiliar(ctx.channel))

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Selecione o canal...", channel_types=[discord.ChannelType.text])
        async def s(self, it, sel):
            salvar_config("canal_destino", sel.values[0].id)
            await it.response.send_message("✅ Canal de tópicos definido!", ephemeral=True)
    await ctx.send("Onde as partidas devem ser criadas?", view=CV())

@bot.command()
@commands.has_permissions(administrator=True)
async def mediar(ctx):
    class ViewSuporte(View):
        async def atualizar_f(self, it):
            txt = "\n".join([m.mention for m in fila_atendimento]) if fila_atendimento else "Vazio"
            emb = discord.Embed(title="🎧 SUPORTE", description=f"**Fila atual:**\n{txt}", color=0x2b2d31)
            await it.message.edit(embed=emb, view=self)
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user not in fila_atendimento: fila_atendimento.append(it.user)
            await it.response.defer(); await self.atualizar_f(it)
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user in fila_atendimento: fila_atendimento.remove(it.user)
            await it.response.defer(); await self.atualizar_f(it)
    await ctx.send(embed=discord.Embed(title="🎧 SUPORTE", description="**Entre aqui e comece a ser atendido**", color=0x2b2d31), view=ViewSuporte())

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, valor: str):
    try:
        val = float(valor.replace(",", "."))
        await ctx.send(embed=discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).add_field(name="Valor", value=f"R$ {formatar_real(val)}"), view=ViewFilaPartida(f"f_{val}", val))
    except: await ctx.send("❌ Ex: `.fila 10,00`")

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Meu Pix"):
        n = TextInput(label="Nome")
        c = TextInput(label="Chave")
        q = TextInput(label="Link da Foto QR Code")
        async def on_submit(self, it):
            conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Pix salvo!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM())
    await ctx.send("Cadastre seus dados:", view=v)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} online!")

bot.run(TOKEN)
        
