import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os
import random
import re

# ================= CONFIGURAÇÕES =================
TOKEN = "SEU_TOKEN_AQUI"
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
LOGO_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/LOGO_ROXA.png" 

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = [] 
filas_partida = {} 
partidas_ativas = {} # {thread_id: {"jogadores": [p1, p2], "med": id, "valor": val}}

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
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
            self.add_item(ButtonVencedor(j, tipo))

class ButtonVencedor(Button):
    def __init__(self, membro, tipo):
        super().__init__(label=f"{membro.name}", style=discord.ButtonStyle.blurple)
        self.membro = membro
        self.tipo = tipo

    async def callback(self, it: discord.Interaction):
        emb = discord.Embed(title="🏆 Resultado da Partida", color=0x2ecc71)
        txt = "W.O" if self.tipo == "wo" else "Vitória"
        emb.description = f"O jogador {self.membro.mention} recebeu **{txt}**!"
        await it.response.send_message(embed=emb)
        self.view.stop()

class ViewAux(View):
    def __init__(self, thread_id):
        super().__init__(timeout=None)
        self.thread_id = thread_id

    @discord.ui.button(label="Dar Vitória", style=discord.ButtonStyle.green)
    async def vitoria(self, it, btn):
        if not await tem_permissao(it, "perm_aux"): return await it.response.send_message("Sem permissão.", ephemeral=True)
        dados = partidas_ativas.get(self.thread_id)
        if not dados: return await it.response.send_message("Partida não encontrada.", ephemeral=True)
        await it.response.send_message("Selecione o vencedor:", view=ViewVitoria(dados['jogadores'], "vitoria"), ephemeral=True)

    @discord.ui.button(label="Dar Vitória por W.O", style=discord.ButtonStyle.gray)
    async def wo(self, it, btn):
        if not await tem_permissao(it, "perm_aux"): return await it.response.send_message("Sem permissão.", ephemeral=True)
        dados = partidas_ativas.get(self.thread_id)
        if not dados: return await it.response.send_message("Partida não encontrada.", ephemeral=True)
        await it.response.send_message("Selecione quem ganhou por W.O:", view=ViewVitoria(dados['jogadores'], "wo"), ephemeral=True)

    @discord.ui.button(label="Finalizar Aposta", style=discord.ButtonStyle.red)
    async def finalizar(self, it, btn):
        if not await tem_permissao(it, "perm_aux"): return await it.response.send_message("Sem permissão.", ephemeral=True)
        await it.response.send_message("Finalizando e arquivando tópico...")
        if self.thread_id in partidas_ativas: del partidas_ativas[self.thread_id]
        await asyncio.sleep(2)
        await it.channel.edit(archived=True, locked=True)

@bot.command()
async def aux(ctx):
    if not isinstance(ctx.channel, discord.Thread):
        return await ctx.send("❌ Este comando só pode ser usado dentro de um tópico de partida.")
    
    # Checa permissão
    cargo_id = puxar_config("perm_aux")
    if not ctx.author.guild_permissions.administrator:
        if not cargo_id or not any(r.id == int(cargo_id) for r in ctx.author.roles):
            return await ctx.send("❌ Você não tem permissão para usar o `.aux`.")

    embed = discord.Embed(title="🛠️ Painel Auxiliar de Partida", description="Escolha uma das opções abaixo para gerenciar esta partida.", color=0x2b2d31)
    await ctx.send(embed=embed, view=ViewAux(ctx.channel.id))

# ================= LÓGICA DE CRIAÇÃO E MONITORAMENTO =================

@bot.event
async def on_message(message):
    if message.author.bot: return
    # Detecta ID e Senha no tópico
    if isinstance(message.channel, discord.Thread) and message.channel.id in partidas_ativas:
        nums = re.findall(r'\d+', message.content)
        if len(nums) >= 2:
            d = partidas_ativas[message.channel.id]
            await message.channel.edit(name=f"Pagar-{d['valor']}")
            await message.channel.purge(limit=50)
            e = discord.Embed(title="🎮 SALA DISPONÍVEL", color=0xf1c40f)
            e.description = f"**🕹️ Modo:** `{d['modo']}`\n**💰 Valor:** `R$ {d['valor']}`\n**👥 Jogadores:** {d['jogadores'][0].mention} vs {d['jogadores'][1].mention}\n\n🆔 **ID:** `{nums[0]}`\n🔑 **SENHA:** `{nums[1]}`"
            e.set_image(url=BANNER_URL)
            await message.channel.send(embed=e)
            # NÃO deletamos de partidas_ativas aqui para o .aux continuar funcionando!
    await bot.process_commands(message)

