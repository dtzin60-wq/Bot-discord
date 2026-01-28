import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os
import asyncio

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

# ================= VIEWS AUXILIARES E PIX =================

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    @discord.ui.button(label="Dar vitória para jogador", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        await it.response.send_message("🏆 **Vitória confirmada!** Tópico encerrado.")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.gray)
    async def finalizar(self, it, btn):
        await it.response.send_message("🏁 **Aposta Finalizada.**")
        await self.thread.edit(locked=True, archived=True)

    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.red)
    async def wo(self, it, btn):
        await it.response.send_message("⚠️ **VITÓRIA POR W.O!**\nEncerrado por ausência.")
        await self.thread.edit(locked=True, archived=True)

class ViewPixMediador(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enviar meu Pix (Mediador)", style=discord.ButtonStyle.blurple, emoji="👮")
    async def enviar(self, it: discord.Interaction, button: Button):
        cargo_id = puxar_config("cargo_mediador_id")
        if not cargo_id or not any(r.id == int(cargo_id) for r in it.user.roles):
            return await it.response.send_message("❌ Apenas o mediador configurado pode usar este botão.", ephemeral=True)

        conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
        cursor.execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (it.user.id,))
        res = cursor.fetchone(); conn.close()
        
        if not res: 
            return await it.response.send_message("❌ Você não tem Pix cadastrado. Use `.pix`.", ephemeral=True)

        # Usamos defer para evitar erro se a limpeza de mensagens demorar
        await it.response.defer()
        await it.channel.purge(limit=5) 
        
        embed = discord.Embed(title="🏦 PAGAMENTO PARA O MEDIADOR", color=0x2ecc71)
        embed.add_field(name="👤 Nome:", value=res[0], inline=False)
        embed.add_field(name="🔑 Chave:", value=f"`{res[1]}`", inline=False)
        if res[2] and res[2].startswith("http"): 
            embed.set_image(url=res[2])
        embed.set_footer(text=f"Mediador Responsável: {it.user.display_name}")
        await it.channel.send(content="@everyone", embed=embed)

# ================= INTERAÇÃO DENTRO DO TÓPICO =================

class ViewConfirmarPartida(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def btn_confirmar(self, it: discord.Interaction, button: Button):
        dados = partidas_ativas.get(self.thread_id)
        if not dados or it.user not in dados["jogadores"]:
            return await it.response.send_message("❌ Você não é um dos jogadores desta partida.", ephemeral=True)
        
        if it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou a partida!")

        if len(set(dados["confirmados"])) >= 2:
            embed_ready = discord.Embed(title="💳 AGUARDANDO PAGAMENTO", color=0xf1c40f, description="Ambos confirmaram! Mediador, envie seu Pix agora.")
            await it.channel.send(embed=embed_ready, view=ViewPixMediador())

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def btn_recusar(self, it: discord.Interaction, button: Button):
        await it.response.send_message(f"❌ {it.user.mention} recusou a partida. Encerrando tópico...")
        await asyncio.sleep(2)
        await it.channel.edit(locked=True, archived=True)

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.gray, emoji="📝")
    async def btn_regras(self, it: discord.Interaction, button: Button):
        await it.response.send_message("📝 **REGRAS:** Usem este chat para definir os detalhes antes do pagamento.", ephemeral=True)

