import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging
import datetime

# ==============================================================================
#                               CONFIGURAÇÕES TÉCNICAS
# ==============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Estados Globais
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================

def init_db():
    """Inicializa as tabelas SQL e garante persistência de dados no Railway."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            chave TEXT,
            qrcode TEXT,
            partidas_feitas INTEGER DEFAULT 0
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    """Executa comandos no banco de dados com segurança."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    """Recupera configurações do banco de dados."""
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

def buscar_mediador(user_id):
    """Busca dados de pagamento e nome salvo do mediador."""
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (user_id,)).fetchone()

# ==============================================================================
#                        SISTEMA DE LOGS E AUDITORIA (NOVO)
# ==============================================================================

async def enviar_log_ws(titulo, descricao, cor=0x3498db):
    """Envia notificações de ações importantes para o canal de logs."""
    log_id = pegar_config("canal_logs")
    if log_id:
        canal = bot.get_channel(int(log_id))
        if canal:
            emb = discord.Embed(title=titulo, description=descricao, color=cor)
            emb.timestamp = datetime.datetime.now()
            emb.set_footer(text="WS Monitoramento")
            try: await canal.send(embed=emb)
            except: pass

# ==============================================================================
#                             COMANDO .Pix (PAINEL)
# ==============================================================================

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar Minha Chave", style=discord.ButtonStyle.green, emoji="💠", custom_id="pix_cad")
    async def cadastrar(self, it: discord.Interaction, b: Button):
        modal = Modal(title="Configuração de Recebimento WS")
        nome = TextInput(label="Nome do Titular", placeholder="Como aparece no seu banco")
        chave = TextInput(label="Chave Pix", placeholder="Sua chave principal")
        qr = TextInput(label="Link do QR Code (Opcional)", required=False)

        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)

        async def on_submit(interaction: discord.Interaction):
            db_execute(
                "INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode, partidas_feitas) VALUES (?,?,?,?, (SELECT partidas_feitas FROM pix WHERE user_id=?))",
                (interaction.user.id, nome.value, chave.value, qr.value, interaction.user.id)
            )
            await interaction.response.send_message(f"✅ Seus dados foram salvos como: **{nome.value}**", ephemeral=True)
            await enviar_log_ws("💠 Cadastro Pix", f"Mediador {interaction.user.mention} atualizou os dados.")

        modal.on_submit = on_submit
        await it.response.send_modal(modal)

    @discord.ui.button(label="Ver Minha Chave Pix", style=discord.ButtonStyle.secondary, emoji="🔍", custom_id="pix_ver")
    async def ver_chave(self, it: discord.Interaction, b: Button):
        r = buscar_mediador(it.user.id)
        if not r: return await it.response.send_message("❌ Você ainda não tem cadastro!", ephemeral=True)
        emb = discord.Embed(title="💠 Seus Dados Salvos", color=0x3498db)
        emb.add_field(name="👤 Titular", value=r[0]); emb.add_field(name="🔑 Chave", value=f"`{r[1]}`")
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

# ==============================================================================
#                             COMANDO .mediar (FILA)
# ==============================================================================

class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        lista = ""
        if fila_mediadores:
            for i, u_id in enumerate(fila_mediadores):
                r = buscar_mediador(u_id)
                nome = r[0] if r else "Mediador"
                lista += f"**{i+1} •** {nome} (<@{u_id}>)\n"
        else: lista = "*Nenhum mediador na fila.*"
        return discord.Embed(title="🛡️ Painel da Fila Controladora", description=lista, color=0x2b2d31)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="med_in")
    async def entrar(self, it: discord.Interaction, b: Button):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴", custom_id="med_out")
    async def sair(self, it: discord.Interaction, b: Button):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())

# ==============================================================================
#                        LÓGICA DE TÓPICOS E PARTIDAS
# ==============================================================================

class ViewConfirmacao(View):
    def __init__(self, p1, p2, med, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.valor, self.modo = p1, p2, med, valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="v16_c")
    async def confirmar(self, it: discord.Interaction, b: Button):
        if it.user.id not in [self.p1, self.p2]: return
        self.confirmados.add(it.user.id)
        await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=2)
        
        if len(self.confirmados) == 2:
            await it.channel.purge(limit=10)
            r = buscar_mediador(self.med)
            try:
                v_limpo = self.valor.replace('R$', '').replace(',', '.').strip()
                v_final = f"{(float(v_limpo) + 0.10):.2f}".replace('.', ',')
            except: v_final = self.valor

            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb.add_field(name="👤 Titular", value=f"**{r[0] if r else 'Pendente'}**")
            emb.add_field(name="💠 Chave Pix", value=f"`{r[1] if r else 'Pendente'}`")
            emb.add_field(name="💰 Valor Total", value=f"R$ {v_final}", inline=False)
            if r and r[2]: emb.set_image(url=r[2])
            await it.channel.send(content=f"🔔 <@{self.med}> | <@{self.p1}> <@{self.p2}>", embed=emb)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="v16_r")
    async def recusar(self, it: discord.Interaction, b: Button):
        if it.user.id in [self.p1, self.p2]:
            await enviar_log_ws("❌ Partida Recusada", f"Partida cancelada no tópico: {it.channel.mention}")
            await it.channel.delete()

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores, self.message = modo, valor, [], None

    def gerar_embed(self):
        emb = discord.Embed(color=0x3498DB)
        emb.set_author(name="🎮 FILA DE APOSTAS", icon_url=bot.user.display_avatar.url)
        emb.add_field(name="💰 **Valor**", value=self.valor, inline=False)
        emb.add_field(name="🏆 **Modo**", value=self.modo, inline=False)
        lista = "\n".join([f"👤 {j['mention']} - `{j['gelo']}`" for j in self.jogadores]) or "Vazia"
        emb.add_field(name="⚡ **Jogadores**", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    @discord.ui.button(label="Gelo Normal", emoji="❄️", style=discord.ButtonStyle.secondary)
    async def g_n(self, it, b): await self.add(it, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", emoji="♾️", style=discord.ButtonStyle.secondary)
    async def g_i(self, it, b): await self.add(it, "Gelo Infinito")

    async def add(self, it, gelo):
        if any(j["id"] == it.user.id for j in self.jogadores): return
        self.jogadores.append({"id": it.user.id, "mention": it.user.mention, "gelo": gelo})
        await it.response.send_message("✅ Na fila!", ephemeral=True)
        await self.message.edit(embed=self.gerar_embed())

        if len(self.jogadores) == 2:
            if not fila_mediadores: return await it.channel.send("❌ Sem mediadores!", delete_after=5)
            j1, j2 = self.jogadores; med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            c_id = pegar_config("canal_th")
            th = await bot.get_channel(int(c_id)).create_thread(name=f"Partida-R${self.valor}", type=discord.ChannelType.public_thread)
            
            emb_th = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_th.set_thumbnail(url=FOTO_BONECA)
            emb_th.add_field(name="👑 **Modo:**", value=self.modo, inline=False)
            emb_th.add_field(name="⚡ **Jogadores:**", value=f"{j1['mention']} - {j1['gelo']}\n{j2['mention']} - {j2['gelo']}", inline=False)
            emb_th.add_field(name="💸 **Valor da aposta:**", value=f"R$ {self.valor}", inline=False)
            
            r_med = buscar_mediador(med_id)
            nome_med = r_med[0] if r_med else "Mediador"
            emb_th.add_field(name="👮 **Mediador:**", value=f"{nome_med} (<@{med_id}>)", inline=False)

            await th.send(content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}", embed=emb_th, view=ViewConfirmacao(j1['id'], j2['id'], med_id, self.valor, self.modo))
            partidas_ativas[th.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            self.jogadores = []; await self.message.edit(embed=self.gerar_embed())

# ==============================================================================
#                               COMANDOS EXTRAS (GERENCIAMENTO)
# ==============================================================================

@bot.command()
async def logs(ctx):
    """Configura o canal onde os logs serão enviados."""
    if not ctx.author.guild_permissions.administrator: return
    db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_logs", str(ctx.channel.id)))
    await ctx.send(f"✅ Canal de logs definido para: {ctx.channel.mention}")

@bot.command()
async def limparfila(ctx):
    """Reseta a fila de mediadores manualmente."""
    if not ctx.author.guild_permissions.manage_messages: return
    global fila_mediadores
    fila_mediadores = []
    await ctx.send("🧹 Fila de mediadores resetada com sucesso!")
    await enviar_log_ws("🧹 Limpeza", f"Fila de mediadores limpa por {ctx.author.mention}")

@bot.command()
async def stats(ctx, usuario: discord.Member = None):
    """Mostra as estatísticas de um mediador."""
    usuario = usuario or ctx.author
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT nome, partidas_feitas FROM pix WHERE user_id=?", (usuario.id,)).fetchone()
    if r:
        await ctx.send(f"📊 **Mediador:** {r[0]}\n✅ **Partidas Mediadas:** `{r[1]}`")
    else:
        await ctx.send("❌ Esse usuário não possui cadastro no sistema.")

# ==============================================================================
#                               EVENTOS FINAIS
# ==============================================================================

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        d = partidas_ativas[message.channel.id]
        if message.author.id == d['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete(); await message.channel.send("✅ ID salvo!", delete_after=2)
            else:
                s = message.content; i = temp_dados_sala.pop(message.channel.id); await message.delete()
                e = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                e.description = f"**ID:** {i}\n**Senha:** {s}\n**Modo:** {d['modo']}"; e.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=e)
                await enviar_log_ws("🚀 Sala Criada", f"Dados enviados no tópico {message.channel.mention}")
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db(); bot.add_view(ViewPix()); bot.add_view(ViewMediar()); print(f"✅ WS Apostas v3.5 Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
                       
