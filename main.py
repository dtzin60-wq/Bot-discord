import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os
import random
import re

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

# ================= SISTEMA DE PERMISSÃO (IGUAL IMAGEM 2) =================
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

# ================= PAINEL PIX (IGUAL IMAGEM 1) =================
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
                await m_it.response.send_message("✅ Chave PIX configurada com sucesso!", ephemeral=True)
        await it.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍")
    async def ver_sua(self, it, btn):
        res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (it.user.id,))
        if res:
            embed = discord.Embed(title="Sua Chave", description=f"**Titular:** {res[0]}\n**Chave:** `{res[1]}`", color=0x2ecc71)
            embed.set_image(url=QR_CODE_IMG)
            await it.response.send_message(embed=embed, ephemeral=True)
        else:
            await it.response.send_message("❌ Você ainda não cadastrou uma chave.", ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.gray, emoji="🔍")
    async def ver_mediador(self, it, btn):
        if not await verificar_permissao(it): return
        class ModalBusca(Modal, title="Consultar Mediador"):
            u = TextInput(label="ID do Mediador", placeholder="ID do usuário")
            async def on_submit(self, m_it):
                res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (int(self.u.value),))
                if res:
                    embed = discord.Embed(title="Dados do Mediador", description=f"👤 <@{self.u.value}>\n**Titular:** {res[0]}\n**Chave:** `{res[1]}`", color=0x2b2d31)
                    embed.set_image(url=QR_CODE_IMG)
                    await m_it.response.send_message(embed=embed, ephemeral=True)
                else: await m_it.response.send_message("❌ Mediador não encontrado.", ephemeral=True)
        await it.response.send_modal(ModalBusca())

# ================= PAINEL MEDIADOR (IGUAL IMAGEM 3) =================
class ViewMed(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def gerar_embed(self):
        embed = discord.Embed(title="Painel da fila controladora", color=0x2b2d31)
        embed.description = "__**Entre na fila para começar a mediar suas filas**__\n\n"
        
        if fila_mediadores:
            lista = "".join([f"{i} • <@{uid}> {uid}\n" for i, uid in enumerate(fila_mediadores, 1)])
            embed.description += lista
        else:
            embed.description += "*Nenhum mediador na fila.*"
        
        embed.set_thumbnail(url=LOGO_URL)
        return embed

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def entrar(self, it, btn):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=await self.gerar_embed())
        else:
            await it.response.send_message("Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴")
    async def sair(self, it, btn):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=await self.gerar_embed())
        else:
            await it.response.send_message("Você não está na fila!", ephemeral=True)

    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.gray, emoji="⚙️")
    async def remover(self, it, btn):
        if not it.user.guild_permissions.administrator: return
        class ModalRemover(Modal, title="Remover da Fila"):
            u = TextInput(label="ID do Mediador")
            async def on_submit(self, m_it):
                uid = int(self.u.value)
                if uid in fila_mediadores: fila_mediadores.remove(uid)
                await m_it.response.send_message("Removido!", ephemeral=True)
        await it.response.send_modal(ModalRemover())

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.gray, emoji="⚙️")
    async def staff(self, it, btn):
        if not it.user.guild_permissions.administrator: return
        await it.response.send_message("Painel de configuração disponível no comando .botconfig", ephemeral=True)

# ================= FILA E CRIAÇÃO DE TÓPICO =================

