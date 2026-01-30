import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging

# ==============================================================================
#                               CONFIGURAÇÕES GERAIS
# ==============================================================================

# Configuração de logs para monitoramento no Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

# O token deve estar configurado nas variáveis de ambiente do Railway
TOKEN = os.getenv("TOKEN")

# Links de Mídia
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

# Estados globais em memória
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================

def init_db():
    """Inicializa as tabelas de PIX e configurações."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            chave TEXT,
            qrcode TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    """Executa comandos SQL genéricos."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    """Recupera valor da tabela de configuração."""
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

# ==============================================================================
#                        VIEW DE CONFIRMAÇÃO NO TÓPICO
# ==============================================================================

class ViewConfirmacaoFoto(View):
    """Gerencia a confirmação dos jogadores e exibição do PIX do mediador."""
    def __init__(self, p1, p2, med, valor, modo):
        super().__init__(timeout=None)
        self.p1 = p1
        self.p2 = p2
        self.med = med
        self.valor = valor
        self.modo = modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_confirm_v6")
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.p1, self.p2]:
            return await interaction.response.send_message("❌ Só jogadores desta partida podem confirmar.", ephemeral=True)

        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!", delete_after=3)

        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=50)

            # Busca dados PIX do mediador escalado
            with sqlite3.connect("dados_bot.db") as con:
                r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()

            # Cálculo da Taxa automática de R$ 0,10
            try:
                v_limpo = self.valor.replace('R$', '').replace(',', '.').strip()
                v_final = f"{(float(v_limpo) + 0.10):.2f}".replace('.', ',')
            except:
                v_final = self.valor

            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb.add_field(name="👤 Titular", value=r[0] if r else "Pendente", inline=True)
            emb.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Pendente", inline=True)
            emb.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)

            if r and r[2]:
                emb.set_image(url=r[2])

            await interaction.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_recuse_v6")
    async def recusar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.p1, self.p2]: return
        await interaction.channel.send(f"❌ Partida cancelada por {interaction.user.mention}. Deletando canal...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it, b): 
        await it.response.send_message("Usem este chat para acertar as regras.", ephemeral=True)

# ==============================================================================
#                             VIEW CADASTRO PIX
# ==============================================================================

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="btn_pix_v6")
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Configuração de Recebimento")
        nome = TextInput(label="Nome do Titular", placeholder="Ex: Fulano de Tal")
        chave = TextInput(label="Chave Pix", placeholder="Sua chave aqui")
        qr = TextInput(label="Link QR Code (Opcional)", required=False)

        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)

        async def submit(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)",
                       (it.user.id, nome.value, chave.value, qr.value))
            await it.response.send_message("✅ Seus dados PIX foram salvos!", ephemeral=True)

        modal.on_submit = submit
        await interaction.response.send_modal(modal)

# ==============================================================================
#                        VIEW FILA DE MEDIADORES
# ==============================================================================

class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        if fila_mediadores:
            lista = "\n".join([f"**{i+1} •** <@{u}>" for i, u in enumerate(fila_mediadores)])
        else:
            lista = "Fila vazia."

        emb = discord.Embed(title="Painel da Fila Controladora", description=f"__Entre para mediar apostas__\n\n{lista}", color=0x2b2d31)
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="btn_med_in_v6")
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed(), view=self)
        else:
            await interaction.response.send_message("⚠️ Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴", custom_id="btn_med_out_v6")
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed(), view=self)
        else:
            await interaction.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

# ==============================================================================
#                          VIEW FILA DE APOSTAS
# ==============================================================================

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = []
        self.message = None

    def gerar_embed(self):
        """Layout da fila de apostas principal"""
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="🏆 Modo", value=self.modo, inline=True)

        if self.jogadores:
            lista = "\n".join([f"{j['mention']} - `{j['gelo']}`" for j in self.jogadores])
        else:
            lista = "Nenhum jogador na fila."

        emb.add_field(name="⚡ Jogadores", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def atualizar(self):
        await self.message.edit(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Gelo Normal", emoji="❄️", style=discord.ButtonStyle.secondary)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.adicionar(interaction, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", emoji="♾️", style=discord.ButtonStyle.secondary)
    async def gelo_inf(self, interaction: discord.Interaction, button: Button):
        await self.adicionar(interaction, "Gelo Infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="btn_sair_fila_v6")
    async def sair(self, interaction: discord.Interaction, button: Button):
        self.jogadores = [j for j in self.jogadores if j["id"] != interaction.user.id]
        await interaction.response.send_message("✅ Você saiu da fila.", ephemeral=True)
        await self.atualizar()

    async def adicionar(self, interaction, gelo):
        if any(j["id"] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

        self.jogadores.append({
            "id": interaction.user.id,
            "mention": interaction.user.mention,
            "gelo": gelo
        })

        await interaction.response.send_message(f"✅ Entrou como {gelo}.", ephemeral=True)
        await self.atualizar()

        if len(self.jogadores) == 2:
            j1, j2 = self.jogadores

            # Validação: só inicia se os mediadores estiverem disponíveis
            if not fila_mediadores:
                self.jogadores = []
                await self.atualizar()
                return await interaction.channel.send("❌ Sem mediadores online para processar a partida.", delete_after=5)

            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)

            canal_id = pegar_config("canal_th")
            canal = bot.get_channel(int(canal_id)) if canal_id else interaction.channel
            thread = await canal.create_thread(name=f"Partida-R${self.valor}", type=discord.ChannelType.public_thread)

            # --- CONSTRUÇÃO DO PAINEL DO TÓPICO ---
            emb_th = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_th.set_thumbnail(url=FOTO_BONECA)
            
            # 1. Modo
            emb_th.add_field(name="👑 Modo:", value=f"```\n{self.modo}\n```", inline=False)
            
            # 2. JOGADORES LOGO ABAIXO DO MODO
            emb_th.add_field(name="⚡ Jogadores:",
                          value=f"{j1['mention']} - `{j1['gelo']}`\n{j2['mention']} - `{j2['gelo']}`",
                          inline=False)
            
            # 3. Valor
            emb_th.add_field(name="💸 Valor da aposta:", value=f"```\nR$ {self.valor}\n```", inline=False)

            # 4. Mediador (Nome de Usuário real)
            u_med = bot.get_user(med_id)
            tag_med = f"@{u_med.name}" if u_med else f"ID: {med_id}"
            emb_th.add_field(name="👮 Mediador:", value=f"```\n{tag_med}\n```", inline=False)

            emb_welcome = discord.Embed(title="✨ SEJAM BEM-VINDOS ✨", color=0x0000FF)
            emb_welcome.description = "• Regras podem ser combinadas entre os participantes.\n• Tire print de acordos extras."

            # Chamada principal no tópico
            await thread.send(
                content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}",
                embeds=[emb_th, emb_welcome],
                view=ViewConfirmacaoFoto(j1["id"], j2["id"], med_id, self.valor, self.modo)
            )

            partidas_ativas[thread.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            self.jogadores = []
            await self.atualizar()

# ==============================================================================
#                               COMANDOS E EVENTOS
# ==============================================================================

@bot.command()
async def Pix(ctx):
    await ctx.send("⚙️ Configurar seus dados de recebimento:", view=ViewPix())

@bot.command()
async def mediar(ctx):
    v = ViewMediar()
    await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx, modo: str, valor: str):
    view = ViewFila(modo, valor)
    msg = await ctx.send(embed=view.gerar_embed(), view=view)
    view.message = msg

@bot.command()
async def canal(ctx):
    v = View()
    sel = ChannelSelect(placeholder="Selecione o canal para os tópicos")

    async def cb(interaction):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await interaction.response.send_message(f"✅ Canal de tópicos definido: {sel.values[0].mention}", ephemeral=True)

    sel.callback = cb
    v.add_item(sel)
    await ctx.send("Escolha onde as apostas serão abertas:", view=v)

@bot.event
async def on_message(message):
    """Gerencia o envio de ID e SENHA da sala pelo mediador."""
    if message.author.bot: return
    
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        # Se o mediador mandar apenas números (ID da sala)
        if message.author.id == dados['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete()
                await message.channel.send("✅ ID salvo! Mande agora a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_s = temp_dados_sala.pop(message.channel.id)
                await message.delete()
                
                emb = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                emb.description = f"**ID:** `{id_s}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db()
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    logger.info(f"✅ Bot Online como: {bot.user}")

if TOKEN:
    bot.run(TOKEN)
else:
    logger.error("❌ TOKEN não encontrado!")

# --- FINALIZAÇÃO DO CÓDIGO (LINHA 350+) ---
# O código acima foi reforçado para evitar erros de autenticação no Railway.
# O layout do tópico prioriza os jogadores logo abaixo do modo selecionado.
# A rotação de mediadores (pop/append) garante que o trabalho seja dividido entre a equipe.
                       
