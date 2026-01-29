import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3
import os
import asyncio
import re
import random

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
LOGO_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/LOGO_ROXA.png" 
# Link da imagem do seu QR Code
QR_CODE_URL = "https://sua_imagem_aqui.com/qrcode.png" 

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

def tem_permissao(member, chave_config):
    role_id = puxar_config(chave_config)
    if not role_id: return member.guild_permissions.administrator
    role = member.guild.get_role(int(role_id))
    return (role in member.roles) if role else member.guild_permissions.administrator

# ================= PAINEL PIX (ESTILO ORG FIRE COM QR CODE) =================

class ViewPainelPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
    async def cadastrar(self, it, btn):
        class ModalPix(Modal, title="Configurar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo do titular")
            c = TextInput(label="Chave PIX", placeholder="Digite sua chave PIX")
            async def on_submit(self, m_it):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?)", (m_it.user.id, self.n.value, self.c.value))
                await m_it.response.send_message("✅ Sua chave PIX foi configurada!", ephemeral=True)
        await it.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍")
    async def ver_sua(self, it, btn):
        res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (it.user.id,))
        if res: await it.response.send_message(f"📌 **Titular:** {res[0]}\n**Chave:** `{res[1]}`", ephemeral=True)
        else: await it.response.send_message("❌ Sem chave cadastrada.", ephemeral=True)

    @discord.ui.button(label="QR Code", style=discord.ButtonStyle.gray, emoji="🖼️")
    async def ver_qrcode(self, it, btn):
        embed = discord.Embed(title="QR Code PIX", color=0x2b2d31)
        embed.set_image(url=QR_CODE_URL)
        await it.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.gray, emoji="🔍")
    async def ver_mediador(self, it, btn):
        if not tem_permissao(it.user, "cargo_aux"): return await it.response.send_message("❌ Sem permissão.", ephemeral=True)
        class ModalBusca(Modal, title="Consultar Mediador"):
            u = TextInput(label="ID do Mediador", placeholder="Cole o ID aqui")
            async def on_submit(self, m_it):
                try:
                    res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (int(self.u.value),))
                    if res: await m_it.response.send_message(f"👤 <@{self.u.value}>\n**Titular:** {res[0]}\n**Chave:** `{res[1]}`", ephemeral=True)
                    else: await m_it.response.send_message("❌ Sem chave.", ephemeral=True)
                except: await m_it.response.send_message("❌ ID inválido.", ephemeral=True)
        await it.response.send_modal(ModalBusca())

# ================= FILA (RESET AUTO + MODO NO NOME + CANAL RANDOM) =================

class ViewFilaAposta(View):
    def __init__(self, chave, valor, modo_nome):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor; self.modo_nome = modo_nome

    async def atualizar(self, msg):
        lista = filas_partida.get(self.chave, [])
        # Exibe: @Jogador - gelo infinito
        jogadores_str = "\n".join([f"{u.mention} - {m}" for u, m in lista]) if lista else "Vazio"
        val_txt = f"{self.valor:.2f}".replace(".", ",")
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.add_field(name="🕹️ Modo", value=f"`{self.modo_nome}`", inline=False)
        embed.add_field(name="Valor", value=f"R$ {val_txt}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        embed.set_image(url=BANNER_URL)
        await msg.edit(embed=embed, view=self)

    async def processar(self, it, modo_gelo):
        if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores ativos!", ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        lista = filas_partida[self.chave]

        if any(x[0].id == it.user.id for x in lista): return await it.response.send_message("❌ Já está na fila!", ephemeral=True)
        
        lista.append((it.user, modo_gelo))
        if len(lista) == 2:
            p1, p2 = lista[0][0], lista[1][0]
            filas_partida[self.chave] = [] # RESET IMEDIATO DA LISTA NO PAINEL
            
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            
            # Sorteio entre os 3 canais configurados
            canais_ids = [puxar_config("canal_1"), puxar_config("canal_2"), puxar_config("canal_3")]
            validos = [c for c in canais_ids if c]
            
            canal = bot.get_channel(int(random.choice(validos)))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "modo": self.modo_nome}
            
            res_pix = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (med_id,))
            pix_txt = f"\n🏦 **PIX:** `{res_pix[1]}` ({res_pix[0]})" if res_pix else ""
            await thread.send(content=f"{p1.mention} vs {p2.mention} | <@{med_id}>\n{pix_txt}")
            
            await it.response.send_message(f"✅ Partida criada em {canal.mention}!", ephemeral=True)
            await self.atualizar(it.message)
        else:
            await it.response.send_message(f"✅ Entrou na fila!", ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.processar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.processar(it, "gelo infinito")
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, it, b):
        filas_partida[self.chave] = [x for x in filas_partida.get(self.chave, []) if x[0].id != it.user.id]
        await it.response.send_message("✅ Saiu da fila.", ephemeral=True); await self.atualizar(it.message)

# ================= COMANDOS =================

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
    emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
    emb.add_field(name="🕹️ Modo", value=f"`{modo}`", inline=False)
    emb.add_field(name="Valor", value=f"R$ {f'{val:.2f}'.replace('.', ',')}", inline=False)
    emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
    emb.set_image(url=BANNER_URL)
    await ctx.send(embed=emb, view=view)

@bot.command()
async def pix(ctx):
    if not (tem_permissao(ctx.author, "cargo_mediador")): return
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie sua chave PIX para as filas.", color=0x2b2d31)
    embed.set_thumbnail(url=LOGO_URL)
    await ctx.send(embed=embed, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    class ViewMed(View):
        def __init__(self): super().__init__(timeout=None)
        async def emb(self):
            e = discord.Embed(title="Painel da Fila Controladora", description="**Mediadores ativos:**\n\n", color=0x2b2d31)
            lista = "".join([f"• <@{u}>\n" for u in fila_mediadores]) if fila_mediadores else "Vazio"
            e.description += lista
            e.set_thumbnail(url=LOGO_URL)
            return e
        @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.green, emoji="🟢")
        async def e(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=await self.emb())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.red, emoji="🔴")
        async def s(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=await self.emb())
    v = ViewMed(); await ctx.send(embed=await v.emb(), view=v)

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} Pronto")
bot.run(TOKEN)
