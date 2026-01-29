import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3
import os
import asyncio
import aiohttp

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
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats 
                      (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, 
                       derrotas INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def db_execute(query, params=()):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = cursor.fetchone()
    conn.commit()
    conn.close()
    return res

def salvar_config(chave, valor):
    db_execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (chave, str(valor)))

def puxar_config(chave):
    res = db_execute("SELECT valor FROM config WHERE chave = ?", (chave,))
    return res[0] if res else None

# ================= MODAIS DE CONFIGURAÇÃO DO BOT =================

class ModalMudarNome(Modal, title="Mudar Nome do Bot"):
    nome = TextInput(label="Qual é o nome que você quer no bot?", placeholder="Ex: WS APOSTAS V2", min_length=3, max_length=32)
    async def on_submit(self, it: discord.Interaction):
        try:
            await bot.user.edit(username=self.nome.value)
            await it.response.send_message(f"✅ Nome do bot alterado para: **{self.nome.value}**", ephemeral=True)
        except Exception as e:
            await it.response.send_message(f"❌ Erro ao mudar nome: {e}", ephemeral=True)

class ModalMudarFoto(Modal, title="Mudar Foto do Bot"):
    url = TextInput(label="Qual foto você quer colocar no bot?", placeholder="Cole o link da imagem aqui (direto)")
    async def on_submit(self, it: discord.Interaction):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url.value) as resp:
                    if resp.status != 200:
                        return await it.response.send_message("❌ Não consegui baixar a imagem. Verifique o link.", ephemeral=True)
                    data = await resp.read()
                    await bot.user.edit(avatar=data)
            await it.response.send_message("✅ Foto do bot alterada com sucesso!", ephemeral=True)
        except Exception as e:
            await it.response.send_message(f"❌ Erro ao mudar foto: {e}", ephemeral=True)

# ================= COMANDO .BOTCONFIG ATUALIZADO =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        def __init__(self):
            super().__init__(timeout=None)
        
        # Seletores de Cargos
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo .aux", custom_id="cfg_aux")
        async def s1(self, it, sel): 
            salvar_config("cargo_aux_id", sel.values[0].id)
            await it.response.send_message("✅ Cargo Aux configurado!", ephemeral=True)
        
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Staff", custom_id="cfg_staff")
        async def s2(self, it, sel): 
            salvar_config("cargo_staff_id", sel.values[0].id)
            await it.response.send_message("✅ Cargo Staff configurado!", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Mediador (Pix)", custom_id="cfg_med")
        async def s3(self, it, sel): 
            salvar_config("cargo_mediador_id", sel.values[0].id)
            await it.response.send_message("✅ Cargo Mediador configurado!", ephemeral=True)

        # Botões de Identidade do Bot
        @discord.ui.button(label="Mudar Nome do Bot", style=discord.ButtonStyle.primary, emoji="📝", row=3)
        async def btn_nome(self, it, btn):
            await it.response.send_modal(ModalMudarNome())

        @discord.ui.button(label="Mudar Foto do Bot", style=discord.ButtonStyle.primary, emoji="🖼️", row=3)
        async def btn_foto(self, it, btn):
            await it.response.send_modal(ModalMudarFoto())

    embed = discord.Embed(title="⚙️ Painel de Configuração", description="Configure os cargos e a identidade do bot abaixo.", color=0x2ecc71)
    await ctx.send(embed=embed, view=ConfigV())

# ================= COMANDO PERFIL .P =================

@bot.command()
async def p(ctx, member: discord.Member = None):
    member = member or ctx.author
    res = db_execute("SELECT vitorias, derrotas, streak, coins FROM stats WHERE user_id = ?", (member.id,))
    v, d, s, c = res if res else (0, 0, 0, 0)

    embed = discord.Embed(title=f"📊 Perfil de {member.display_name}", color=0x2ecc71)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🏆 Quantas partidas ganhou", value=f"`{v}`", inline=True)
    embed.add_field(name="❌ Quantas partidas perdeu", value=f"`{d}`", inline=True)
    embed.add_field(name="🔥 Partidas consecutivas", value=f"`{s}`", inline=True)
    embed.add_field(name="💰 Coins", value=f"`{c}`", inline=True)
    embed.set_footer(text="WS APOSTAS")
    await ctx.send(embed=embed)

# ================= SISTEMA DE FILA =================

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor

    async def atualizar(self, message):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - `{m}`" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.set_image(url=BANNER_URL)
        embed.add_field(name="🕹️ Modo", value="`1v1-mobile`", inline=False)
        embed.add_field(name="Valor da Partida", value=f"R$ {self.valor:.2f}", inline=False)
        embed.add_field(name="Fila Atual", value=jogadores_str, inline=False)
        await message.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.entrar(it, "gelo infinito")
    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red)
    async def sair(self, it, b):
        lista = filas_partida.get(self.chave, [])
        filas_partida[self.chave] = [i for i in lista if i[0].id != it.user.id]
        await it.response.send_message("✅ Você saiu da fila.", ephemeral=True)
        await self.atualizar(it.message)

    async def entrar(self, it, submodo):
        c_id = puxar_config("canal_destino")
        if not c_id: return await it.response.send_message("❌ Canal não configurado.", ephemeral=True)
        await it.response.defer(ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(u.id == it.user.id for u, _ in filas_partida[self.chave]):
             return await it.followup.send("❌ Já estás na fila!", ephemeral=True)
        filas_partida[self.chave].append((it.user, submodo))
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]
        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            thread = await bot.get_channel(int(c_id)).create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}")
            partidas_ativas[thread.id] = {"jogadores": [p1, p2]}
            emb = discord.Embed(title="Aguardando Confirmação", color=0x2ecc71)
            emb.add_field(name="👑 Modo:", value=f"1v1-mobile | {submodo}", inline=False)
            await thread.send(content=f"{p1.mention} {p2.mention}", embed=emb, view=ViewConfirmarPartida(thread.id))
            await self.atualizar(it.message)
        else: await self.atualizar(it.message)

