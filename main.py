import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os
import random
import re
import asyncio

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
LOGO_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/LOGO_ROXA.png" 

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = [] 
filas_partida = {} 
partidas_ativas = {} # {thread_id: {"jogadores": [p1, p2], "med": id, "valor": val, "modo": modo}}

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
    conn.commit()
    conn.close()

def salvar_config(chave, valor):
    conn = sqlite3.connect("dados.db")
    conn.execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (chave, str(valor)))
    conn.commit()
    conn.close()

def puxar_config(chave):
    conn = sqlite3.connect("dados.db")
    res = conn.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    conn.close()
    return res[0] if res else None

async def tem_permissao(it, chave):
    if it.user.guild_permissions.administrator: return True
    cid = puxar_config(chave)
    if cid and any(r.id == int(cid) for r in it.user.roles): return True
    return False

# ================= SISTEMA AUXILIAR (.AUX) =================

class ViewVitoria(View):
    def __init__(self, jogadores, tipo="vitória"):
        super().__init__(timeout=60)
        for j in jogadores:
            btn = Button(label=f"Vencedor: {j.name}", style=discord.ButtonStyle.blurple)
            async def callback(it, alvo=j):
                emb = discord.Embed(title="🏆 Resultado da Partida", description=f"O jogador {alvo.mention} recebeu **{tipo.upper()}**!", color=0x2ecc71)
                await it.response.send_message(embed=emb)
            btn.callback = callback
            self.add_item(btn)

class ViewAux(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Dar Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        if not await tem_permissao(it, "perm_aux"): return
        dados = partidas_ativas.get(self.thread_id)
        if dados: await it.response.send_message("Escolha o vencedor:", view=ViewVitoria(dados['jogadores'], "vitória"), ephemeral=True)

    @discord.ui.button(label="Dar Vitória por W.O", style=discord.ButtonStyle.gray)
    async def wo(self, it, btn):
        if not await tem_permissao(it, "perm_aux"): return
        dados = partidas_ativas.get(self.thread_id)
        if dados: await it.response.send_message("Escolha o vencedor por W.O:", view=ViewVitoria(dados['jogadores'], "W.O"), ephemeral=True)

    @discord.ui.button(label="Finalizar Aposta", style=discord.ButtonStyle.red)
    async def finalizar(self, it, btn):
        if not await tem_permissao(it, "perm_aux"): return
        await it.response.send_message("🏁 Finalizando aposta e fechando tópico...")
        if self.thread_id in partidas_ativas: del partidas_ativas[self.thread_id]
        await asyncio.sleep(2)
        await it.channel.edit(archived=True, locked=True)

# ================= FLUXO DE FILA E TÓPICO =================

class ViewConfirmacao(View):
    def __init__(self, p1, p2, med_id, valor, modo, fila_view, original_msg):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med_id = p1, p2, med_id
        self.valor, self.modo = valor, modo
        self.fila_view, self.original_msg = fila_view, original_msg
        self.confirmados = []

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar(self, it, btn):
        if it.user.id not in [self.p1.id, self.p2.id]: return
        if it.user.id in self.confirmados: return
        self.confirmados.append(it.user.id)

        if len(self.confirmados) == 1:
            emb = discord.Embed(description=f"✅ **{it.user.mention}** confirmou! Aguardando o oponente.", color=0x2ecc71)
            await it.response.send_message(embed=emb)
        else:
            canais = [puxar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [c for c in canais if c]
            if not validos: return await it.response.send_message("❌ Erro: Canais não configurados (.canal)", ephemeral=True)
            
            canal_sorteado = bot.get_channel(int(random.choice(validos)))
            thread = await canal_sorteado.create_thread(name="Aguardando-confirmação", type=discord.ChannelType.public_thread)
            
            partidas_ativas[thread.id] = {"jogadores": [self.p1, self.p2], "med": self.med_id, "valor": self.valor, "modo": self.modo}
            
            await thread.send(f"{self.p1.mention} vs {self.p2.mention} | Mediador: <@{self.med_id}>")
            e = discord.Embed(title="🎮 SALA DISPONÍVEL", color=0xf1c40f)
            e.description = f"**🕹️ Modo:** `{self.modo}`\n**💰 Valor:** `R$ {self.valor}`\n**👥 Jogadores:** {self.p1.mention} vs {self.p2.mention}"
            e.set_image(url=BANNER_URL)
            await thread.send(embed=e)
            
            await it.response.send_message(f"✅ Partida Confirmada! Tópico: {thread.mention}")
            filas_partida[self.fila_view.chave] = []
            await self.fila_view.update_embed(self.original_msg)

class ViewFila(View):
    def __init__(self, chave, modo, valor):
        super().__init__(timeout=None)
        self.chave, self.modo, self.valor = chave, modo, valor

    async def update_embed(self, msg):
        e = discord.Embed(title="🎮 WS APOSTAS", color=0x5865f2)
        lista = filas_partida.get(self.chave, [])
        j_str = "\n".join([f"{u.mention} -{g}" for u, g in lista]) if lista else "*Nenhum jogador*"
        e.add_field(name="💎 Modo", value=f"`{self.modo}`", inline=False)
        e.add_field(name="💵 Valor", value=f"`R$ {self.valor}`", inline=False)
        e.add_field(name="⚡ Jogadores", value=j_str, inline=False)
        e.set_image(url=BANNER_URL)
        await msg.edit(embed=e, view=self)

    async def entrar(self, it, gelo):
        if not await tem_permissao(it, "perm_geral"): return
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        l = filas_partida[self.chave]
        if any(u.id == it.user.id for u, g in l): return
        
        l.append((it.user, gelo))
        if len(l) == 2:
            if not fila_mediadores: 
                l.pop()
                return await it.response.send_message("❌ Sem mediadores na fila!", ephemeral=True)
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            await it.response.send_message("🤝 Partida encontrada! Confirmem o pagamento abaixo.", view=ViewConfirmacao(l[0][0], l[1][0], med_id, self.valor, self.modo, self, it.message))
        else:
            await it.response.send_message(f"Você entrou como -{gelo}!", ephemeral=True)
            await self.update_embed(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.secondary)
    async def g1(self, it, b): await self.entrar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.secondary)
    async def g2(self, it, b): await self.entrar(it, "gelo infinito")

# ================= COMANDOS PRINCIPAIS =================

@bot.command()
async def fila(ctx, modo: str, valor: str, dispositivo: str = "mobile"):
    modo_formatado = f"{modo}-{dispositivo}"
    chave = f"f_{ctx.message.id}"
    view = ViewFila(chave, modo_formatado, valor)
    msg = await ctx.send(embed=discord.Embed(title="🔄 Iniciando painel..."), view=view)
    await view.update_embed(msg)

@bot.command()
async def mediar(ctx):
    class VM(View):
        async def gerar(self):
            l = "".join([f"• <@{u}>\n" for u in fila_mediadores]) if fila_mediadores else "*Vazia*"
            e = discord.Embed(title="Painel da fila controladora", description=f"**Entre na fila para mediar**\n\n{l}", color=0x2b2d31)
            e.set_thumbnail(url=LOGO_URL)
            return e
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
        async def e(self, it, b):
            if not await tem_permissao(it, "perm_mediador"): return
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=await self.gerar())
    await ctx.send(embed=await VM().gerar(), view=VM())

