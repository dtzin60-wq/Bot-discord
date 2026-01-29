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

# Listas globais para o rodízio
fila_mediadores = [] # Lista de IDs de mediadores na espera

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

# ================= SISTEMA DE RODÍZIO DE MEDIADORES =================

class ViewFilaMediadores(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar_painel(self, it):
        embed = discord.Embed(title="👮 ESCALA DE MEDIAÇÃO", color=0x3498db)
        if fila_mediadores:
            nomes = []
            for idx, uid in enumerate(fila_mediadores):
                u = await bot.fetch_user(uid)
                prefixo = "➡️ **ATUAL:**" if idx == 0 else f"{idx+1}º:"
                nomes.append(f"{prefixo} {u.mention}")
            desc = "\n".join(nomes)
        else:
            desc = "Nenhum mediador na fila no momento."
        
        embed.description = f"**Entre na fila e seja atendido!**\n\n{desc}"
        embed.set_footer(text="O primeiro da lista será chamado para a próxima partida.")
        await it.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green, emoji="✅")
    async def entrar(self, it, btn):
        if it.user.id in fila_mediadores:
            return await it.response.send_message("❌ Você já está na fila!", ephemeral=True)
        fila_mediadores.append(it.user.id)
        await it.response.send_message("✅ Você entrou na escala de mediadores!", ephemeral=True)
        await self.atualizar_painel(it)

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.red, emoji="❌")
    async def sair(self, it, btn):
        if it.user.id not in fila_mediadores:
            return await it.response.send_message("❌ Você não está na fila!", ephemeral=True)
        fila_mediadores.remove(it.user.id)
        await it.response.send_message("✅ Você saiu da escala.", ephemeral=True)
        await self.atualizar_painel(it)

@bot.command()
@commands.has_permissions(administrator=True)
async def mediar(ctx):
    embed = discord.Embed(
        title="👮 ESCALA DE MEDIAÇÃO",
        description="**Entre na fila e seja atendido!**\n\nNenhum mediador na fila no momento.",
        color=0x3498db
    )
    await ctx.send(embed=embed, view=ViewFilaMediadores())

# ================= LÓGICA DE PARTIDA COM RODÍZIO =================

async def enviar_pix_automatico(channel, user_id):
    res = db_execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (user_id,))
    if res:
        embed = discord.Embed(title="🏦 PAGAMENTO PARA MEDIADOR", color=0x2ecc71)
        embed.add_field(name="Titular", value=res[0], inline=False)
        embed.add_field(name="Chave Pix", value=f"`{res[1]}`", inline=False)
        if res[2]: embed.set_image(url=res[2])
        await channel.send(content="@everyone", embed=embed)

class ViewConfirmarPartida(View):
    def __init__(self, tid, mediador_id):
        super().__init__(timeout=None)
        self.tid = tid
        self.mediador_id = mediador_id

    @discord.ui.button(label="Confirmar Partida", style=discord.ButtonStyle.green, emoji="⚔️")
    async def c(self, it, b):
        dados = partidas_ativas.get(self.tid)
        if it.user in dados["jogadores"] and it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!")
            
            if len(set(dados["confirmados"])) >= 2:
                # Chama o PIX do mediador que foi escalado
                await enviar_pix_automatico(it.channel, self.mediador_id)
                # Libera o painel auxiliar para o mediador
                med_obj = await bot.fetch_user(self.mediador_id)
                await it.channel.send(f"🛠️ Painel liberado para {med_obj.mention}", view=ViewAuxiliar(it.channel))
        else:
            await it.response.send_message("❌ Você não está nesta partida!", ephemeral=True)