# ================= FILA E CRIAÇÃO DE TÓPICOS =================

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave, self.valor = chave, valor

    async def atualizar(self, message):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - `{m.title()}`" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="Valor da Partida", value=f"R$ {formatar_real(self.valor)}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    async def entrar(self, it: discord.Interaction, submodo):
        canal_id = puxar_config("canal_destino")
        if not canal_id: 
            return await it.response.send_message("❌ Canal de destino não configurado. Use `.canal`.", ephemeral=True)

        # Defer imediato para evitar erro de interação enquanto o código processa
        await it.response.defer(ephemeral=True)

        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(u.id == it.user.id for u, _ in filas_partida[self.chave]):
            return await it.followup.send("❌ Você já está nesta fila!", ephemeral=True)

        filas_partida[self.chave].append((it.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]

        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}

            # Lógica do Mediador da Fila
            mediador_link = fila_atendimento[0].mention if fila_atendimento else "*Ninguém na fila*"
            
            emb = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb.add_field(name="👮 Mediador:", value=mediador_link, inline=False)
            emb.add_field(name="👑 Modo:", value=f"1v1 | {submodo.title()}", inline=False)
            emb.add_field(name="⚡ Jogadores:", value=f"{p1.mention}\n{p2.mention}", inline=False)
            
            chamada = f"{p1.mention} {p2.mention}"
            if fila_atendimento: chamada += f" {fila_atendimento[0].mention}"
            
            await thread.send(content=chamada, embed=emb, view=ViewConfirmarPartida(thread.id))
            await it.followup.send(f"⚔️ Partida encontrada! Tópico: {thread.mention}", ephemeral=True)
            await self.atualizar(it.message)
        else:
            await it.followup.send("✅ Você entrou na fila!", ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def gelo_n(self, it, btn): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def gelo_i(self, it, btn): await self.entrar(it, "gelo infinito")

# ================= COMANDOS DE CONFIGURAÇÃO =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Qual cargo pode dar Aux?")
        async def s_aux(self, it, sel):
            salvar_config("cargo_aux_id", sel.values[0].id)
            await it.response.send_message(f"✅ Permissão de `.aux` para: {sel.values[0].mention}", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Qual cargo pode enviar Pix?")
        async def s_med(self, it, sel):
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message(f"✅ Permissão de Pix para: {sel.values[0].mention}", ephemeral=True)
    await ctx.send("⚙️ **Configuração de Permissões**", view=ConfigV())

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal para os tópicos...", channel_types=[discord.ChannelType.text])
        async def s(self, it, sel):
            salvar_config("canal_destino", sel.values[0].id)
            await it.response.send_message(f"✅ Tópicos serão criados em: {sel.values[0].mention}", ephemeral=True)
    await ctx.send("Selecione o canal de destino:", view=CV())

@bot.command()
async def aux(ctx):
    c_id = puxar_config("cargo_aux_id")
    if not c_id or not any(r.id == int(c_id) for r in ctx.author.roles):
        return await ctx.send("❌ Você não tem permissão de Auxiliar.")
    if not isinstance(ctx.channel, discord.Thread):
        return await ctx.send("❌ Use este comando apenas dentro de um tópico de partida.")
    await ctx.send(embed=discord.Embed(title="🛠️ PAINEL DE CONTROLE", color=0x3498db), view=ViewAuxiliar(ctx.channel))

@bot.command()
@commands.has_permissions(administrator=True)
async def mediar(ctx):
    class ViewSuporte(View):
        async def atualizar_f(self, it):
            txt = "\n".join([m.mention for m in fila_atendimento]) if fila_atendimento else "Fila Vazia"
            emb = discord.Embed(title="🎧 FILA DE MEDIAÇÃO", description=f"Mediadores online para suporte:\n\n{txt}", color=0x2b2d31)
            await it.message.edit(embed=emb, view=self)
        @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user not in fila_atendimento: fila_atendimento.append(it.user)
            await it.response.defer(); await self.atualizar_f(it)
        @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red)
        async def s(self, it, b):
            if it.user in fila_atendimento: fila_atendimento.remove(it.user)
            await it.response.defer(); await self.atualizar_f(it)
    await ctx.send(embed=discord.Embed(title="🎧 FILA DE MEDIAÇÃO", description="Clique abaixo para gerenciar sua presença na fila."), view=ViewSuporte())

@bot.command()
@commands.has_permissions(administrator=True)
async def fila(ctx, valor: str):
    try:
        val = float(valor.replace(",", "."))
        emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        emb.set_image(url=BANNER_URL)
        emb.add_field(name="Valor da Partida", value=f"R$ {formatar_real(val)}", inline=False)
        emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
        await ctx.send(embed=emb, view=ViewFilaPartida(f"f_{val}", val))
    except: await ctx.send("❌ Use: `.fila 10,00`")

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Cadastro de Pix"):
        n = TextInput(label="Nome do Titular")
        c = TextInput(label="Chave Pix")
        q = TextInput(label="Link do QR Code (Imagem)", placeholder="https://i.imgur.com/foto.png")
        async def on_submit(self, it):
            conn = sqlite3.connect("dados.db"); cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Seus dados de Pix foram salvos!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar Meus Dados", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM())
    await ctx.send("Configure como você receberá os pagamentos:", view=v)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ Bot {bot.user} conectado com sucesso!")

bot.run(TOKEN)
        