@bot.command()
async def Pix(ctx):
    class VP(View):
        @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
        async def c(self, it, b):
            if not await tem_permissao(it, "perm_pix"): return
            class M(Modal, title="Configurar PIX"):
                n = TextInput(label="Titular"); c = TextInput(label="Chave")
                async def on_submit(self, m_it):
                    db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (m_it.user.id, self.n.value, self.c.value))
                    await m_it.response.send_message("✅ Chave salva!", ephemeral=True)
            await it.response.send_modal(M())
    e = discord.Embed(title="Painel PIX", description="Gerencie suas chaves de pagamento.", color=0x2b2d31)
    e.set_thumbnail(url=LOGO_URL)
    await ctx.send(embed=e, view=VP())

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class VC(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode dar .aux", row=0)
        async def s1(self, it, sel): salvar_config("perm_aux", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode ser Mediador", row=1)
        async def s2(self, it, sel): salvar_config("perm_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem cadastra Pix", row=2)
        async def s3(self, it, sel): salvar_config("perm_pix", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem usa comandos", row=3)
        async def s4(self, it, sel): salvar_config("perm_geral", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("⚙️ Configurações de Permissão", view=VC())

@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class VCA(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 1")
        async def c1(self, it, sel): salvar_config("canal_1", sel.values[0].id); await it.response.send_message("✅ Canal 1 Salvo", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 2")
        async def c2(self, it, sel): salvar_config("canal_2", sel.values[0].id); await it.response.send_message("✅ Canal 2 Salvo", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 3")
        async def c3(self, it, sel): salvar_config("canal_3", sel.values[0].id); await it.response.send_message("✅ Canal 3 Salvo", ephemeral=True)
    await ctx.send("Escolha os 3 canais para os tópicos:", view=VCA())

@bot.command()
async def aux(ctx):
    if not isinstance(ctx.channel, discord.Thread): return await ctx.send("Use este comando dentro de um tópico de partida!")
    await ctx.send("🛠️ Gerenciamento da Partida:", view=ViewAux(ctx.channel.id))

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} está pronto!")

bot.run(TOKEN)
    