# ================= CRIAÇÃO DO TÓPICO (AJUSTADO) =================

class ViewConfirmacao(View):
    def __init__(self, p1, p2, med_id, valor, modo, fila_view, original_msg):
        super().__init__(timeout=120)
        self.p1, self.p2, self.med_id, self.valor, self.modo = p1, p2, med_id, valor, modo
        self.confirmados = []; self.fila_view, self.original_msg = fila_view, original_msg

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar(self, it: discord.Interaction, btn):
        if it.user.id not in [self.p1.id, self.p2.id]: return
        if it.user.id in self.confirmados: return
        self.confirmados.append(it.user.id)
        val_f = f"{self.valor:.2f}".replace(".", ",")
        if len(self.confirmados) == 1:
            await it.response.edit_message(embed=discord.Embed(title="🟩 | Pagamento Confirmado", description=f"{it.user.mention} confirmou!"))
        else:
            await it.response.defer()
            canais = [puxar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [c for c in canais if c]
            canal_sorteado = bot.get_channel(int(random.choice(validos)))
            thread = await canal_sorteado.create_thread(name="Aguardando-confirmaçao", type=discord.ChannelType.public_thread)
            
            # SALVA OS DADOS PARA O .AUX FUNCIONAR DEPOIS
            partidas_ativas[thread.id] = {"jogadores": [self.p1, self.p2], "med": self.med_id, "valor": val_f, "modo": self.modo}
            
            emb_pix = discord.Embed(title="Pagamento", description=f"💰 Valor: **R$ {val_f}**\n👤 Mediador: <@{self.med_id}>", color=0x2ecc71)
            await thread.send(content=f"{self.p1.mention} vs {self.p2.mention} | <@{self.med_id}>", embed=emb_pix)
            await it.edit_original_response(content=f"✅ Tópico: {thread.mention}", embed=None, view=None)
            filas_partida[self.fila_view.chave] = []; await self.fila_view.atualizar(self.original_msg)

# ================= COMANDOS RESTANTES =================
@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class V(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode dar .aux", row=0)
        async def s1(self, it, sel): salvar_config("perm_aux", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode usar comandos", row=1)
        async def s2(self, it, sel): salvar_config("perm_geral", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode cadastrar Pix", row=2)
        async def s3(self, it, sel): salvar_config("perm_pix", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem pode ser Mediador", row=3)
        async def s4(self, it, sel): salvar_config("perm_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("⚙️ Configurações de Cargos", view=V())

@bot.command()
async def fila(ctx, v: str, *, modo: str = "1v1"):
    try: val = float(v.replace(",", "."))
    except: return
    class VF(View):
        def __init__(self, c, v, m):
            super().__init__(timeout=None)
            self.chave, self.valor, self.modo = c, v, m
        async def atualizar(self, msg):
            l = filas_partida.get(self.chave, [])
            j_str = "\n".join([f"{u.mention} -{m}" for u, m in l]) if l else "Vazio"
            e = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
            e.add_field(name="Valor", value=f"R$ {self.valor}", inline=False)
            e.add_field(name="Jogadores", value=j_str, inline=False)
            e.set_image(url=BANNER_URL); await msg.edit(embed=e, view=self)
        @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
        async def g1(self, it, b):
            if self.chave not in filas_partida: filas_partida[self.chave] = []
            l = filas_partida[self.chave]
            l.append((it.user, "gelo normal"))
            if len(l) == 2:
                med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
                await it.response.send_message(view=ViewConfirmacao(l[0][0], l[1][0], med_id, self.valor, self.modo, self, it.message))
            else: await it.response.send_message("Entrou!", ephemeral=True); await self.atualizar(it.message)
    v = VF(f"f_{ctx.message.id}", val, modo)
    await ctx.send(embed=discord.Embed(title="🎮"), view=v)

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} Online")
bot.run(TOKEN)
                                                               
