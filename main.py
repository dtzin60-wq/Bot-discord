import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3
import os
import asyncio
import re

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
LOGO_URL = "https://cdn.discordapp.com/emojis/1234567890.png" 

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = [] 
filas_partida = {} 
partidas_ativas = {}

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qr TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats 
                      (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)''')
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

# ================= PAINÉIS (PIX & MEDIADOR) =================

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
    async def cadastrar(self, it, btn):
        class ModalPix(Modal, title="Configurar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo")
            c = TextInput(label="Chave PIX", placeholder="Sua chave aqui")
            async def on_submit(self, m_it):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (m_it.user.id, self.n.value, self.c.value, ""))
                await m_it.response.send_message("✅ Chave cadastrada!", ephemeral=True)
        await it.response.send_modal(ModalPix())

class ViewFilaControladora(View):
    def __init__(self): super().__init__(timeout=None)
    async def gerar_embed(self):
        embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para mediar**\n\n", color=0x2b2d31)
        if fila_mediadores:
            lista = "".join([f"{i+1} • <@{uid}>\n" for i, uid in enumerate(fila_mediadores)])
            embed.description += lista
        else: embed.description += "*Nenhum mediador ativo.*"
        return embed
    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def entrar(self, it, btn):
        if not tem_permissao(it.user, "cargo_mediador"): return
        if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
        await it.response.edit_message(embed=await self.gerar_embed())
    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴")
    async def sair(self, it, btn):
        if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
        await it.response.edit_message(embed=await self.gerar_embed())

# ================= FILA DE APOSTA (JOGADORES) =================

class ViewFilaAposta(View):
    def __init__(self, chave, valor, modo_nome):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor; self.modo_nome = modo_nome

    async def atualizar(self, msg):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - {m}" for u, m in lista]) if lista else "Vazio"
        valor_formatado = f"{self.valor:.2f}".replace(".", ",")
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.add_field(name="🕹️ Modo", value=f"`{self.modo_nome}`", inline=False)
        embed.add_field(name="Valor", value=f"R$ {valor_formatado}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        embed.set_image(url=BANNER_URL)
        await msg.edit(embed=embed, view=self)

    async def processar(self, it, modo_jogo):
        if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores!", ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        lista = filas_partida[self.chave]

        if any(x[0].id == it.user.id for x in lista): return await it.response.send_message("❌ Já está na fila!", ephemeral=True)
        if len(lista) >= 2: return await it.response.send_message("❌ Fila cheia!", ephemeral=True)

        lista.append((it.user, modo_jogo))
        if len(lista) == 2:
            p1, p2 = lista[0][0], lista[1][0]
            filas_partida[self.chave] = [] # RESET DA FILA DESTE PAINEL
            
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            canal = bot.get_channel(int(puxar_config("canal_destino")))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "mediador_id": med_id, "modo": self.modo_nome}
            
            pix_res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (med_id,))
            msg_pix = f"\n🏦 PIX: `{pix_res[1]}` ({pix_res[0]})" if pix_res else ""
            await thread.send(content=f"{p1.mention} {p2.mention} | <@{med_id}>\nMandem ID e Senha aqui!{msg_pix}")
            await it.response.send_message("✅ Partida criada!", ephemeral=True)
            await self.atualizar(it.message)
        else:
            await it.response.send_message(f"✅ Aguardando oponente...", ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.processar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.processar(it, "gelo infinito")
    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, it, b):
        filas_partida[self.chave] = [x for x in filas_partida.get(self.chave, []) if x[0].id != it.user.id]
        await it.response.send_message("✅ Saiu!", ephemeral=True); await self.atualizar(it.message)

# ================= COMANDO .AUX & VENCEDOR =================

class ViewAuxiliar(View):
    def __init__(self, thread): super().__init__(timeout=None); self.thread = thread
    @discord.ui.button(label="Escolher Vencedor", style=discord.ButtonStyle.green)
    async def v(self, it, b):
        if not tem_permissao(it.user, "cargo_aux"): return
        dados = partidas_ativas.get(self.thread.id)
        opts = [discord.SelectOption(label=j.name, value=str(j.id)) for j in dados["jogadores"]]
        sel = Select(options=opts)
        async def callback(interaction):
            v_id = int(sel.values[0])
            db_execute("INSERT OR IGNORE INTO stats (user_id, vitorias, coins) VALUES (?, 0, 0)")
            db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1 WHERE user_id = ?", (v_id,))
            await interaction.response.send_message(f"🏆 <@{v_id}> venceu e ganhou 1 coin!")
            await asyncio.sleep(5)
            await self.thread.edit(locked=True, archived=True)
        sel.callback = callback; v = View(); v.add_item(sel)
        await it.response.send_message("Selecione o vencedor:", view=v, ephemeral=True)

# ================= EVENTOS E COMANDOS =================

@bot.event
async def on_message(message):
    if message.author.bot: return
    if isinstance(message.channel, discord.Thread) and message.channel.id in partidas_ativas:
        nums = re.findall(r'\d+', message.content)
        if len(nums) >= 2:
            dados = partidas_ativas[message.channel.id]
            await message.delete()
            await message.channel.send(
                f"**Sala criada 3 a 5 minutos e da go!**\n\n"
                f"**Modo:** `{dados['modo']}`\n"
                f"**Jogadores:** {dados['jogadores'][0].mention} vs {dados['jogadores'][1].mention}\n\n"
                f"**Id da sala:** `{nums[0]}`\n"
                f"**Senha da sala:** `{nums[1]}`"
            )
    await bot.process_commands(message)

@bot.command()
async def fila(ctx, v: str, modo: str = "1v1-mobile"):
    val = float(v.replace(",", "."))
    view = ViewFilaAposta(f"f_{ctx.message.id}", val, modo)
    val_txt = f"{val:.2f}".replace(".", ",")
    emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
    emb.add_field(name="🕹️ Modo", value=f"`{modo}`", inline=False)
    emb.add_field(name="Valor", value=f"R$ {val_txt}", inline=False)
    emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
    await ctx.send(embed=emb, view=view)

@bot.command()
async def pix(ctx):
    if tem_permissao(ctx.author, "cargo_pix"): await ctx.send("⚙️ Configurar Pix", view=ViewPainelPix())

@bot.command()
async def mediar(ctx): await ctx.send(embed=await ViewFilaControladora().gerar_embed(), view=ViewFilaControladora())

@bot.command()
async def aux(ctx): 
    if tem_permissao(ctx.author, "cargo_aux"): await ctx.send("🛠️ Auxiliar", view=ViewAuxiliar(ctx.channel))

@bot.command()
async def coins(ctx):
    res = db_execute("SELECT coins FROM stats WHERE user_id = ?", (ctx.author.id,))
    c = res[0] if res else 0
    await ctx.send(f"🪙 Você possui **{c} coins**.")

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Mediador")
        async def s1(self, it, sel): salvar_config("cargo_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal Partidas")
        async def s2(self, it, sel): salvar_config("canal_destino", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("⚙️ Configuração", view=ConfigV())

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} Pronto")
bot.run(TOKEN)
                                                                  
