import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio

# --- CONFIGURAÇÕES DE AMBIENTE ---
# Certifique-se de configurar a variável 'TOKEN' no Railway para evitar o erro 401 Unauthorized
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# --- MEMÓRIA EM TEMPO DE EXECUÇÃO ---
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ================= BANCO DE DADOS (SQLite) =================
def init_db():
    con = sqlite3.connect("dados_bot.db")
    cursor = con.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit()
    con.close()

def db_execute(query, params=()):
    con = sqlite3.connect("dados_bot.db")
    con.execute(query, params)
    con.commit()
    con.close()

def pegar_config(chave):
    con = sqlite3.connect("dados_bot.db")
    res = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    con.close()
    return res[0] if res else None

# ================= PAINEL DE CONFIRMAÇÃO (DESIGN DA FOTO) =================
class ViewConfirmacaoFoto(View):
    def __init__(self, p1_id, p2_id, med_id, valor, modo):
        super().__init__(timeout=None)
        self.p1 = p1_id
        self.p2 = p2_id
        self.med = med_id
        self.valor = valor
        self.modo = modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]:
            return await interaction.response.send_message("Você não é um dos jogadores desta partida.", ephemeral=True)
        
        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou a partida!", delete_after=3)
        
        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=20)
            
            # Recupera dados PIX do mediador
            con = sqlite3.connect("dados_bot.db")
            dados_pix = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()
            con.close()
            
            # Lógica da Taxa de R$ 0,10
            try:
                valor_base = float(self.valor.replace(',', '.'))
                valor_final = f"{(valor_base + 0.10):.2f}".replace('.', ',')
            except ValueError:
                valor_final = self.valor

            embed_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            embed_pix.add_field(name="👤 Titular", value=dados_pix[0] if dados_pix else "Não cadastrado", inline=True)
            embed_pix.add_field(name="💠 Chave Pix", value=f"`{dados_pix[1]}`" if dados_pix else "Não cadastrada", inline=True)
            embed_pix.add_field(name="💰 Valor (Total + Taxa)", value=f"R$ {valor_final}", inline=False)
            
            if dados_pix and dados_pix[2]:
                embed_pix.set_image(url=dados_pix[2])
            
            await interaction.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=embed_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_recusar")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]:
            return await interaction.response.send_message("Apenas jogadores podem cancelar.", ephemeral=True)
        
        await interaction.channel.send(f"❌ A partida foi recusada por {interaction.user.mention}. O tópico será deletado em 5 segundos.")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️", custom_id="btn_regras")
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Utilizem este espaço para alinhar as regras antes do início.", ephemeral=True)

# ================= COMANDO .Pix (VISUAL ORIGINAL) =================
class ModalPix(Modal, title="Configuração de Recebimento"):
    nome = TextInput(label="Nome do Titular", placeholder="Digite o nome completo")
    chave = TextInput(label="Chave PIX", placeholder="CPF, Celular, E-mail ou Aleatória")
    qrcode = TextInput(label="Link da Imagem do QR Code", placeholder="Opcional: URL da imagem", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode) VALUES (?, ?, ?, ?)",
                   (interaction.user.id, self.nome.value, self.chave.value, self.qrcode.value))
        await interaction.response.send_message("✅ Seus dados PIX foram salvos com sucesso!", ephemeral=True)

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="pix_cadastrar")
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="pix_visualizar")
    async def visualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        con = sqlite3.connect("dados_bot.db")
        res = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (interaction.user.id,)).fetchone()
        con.close()
        
        if not res:
            return await interaction.response.send_message("❌ Você ainda não cadastrou uma chave PIX.", ephemeral=True)
        
        embed = discord.Embed(title="Sua Chave Cadastrada", color=0x2ecc71)
        embed.add_field(name="Titular", value=res[0])
        embed.add_field(name="Chave", value=res[1])
        if res[2]: embed.set_image(url=res[2])
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= COMANDO .mediar (VISUAL ORIGINAL) =================
class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    def gerar_embed(self):
        if not fila_mediadores:
            lista = "Não há mediadores na fila no momento."
        else:
            lista = "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        
        embed = discord.Embed(
            title="Painel da fila controladora",
            description=f"__**Entre na fila para começar a mediar**__\n\n{lista}",
            color=0x2b2d31
        )
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        return embed

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="fila_entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="fila_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("⚠️ Você não está na fila!", ephemeral=True)

