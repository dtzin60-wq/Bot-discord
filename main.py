import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os

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
        await it.response.send_message("🏆 **Vitória confirmada!** O mediador encerrou a partida e declarou um vencedor.")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.gray)
    async def finalizar(self, it, btn):
        await it.response.send_message("🏁 **Aposta Finalizada.** O tópico será arquivado.")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.red)
    async def wo(self, it, btn):
        await it.response.send_message("⚠️ **VITÓRIA POR W.O!**\nO mediador declarou vitória por ausência do adversário.")
        await self.thread.edit(locked=True, archived=True)

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, interaction: discord.Interaction, button: Button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Apenas mediadores autorizados podem enviar o Pix.", ephemeral=True)

        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (interaction.user.id,))
        res = cursor.fetchone(); conn.close()
        
        if not res: return await interaction.response.send_message("❌ Você ainda não cadastrou seu Pix. Use `.pix`.", ephemeral=True)

        await interaction.channel.purge(limit=2)
        embed = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed.add_field(name="👤 Nome da conta:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave Pix:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"): 
            embed.set_image(url=res[2])
        embed.set_footer(text=f"Mediador: {interaction.user.display_name}")
        await interaction.channel.send(content="@everyone", embed=embed)

# ================= INTERAÇÃO NO TÓPICO =================

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas_ativas.get(self.thread_id)
        if not dados or interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não faz parte desta partida.", ephemeral=True)
        
        if interaction.user not in dados["confirmados"]:
            dados["confirmados"].append(interaction.user)
            await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!", color=0x00ff00)

        if len(set(dados["confirmados"])) >= 2:
            embed_ready = discord.Embed(title="💳 AGUARDANDO PAGAMENTO", color=0xf1c40f, description="Ambos confirmaram! Mediador, por favor, envie os dados de pagamento.")
            await interaction.channel.send(embed=embed_ready, view=ViewPixMediador())

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def btn_recusar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(f"❌ {interaction.user.mention} recusou a partida. O tópico será fechado.")
        await interaction.channel.edit(locked=True, archived=True)

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.gray, emoji="📝")
    async def btn_regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("📝 Use este chat para combinar as regras antes de pagar.", ephemeral=True)

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
        embed.add_field(name="Valor da Partida", value=f"R$ {formatar_real(self.valor)}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, interaction, submodo):
        canal_id = puxar_config("canal_destino")
        if not canal_id: return await interaction.response.send_message("❌ O canal de tópicos não foi definido. Use `.canal`.", ephemeral=True)

        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(u.id == interaction.user.id for u, _ in filas_partida[self.chave]):
            return await interaction.response.send_message("❌ Você já está na fila.", ephemeral=True)

        filas_partida[self.chave].append((interaction.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]

        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}

            # Puxa o primeiro mediador da fila de suporte
            mediador_resp = fila_atendimento[0].mention if fila_atendimento else "*Ninguém na fila (Use .mediar)*"
            
            emb = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb.add_field(name="👮 Mediador:", value=mediador_resp, inline=False)
            emb.add_field(name="👑 Modo:", value=f"1v1 | {submodo.title()}", inline=False)
            emb.add_field(name="⚡ Jogadores:", value=f"{p1.mention} vs {p2.mention}", inline=False)
            
            mencionados = f"{p1.mention} {p2.mention}"
            if fila_atendimento: mencionados += f" {fila_atendimento[0].mention}"
            
            await thread.send(content=mencionados, embed=emb, view=ViewConfirmarPartida(thread.id))
            await interaction.response.send_message(f"⚔️ Partida criada: {thread.mention}", ephemeral=True)
            await self.atualizar(interaction.message)
        else:
            await interaction.response.defer(); await self.atualizar(interaction.message)

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
            await it.response.send_message(f"✅ Cargo {sel.values[0].mention} definido para o comando .aux", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Qual cargo pode mandar Pix?")
        async def s_mediador(self, it, sel):
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo {sel.values[0].mention} definido como Mediador (Pix).", ephemeral=True)
    await ctx.send("⚙️ **Painel de Configuração**", view=ConfigV())

@bot.command()
async def aux(ctx):
    c_id = puxar_config("cargo_aux_id")
    if not c_id or not any(r.id == int(c_id) for r in ctx.author.roles):
        return await ctx.send("❌ Você não tem permissão para usar o painel auxiliar.")
    if not isinstance(ctx.channel, discord.Thread):
        return await ctx.send("❌ Este comando deve ser usado dentro de um tópico de partida.")
    await ctx.send(embed=discord.Embed(title="🛠️ PAINEL AUXILIAR", color=0x3498db), view=ViewAuxiliar(ctx.channel))

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Escolha o canal de tópicos...", channel_types=[discord.ChannelType.text])
        async def s(self, it, sel):
            salvar_config("canal_destino", sel.values[0].id)
            await it.response.send_message(f"✅ Canal {sel.values[0].mention} configurado!", ephemeral=True)
    await ctx.send("Selecione o canal onde as partidas serão criadas:", view=CV())

@bot.command()
@commands.has_permissions(administrator=True)
async def mediar(ctx):
    class ViewSuporte(View):
        def __init__(self): super().__init__(timeout=None)
        async def atualizar_fila(self, it):
            txt = "\n".join([m.mention for m in fila_atendimento]) if fila_atendimento else "Vazio"
            emb = discord.Embed(title="🎧 SUPORTE", description=f"**Entre aqui e comece a ser atendido**\n\n**Fila atual:**\n{txt}", color=0x2b2d31)
            await it.message.edit(embed=emb, view=self)
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user not in fila_atendimento: fila_atendimento.append(it.user)
            await it.response.defer(); await self.atualizar_fila(it)
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user in fila_atendimento: fila_atendimento.remove(it.user)
            await it.response.defer(); await self.atualizar_fila(it)

    emb = discord.Embed(title="🎧 SUPORTE", description="**Entre aqui e comece a ser atendido**", color=0x2b2d31)
    await ctx.send(embed=emb, view=ViewSuporte())

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, valor: str):
    try:
        v = float(valor.replace(",", "."))
        emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        emb.set_image(url=BANNER_URL)
        emb.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        emb.add_field(name="Valor", value=f"R$ {formatar_real(v)}", inline=False)
        emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
        await ctx.send(embed=emb, view=ViewFilaPartida(f"f_{v}", v))
    except: await ctx.send("❌ Use: `.fila 10,00`")

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Cadastro de Pix"):
        n = TextInput(label="Nome Completo")
        c = TextInput(label="Chave Pix")
        q = TextInput(label="Link da Imagem do QR Code", placeholder="https://imgur.com/foto.png")
        async def on_submit(self, it):
            conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Seus dados foram salvos!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Dados", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM())
    await ctx.send("Clique abaixo para configurar seu Pix:", view=v)

@bot.event
async def on_ready():
    init_db(); print(f"✅ Bot {bot.user} online e pronto!")

bot.run(TOKEN)
            
