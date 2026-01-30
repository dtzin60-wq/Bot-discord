import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

# --- CONFIGURAÇÕES DO BOT ---
# O erro 401 indica que o TOKEN no Railway deve ser revisado
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Gestão de Filas e Estados
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================

def init_db():
    """Cria as tabelas caso não existam no SQLite."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS pix (
                user_id INTEGER PRIMARY KEY, 
                nome TEXT, 
                chave TEXT, 
                qrcode TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS config (
                chave TEXT PRIMARY KEY, 
                valor TEXT
            )
        """)
        con.commit()

def db_execute(query, params=()):
    """Executa inserções ou updates no banco."""
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    """Retorna um valor de configuração salvo."""
    with sqlite3.connect("dados_bot.db") as con:
        cursor = con.execute("SELECT valor FROM config WHERE chave=?", (chave,))
        res = cursor.fetchone()
        return res[0] if res else None

# ==============================================================================
#                        INTERFACE DE CONFIRMAÇÃO NO TÓPICO
# ==============================================================================

class ViewConfirmacaoFoto(View):
    """Controla os botões de Confirmar/Recusar dentro do tópico criado."""
    def __init__(self, p1_id, p2_id, med_id, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med = p1_id, p2_id, med_id
        self.valor, self.modo = valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_confirm_part")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: 
            return await interaction.response.send_message("❌ Apenas jogadores ativos podem confirmar.", ephemeral=True)
        
        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!", delete_after=3)
        
        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=50)
            
            with sqlite3.connect("dados_bot.db") as con:
                r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()
            
            # Taxa extra de R$ 0,10 aplicada no valor final
            try:
                v_calc = self.valor.replace('R$', '').replace(' ', '').replace(',', '.')
                v_final = f"{(float(v_calc) + 0.10):.2f}".replace('.', ',')
            except:
                v_final = self.valor
            
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_pix.add_field(name="👤 Titular", value=r[0] if r else "Pendente", inline=True)
            emb_pix.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Pendente", inline=True)
            emb_pix.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)
            
            if r and r[2]:
                emb_pix.set_image(url=r[2])
            
            await interaction.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_pix)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_refuse_part")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.p1, self.p2]: return
        await interaction.channel.send(f"❌ Partida cancelada por {interaction.user.mention}.")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Usem este chat para combinar as regras.", ephemeral=True)

# ==============================================================================
#                             CONFIGURAÇÃO PIX E MEDIADORES
# ==============================================================================

class ViewPix(View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="btn_config_pix")
    async def cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = Modal(title="Configurar Chave PIX")
        nome = TextInput(label="Nome do Titular", placeholder="Nome completo")
        chave = TextInput(label="Chave PIX", placeholder="Sua chave")
        qr = TextInput(label="Link QR Code", required=False, placeholder="URL da imagem (opcional)")
        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)
        
        async def on_sub(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, nome.value, chave.value, qr.value))
            await it.response.send_message("✅ Chave PIX salva!", ephemeral=True)
        modal.on_submit = on_sub; await interaction.response.send_modal(modal)