class ViewFilaAposta(View):
    def __init__(self, chave, valor, modo):
        super().__init__(timeout=None)
        self.chave = chave; self.valor = valor; self.modo = modo

    async def atualizar(self, msg):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} -{m}" for u, m in lista]) if lista else "Vazio"
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.add_field(name="🕹️ Modo", value=f"`{self.modo}`", inline=False)
        embed.add_field(name="Valor", value=f"R$ {f'{self.valor:.2f}'.replace('.', ',')}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        embed.set_image(url=BANNER_URL)
        await msg.edit(embed=embed, view=self)

    async def processar(self, it, gelo):
        if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores ativos!", ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        lista = filas_partida[self.chave]
        
        if any(x[0].id == it.user.id for x in lista): return await it.response.send_message("Você já está na fila!", ephemeral=True)
        
        lista.append((it.user, gelo))
        if len(lista) == 2:
            p1, p2 = lista[0][0], lista[1][0]
            filas_partida[self.chave] = [] # Reset imediato do painel
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            
            # Sorteio de canal
            canais = [puxar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [c for c in canais if c]
            canal = bot.get_channel(int(random.choice(validos)))
            
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}", type=discord.ChannelType.public_thread)
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "modo": self.modo}
            
            res_pix = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (med_id,))
            emb_pix = discord.Embed(title="Pagamento da Partida", description=f"👤 Mediador: <@{med_id}>\n🔑 Chave: `{res_pix[1] if res_pix else 'N/A'}`", color=0x2ecc71)
            emb_pix.set_image(url=QR_CODE_IMG)
            
            await thread.send(content=f"{p1.mention} vs {p2.mention} | <@{med_id}>", embed=emb_pix)
            await it.response.send_message(f"✅ Tópico criado: {thread.mention}", ephemeral=True)
            await self.atualizar(it.message)
        else:
            await it.response.send_message(f"Entrou como -{gelo}!", ephemeral=True)
            await self.atualizar(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.processar(it, "gelo normal")
    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.processar(it, "gelo infinito")
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, it, b):
        filas_partida[self.chave] = [x for x in filas_partida.get(self.chave, []) if x[0].id != it.user.id]
        await self.atualizar(it.message)

# ================= COMANDOS E LIMPEZA DE MENSAGENS =================

@bot.event
async def on_message(message):
    if message.author.bot: return
    if isinstance(message.channel, discord.Thread) and message.channel.id in partidas_ativas:
        # Detecta ID e Senha (dois conjuntos de números)
        nums = re.findall(r'\d+', message.content)
        if len(nums) >= 2:
            dados = partidas_ativas[message.channel.id]
            # APAGA AS MENSAGENS DE CIMA (Limpeza do tópico)
            await message.channel.purge(limit=20)
            
            emb = discord.Embed(title="🎮 SALA DISPONÍVEL", color=0xf1c40f)
            emb.description = (
                f"**Modo:** `{dados['modo']}`\n"
                f"**Jogadores:** {dados['jogadores'][0].mention} vs {dados['jogadores'][1].mention}\n\n"
                f"🆔 **ID:** `{nums[0]}`\n"
                f"🔑 **SENHA:** `{nums[1]}`\n\n"
                "*Sala criada! Aguardem o início.*"
            )
            await message.channel.send(embed=emb)
    await bot.process_commands(message)

@bot.command()
async def pix(ctx):
    embed = discord.Embed(
        title="Painel Para Configurar Chave PIX",
        description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.",
        color=0x2b2d31
    )
    embed.set_thumbnail(url=LOGO_URL)
    await ctx.send(embed=embed, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    view = ViewMed()
    await ctx.send(embed=await view.gerar_embed(), view=view)

@bot.command()
async def fila(ctx, v: str, *, modo: str = "1v1"):
    try: val = float(v.replace(",", "."))
    except: return
    view = ViewFilaAposta(f"f_{ctx.message.id}", val, modo)
    await ctx.send(embed=discord.Embed(title="🎮 Carregando..."), view=view)
    await view.atualizar(ctx.channel.last_message)

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class ConfigV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal Aleatório 1", row=0)
        async def s1(self, it, sel): salvar_config("canal_1", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal Aleatório 2", row=1)
        async def s2(self, it, sel): salvar_config("canal_2", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=ChannelSelect, placeholder="Canal Aleatório 3", row=2)
        async def s3(self, it, sel): salvar_config("canal_3", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Cargo Mediador", row=3)
        async def s4(self, it, sel): salvar_config("cargo_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("⚙️ **Configurações do Sistema**", view=ConfigV())

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} Online")
bot.run(TOKEN)
                    
