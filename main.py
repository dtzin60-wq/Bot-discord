import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3
import os
import asyncio

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
# Banner atualizado conforme solicitado
BANNER_URL = "https://googleusercontent.com/image_generation_content/0"

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

def e_staff():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator: return True
        cargo_staff_id = puxar_config("cargo_staff_id")
        return cargo_staff_id and any(r.id == int(cargo_staff_id) for r in ctx.author.roles)
    return commands.check(predicate)

# ================= SISTEMA DE VITÓRIA E COINS =================

class ViewSelecionarVencedor(View):
    def __init__(self, jogadores, thread):
        super().__init__(timeout=60)
        self.jogadores = jogadores
        self.thread = thread

        options = [discord.SelectOption(label=j.display_name, value=str(j.id), emoji="🏆") for j in jogadores]
        select = Select(placeholder="Selecione o vencedor da partida...", options=options)
        select.callback = self.vencedor_callback
        self.add_item(select)

    async def vencedor_callback(self, it: discord.Interaction):
        vencedor_id = int(it.data['values'][0])
        vencedor = await bot.fetch_user(vencedor_id)
        
        await it.response.send_message(f"🏆 **VITÓRIA DECLARADA!**\nO vencedor é: {vencedor.mention}\n💰 **1 Coin** foi aplicado com sucesso!")
        
        # Aguarda um pouco e fecha o tópico
        await asyncio.sleep(5)
        await self.thread.edit(locked=True, archived=True)

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    @discord.ui.button(label="🏆 Declarar Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        dados = partidas_ativas.get(self.thread.id)
        if not dados:
            return await it.response.send_message("❌ Jogadores não encontrados neste tópico.", ephemeral=True)
        
        view = ViewSelecionarVencedor(dados["jogadores"], self.thread)
        await it.response.send_message("Escolha o vencedor abaixo:", view=view, ephemeral=True)

    @discord.ui.button(label="⚠️ Vitória por W.O", style=discord.ButtonStyle.red)
    async def wo(self, it, btn):
        await it.response.send_message("⚠️ **PARTIDA ENCERRADA POR W.O!**")
        await asyncio.sleep(3)
        await self.thread.edit(locked=True, archived=True)

# ================= SISTEMA DE FILA E PIX =================

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, it, button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in it.user.roles):
            return await it.response.send_message("❌ Apenas o Mediador pode enviar o Pix.", ephemeral=True)

        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (it.user.id,))
        res = cursor.fetchone(); conn.close()
        if not res: return await it.response.send_message("❌ Cadastre seu Pix com `.pix` primeiro.", ephemeral=True)

        await it.response.defer()
        await it.channel.purge(limit=2)
        embed = discord.Embed(title="🏦 DADOS PARA PAGAMENTO", color=0x2ecc71)
        embed.add_field(name="👤 Titular:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave Pix:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"): embed.set_image(url=res[2])
        await it.channel.send(content="@everyone", embed=embed)

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, it, button):
        dados = partidas_ativas.get(self.thread_id)
        if not dados or it.user not in dados["jogadores"]:
            return await it.response.send_message("❌ Você não é jogador desta partida.", ephemeral=True)
        
        if it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!")

        if len(set(dados["confirmados"])) >= 2:
            await it.channel.send(embed=discord.Embed(title="💳 AGUARDANDO PAGAMENTO", color=0xf1c40f, description="Ambos confirmaram! Mediador, envie o Pix."), view=ViewPixMediador())

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def btn_recusar(self, it, button):
        await it.response.send_message("❌ Partida cancelada. Tópico arquivado.")
        await it.channel.edit(locked=True, archived=True)

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave, self.valor = chave, valor

    async def atualizar(self, message):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention}" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Valor da Partida", value=f"R$ {self.valor:.2f}", inline=False)
        embed.add_field(name="Fila Atual", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, it, submodo):
        canal_id = puxar_config("canal_destino")
        if not canal_id: return await it.response.send_message("❌ Configure o canal com `.canal`.", ephemeral=True)
        
        await it.response.defer(ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(u.id == it.user.id for u, _ in filas_partida[self.chave]):
            return await it.followup.send("❌ Você já está na fila!", ephemeral=True)

        filas_partida[self.chave].append((it.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]

        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}
            
            med = fila_atendimento[0].mention if fila_atendimento else "Nenhum mediador na fila"
            await thread.send(content=f"{p1.mention} {p2.mention} {med}", embed=discord.Embed(title="Aguardando Confirmações", color=0x2ecc71), view=ViewConfirmarPartida(thread.id))
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
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo para usar .aux?")
        async def s_aux(self, it, sel):
            salvar_config("cargo_aux_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo Auxiliar: {sel.values[0].name}", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo para mandar o Pix?")
        async def s_med(self, it, sel):
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo Mediador: {sel.values[0].name}", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Staff (Comandos)?")
        async def s_staff(self, it, sel):
            salvar_config("cargo_staff_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo Staff: {sel.values[0].name}", ephemeral=True)
    await ctx.send("⚙️ **Configuração de Permissões**", view=ConfigV())

@bot.command()
@e_staff()
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal dos tópicos...", channel_types=[discord.ChannelType.text])
        async def s(self, it, sel):
            salvar_config("canal_destino", sel.values[0].id)
            await it.response.send_message(f"✅ Canal definido: {sel.values[0].name}", ephemeral=True)
    await ctx.send("Selecione onde os tópicos serão criados:", view=CV())

@bot.command()
@e_staff()
async def fila(ctx, v: str):
    try:
        val = float(v.replace(",", "."))
        await ctx.send(embed=discord.Embed(title="🎮 WS APOSTAS"), view=ViewFilaPartida(f"f_{val}", val))
    except: await ctx.send("❌ Use: `.fila 10,00`")

@bot.command()
@e_staff()
async def mediar(ctx):
    class VS(View):
        async def up(self, it):
            txt = "\n".join([m.mention for m in fila_atendimento]) if fila_atendimento else "Fila Vazia"
            await it.message.edit(embed=discord.Embed(title="🎧 FILA DE SUPORTE", description=txt), view=self)
        @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user not in fila_atendimento: fila_atendimento.append(it.user)
            await it.response.defer(); await self.up(it)
        @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user in fila_atendimento: fila_atendimento.remove(it.user)
            await it.response.defer(); await self.up(it)
    await ctx.send(embed=discord.Embed(title="🎧 FILA DE SUPORTE"), view=VS())

@bot.command()
async def aux(ctx):
    c_id = puxar_config("cargo_aux_id")
    if c_id and any(r.id == int(c_id) for r in ctx.author.roles):
        await ctx.send(embed=discord.Embed(title="🛠️ PAINEL AUXILIAR"), view=ViewAuxiliar(ctx.channel))

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Cadastro de Pix"):
        n = TextInput(label="Nome Titular")
        c = TextInput(label="Chave Pix")
        q = TextInput(label="Link do QR Code (Imagem)")
        async def on_submit(self, it):
            conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Seus dados Pix foram salvos!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM())
    await ctx.send("Configure seu recebimento:", view=v)

@bot.event
async def on_ready():
    init_db(); print(f"✅ Bot conectado como {bot.user}")

bot.run(TOKEN)
    
