import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import sqlite3
import os

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qr TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor INTEGER)')
    conn.commit()
    conn.close()

def salvar_pix(user_id, nome, chave, qr):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO pix VALUES (?, ?, ?, ?)", (user_id, nome, chave, qr))
    conn.commit()
    conn.close()

def puxar_pix(user_id):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return {"nome": res[0], "chave": res[1], "qr": res[2]} if res else None

def salvar_canal(id_canal):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config VALUES ('canal_destino', ?)", (id_canal,))
    conn.commit()
    conn.close()

def puxar_canal():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM config WHERE chave = 'canal_destino'")
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# Variáveis temporárias
filas = {}
partidas = {}

def formatar_real(valor):
    return f"{valor:.2f}".replace(".", ",")

# ================= SISTEMA DE PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome da Conta")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link do QR Code (Opcional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        salvar_pix(interaction.user.id, self.nome.value, self.chave.value, self.qr.value or "Não informado")
        await interaction.response.send_message("✅ Pix salvo!", ephemeral=True)

# ================= SISTEMA DE MEDIADOR =================
class AtendimentoView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirmar Atendimento", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar_atendimento(self, interaction: discord.Interaction, button: Button):
        pix = puxar_pix(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Mediador, cadastre seu Pix com `.pix`!", ephemeral=True)

        await interaction.channel.purge(limit=100)
        embed = discord.Embed(title="🏦 DADOS PARA PAGAMENTO (MEDIADOR)", color=0x2ecc71)
        embed.add_field(name="👤 Nome da conta do Pix do mediador:", value=pix['nome'], inline=False)
        embed.add_field(name="🔑 Chave Pix do mediador:", value=f"`{pix['chave']}`", inline=False)
        embed.add_field(name="🖼️ QR code do mediador:", value=pix['qr'], inline=False)
        await interaction.channel.send(embed=embed)

class MediadorView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Entre para ser atendido", style=discord.ButtonStyle.blurple, emoji="👮")
    async def entrar_mediador(self, interaction: discord.Interaction, button: Button):
        id_canal = puxar_canal()
        if not id_canal: return await interaction.response.send_message("❌ Configure o canal com `.canal`.", ephemeral=True)
        
        canal = bot.get_channel(id_canal)
        thread = await canal.create_thread(name=f"🆘-atendimento-{interaction.user.name}", type=discord.ChannelType.public_thread)
        
        embed = discord.Embed(title="🚀 NOVO ATENDIMENTO", color=0xe74c3c)
        embed.add_field(name="🎮 Modo", value="A definir", inline=True)
        embed.add_field(name="👮 Mediador", value="Aguardando...", inline=True)
        embed.add_field(name="💰 Valor", value="A definir", inline=True)
        embed.add_field(name="👥 Jogadores", value=f"{interaction.user.mention}", inline=False)
        
        await thread.send(content=f"{interaction.user.mention} | @here", embed=embed, view=AtendimentoView())
        await interaction.response.send_message(f"✅ Tópico aberto: {thread.mention}", ephemeral=True)

# ================= CONFIRMAÇÃO DE PARTIDA (ESTILO PRINT) =================
class ViewConfirmacaoPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas.get(self.thread_id)
        if not dados or interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não está nesta partida.", ephemeral=True)

        if interaction.user in dados["confirmados"]:
            return await interaction.response.send_message("⚠️ Você já confirmou.", ephemeral=True)

        dados["confirmados"].append(interaction.user)

        # MENSAGEM DO SEGUNDO PRINT
        embed_status = discord.Embed(
            description=f"✅ | **Partida Confirmada**\n\n{interaction.user.mention} confirmou a aposta!\n↳ *O outro jogador precisa confirmar para continuar.*",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed_status)

        if len(dados["confirmados"]) == 2:
            p1_u, p2_u = dados["jogadores"]
            pix1, pix2 = puxar_pix(p1_u.id), puxar_pix(p2_u.id)
            eb_pix = discord.Embed(title="💰 DADOS PARA PAGAMENTO", color=0x2ecc71)
            for u, p in zip([p1_u, p2_u], [pix1, pix2]):
                info = f"**Nome:** {p['nome']}\n**Chave:** `{p['chave']}`\n**QR:** {p['qr']}" if p else "❌ Pix não cadastrado."
                eb_pix.add_field(name=f"Pix de {u.name}", value=info, inline=False)
            await interaction.channel.send(embed=eb_pix)

# ================= SISTEMA DE FILA =================
class FilaView(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave, self.modo, self.valor = chave, modo, valor

    async def atualizar(self, message):
        fila = filas.get(self.chave, [])
        texto = "\n".join([f"{u.mention}" for u, m in fila]) if fila else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Valor", value=f"R$ {formatar_real(self.valor)}", inline=False)
        embed.add_field(name="Na Fila", value=texto, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, interaction, modo_escolhido):
        id_canal = puxar_canal()
        if not id_canal: return await interaction.response.send_message("❌ Configure o canal!", ephemeral=True)
        
        if self.chave not in filas: filas[self.chave] = []
        if any(u.id == interaction.user.id for u, _ in filas[self.chave]):
            return await interaction.response.send_message("❌ Já está na fila!", ephemeral=True)

        filas[self.chave].append((interaction.user, modo_escolhido))
        match = [i for i in filas[self.chave] if i[1] == modo_escolhido]

        if len(match) >= 2:
            p1, p2 = match[0], match[1]
            filas[self.chave].remove(p1); filas[self.chave].remove(p2)
            
            canal = bot.get_channel(id_canal)
            thread = await canal.create_thread(name=f"⚔️-{p1[0].name}-vs-{p2[0].name}", type=discord.ChannelType.public_thread)
            partidas[thread.id] = {"jogadores": [p1[0], p2[0]], "confirmados": []}

            # EMBED DO PRIMEIRO PRINT
            embed_ini = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            embed_ini.add_field(name="👑 Modo:", value=f"1v1 | {modo_escolhido.title()}", inline=False)
            embed_ini.add_field(name="💎 Valor da aposta:", value=f"R$ {formatar_real(self.valor)}", inline=False)
            embed_ini.add_field(name="⚡ Jogadores:", value=f"{p1[0].mention}\n{p2[0].mention}", inline=False)
            embed_ini.set_thumbnail(url="https://emoji.discourse-static.com/twa/1f3ae.png")

            await thread.send(content=f"{p1[0].mention} {p2[0].mention}", embed=embed_ini, view=ViewConfirmacaoPartida(thread.id))
            await thread.send("✨ **SEJAM MUITO BEM-VINDOS** ✨\n\n• Regras adicionais podem ser combinadas entre os participantes.")
            await interaction.response.send_message(f"⚔️ Match! Tópico: {thread.mention}", ephemeral=True)
            await self.atualizar(interaction.message)
        else:
            await interaction.response.defer(); await self.atualizar(interaction.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction, button): await self.entrar(interaction, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction, button): await self.entrar(interaction, "gelo infinito")

# ================= COMANDOS =================
@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx, canal_selecionado: discord.TextChannel):
    salvar_canal(canal_selecionado.id)
    await ctx.send(f"✅ Canal de tópicos salvo: {canal_selecionado.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, modo: str, valor_txt: str):
    try:
        valor = float(valor_txt.replace(",", "."))
        chave = f"{modo}_{valor}"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Valor", value=f"R$ {formatar_real(valor)}", inline=False)
        embed.add_field(name="Na Fila", value="Vazio", inline=False)
        await ctx.send(embed=embed, view=FilaView(chave, modo, valor))
    except: await ctx.send("❌ Use: `.fila [modo] 10,00`")

@bot.command()
@commands.has_permissions(administrator=True)
async def painel_mediador(ctx):
    embed = discord.Embed(title="⚠️ ENTRE PRA SER ATENDIDO", color=0xe74c3c)
    embed.set_image(url=BANNER_URL)
    await ctx.send(embed=embed, view=MediadorView())

@bot.command()
async def pix(ctx):
    view = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green, custom_id="reg_pix"))
    await ctx.send("Clique para cadastrar seus dados:", view=view)

@bot.event
async def on_interaction(interaction):
    if interaction.type == discord.InteractionType.component and interaction.data.get("custom_id") == "reg_pix":
        await interaction.response.send_modal(PixModal())

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} online!")

bot.run(TOKEN)
    