# ================= SISTEMA DE FILA E TÓPICOS =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = []

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def gelo_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.adicionar_jogador(interaction, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def gelo_infinito(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.adicionar_jogador(interaction, "Gelo Infinito")

    async def adicionar_jogador(self, interaction, tipo_gel):
        if any(j['id'] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("Você já está nesta fila!", ephemeral=True)
        
        self.jogadores.append({
            'id': interaction.user.id,
            'mention': interaction.user.mention,
            'gelo': tipo_gel
        })
        
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []
                return await interaction.response.send_message("❌ Não há mediadores disponíveis. Fila resetada.", ephemeral=True)
            
            # Rotação de mediadores
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)
            
            canal_id = pegar_config("canal_th")
            canal = bot.get_channel(int(canal_id)) if canal_id else interaction.channel
            
            # Criação do Tópico (Thread)
            thread = await canal.create_thread(
                name=f"Partida R$ {self.valor}",
                type=discord.ChannelType.public_thread
            )
            
            # --- EMBED 1 (Aguardando Confirmações) ---
            emb1 = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb1.set_thumbnail(url=FOTO_BONECA)
            emb1.add_field(name="👑 Modo:", value=f"```\n{self.modo}\n```", inline=False)
            emb1.add_field(name="💸 Valor da aposta:", value=f"```\nR$ {self.valor}\n```", inline=False)
            
            # Nome do mediador buscado via bot
            user_med = bot.get_user(med_id)
            nome_med = f"@{user_med.name}" if user_med else f"ID: {med_id}"
            emb1.add_field(name="👮 Mediador:", value=f"```\n{nome_med}\n```", inline=False)
            
            # Jogadores e seus respectivos gelos
            p1, p2 = self.jogadores[0], self.jogadores[1]
            emb1.add_field(name="⚡ Jogadores:", value=f"{p1['mention']} - `{p1['gelo']}`\n{p2['mention']} - `{p2['gelo']}`", inline=False)
            
            # --- EMBED 2 (Regras/Boas-vindas) ---
            emb2 = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=0x0000FF)
            emb2.description = "• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra combinada não existir no regulamento oficial da organização, é obrigatório tirar print do acordo antes do início da partida."
            
            partidas_ativas[thread.id] = {
                'med': med_id,
                'p1': p1['id'],
                'p2': p2['id'],
                'modo': self.modo
            }
            
            await thread.send(embeds=[emb1, emb2], view=ViewConfirmacaoFoto(p1['id'], p2['id'], med_id, self.valor, self.modo))
            self.jogadores = []
            await interaction.response.send_message(f"✅ Partida criada: {thread.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Você entrou na fila como `{tipo_gel}`!", ephemeral=True)

# ================= COMANDOS DO BOT =================
@bot.command()
async def Pix(ctx):
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Configure sua chave para receber pagamentos.", color=0x2b2d31)
    await ctx.send(embed=embed, view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo: str, valor: str):
    embed = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    embed.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
    embed.add_field(name="🏆 Modo", value=modo, inline=True)
    embed.set_image(url=BANNER_URL)
    await ctx.send(embed=embed, view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    view = View()
    select = ChannelSelect(placeholder="Selecione o canal para os tópicos")
    
    async def select_callback(interaction):
        db_execute("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_th", str(select.values[0].id)))
        await interaction.response.send_message(f"✅ Canal de tópicos definido: {select.values[0].mention}", ephemeral=True)
    
    select.callback = select_callback
    view.add_item(select)
    await ctx.send("Configuração do Canal de Partidas:", view=view)

# ================= EVENTOS E LOGICA DE SALA =================
@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # Lógica de recebimento de ID e Senha dentro do tópico pelo mediador
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete()
                await message.channel.send("✅ **ID Salvo!** Agora envie a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados_sala.pop(message.channel.id)
                await message.delete()
                
                embed_sala = discord.Embed(title="🚀 DADOS DA SALA DISPONÍVEIS", color=0x2ecc71)
                embed_sala.description = f"**ID:** `{id_sala}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                embed_sala.set_image(url=BANNER_URL)
                
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=embed_sala)
    
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db()
    # Adiciona as views persistentes
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    print(f"✅ Sistema iniciado como {bot.user.name}")

if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO CRÍTICO: Variável 'TOKEN' não encontrada no ambiente.")
    
