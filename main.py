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
QR_CODE_IMG = "https://sua_imagem_aqui.com/qrcode.png" 

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

# ================= PERMISSÃO PERSONALIZADA =================
async def verificar_permissao(it: discord.Interaction):
    role_id = puxar_config("cargo_mediador")
    has_role = any(r.id == int(role_id) for r in it.user.roles) if role_id else it.user.guild_permissions.administrator
    
    if not has_role:
        embed = discord.Embed(
            title="⚠️ Sem Permissão",
            description=f"{it.user.mention} você não possui permissão para essa ação.",
            color=0xff4b4b 
        )
        await it.response.send_message(embed=embed, ephemeral=True)
        return False
    return True

# ================= MODAIS E VIEWS PIX/MEDIAR =================

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
    async def cadastrar(self, it, btn):
        class ModalPix(Modal, title="Configurar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo")
            c = TextInput(label="Chave PIX", placeholder="Sua chave aqui")
            async def on_submit(self, m_it):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (m_it.user.id, self.n.value, self.c.value))
                await m_it.response.send_message("✅ Chave configurada!", ephemeral=True)
        await it.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍")
    async def ver_sua(self, it, btn):
        res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (it.user.id,))
        if res:
            embed = discord.Embed(title="Sua Chave", description=f"**Titular:** {res[0]}\n**Chave:** `{res[1]}`", color=0x2ecc71)
            embed.set_image(url=QR_CODE_IMG)
            await it.response.send_message(embed=embed, ephemeral=True)
        else: await it.response.send_message("❌ Nenhuma chave cadastrada.", ephemeral=True)

class ViewMed(View):
    def __init__(self): super().__init__(timeout=None)
    async def gerar_embed(self):
        embed = discord.Embed(title="Painel da fila controladora", color=0x2b2d31)
        embed.description = "__**Entre na fila para começar a mediar suas filas**__\n\n"
        lista = "".join([f"{i} • <@{uid}> {uid}\n" for i, uid in enumerate(fila_mediadores, 1)]) if fila_mediadores else "*Nenhum mediador na fila.*"
        embed.description += lista
        embed.set_thumbnail(url=LOGO_URL)
        return embed

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def entrar(self, it, btn):
        if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
        await it.response.edit_message(embed=await self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴")
    async def sair(self, it, btn):
        if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
        await it.response.edit_message(embed=await self.gerar_embed())

# ================= CONFIRMAÇÃO E TÓPICO =================

class ViewConfirmacaoAposta(View):
    def __init__(self, p1, p2, med_id, valor, modo, fila_view, original_msg):
        super().__init__(timeout=120)
        self.p1, self.p2 = p1, p2
        self.med_id = med_id
        self.valor = valor
        self.modo = modo
        self.confirmados = []
        self.fila_view = fila_view
        self.original_msg = original_msg

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green, emoji="✅")
    async def confirmar(self, it: discord.Interaction, btn):
        if it.user.id not in [self.p1.id, self.p2.id]: return
        if it.user.id in self.confirmados: return
        
        self.confirmados.append(it.user.id)
        val_f = f"{self.valor:.2f}".replace(".", ",")

        if len(self.confirmados) == 1:
            emb = discord.Embed(title="🟩 | Pagamento Confirmado", color=0x2ecc71)
            emb.description = f"{it.user.mention} confirmou que vai pagar!\n\u21aa Aguardando o outro jogador."
            await it.response.edit_message(embed=emb, view=self)
        else:
            await it.response.defer()
            canais = [puxar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [c for c in canais if c]
            canal = bot.get_channel(int(random.choice(validos)))
            
            thread = await canal.create_thread(name="Aguardando-confirmaçao", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [self.p1, self.p2], "modo": self.modo, "valor": val_f}
            
            res_pix = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (self.med_id,))
            emb_pix = discord.Embed(title="Pagamento da Partida", description=f"💰 Valor: **R$ {val_f}**\n👤 Mediador: <@{self.med_id}>\n🔑 Chave: `{res_pix[1] if res_pix else 'N/A'}`", color=0x2ecc71)
            emb_pix.set_image(url=QR_CODE_IMG)
            
            await thread.send(content=f"{self.p1.mention} vs {self.p2.mention} | <@{self.med_id}>", embed=emb_pix)
            await it.edit_original_response(content=f"✅ Tópico criado: {thread.mention}", embed=None, view=None)
            
            filas_partida[self.fila_view.chave] = []
            await self.fila_view.atualizar(self.original_msg)