# ================= FILA DE JOGADORES =================

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor

    async def entrar(self, it, submodo):
        c_id = puxar_config("canal_destino")
        if not c_id: return await it.response.send_message("❌ Canal não configurado.", ephemeral=True)
        if not fila_mediadores: return await it.response.send_message("❌ Não há mediadores disponíveis na escala no momento!", ephemeral=True)

        await it.response.defer(ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        filas_partida[self.chave].append((it.user, submodo))
        
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]
        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            
            # PEGA O MEDIADOR DA VEZ (O PRIMEIRO)
            mediador_atual = fila_mediadores.pop(0) # Tira o 1º da lista
            fila_mediadores.append(mediador_atual) # Joga ele pro FINAL da lista (Rodízio)

            canal = bot.get_channel(int(c_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}
            
            med_obj = await bot.fetch_user(mediador_atual)
            emb = discord.Embed(title="Aguardando Confirmação", color=0x2ecc71)
            emb.add_field(name="🕹️ Modo:", value=f"1v1-mobile | {submodo}", inline=False)
            emb.add_field(name="👮 Mediador Responsável:", value=med_obj.mention, inline=False)
            
            await thread.send(content=f"{p1.mention} {p2.mention} | {med_obj.mention}", embed=emb, view=ViewConfirmarPartida(thread.id, mediador_atual))
            await self.atualizar_painel_jogador(it.message)
        else:
            await self.atualizar_painel_jogador(it.message)

    async def atualizar_painel_jogador(self, msg):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - `{m}`" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
        embed.add_field(name="🕹️ Modo", value="`1v1-mobile`", inline=False)
        embed.add_field(name="Valor", value=f"R$ {self.valor:.2f}", inline=False)
        embed.add_field(name="Fila Atual", value=jogadores_str, inline=False)
        await msg.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.entrar(it, "gelo infinito")

# ================= RESTANTE (AUX / PERFIL / BOTCONFIG) =================

class ViewAuxiliar(View):
    def __init__(self, thread): super().__init__(timeout=None); self.thread = thread
    @discord.ui.button(label="🏆 Declarar Vitória", style=discord.ButtonStyle.green)
    async def v(self, it, b):
        dados = partidas_ativas.get(self.thread.id)
        if not dados: return await it.response.send_message("❌ Partida não encontrada.", ephemeral=True)
        
        options = [discord.SelectOption(label=j.display_name, value=str(j.id)) for j in dados["jogadores"]]
        select = Select(placeholder="Quem venceu?", options=options)
        
        async def sel_callback(interaction):
            v_id = int(select.values[0])
            perdedor = [j for j in dados["jogadores"] if j.id != v_id]
            db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1, streak = streak + 1 WHERE user_id = ?", (v_id,))
            if perdedor: db_execute("UPDATE stats SET derrotas = derrotas + 1, streak = 0 WHERE user_id = ?", (perdedor[0].id,))
            await interaction.response.send_message(f"🏆 Vitória confirmada para <@{v_id}>!")
            await asyncio.sleep(5); await self.thread.edit(locked=True, archived=True)
            
        select.callback = sel_callback
        v = View(); v.add_item(select)
        await it.response.send_message("Selecione:", view=v, ephemeral=True)

@bot.command()
async def p(ctx, member: discord.Member = None):
    member = member or ctx.author
    res = db_execute("SELECT vitorias, derrotas, streak, coins FROM stats WHERE user_id = ?", (member.id,))
    v, d, s, c = res if res else (0,0,0,0)
    embed = discord.Embed(title=f"📊 Perfil: {member.display_name}", color=0x2ecc71)
    embed.add_field(name="🏆 Ganhas", value=f"`{v}`"); embed.add_field(name="❌ Perdidas", value=f"`{d}`")
    embed.add_field(name="💰 Coins", value=f"`{c}`"); embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def fila(ctx, v: str):
    val = float(v.replace(",", "."))
    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
    embed.add_field(name="🕹️ Modo", value="`1v1-mobile`", inline=False)
    embed.add_field(name="Valor", value=f"R$ {val:.2f}", inline=False)
    embed.add_field(name="Fila Atual", value="Vazio", inline=False)
    await ctx.send(embed=embed, view=ViewFilaPartida(f"f_{val}", val))

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal tópicos")
        async def s(self, it, sel): salvar_config("canal_destino", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("Canal:", view=CV())

@bot.command()
async def pix(ctx):
    class PM(Modal, title="Meu Pix"):
        n = TextInput(label="Nome"); c = TextInput(label="Chave"); q = TextInput(label="Link Foto QR")
        async def on_submit(self, it):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (it.user.id, self.n.value, self.c.value, self.q.value))
            await it.response.send_message("✅ Pix salvo!", ephemeral=True)
    v = View().add_item(Button(label="Cadastrar", style=discord.ButtonStyle.green))
    v.children[0].callback = lambda i: i.response.send_modal(PM()); await ctx.send("Pix:", view=v)

filas_partida = {}; partidas_ativas = {}
@bot.event
async def on_ready(): init_db(); print(f"✅ WS APOSTAS ONLINE")

bot.run(TOKEN)
        
