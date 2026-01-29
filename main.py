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

fila_mediadores = [] # Escala de mediadores ativos

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

def tem_permissao(member, chave_config):
    role_id = puxar_config(chave_config)
    if not role_id: return member.guild_permissions.administrator
    role = member.guild.get_role(int(role_id))
    return role in member.roles or member.guild_permissions.administrator

# ================= MODAIS DE IDENTIDADE =================

class ModalMudarNome(Modal, title="Nome do Bot"):
    n = TextInput(label="Qual o novo nome?", min_length=3, max_length=32)
    async def on_submit(self, it):
        await bot.user.edit(username=self.n.value)
        await it.response.send_message("✅ Nome alterado!", ephemeral=True)

class ModalMudarFoto(Modal, title="Foto do Bot"):
    u = TextInput(label="Link da Imagem")
    async def on_submit(self, it):
        async with aiohttp.ClientSession() as s:
            async with s.get(self.u.value) as r:
                data = await r.read()
                await bot.user.edit(avatar=data)
        await it.response.send_message("✅ Foto alterada!", ephemeral=True)

# ================= COMANDO .BOTCONFIG =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo que usa comandos", row=0)
        async def s1(self, it, sel): salvar_config("cargo_comandos", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar .aux", row=1)
        async def s2(self, it, sel): salvar_config("cargo_aux", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem cadastra Pix", row=2)
        async def s3(self, it, sel): salvar_config("cargo_pix", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)

        @discord.ui.select(cls=RoleSelect, placeholder="Quem entra na fila mediador", row=3)
        async def s4(self, it, sel): salvar_config("cargo_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)

        @discord.ui.button(label="Mudar Nome", style=discord.ButtonStyle.secondary, row=4)
        async def b1(self, it, btn): await it.response.send_modal(ModalMudarNome())

        @discord.ui.button(label="Mudar Foto", style=discord.ButtonStyle.secondary, row=4)
        async def b2(self, it, btn): await it.response.send_modal(ModalMudarFoto())

    await ctx.send("⚙️ **Painel de Configurações WS**", view=ConfigV())

# ================= SISTEMA .AUX E FINALIZAÇÃO =================

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    async def finalizar(self, it, motivo):
        if not tem_permissao(it.user, "cargo_aux"):
            return await it.response.send_message("❌ Sem permissão.", ephemeral=True)

        dados = partidas_ativas.get(self.thread.id)
        if not dados: return await it.response.send_message("❌ Erro.", ephemeral=True)

        options = [discord.SelectOption(label=j.display_name, value=str(j.id)) for j in dados["jogadores"]]
        sel = Select(placeholder="Selecione o vencedor...", options=options)

        async def callback(interaction):
            v_id = int(sel.values[0])
            db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1 WHERE user_id = ?", (v_id,))
            await interaction.response.send_message(f"🏆 **{motivo}**\n1 coin adicionado para <@{v_id}>!\n*Removendo membros em 5s...*")
            
            await asyncio.sleep(5)
            # Remove jogadores e mediador do tópico
            for j in dados["jogadores"]: await self.thread.remove_user(j)
            med = await bot.fetch_user(dados["mediador_id"])
            await self.thread.remove_user(med)
            await self.thread.edit(locked=True, archived=True)

        sel.callback = callback
        v = View(); v.add_item(sel)
        await it.response.send_message("Escolha o vencedor:", view=v, ephemeral=True)

    @discord.ui.button(label="Escolher vencedor", style=discord.ButtonStyle.green)
    async def v1(self, it, b): await self.finalizar(it, "Vencedor Escolhido")
    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.blurple)
    async def v2(self, it, b): await self.finalizar(it, "Aposta Finalizada")
    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.danger)
    async def v3(self, it, b): await self.finalizar(it, "Vitória por W.O")

@bot.command()
async def aux(ctx):
    if not tem_permissao(ctx.author, "cargo_aux"): return
    await ctx.send("🛠️ **Painel Auxiliar**", view=ViewAuxiliar(ctx.channel))

# ================= FILA E CONFIRMAÇÃO =================

class ViewConfirmarPartida(View):
    def __init__(self, tid, mediador_id, msg_id):
        super().__init__(timeout=None)
        self.tid = tid; self.mediador_id = mediador_id; self.msg_id = msg_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        dados = partidas_ativas.get(self.tid)
        if it.user in dados["jogadores"] and it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=3)
            if len(set(dados["confirmados"])) >= 2:
                # Limpa mensagens e envia Pix
                try: m = await it.channel.fetch_message(self.msg_id); await m.delete()
                except: pass
                res = db_execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (self.mediador_id,))
                if res:
                    emb = discord.Embed(title="🏦 PAGAMENTO", color=0x2ecc71)
                    emb.add_field(name="Titular", value=res[0], inline=False)
                    emb.add_field(name="Chave", value=f"`{res[1]}`", inline=False)
                    if res[2]: emb.set_image(url=res[2])
                    await it.channel.send(content="@everyone", embed=emb)
        else: await it.response.send_message("❌ Inválido.", ephemeral=True)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def r(self, it, b): await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary)
    async def reg(self, it, b): await it.response.send_message("📝 Combinem as regras aqui!", ephemeral=True)

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor

    async def entrar(self, it, submodo):
        c_id = puxar_config("canal_destino")
        if not c_id or not fila_mediadores: return await it.response.send_message("❌ Sem mediadores ou canal!", ephemeral=True)
        
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        filas_partida[self.chave].append((it.user, submodo))
        
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]
        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            canal = bot.get_channel(int(c_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}")
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": [], "mediador_id": med_id}
            
            emb = discord.Embed(title="Aguardando Confirmação", color=0x2ecc71)
            emb.add_field(name="🕹️ Modo", value=f"1v1-mobile | {submodo}", inline=False)
            emb.add_field(name="⚡ Jogadores", value=f"{p1.mention} vs {p2.mention}", inline=False)
            msg = await thread.send(content=f"{p1.mention} {p2.mention}", embed=emb)
            await msg.edit(view=ViewConfirmarPartida(thread.id, med_id, msg.id))
            await it.response.send_message("✅ Criado!", ephemeral=True)
        else: await it.response.send_message("✅ Na fila!", ephemeral=True)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.entrar(it, "gelo infinito")

# ================= COMANDOS GERAIS =================

@bot.command()
async def mediar(ctx):
    if not tem_permissao(ctx.author, "cargo_mediador"): return
    v = View(); b = Button(label="Entrar na Escala", style=discord.ButtonStyle.green)
    async def bc(it): 
        if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id); await it.response.send_message("✅", ephemeral=True)
    b.callback = bc; v.add_item(b)
    await ctx.send("👮 **Escala de Mediadores**", view=v)

