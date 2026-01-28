import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import sqlite3
import os

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
NOME_CARGO_MEDIADOR = "Mediador" # Nome exato do cargo no seu servidor

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
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

filas = {}
partidas = {}

def formatar_real(valor):
    return f"{valor:.2f}".replace(".", ",")

# ================= VIEWS DE PAGAMENTO E CONFIRMAÇÃO =================

class ViewAguardandoMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar_pix_mediador(self, interaction: discord.Interaction, button: Button):
        # VERIFICAÇÃO DE CARGO
        cargo = discord.utils.get(interaction.guild.roles, name=NOME_CARGO_MEDIADOR)
        if cargo not in interaction.user.roles:
            return await interaction.response.send_message(f"❌ Apenas usuários com o cargo **{NOME_CARGO_MEDIADOR}** podem enviar o Pix.", ephemeral=True)

        pix = puxar_pix(interaction.user.id)
        if not pix:
            return await interaction.response.send_message("❌ Você é mediador, mas não cadastrou seu Pix com `.pix`!", ephemeral=True)

        await interaction.channel.purge(limit=10)
        embed_pix = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed_pix.add_field(name="👤 Nome da conta:", value=pix['nome'], inline=False)
        embed_pix.add_field(name="🔑 Chave Pix:", value=f"`{pix['chave']}`", inline=False)
        embed_pix.add_field(name="🖼️ QR code:", value=pix['qr'], inline=False)
        embed_pix.set_footer(text=f"Mediador responsável: {interaction.user.display_name}")
        await interaction.channel.send(content="@everyone", embed=embed_pix)

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
            return await interaction.response.send_message("⚠️ Você já confirmou!", ephemeral=True)

        dados["confirmados"].append(interaction.user)
        embed_status = discord.Embed(
            description=f"✅ | **Partida Confirmada**\n\n{interaction.user.mention} confirmou a aposta!\n↳ *O outro jogador precisa confirmar para continuar.*",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed_status)

        if len(dados["confirmados"]) == 2:
            embed_msg = discord.Embed(title="💳 AGUARDANDO MEDIADOR", color=0xf1c40f, description="Ambos confirmaram! Um mediador deve clicar abaixo para enviar o Pix.")
            await interaction.channel.send(embed=embed_msg, view=ViewAguardandoMediador())

# ================= SISTEMA DE FILA =================

class FilaView(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.valor = valor

    async def atualizar(self, message):
        fila = filas.get(self.chave, [])
        texto = "\n".join([f"{u.mention} - `{m.title()}`" for u, m in fila]) if fila else "Vazio"
        
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        embed.add_field(name="Valor da Partida", value=f"R$ {formatar_real(self.valor)}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=texto, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, interaction, subtipo):
        id_canal = puxar_canal()
        if not id_canal: return await interaction.response.send_message("❌ ADM, use `.canal` primeiro.", ephemeral=True)
        
        if self.chave not in filas: filas[self.chave] = []
        if any(u.id == interaction.user.id for u, _ in filas[self.chave]):
            return await interaction.response.send_message("❌ Você já está na fila!", ephemeral=True)

        filas[self.chave].append((interaction.user, subtipo))
        match = [i for i in filas[self.chave] if i[1] == subtipo]

        if len(match) >= 2:
            p1, p2 = match[0], match[1]
            filas[self.chave].remove(p1); filas[self.chave].remove(p2)
            
            canal = bot.get_channel(id_canal)
            thread = await canal.create_thread(name=f"⚔️-{p1[0].name}-vs-{p2[0].name}", type=discord.ChannelType.public_thread)
            partidas[thread.id] = {"jogadores": [p1[0], p2[0]], "confirmados": []}

            embed_ini = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            embed_ini.add_field(name="👑 Modo:", value=f"1v1 | {subtipo.title()}", inline=False)
            embed_ini.add_field(name="💎 Valor da aposta:", value=f"R$ {formatar_real(self.valor)}", inline=False)
            embed_ini.add_field(name="⚡ Jogadores:", value=f"{p1[0].mention}\n{p2[0].mention}", inline=False)
            embed_ini.set_thumbnail(url="https://emoji.discourse-static.com/twa/1f3ae.png")

            await thread.send(content=f"{p1[0].mention} {p2[0].mention}", embed=embed_ini, view=ViewConfirmacaoPartida(thread.id))
            await interaction.response.send_message(f"⚔️ Tópico criado: {thread.mention}", ephemeral=True)
            await self.atualizar(interaction.message)
        else:
            await interaction.response.defer()
            await self.atualizar(interaction.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, it, bu): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, it, bu): await self.entrar(it, "gelo infinito")

# ================= COMANDOS =================

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx, canal_selecionado: discord.TextChannel):
    salvar_canal(canal_selecionado.id)
    await ctx.send(f"✅ Canal de tópicos definido: {canal_selecionado.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, valor_txt: str):
    try:
        valor = float(valor_txt.replace(",", "."))
        chave = f"mobile_{valor}"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        embed.add_field(name="Valor da Partida", value=f"R$ {formatar_real(valor)}", inline=False)
        embed.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
        await ctx.send(embed=embed, view=FilaView(chave, valor))
    except: await ctx.send("❌ Use: `.fila 10,00`")

@bot.command()
async def pix(ctx):
    class PixModal(Modal, title="Cadastro Pix"):
        n = TextInput(label="Nome")
        c = TextInput(label="Chave")
        q = TextInput(label="QR Link (Opcional)", required=False)
        async def on_submit(self, interaction):
            salvar_pix(interaction.user.id, self.n.value, self.c.value, self.q.value or "Não informado")
            await interaction.response.send_message("✅ Seus dados foram salvos!", ephemeral=True)

    view = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green))
    view.children[0].callback = lambda i: i.response.send_modal(PixModal())
    await ctx.send("Clique para cadastrar seus dados de Pix (Mediadores):", view=view)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} online!")

bot.run(TOKEN)
        
