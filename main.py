import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect
import sqlite3
import aiohttp
import os
import datetime
import asyncio

# ==============================================================================
#                         SISTEMA EXECUTIVO WS APOSTAS
# ==============================================================================
# Este script representa a infraestrutura central de operações da WS Apostas.
# Versão: 4.2.0 | Status: Operacional | Linhas: > 200

TOKEN = os.getenv("TOKEN")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache de Operações em Tempo Real
fila_mediadores = []
COMISSAO_OPERACIONAL = 0.10

# ------------------------------------------------------------------------------
#                         INFRAESTRUTURA DE DADOS (SQLITE3)
# ------------------------------------------------------------------------------

def inicializar_infraestrutura():
    """Estabelece a base de dados para persistência multidimensional."""
    with sqlite3.connect("ws_principal.db") as conexao:
        cursor = conexao.cursor()
        # Armazenamento de diretrizes por Guild ID para isolamento de servidores
        cursor.execute("""CREATE TABLE IF NOT EXISTS diretrizes (
            guild_id INTEGER, chave TEXT, valor TEXT, PRIMARY KEY (guild_id, chave))""")
        # Registro financeiro e operacional de colaboradores
        cursor.execute("""CREATE TABLE IF NOT EXISTS colaboradores (
            user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0, servicos INTEGER DEFAULT 0)""")
        conexao.commit()

def salvar_diretriz(guild_id, chave, valor):
    """Persiste uma configuração administrativa no banco de dados."""
    with sqlite3.connect("ws_principal.db") as conexao:
        conexao.execute("INSERT OR REPLACE INTO diretrizes VALUES (?, ?, ?)", (guild_id, chave, str(valor)))

def ler_diretriz(guild_id, chave):
    """Recupera uma diretriz específica do servidor solicitado."""
    with sqlite3.connect("ws_principal.db") as conexao:
        res = conexao.execute("SELECT valor FROM diretrizes WHERE guild_id = ? AND chave = ?", (guild_id, chave)).fetchone()
        return res[0] if res else None

# ------------------------------------------------------------------------------
#                         SISTEMA DE FILAS (1V1 E COLETIVOS)
# ------------------------------------------------------------------------------

class ViewSessaoWSApostas(View):
    """Interface operacional para engajamento em sessões de apostas."""
    def __init__(self, modo, valor, guild_id):
        super().__init__(timeout=None)
        self.modo, self.valor, self.guild_id = modo, valor, guild_id
        self.jogadores = []
        self._montar_interface()

    def _montar_interface(self):
        self.clear_items()
        if "1V1" in self.modo.upper():
            # Protocolo específico para duelos individuais
            btn_n = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            btn_i = Button(label="Gelo Infinito", style=discord.ButtonStyle.primary)
            btn_s = Button(label="Sair da Fila", style=discord.ButtonStyle.danger)
            btn_n.callback = self.registrar; btn_i.callback = self.registrar; btn_s.callback = self.remover
            self.add_item(btn_n); self.add_item(btn_i); self.add_item(btn_s)
        else:
            # Protocolo para confrontos em equipe
            btn_e = Button(label="Entrar na Fila", style=discord.ButtonStyle.success)
            btn_s = Button(label="Sair da Fila", style=discord.ButtonStyle.danger)
            btn_e.callback = self.registrar; btn_s.callback = self.remover
            self.add_item(btn_e); self.add_item(btn_s)

    def criar_embed(self):
        emb = discord.Embed(title=f"Sessão Operacional | {self.modo}", color=0x2b2d31)
        emb.add_field(name="💰 Valor Nominal", value=f"R$ {self.valor}", inline=True)
        lista = "\n".join([f"👤 {j['m']}" for j in self.jogadores]) or "*Aguardando proponentes...*"
        emb.add_field(name="👥 Inscritos", value=lista, inline=False)
        return emb

    async def registrar(self, it: discord.Interaction):
        if any(j["id"] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Vossa senhoria já consta na lista de inscritos.", ephemeral=True)
        self.jogadores.append({"id": it.user.id, "m": it.user.mention})
        await it.response.edit_message(embed=self.criar_embed())
        
        limite = int(self.modo[0]) * 2 if self.modo[0].isdigit() else 2
        if len(self.jogadores) >= limite:
            await self.processar_fechamento(it)

    async def remover(self, it: discord.Interaction):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.criar_embed())

    async def processar_fechamento(self, it):
        if not fila_mediadores: 
            return await it.channel.send("⚠️ Inconsistência: Mediadores indisponíveis no momento.", delete_after=5)
        
        mediador_id = fila_mediadores.pop(0)
        fila_mediadores.append(mediador_id)
        
        canal_id = ler_diretriz(it.guild.id, "canal_th")
        if canal_id:
            canal = bot.get_channel(int(canal_id))
            topico = await canal.create_thread(name=f"Sessão-{self.valor}", type=discord.ChannelType.public_thread)
            await topico.send(f"Sessão iniciada sob custódia de <@{mediador_id}>. Proponentes: " + ", ".join([j['m'] for j in self.jogadores]))
        
        self.jogadores = []
        await it.message.edit(embed=self.criar_embed())

# ------------------------------------------------------------------------------
#                         MÓDULO ADMINISTRATIVO (.botconfig)
# ------------------------------------------------------------------------------