@bot.command()
async def fila(ctx, v: str):
    val = float(v.replace(",", "."))
    emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
    emb.add_field(name="🕹️ Modo", value="`1v1-mobile`", inline=False)
    emb.add_field(name="Valor", value=f"R$ {val:.2f}", inline=False)
    await ctx.send(embed=emb, view=ViewFilaPartida(f"f_{val}", val))

@bot.command()
async def p(ctx, member: discord.Member = None):
    member = member or ctx.author
    res = db_execute("SELECT vitorias, derrotas, coins FROM stats WHERE user_id = ?", (member.id,))
    v, d, c = res if res else (0,0,0)
    emb = discord.Embed(title=f"📊 Perfil: {member.display_name}", color=0x2ecc71)
    emb.add_field(name="🏆 Ganhas", value=f"`{v}`"); emb.add_field(name="❌ Perdidas", value=f"`{d}`"); emb.add_field(name="💰 Coins", value=f"`{c}`")
    await ctx.send(embed=emb)

@bot.command()
async def pix(ctx):
    if not tem_permissao(ctx.author, "cargo_pix"): return
    class PM(Modal, title="Meu Pix"):
        n = TextInput(label="Nome"); c = TextInput(label="Chave"); q = TextInput(label="Link QR")
        async def on_submit(self, it):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            await it.response.send_message("✅ Pix salvo!", ephemeral=True)
    v = View(); b = Button(label="Cadastrar", style=discord.ButtonStyle.green)
    b.callback = lambda i: i.response.send_modal(PM()); v.add_item(b)
    await ctx.send("Configure seu Pix:", view=v)

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal das partidas")
        async def s(self, it, sel): salvar_config("canal_destino", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("Onde criar as partidas?", view=CV())

filas_partida = {}; partidas_ativas = {}
@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} ONLINE")

bot.run(TOKEN)
    
