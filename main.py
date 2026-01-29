import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import os
import random
import re
import asyncio

# ================= CONFIGURAÇÕES E ASSETS =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_FILA = "https://i.imgur.com/vHqL6H9.png" # Substitua pelo seu banner da imagem 7
LOGO_ORG = "https://i.imgur.com/z8pGf89.png"   # Substitua pela logo das imagens 1 e 3

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

# Memória temporária para filas e partidas
fila_mediadores = [] 
filas_ativas = {} 
partidas_em_curso = {} # {thread_id: {"p1": user, "p2": user, "med": user, "valor": str, "modo": str}}

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    # Tabelas para PIX e Configurações de Cargos/Canais
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

# ================= CHECAGEM DE PERMISSÕES (.botconfig) =================
async def check_perm(it: discord.Interaction, chave_perm):
    if it.user.guild_permissions.administrator: return True
    cargo_id = puxar_config(chave_perm)
    if cargo_id and any(r.id == int(cargo_id) for r in it.user.roles): return True
    await it.response.send_message("⚠️ Você não tem permissão para esta ação.", ephemeral=True)
    return False

# ================= IMAGEM 3 & 5: SISTEMA DE PIX =================
class ViewPix(View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cadastrar(self, it, btn):
        if not await check_perm(it, "perm_pix"): return
        class ModalPix(Modal, title="Configurar Chave PIX"):
            nome = TextInput(label="Nome do Titular")
            chave = TextInput(label="Chave PIX")
            async def on_submit(self, m_it):
                conn = sqlite3.connect("dados.db")
                conn.execute("INSERT OR REPLACE INTO pix VALUES (?, ?, ?)", (m_it.user.id, self.nome.value, self.chave.value))
                conn.commit()
                conn.close()
                await m_it.response.send_message("✅ Chave PIX salva com sucesso!", ephemeral=True)
        await it.response.send_modal(ModalPix())

# ================= IMAGEM 2: FILA CONTROLADORA (.mediar) =================
class ViewMediar(View):
    def __init__(self): super().__init__(timeout=None)

    async def atualizar_painel(self, it):
        embed = discord.Embed(title="Painel da fila controladora", color=0x2b2d31)
        desc = "**Entre na fila para começar a mediar suas filas**\n\n"
        for i, uid in enumerate(fila_mediadores, 1):
            desc += f"{i} • <@{uid}> {uid}\n"
        embed.description = desc
        embed.set_thumbnail(url=LOGO_ORG)
        await it.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢")
    async def entrar(self, it, btn):
        if not await check_perm(it, "perm_med"): return
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await self.atualizar_painel(it)
        else: await it.response.send_message("Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def sair(self, it, btn):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await self.atualizar_painel(it)
        else: await it.response.send_message("Você não está na fila!", ephemeral=True)

# ================= IMAGEM 4, 8, 9, 10: FLUXO DE TÓPICO E CONFIRMAÇÃO =================
class ViewConfirmacao(View):
    def __init__(self, p1, p2, med_id, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med_id = p1, p2, med_id
        self.valor, self.modo = valor, modo
        self.confirms = {p1.id: False, p2.id: False}

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, it, btn):
        if it.user.id not in self.confirms: return
        self.confirms[it.user.id] = True
        
        if all(self.confirms.values()):
            # Imagem 10: Apaga e mostra o card final
            await it.channel.purge(limit=10)
            embed = discord.Embed(title="Partida Confirmada", color=0x5865f2)
            embed.add_field(name="🎮 Estilo de Jogo", value=self.modo, inline=False)
            embed.add_field(name="ℹ️ Informações", value=f"Mediador: <@{self.med_id}>", inline=False)
            embed.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=False)
            embed.add_field(name="👥 Jogadores", value=f"{self.p1.mention}\n{self.p2.mention}", inline=False)
            embed.set_thumbnail(url="https://i.imgur.com/your_squid_game_thumb.png")
            await it.channel.send(embed=embed)
        else:
            # Imagem 9: Um confirmou
            embed = discord.Embed(description=f"✅ **{it.user.mention}** confirmou a aposta!\n└ O outro jogador precisa confirmar para continuar.", color=0x2ecc71)
            await it.channel.send(embed=embed)
            await it.response.defer()

# ================= IMAGEM 1 & 7: SISTEMA DE FILA (.fila) =================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor = modo, valor
        self.jogadores = [] # Lista de (user, gelo_tipo)

    async def update_embed(self, msg):
        embed = discord.Embed(title="1v1 | SPACE APOSTAS 5K", color=0x5865f2)
        embed.add_field(name="💎 Modo", value=self.modo, inline=False)
        embed.add_field(name="💵 Valor", value=f"R$ {self.valor}", inline=False)
        
        j_text = "Nenhum jogador na fila"
        if self.jogadores:
            j_text = "\n".join([f"{u.mention} -{g}" for u, g in self.jogadores])
        embed.add_field(name="⚡ Jogadores", value=j_text, inline=False)
        embed.set_image(url=BANNER_FILA)
        await msg.edit(embed=embed, view=self)

    async def processar_entrada(self, it, gelo):
        if any(u.id == it.user.id for u, g in self.jogadores):
            return await it.response.send_message("Você já está na fila!", ephemeral=True)
        
        self.jogadores.append((it.user, gelo))
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores.pop()
                return await it.response.send_message("❌ Não há mediadores disponíveis no momento!", ephemeral=True)
            
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) # Rotatividade
            
            # Criar Tópico Aleatório (.canal)
            canais = [puxar_config(f"canal_{i}") for i in range(1, 4)]
            validos = [c for c in canais if c]
            if not validos: return await it.response.send_message("Canais não configurados pelo ADM!", ephemeral=True)
            
            target_channel = bot.get_channel(int(random.choice(validos)))
            thread = await target_channel.create_thread(name="aguardando-confirmação", type=discord.ChannelType.public_thread)
            
            # Salva na memória para o .aux
            partidas_em_curso[thread.id] = {
                "jogadores": [self.jogadores[0][0], self.jogadores[1][0]],
                "med_id": med_id, "valor": self.valor, "modo": self.modo
            }
            
            # Imagem 8: Painel inicial do tópico
            await thread.send(f"{self.jogadores[0][0].mention} {self.jogadores[1][0].mention} mediador: <@{med_id}>", 
                             view=ViewConfirmacao(self.jogadores[0][0], self.jogadores[1][0], med_id, self.valor, self.modo))
            
            self.jogadores = [] # Reseta a fila do chat
            await it.response.send_message(f"✅ Partida encontrada! Tópico: {thread.mention}", ephemeral=True)
        else:
            await it.response.send_message("Você entrou na fila!", ephemeral=True)
        
        await self.update_embed(it.message)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.secondary)
    async def gelo_n(self, it, btn): await self.processar_entrada(it, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.secondary)
    async def gelo_i(self, it, btn): await self.processar_entrada(it, "gelo infinito")

