import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect
import sqlite3
import os

# ================= CONFIGURAÇÕES INICIAIS =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

# ================= SISTEMA DE BANCO DE DADOS =================
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

def puxar_pix(user_id):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return {"nome": res[0], "chave": res[1], "qr": res[2]} if res else None

# Variáveis globais de controle
filas = {}
partidas = {}

def formatar_real(valor):
    return f"{valor:.2f}".replace(".", ",")

# ================= PAINEL DE GERENCIAMENTO =================

class ViewGerenciarCargo(View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.select(cls=RoleSelect, placeholder="Selecione o cargo de Mediador...")
    async def select_role(self, interaction: discord.Interaction, select: RoleSelect):
        role = select.values[0]
        salvar_config("cargo_mediador_id", role.id)
        await interaction.response.send_message(f"✅ Cargo {role.mention} definido como Mediador!", ephemeral=True)

class PainelPrincipal(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Gerenciar cargo mediador", style=discord.ButtonStyle.gray, emoji="⚙️")
    async def btn_gerenciar(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
        await interaction.response.send_message("Selecione o cargo abaixo:", view=ViewGerenciarCargo(), ephemeral=True)

# ================= LÓGICA DO PIX DO MEDIADOR =================

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar_pix(self, interaction: discord.Interaction, button: Button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(role.id == int(cargo_id) for role in interaction.user.roles):
            return await interaction.response.send_message("❌ Você não tem o cargo de mediador configurado.", ephemeral=True)

        dados_pix = puxar_pix(interaction.user.id)
        if not dados_pix:
            return await interaction.response.send_message("❌ Cadastre seu pix primeiro com `.pix`.", ephemeral=True)

        await interaction.channel.purge(limit=5)
        embed = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed.add_field(name="👤 Nome da conta:", value=dados_pix['nome'], inline=False)
        embed.add_field(name="🔑 Chave Pix:", value=f"`{dados_pix['chave']}`", inline=False)
        embed.add_field(name="🖼️ QR code:", value=dados_pix['qr'], inline=False)
        embed.set_footer(text=f"Mediador: {interaction.user.display_name}")
        await interaction.channel.send(content="@everyone", embed=embed)

# ================= CONFIRMAÇÃO DA PARTIDA =================

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, interaction: discord.Interaction, button: Button):
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
            embed_ready = discord.Embed(title="💳 AGUARDANDO MEDIADOR", color=0xf1c40f, description="Os dois confirmaram. Um mediador deve enviar o Pix.")
            await interaction.channel.send(embed=embed_ready, view=ViewPixMediador())

# ================= SISTEMA DE FILA =================

class ViewFila(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.valor = valor

    async def msg_fila(self, message):
        lista = filas.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - `{m.title()}`" for u, m in lista]) if lista else "Vazio"
        
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        embed.add_field(name="Valor da Partida", value=f"R$ {formatar_real(self.valor)}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    async def processar_entrada(self, interaction, submodo):
        canal_id = puxar_config("canal_destino")
        if not canal_id: return await interaction.response.send_message("❌ Defina o canal com `.canal`.", ephemeral=True)

        if self.chave not in filas: filas[self.chave] = []
        if any(u.id == interaction.user.id for u, _ in filas[self.chave]):
            return await interaction.response.send_message("❌ Você já está na fila!", ephemeral=True)

        filas[self.chave].append((interaction.user, submodo))
        match = [i for i in filas[self.chave] if i[1] == submodo]

        if len(match) >= 2:
            p1, p2 = match[0], match[1]
            filas[self.chave].remove(p1); filas[self.chave].remove(p2)
            
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1[0].name}-vs-{p2[0].name}", type=discord.ChannelType.public_thread)
            partidas[thread.id] = {"jogadores": [p1[0], p2[0]], "confirmados": []}

            emb = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb.add_field(name="👑 Modo:", value=f"1v1 | {submodo.title()}", inline=False)
            emb.add_field(name="💎 Valor da aposta:", value=f"R$ {formatar_real(self.valor)}", inline=False)
            emb.add_field(name="⚡ Jogadores:", value=f"{p1[0].mention}\n{p2[0].mention}", inline=False)
            emb.set_thumbnail(url="https://emoji.discourse-static.com/twa/1f3ae.png")

            await thread.send(content=f"{p1[0].mention} {p2[0].mention}", embed=emb, view=ViewConfirmarPartida(thread.id))
            await interaction.response.send_message(f"⚔️ Partida: {thread.mention}", ephemeral=True)
            await self.msg_fila(interaction.message)
        else:
            await interaction.response.defer()
            await self.msg_fila(interaction.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_n(self, it, btn): await self.processar_entrada(it, "gelo normal")
    
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_i(self, it, btn): await self.processar_entrada(it, "gelo infinito")

# ================= COMANDOS =================

@bot.command()
@commands.has_permissions(administrator=True)
async def painel(ctx):
    emb = discord.Embed(title="⚙️ Painel de Controle", color=0x2b2d31, description="Gerencie as configurações do bot abaixo.")
    await ctx.send(embed=emb, view=PainelPrincipal())

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx, canal: discord.TextChannel):
    salvar_config("canal_destino", canal.id)
    await ctx.send(f"✅ Canal de tópicos: {canal.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, valor_txt: str):
    try:
        val = float(valor_txt.replace(",", "."))
        chave = f"mob_{val}"
        emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        emb.set_image(url=BANNER_URL)
        emb.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        emb.add_field(name="Valor da Partida", value=f"R$ {formatar_real(val)}", inline=False)
        emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
        await ctx.send(embed=emb, view=ViewFila(chave, val))
    except: await ctx.send("❌ Use: `.fila 10,00`")

@bot.command()
async def pix(ctx):
    class PixModal(Modal, title="Dados do Pix"):
        n = TextInput(label="Nome Completo")
        c = TextInput(label="Chave Pix")
        q = TextInput(label="Link do QR (Opcional)", required=False)
        async def on_submit(self, interaction):
            salvar_pix_db(interaction.user.id, self.n.value, self.c.value, self.q.value)
            await interaction.response.send_message("✅ Pix salvo!", ephemeral=True)
    
    def salvar_pix_db(uid, n, c, q):
        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (uid, n, c, q or "N/A"))
        conn.commit(); conn.close()

    btn = Button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    btn.callback = lambda i: i.response.send_modal(PixModal())
    await ctx.send("Clique para configurar seu Pix:", view=View().add_item(btn))

@bot.event
async def on_ready():
    init_db()
    print(f"✅ Logado como {bot.user}")

bot.run(TOKEN)
    