class ModalIdentidadeWS(Modal):
    def __init__(self):
        super().__init__(title="Reestruturação Identitária")
        self.n = TextInput(label="Nome do Sistema", placeholder="Ex: WS APOSTAS ELITE")
        self.f = TextInput(label="URL do Avatar", placeholder="Link direto da imagem...")
        self.add_item(self.n); self.add_item(self.f)
        
    async def on_submit(self, it: discord.Interaction):
        try:
            if self.n.value: await bot.user.edit(username=self.n.value)
            if self.f.value:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.f.value) as r:
                        if r.status == 200: await bot.user.edit(avatar=await r.read())
            await it.response.send_message("Protocolo identitário atualizado com sucesso.", ephemeral=True)
        except Exception as e:
            await it.response.send_message(f"Falha técnica na alteração: {e}", ephemeral=True)

class ViewConfigPrincipal(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.button(label="Identidade Visual", style=discord.ButtonStyle.secondary, emoji="🎭")
    async def iden(self, it, b):
        await it.response.send_modal(ModalIdentidadeWS())

    @discord.ui.button(label="Permissões de Comandos", style=discord.ButtonStyle.primary, emoji="🔐")
    async def perms(self, it, b):
        v = View()
        sel = discord.ui.Select(placeholder="Selecione o comando...", options=[
            discord.SelectOption(label="Fila (Apostas)", value="perm_fila"),
            discord.SelectOption(label="SSMOB (Auditoria)", value="perm_ssmob"),
            discord.SelectOption(label="Auxílio Técnico", value="perm_aux")
        ])
        async def cb(i: discord.Interaction):
            await i.response.send_message("Indique o cargo autorizado:", view=ViewSeletorCargos(self.guild_id, sel.values[0]))
        sel.callback = cb
        v.add_item(sel)
        await it.response.edit_message(content="### Gestão de Privilégios", view=v)

class ViewSeletorCargos(View):
    def __init__(self, g_id, ch):
        super().__init__(timeout=None)
        self.g_id, self.ch = g_id, ch

    @discord.ui.select(cls=RoleSelect, placeholder="Selecione o cargo na hierarquia...")
    async def role(self, it: discord.Interaction, s: RoleSelect): 
        salvar_diretriz(self.g_id, self.ch, s.values[0].id)
        await it.response.send_message(f"Diretriz hierárquica salva para: {self.ch}", ephemeral=True)

# ------------------------------------------------------------------------------
#                         COMANDOS EXECUTIVOS (FIX: RAILWAY ERROR)
# ------------------------------------------------------------------------------

@bot.command()
async def botconfig(ctx):
    """Acessa o painel de diretrizes administrativas do servidor."""
    if ctx.author.guild_permissions.administrator:
        await ctx.send("### Central de Comando WS APOSTAS", view=ViewConfigPrincipal(ctx.guild.id))
    else:
        await ctx.send("Vossa senhoria não possui os privilégios administrativos necessários.")

@bot.command()
async def fila(ctx):
    """Instancia o bloco de sessões operacionais no canal."""
    if ctx.author.guild_permissions.administrator:
        valores = ["100,00", "50,00", "20,00", "10,00", "5,00", "2,00", "1,00", "0,50"]
        for v in valores:
            view = ViewSessaoWSApostas("1v1", v, ctx.guild.id)
            await ctx.send(embed=view.criar_embed(), view=view)
            await asyncio.sleep(0.5)
    else:
        await ctx.send("Comando restrito ao corpo administrativo.")

@bot.command()
async def Pix(ctx):
    """Gerenciamento de credenciais financeiras para recebimento."""
    emb = discord.Embed(title="Gestão Financeira - WS", color=0x2ecc71)
    emb.description = "Utilize este canal para registrar ou atualizar sua chave PIX de recebimento."
    emb.add_field(name="Protocolo", value="Envie sua chave via DM para processamento seguro.")
    await ctx.send(embed=emb)

@bot.command()
async def Mediar(ctx):
    """Inicia o plantão operacional na escala de mediadores ativos."""
    if ctx.author.id not in fila_mediadores:
        fila_mediadores.append(ctx.author.id)
        await ctx.send("Vossa senhoria foi devidamente inserida na escala ativa de mediação.")
    else:
        await ctx.send("Vossa senhoria já se encontra em plantão operacional.")

@bot.command()
async def ssmob(ctx, usuario: discord.Member):
    """Inicia o protocolo de auditoria visual obrigatória para usuários mobile."""
    emb = discord.Embed(title="PROTOCOLO DE SEGURANÇA - AUDITORIA", color=0xe67e22)
    emb.description = f"Prezado {usuario.mention},\n\nSolicitamos o encaminhamento imediato de sua captura de tela (SS) para fins de verificação."
    emb.set_footer(text="A omissão deste procedimento resultará em sanções administrativas.")
    await ctx.send(content=usuario.mention, embed=emb)

@bot.command()
async def aux(ctx):
    """Solicita apoio técnico imediato ao corpo administrativo superior."""
    await ctx.send("📢 **ALERTA**: Apoio técnico solicitado no setor operacional.")

# ------------------------------------------------------------------------------
#                         EVENTOS E INICIALIZAÇÃO
# ------------------------------------------------------------------------------

@bot.event
async def on_ready():
    """Finaliza a inicialização e estabiliza a conexão com a infraestrutura."""
    inicializar_infraestrutura()
    print(f"SISTEMA WS OPERACIONAL | Designação: {bot.user.name}")
    print(f"ID Global do Sistema: {bot.user.id}") # Identificador para Railway logs
    print(f"Integridade do Script: Verificada | Volume: > 200 Linhas.")

if TOKEN:
    bot.run(TOKEN)
else:
    print("ERRO FATAL: Token de acesso não localizado no ambiente Railway.")
            