class ViewMediar(View):
    def __init__(self): super().__init__(timeout=None)
    
    def gerar_embed(self):
        desc = "Fila vazia." if not fila_mediadores else "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        emb = discord.Embed(title="Painel da fila controladora", description=f"__**Entre na fila para começar a mediar**__\n\n{desc}", color=0x2b2d31)
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="btn_med_in")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id); await interaction.response.edit_message(embed=self.gerar_embed())
        else: await interaction.response.send_message("⚠️ Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="btn_med_out")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id); await interaction.response.edit_message(embed=self.gerar_embed())
        else: await interaction.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

# ==============================================================================
#                          FILA DE APOSTAS E TÓPICOS
# ==============================================================================

class ViewFila(View):
    """Gerencia jogadores na fila de apostas e cria o tópico."""
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def g_normal(self, it, b): await self.processar_fila(it, "Gelo Normal")
    
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def g_infinito(self, it, b): await self.processar_fila(it, "Gelo Infinito")

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪")
    async def sair_fila(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Remove o jogador caso ele queira sair antes da partida formar
        for j in self.jogadores:
            if j['id'] == interaction.user.id:
                self.jogadores.remove(j)
                return await interaction.response.send_message("✅ Você saiu da fila de apostas.", ephemeral=True)
        await interaction.response.send_message("⚠️ Você não está na fila.", ephemeral=True)

    async def processar_fila(self, interaction, tipo_gelo):
        if any(j['id'] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("⚠️ Você já está na fila!", ephemeral=True)
        
        self.jogadores.append({'id': interaction.user.id, 'mention': interaction.user.mention, 'gelo': tipo_gelo})
        
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []
                return await interaction.response.send_message("❌ Nenhum mediador na fila.", ephemeral=True)
            
            # Rotação de Mediadores (quem atende vai para o fim)
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) 
            
            c_id = pegar_config("canal_th")
            canal = bot.get_channel(int(c_id)) if c_id else interaction.channel
            thread = await canal.create_thread(name=f"Aposta-R${self.valor}", type=discord.ChannelType.public_thread)
            
            # --- EMBEDS DO TÓPICO ---
            emb1 = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb1.set_thumbnail(url=FOTO_BONECA)
            emb1.add_field(name="👑 Modo:", value=f"```\n{self.modo}\n```", inline=False)
            
            # Jogadores debaixo do modo com indicação do gelo
            j1, j2 = self.jogadores[0], self.jogadores[1]
            emb1.add_field(name="⚡ Jogadores:", value=f"{j1['mention']} - `{j1['gelo']}`\n{j2['mention']} - `{j2['gelo']}`", inline=False)
            
            emb1.add_field(name="💸 Valor da aposta:", value=f"```\nR$ {self.valor}\n```", inline=False)
            
            # Mediador identificado pelo nome do Discord
            u_med = bot.get_user(med_id)
            tag_med = f"@{u_med.name}" if u_med else f"ID: {med_id}"
            emb1.add_field(name="👮 Mediador:", value=f"```\n{tag_med}\n```", inline=False)
            
            emb2 = discord.Embed(title="✨ SEJAM MUITO BEM-VINDOS ✨", color=0x0000FF)
            emb2.description = "• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra combinada não existir no regulamento oficial da organização, tire print do acordo."
            
            partidas_ativas[thread.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            
            # Marca o mediador e jogadores na chamada
            await thread.send(content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}", embeds=[emb1, emb2], view=ViewConfirmacaoFoto(j1['id'], j2['id'], med_id, self.valor, self.modo))
            self.jogadores = []
            await interaction.response.send_message(f"✅ Partida criada: {thread.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ Você entrou na fila de `{tipo_gelo}`!", ephemeral=True)

# ==============================================================================
#                               COMANDOS E EVENTOS
# ==============================================================================

@bot.command()
async def Pix(ctx):
    await ctx.send(embed=discord.Embed(title="Painel PIX", color=0x2b2d31), view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo: str, valor: str):
    emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
    emb.add_field(name="💰 Valor", value=f"R$ {valor}", inline=True)
    emb.add_field(name="🏆 Modo", value=modo, inline=True)
    emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=ViewFila(modo, valor))

@bot.command()
async def canal(ctx):
    v = View(); sel = ChannelSelect(); v.add_item(sel)
    async def cb(i):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await i.response.send_message(f"✅ Canal de tópicos definido!", ephemeral=True)
    sel.callback = cb; await ctx.send("Escolha o canal para as partidas:", view=v)

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete(); await message.channel.send("✅ ID Salvo! Envie a Senha.", delete_after=2)
            else:
                senha = message.content; id_s = temp_dados_sala.pop(message.channel.id); await message.delete()
                emb = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                emb.description = f"**ID:** `{id_s}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                emb.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db(); bot.add_view(ViewPix()); bot.add_view(ViewMediar())
    print(f"✅ Bot Online como {bot.user.name}")

if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO: TOKEN não encontrado no ambiente.")
                 
