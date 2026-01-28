import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import json
import os

# Configurações de Ambiente (Railway usa variáveis de ambiente)
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

# --- Banco de Dados em JSON ---
def carregar_pix():
    if os.path.exists("pix_db.json"):
        with open("pix_db.json", "r") as f:
            return json.load(f)
    return {}

def salvar_pix(dados):
    with open("pix_db.json", "w") as f:
        json.dump(dados, f, indent=4)

# Variáveis globais
filas = {}
pix_db = carregar_pix()
partidas = {}
CANAIS_TOPICO = []
canal_index = 0

# ================= PIX =================
class PixModal(Modal, title="Cadastrar Pix"):
    nome = TextInput(label="Nome")
    chave = TextInput(label="Chave Pix")
    qr = TextInput(label="Link QR Code", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        # Transforma o ID em string para o JSON aceitar
        pix_db[str(interaction.user.id)] = {
            "nome": self.nome.value,
            "chave": self.chave.value,
            "qr": self.qr.value or "Não informado"
        }
        salvar_pix(pix_db)
        await interaction.response.send_message("✅ Pix cadastrado e salvo!", ephemeral=True)

class PixView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(PixModal())

# ================= TÓPICO =================
class TopicoView(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if self.thread_id not in partidas:
            return await interaction.response.send_message("❌ Partida expirada.", ephemeral=True)

        dados = partidas[self.thread_id]
        if interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não está nesta partida.", ephemeral=True)

        if interaction.user in dados["confirmados"]:
            return await interaction.response.send_message("⚠️ Você já confirmou.", ephemeral=True)

        dados["confirmados"].append(interaction.user)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!")

        if len(dados["confirmados"]) == 2:
            j1, j2 = dados["jogadores"]
            p1 = pix_db.get(str(j1.id))
            p2 = pix_db.get(str(j2.id))

            embed = discord.Embed(title="💰 DADOS DE PAGAMENTO", color=0x2ecc71)
            for j, p in [(j1, p1), (j2, p2)]:
                val = f"**Nome:** {p['nome']}\n**Chave:** `{p['chave']}`\n**QR:** {p['qr']}" if p else "❌ Pix não cadastrado"
                embed.add_field(name=f"Pix de {j.display_name}", value=val, inline=False)
            
            await interaction.channel.send(embed=embed)

# ================= FILA =================
class FilaView(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave = chave
        self.valor = valor

    async def atualizar(self, interaction):
        fila = filas.get(self.chave, [])
        texto = "\n".join([f"{u.mention} - `{m}`" for u, m in fila]) if fila else "Nenhum"
        
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Valor", value=f"R$ {self.valor:.2f}".replace(".", ","), inline=False)
        embed.add_field(name="Jogadores na Fila", value=texto, inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    async def entrar(self, interaction, modo_escolhido):
        if self.chave not in filas: filas[self.chave] = []
        fila = filas[self.chave]

        if any(u.id == interaction.user.id for u, _ in fila):
            return await interaction.response.send_message("❌ Você já está na fila.", ephemeral=True)

        fila.append((interaction.user, modo_escolhido))
        
        # Match do mesmo modo
        match = [item for item in fila if item[1] == modo_escolhido]

        if len(match) >= 2:
            p1, p2 = match[0], match[1]
            filas[self.chave].remove(p1)
            filas[self.chave].remove(p2)
            
            await criar_topico(interaction.guild, p1[0], p2[0], modo_escolhido, self.valor)
            await interaction.response.send_message(f"⚔️ Match encontrado: {modo_escolhido}!", ephemeral=True)
            
            # Atualiza a mensagem original da fila
            texto = "\n".join([f"{u.mention} - `{m}`" for u, m in filas[self.chave]]) if filas[self.chave] else "Nenhum"
            embed = interaction.message.embeds[0]
            embed.set_field_at(1, name="Jogadores na Fila", value=texto, inline=False)
            await interaction.message.edit(embed=embed, view=self)
        else:
            await self.atualizar(interaction)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_infinito(self, interaction: discord.Interaction, button: Button):
        await self.entrar(interaction, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if self.chave in filas:
            filas[self.chave] = [x for x in filas[self.chave] if x[0].id != interaction.user.id]
        await self.atualizar(interaction)

# ================= CRIAR TÓPICO =================
async def criar_topico(guild, j1, j2, modo, valor):
    global canal_index
    if not CANAIS_TOPICO: return
    
    id_canal = CANAIS_TOPICO[canal_index]
    canal = bot.get_channel(id_canal)
    canal_index = (canal_index + 1) % len(CANAIS_TOPICO)

    thread = await canal.create_thread(name=f"⚔️-{valor}-{modo}")
    partidas[thread.id] = {"jogadores": [j1, j2], "confirmados": []}

    embed = discord.Embed(title="⚔️ PARTIDA INICIADA", color=0x3498db)
    embed.add_field(name="Modo", value=modo.upper(), inline=True)
    embed.add_field(name="Valor", value=f"R$ {valor:.2f}", inline=True)
    embed.add_field(name="Confronto", value=f"{j1.mention} VS {j2.mention}", inline=False)
    
    await thread.send(content=f"{j1.mention} {j2.mention}", embed=embed, view=TopicoView(thread.id))

# ================= COMANDOS =================
@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx, *canais: discord.TextChannel):
    global CANAIS_TOPICO
    CANAIS_TOPICO = [c.id for c in canais]
    await ctx.send(f"✅ Canais de tópicos configurados!")

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, modo: str, valor_txt: str):
    try:
        valor = float(valor_txt.replace(",", "."))
        chave = f"{modo}_{valor}"
        filas[chave] = []
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Modo", value=modo, inline=False)
        embed.add_field(name="Valor", value=f"R$ {valor:.2f}", inline=False)
        embed.add_field(name="Fila", value="Vazia", inline=False)
        await ctx.send(embed=embed, view=FilaView(chave, modo, valor))
    except:
        await ctx.send("Formato inválido. Use: `.fila 1v1 10.00`")

@bot.command()
async def pix(ctx):
    await ctx.send("Gerencie seu Pix abaixo:", view=PixView())

@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
                                                            
