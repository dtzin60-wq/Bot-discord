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

fila_mediadores = [] # Escala de mediadores

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

# ================= MODAIS DE CONFIGURAÇÃO =================

class ModalMudarNome(Modal, title="Mudar Nome do Bot"):
    nome = TextInput(label="Qual é o nome que você quer no bot?", min_length=3, max_length=32)
    async def on_submit(self, it: discord.Interaction):
        await bot.user.edit(username=self.nome.value)
        await it.response.send_message(f"✅ Nome alterado!", ephemeral=True)

class ModalMudarFoto(Modal, title="Mudar Foto do Bot"):
    url = TextInput(label="Qual foto você quer colocar no bot?")
    async def on_submit(self, it: discord.Interaction):
        async with aiohttp.ClientSession() as session:
            async with session.get(self.url.value) as resp:
                data = await resp.read()
                await bot.user.edit(avatar=data)
        await it.response.send_message("✅ Foto alterada!", ephemeral=True)

# ================= COMANDO .BOTCONFIG =================

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo .aux")
        async def s1(self, it, sel): 
            salvar_config("cargo_aux_id", sel.values[0].id)
            await it.response.send_message("✅ Cargo Aux definido!", ephemeral=True)
        
        @discord.ui.button(label="Mudar Nome", style=discord.ButtonStyle.primary, row=2)
        async def b1(self, it, btn): await it.response.send_modal(ModalMudarNome())
        
        @discord.ui.button(label="Mudar Foto", style=discord.ButtonStyle.primary, row=2)
        async def b2(self, it, btn): await it.response.send_modal(ModalMudarFoto())

    await ctx.send("⚙️ **Configurações do Bot**", view=ConfigV())

# ================= SISTEMA .AUX (VENCEDOR / W.O) =================

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None)
        self.thread = thread

    async def finalizar(self, it, titulo):
        dados = partidas_ativas.get(self.thread.id)
        if not dados: return await it.response.send_message("❌ Partida não encontrada.", ephemeral=True)
        
        options = [discord.SelectOption(label=j.display_name, value=str(j.id)) for j in dados["jogadores"]]
        select = Select(placeholder=f"Escolha quem venceu ({titulo})", options=options)
        
        async def callback(interaction):
            v_id = int(select.values[0])
            db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1 WHERE user_id = ?", (v_id,))
            await interaction.response.send_message(f"🏆 **{titulo}**\n1 coins adicionados para <@{v_id}>!")
            await asyncio.sleep(5)
            await self.thread.edit(locked=True, archived=True)
            
        select.callback = callback
        v = View(); v.add_item(select)
        await it.response.send_message("Selecione o jogador:", view=v, ephemeral=True)

    @discord.ui.button(label="Escolher vencedor", style=discord.ButtonStyle.green)
    async def v1(self, it, b): await self.finalizar(it, "Vencedor Escolhido")

    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.blurple)
    async def v2(self, it, b): await self.finalizar(it, "Aposta Finalizada")

    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.danger)
    async def v3(self, it, b): await self.finalizar(it, "Vitória por W.O")

@bot.command()
async def aux(ctx):
    await ctx.send("🛠️ **Painel de Controle de Aposta**", view=ViewAuxiliar(ctx.channel))

# ================= SISTEMA DE CONFIRMAÇÃO E PIX =================

class ViewConfirmarPartida(View):
    def __init__(self, tid, mediador_id, msg_ids_to_delete):
        super().__init__(timeout=None)
        self.tid = tid
        self.mediador_id = mediador_id
        self.msg_ids = msg_ids_to_delete # Lista de IDs para apagar

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        dados = partidas_ativas.get(self.tid)
        if it.user in dados["jogadores"] and it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=5)
            
            if len(set(dados["confirmados"])) >= 2:
                # APAGAR MENSAGENS DE CIMA
                for msg_id in self.msg_ids:
                    try:
                        m = await it.channel.fetch_message(msg_id)
                        await m.delete()
                    except: pass
                
                # ENVIAR PIX
                res = db_execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (self.mediador_id,))
                if res:
                    emb = discord.Embed(title="🏦 PAGAMENTO", color=0x2ecc71)
                    emb.add_field(name="Titular", value=res[0], inline=False)
                    emb.add_field(name="Chave", value=f"`{res[1]}`", inline=False)
                    if res[2]: emb.set_image(url=res[2])
                    await it.channel.send(content="@everyone", embed=emb)
        else:
            await it.response.send_message("❌ Ação inválida.", ephemeral=True)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def r(self, it, b):
        await it.response.send_message("❌ Aposta recusada. O tópico será fechado.")
        await asyncio.sleep(3); await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="📝")
    async def reg(self, it, b):
        await it.response.send_message("📝 Utilizem este chat para combinar as regras antes de iniciar.", ephemeral=True)

# ================= FILA E RODÍZIO =================

class ViewFilaPartida(View):
    def __init__(self, chave, valor):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.entrar(it, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.entrar(it, "gelo infinito")

    async def entrar(self, it, submodo):
        c_id = puxar_config("canal_destino")
        if not c_id: return await it.response.send_message("❌ Configure o canal!", ephemeral=True)
        if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores na escala!", ephemeral=True)

        if self.chave not in filas_partida: filas_partida[self.chave] = []
        filas_partida[self.chave].append((it.user, submodo))
        
        match = [i for i in filas_partida[self.chave] if i[1] == submodo]
        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            
            # Rodízio
            mediador_atual = fila_mediadores.pop(0)
            fila_mediadores.append(mediador_atual)

            canal = bot.get_channel(int(c_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}")
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": []}
            
            med_obj = await bot.fetch_user(mediador_atual)
            
            # Embed de Confirmação (IMAGEM 4 e 5)
            emb = discord.Embed(title="Aguardando Confirmação", color=0x2ecc71)
            emb.add_field(name="🕹️ Modo:", value=f"1v1-mobile | {submodo}", inline=False)
            emb.add_field(name="👮 Mediador Responsável:", value=med_obj.mention, inline=False)
            emb.add_field(name="⚡ Jogadores:", value=f"{p1.mention}\n{p2.mention}", inline=False) # Adicionado conforme pedido
            
            msg = await thread.send(content=f"{p1.mention} {p2.mention} | {med_obj.mention}", embed=emb)
            # Passamos o ID da mensagem da embed para ser apagada depois
            await msg.edit(view=ViewConfirmarPartida(thread.id, mediador_atual, [msg.id]))
            await it.response.send_message("✅ Partida criada!", ephemeral=True)
        else:
            await it.response.send_message("✅ Você entrou na fila!", ephemeral=True)

# ================= COMANDO .MEDIAR E ESCALA =================

@bot.command()
async def mediar(ctx):
    class EscalaV(View):
        @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green)
        async def e(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.send_message("✅ Você entrou na escala!", ephemeral=True)
    await ctx.send("👮 **Escala de Mediação**\nEntre na fila para atender partidas.", view=EscalaV())

@bot.command()
async def fila(ctx, v: str):
    val = float(v.replace(",", "."))
    embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
    embed.add_field(name="🕹️ Modo", value="`1v1-mobile`", inline=False)
    embed.add_field(name="Valor", value=f"R$ {val:.2f}", inline=False)
    await ctx.send(embed=embed, view=ViewFilaPartida(f"f_{val}", val))

filas_partida = {}; partidas_ativas = {}
@bot.event
async def on_ready(): init_db(); print("✅ ONLINE")

bot.run(TOKEN)
        