# ================= RESTANTE DO CÓDIGO (AUX / PIX / EVENTOS) =================

class ViewSelecionarVencedor(View):
    def __init__(self, jogadores, thread):
        super().__init__(timeout=60)
        self.jogadores = jogadores; self.thread = thread
        options = [discord.SelectOption(label=j.display_name, value=str(j.id), emoji="🏆") for j in jogadores]
        select = Select(placeholder="Escolha o vencedor...", options=options)
        select.callback = self.vencedor_callback
        self.add_item(select)

    async def vencedor_callback(self, it: discord.Interaction):
        v_id = int(it.data['values'][0])
        perdedor = [j for j in self.jogadores if j.id != v_id]
        db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1, streak = streak + 1 WHERE user_id = ?", (v_id,))
        if perdedor: db_execute("UPDATE stats SET derrotas = derrotas + 1, streak = 0 WHERE user_id = ?", (perdedor[0].id,))
        v_obj = await bot.fetch_user(v_id)
        await it.response.send_message(f"🏆 **VITÓRIA CONFIRMADA!**\n{v_obj.mention} venceu e ganhou **1 Coin**.")
        await asyncio.sleep(5); await self.thread.edit(locked=True, archived=True)

class ViewConfirmarPartida(View):
    def __init__(self, tid): super().__init__(timeout=None); self.tid = tid
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        await it.response.send_message(f"✅ {it.user.mention} confirmou!")
        if it.message.components[0].children[0].disabled == False:
             await it.channel.send("💳 Mediadores, podem enviar o Pix.", view=ViewPixMediador())

class ViewPixMediador(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Enviar meu Pix", style=discord.ButtonStyle.blurple)
    async def enviar(self, it, button):
        res = db_execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (it.user.id,))
        if not res: return await it.response.send_message("❌ Use `.pix`.", ephemeral=True)
        embed = discord.Embed(title="🏦 PAGAMENTO", color=0x2ecc71)
        embed.add_field(name="Titular", value=res[0]); embed.add_field(name="Chave", value=f"`{res[1]}`")
        if res[2]: embed.set_image(url=res[2])
        await it.channel.send(content="@everyone", embed=embed)

@bot.command()
async def fila(ctx, v: str):
    val = float(v.replace(",", "."))
    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
    embed.add_field(name="🕹️ Modo", value="`1v1-mobile`", inline=False)
    embed.add_field(name="Valor da Partida", value=f"R$ {val:.2f}", inline=False)
    embed.add_field(name="Fila Atual", value="Vazio", inline=False)
    await ctx.send(embed=embed, view=ViewFilaPartida(f"f_{val}", val))

@bot.command()
async def aux(ctx): await ctx.send(embed=discord.Embed(title="🛠️ PAINEL"), view=ViewAuxiliar(ctx.channel))

class ViewAuxiliar(View):
    def __init__(self, thread): super().__init__(timeout=None); self.thread = thread
    @discord.ui.button(label="🏆 Declarar Vitória", style=discord.ButtonStyle.green)
    async def v(self, it, b):
        dados = partidas_ativas.get(self.thread.id)
        if not dados: return await it.response.send_message("❌ Erro.", ephemeral=True)
        await it.response.send_message("Vencedor:", view=ViewSelecionarVencedor(dados["jogadores"], self.thread), ephemeral=True)

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Meu Pix"):
        n = TextInput(label="Nome"); c = TextInput(label="Chave"); q = TextInput(label="Link Foto QR")
        async def on_submit(self, it):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            await it.response.send_message("✅ Salvo!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM()); await ctx.send("Pix:", view=v)

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal tópicos")
        async def s(self, it, sel): salvar_config("canal_destino", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("Canal:", view=CV())

filas_partida = {}; partidas_ativas = {}
@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} ONLINE")

bot.run(TOKEN)
        