# ================= FILA E MONITORAMENTO =================

class ViewFilaAposta(View):
    def __init__(self, chave, valor, modo):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor; self.modo = modo

    async def atualizar(self, msg):
        lista = filas_partida.get(self.chave, [])
        j_str = "\n".join([f"{u.mention} -{m}" for u, m in lista]) if lista else "Vazio"
        e = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        e.add_field(name="🕹️ Modo", value=f"`{self.modo}`", inline=False)
        e.add_field(name="Valor", value=f"R$ {f'{self.valor:.2f}'.replace('.', ',')}", inline=False)
        e.add_field(name="Jogadores na Fila", value=j_str, inline=False)
        e.set_image(url=BANNER_URL); await msg.edit(embed=e, view=self)

    async def processar(self, it, gelo):
        if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores!", ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        l = filas_partida[self.chave]
        if any(x[0].id == it.user.id for x in l): return await it.response.send_message("Já está na fila!", ephemeral=True)
        
        l.append((it.user, gelo))
        if len(l) == 2:
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            view_c = ViewConfirmacaoAposta(l[0][0], l[1][0], med_id, self.valor, self.modo, self, it.message)
            await it.response.send_message(embed=discord.Embed(title="Confirmação de Pagamento", color=0xf1c40f), view=view_c)
        else:
            await it.response.send_message(f"Entrou como -{gelo}!", ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.processar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.processar(it, "gelo infinito")

@bot.event
async def on_message(message):
    if message.author.bot: return
    if isinstance(message.channel, discord.Thread) and message.channel.id in partidas_ativas:
        nums = re.findall(r'\d+', message.content)
        if len(nums) >= 2:
            d = partidas_ativas[message.channel.id]
            await message.channel.edit(name=f"Pagar-{d['valor']}")
            await message.channel.purge(limit=50)
            e = discord.Embed(title="🎮 SALA DISPONÍVEL", color=0xf1c40f)
            e.description = f"**Valor:** `R$ {d['valor']}`\n**Modo:** `{d['modo']}`\n**Jogadores:** {d['jogadores'][0].mention} vs {d['jogadores'][1].mention}\n\n🆔 **ID:** `{nums[0]}`\n🔑 **SENHA:** `{nums[1]}`"
            await message.channel.send(embed=e); del partidas_ativas[message.channel.id]
    await bot.process_commands(message)

# ================= COMANDOS ADMIN E GERAIS =================

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class ConfigV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 1", row=0)
        async def s1(self, it, sel): salvar_config("canal_1", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 2", row=1)
        async def s2(self, it, sel): salvar_config("canal_2", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal 3", row=2)
        async def s3(self, it, sel): salvar_config("canal_3", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Mediador", row=3)
        async def s4(self, it, sel): salvar_config("cargo_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("⚙️ Configurações", view=ConfigV())

@bot.command()
async def fila(ctx, v: str, *, modo: str = "1v1"):
    try: val = float(v.replace(",", "."))
    except: return
    view = ViewFilaAposta(f"f_{ctx.message.id}", val, modo)
    await ctx.send(embed=discord.Embed(title="🎮 Carregando..."), view=view)
    await view.atualizar(ctx.channel.last_message)

@bot.command()
async def pix(ctx):
    e = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.", color=0x2b2d31)
    e.set_thumbnail(url=LOGO_URL); await ctx.send(embed=e, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    v = ViewMed(); await ctx.send(embed=await v.gerar_embed(), view=v)

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} Pronto.")
bot.run(TOKEN)
        