# ================= COMANDOS DE PREFIXO =================

@bot.command()
async def fila(ctx, modo_input: str, valor: str, tipo_dispositivo: str = "mobile"):
    # Lógica: .fila 1v1 10,00 -> 1v1-mobile
    modo_final = f"{modo_input}-{tipo_dispositivo}"
    view = ViewFila(modo_final, valor)
    embed = discord.Embed(title="Iniciando Fila...", color=0x5865f2)
    msg = await ctx.send(embed=embed, view=view)
    await view.update_embed(msg)

@bot.command()
async def mediar(ctx):
    view = ViewMediar()
    embed = await view.gerar()
    await ctx.send(embed=embed, view=view)

@bot.command()
async def Pix(ctx):
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Selecione uma das opções abaixo para gerenciar sua chave.", color=0x2b2d31)
    embed.set_thumbnail(url=LOGO_ORG)
    await ctx.send(embed=embed, view=ViewPix())

@bot.command()
async def botconfig(ctx):
    if not ctx.author.guild_permissions.administrator: return
    view = View()
    # Adiciona selects para cargos de acordo com a solicitação
    perms = [("perm_aux", "Quem pode usar .aux"), ("perm_med", "Quem pode mediar"), ("perm_pix", "Quem pode cadastrar Pix"), ("perm_cmd", "Quem usa comandos")]
    for chave, label in perms:
        async def callback(it, c=chave):
            salvar_config(c, it.data['values'][0])
            await it.response.send_message("✅ Salvo", ephemeral=True)
        sel = RoleSelect(placeholder=label)
        sel.callback = callback
        view.add_item(sel)
    await ctx.send("⚙️ Configuração de Permissões", view=view)

@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator: return
    view = View()
    for i in range(1, 4):
        async def callback(it, idx=i):
            salvar_config(f"canal_{idx}", it.data['values'][0])
            await it.response.send_message(f"✅ Canal {idx} configurado", ephemeral=True)
        sel = ChannelSelect(placeholder=f"Escolher Canal {i}")
        sel.callback = callback
        view.add_item(sel)
    await ctx.send("🎥 Selecione os 3 canais para criação automática de tópicos", view=view)

@bot.command()
async def aux(ctx):
    if not isinstance(ctx.channel, discord.Thread): return
    dados = partidas_em_curso.get(ctx.channel.id)
    if not dados: return await ctx.send("Esta partida não está registrada.")

    view = View()
    # Botão Vitória
    async def vit_cb(it):
        v_view = View()
        for p in dados['jogadores']:
            btn = Button(label=f"Vitória {p.name}", style=discord.ButtonStyle.green)
            async def p_cb(it2, player=p):
                await it2.channel.send(f"🏆 Vitória confirmada para {player.mention}!")
            btn.callback = p_cb
            v_view.add_item(btn)
        await it.response.send_message("Selecione o vencedor:", view=v_view, ephemeral=True)
    
    b_vit = Button(label="Dar vitória", style=discord.ButtonStyle.success)
    b_vit.callback = vit_cb
    
    # Botão Finalizar
    async def fin_cb(it):
        await it.channel.send("🏁 Aposta finalizada. Expulsando membros...")
        await asyncio.sleep(3)
        await it.channel.edit(archived=True, locked=True)
    
    b_fin = Button(label="Finalizar Aposta", style=discord.ButtonStyle.danger)
    b_fin.callback = fin_cb

    view.add_item(b_vit)
    view.add_item(b_fin)
    await ctx.send("🛠️ Opções de Administrador", view=view)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ Logado como {bot.user}")

bot.run(TOKEN)
    
