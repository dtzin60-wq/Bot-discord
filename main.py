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

# ================= VIEWS DO TÓPICO (DENTRO DA PARTIDA) =================

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, interaction: discord.Interaction, button: Button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Apenas mediadores autorizados!", ephemeral=True)

        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (interaction.user.id,))
        res = cursor.fetchone(); conn.close()
        
        if not res: return await interaction.response.send_message("❌ Use `.pix` primeiro.", ephemeral=True)

        await interaction.channel.purge(limit=5)
        embed = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed.add_field(name="👤 Nome da conta:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave Pix:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"):
            embed.set_image(url=res[2]) # Exibe a foto do QR Code
        embed.set_footer(text=f"Mediador: {interaction.user.display_name}")
        await interaction.channel.send(content="@everyone", embed=embed)

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, interaction: discord.Interaction, button: Button):
        dados = partidas_ativas.get(self.thread_id)
        if not dados or interaction.user not in dados["jogadores"]:
            return await interaction.response.send_message("❌ Você não está nesta partida.", ephemeral=True)
        if interaction.user in dados["confirmados"]:
            return await interaction.response.send_message("⚠️ Já confirmou!", ephemeral=True)

        dados["confirmados"].append(interaction.user)
        embed_status = discord.Embed(description=f"✅ | **Partida Confirmada**\n\n{interaction.user.mention} confirmou!", color=0x00ff00)
        await interaction.response.send_message(embed=embed_status)

        if len(dados["confirmados"]) == 2:
            embed_ready = discord.Embed(title="💳 AGUARDANDO MEDIADOR", color=0xf1c40f, description="Ambos confirmaram! Clique abaixo para chamar um mediador disponível ou enviar o Pix.")
            
            view = ViewPixMediador()
            # Botão para chamar quem está na fila de atendimento
            btn_chamar = Button(label="Chamar Mediador da Fila", style=discord.ButtonStyle.gray, emoji="📢")
            async def chamar_callback(it: discord.Interaction):
                if not fila_atendimento: return await it.response.send_message("⚠️ Não há mediadores na fila de atendimento agora.", ephemeral=True)
                mentions = " ".join([m.mention for m in fila_atendimento])
                await it.channel.send(f"📢 **Chamando mediadores:** {mentions}\nUma nova partida precisa de mediação!")
                await it.response.send_message("Mediadores notificados!", ephemeral=True)
            
            btn_chamar.callback = chamar_callback
            view.add_item(btn_chamar)
            await interaction.channel.send(embed=embed_ready, view=view)

# ================= SISTEMA DE FILA 1V1 =================

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
        if not canal_id: return await interaction.response.send_message("❌ Configure o canal com `.canal`.", ephemeral=True)

        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(u.id == interaction.user.id for u, _ in filas_partida[self.chave]):
            return await interaction.response.send_message("❌ Já está na fila!", ephemeral=True)

        filas_partida[self.chave].append((interaction.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]

        if len(match) >= 2:
            p1, p2 = match[0], match[1]
            filas_partida[self.chave].remove(p1); filas_partida[self.chave].remove(p2)
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1[0].name}-vs-{p2[0].name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1[0], p2[0]], "confirmados": []}

            emb = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb.add_field(name="👮 Mediador:", value="*Aguardando mediador assumir...*", inline=False) # Mediador acima
            emb.add_field(name="👑 Modo:", value=f"1v1 | {submodo.title()}", inline=False)
            emb.add_field(name="💎 Valor:", value=f"R$ {formatar_real(self.valor)}", inline=False)
            emb.add_field(name="⚡ Jogadores:", value=f"{p1[0].mention}\n{p2[0].mention}", inline=False)
            emb.set_thumbnail(url="https://emoji.discourse-static.com/twa/1f3ae.png")

            await thread.send(content=f"{p1[0].mention} {p2[0].mention}", embed=emb, view=ViewConfirmarPartida(thread.id))
            await interaction.response.send_message(f"⚔️ Tópico: {thread.mention}", ephemeral=True)
            await self.atualizar(interaction.message)
        else:
            await interaction.response.defer(); await self.atualizar(interaction.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_n(self, it, btn): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_i(self, it, btn): await self.entrar(it, "gelo infinito")

# ================= COMANDOS E SUPORTE =================

@bot.command()
@commands.has_permissions(administrator=True)
async def mediar(ctx):
    class ViewSuporte(View):
        def __init__(self): super().__init__(timeout=None)
        async def atualizar_msg(self, it):
            txt = "\n".join([m.mention for m in fila_atendimento]) if fila_atendimento else "Ninguém na fila."
            emb = discord.Embed(title="🎧 SUPORTE", description=f"**Entre aqui e comece a ser atendido**\n\n**Fila atual:**\n{txt}", color=0x2b2d31)
            await it.message.edit(embed=emb, view=self)

        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green)
        async def entrar(self, it, btn):
            if it.user not in fila_atendimento: 
                fila_atendimento.append(it.user)
                await it.response.defer(); await self.atualizar_msg(it)
            else: await it.response.send_message("Já está na fila!", ephemeral=True)

        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
        async def sair(self, it, btn):
            if it.user in fila_atendimento: 
                fila_atendimento.remove(it.user)
                await it.response.defer(); await self.atualizar_msg(it)
            else: await it.response.send_message("Não está na fila!", ephemeral=True)

    emb = discord.Embed(title="🎧 SUPORTE", description="**Entre aqui e comece a ser atendido**\n\n**Fila atual:**\nVazio", color=0x2b2d31)
    await ctx.send(embed=emb, view=ViewSuporte())

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CanalV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Escolha o canal...", channel_types=[discord.ChannelType.text])
        async def s(self, it, sel):
            salvar_config("canal_destino", sel.values[0].id)
            await it.response.send_message(f"✅ Canal definido: {sel.values[0].mention}", ephemeral=True)
    await ctx.send("Selecione o canal:", view=CanalV())

@bot.command()
@commands.has_permissions(administrator=True)
async def painel(ctx):
    class PainelV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Selecione o cargo mediador...")
        async def s(self, it, sel):
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message(f"✅ Cargo {sel.values[0].mention} configurado!", ephemeral=True)
    await ctx.send("Gerenciar Mediadores:", view=PainelV())

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, valor_txt: str):
    try:
        val = float(valor_txt.replace(",", "."))
        emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        emb.set_image(url=BANNER_URL)
        emb.add_field(name="Modo", value="`1v1 MOBILE`", inline=False)
        emb.add_field(name="Valor da Partida", value=f"R$ {formatar_real(val)}", inline=False)
        emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
        await ctx.send(embed=emb, view=ViewFilaPartida(f"mob_{val}", val))
    except: await ctx.send("❌ Use: `.fila 10,00`")

@bot.command()
async def pix(ctx):
    class PModal(Modal, title="Cadastro Pix"):
        n = TextInput(label="Nome")
        c = TextInput(label="Chave")
        q = TextInput(label="Link do QR Code (Foto)", placeholder="https://link-da-imagem.jpg")
        async def on_submit(self, it):
            conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Pix e QR Code salvos!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Pix", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PModal())
    await ctx.send("Configure seu Pix e QR Code:", view=v)

@bot.event
async def on_ready():
    init_db(); print(f"✅ {bot.user} pronto!")

bot.run(TOKEN)
                                                           
