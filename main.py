import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import aiohttp
import os
import datetime
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES E IDENTIDADE VISUAL
# ==============================================================================
TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache de Sistema Operacional
fila_mediadores = [] 
COMISSAO_FIXA = 0.10  # Dez centavos por serviço prestado

# ==============================================================================
#                         GESTÃO DE BANCO DE DADOS (SQLITE)
# ==============================================================================
def init_db():
    """Inicializa as tabelas de persistência de dados do ecossistema WS."""
    with sqlite3.connect("dados_ws_final.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY, 
            nome TEXT, 
            chave TEXT, 
            qrcode TEXT,
            saldo_acumulado REAL DEFAULT 0.0,
            total_servicos INTEGER DEFAULT 0
        )""")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS restricoes (user_id INTEGER PRIMARY KEY, motivo TEXT)")
        con.execute("""CREATE TABLE IF NOT EXISTS registro_atividades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            med_id INTEGER, 
            valor_partida TEXT, 
            timestamp TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    with sqlite3.connect("dados_ws_final.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("dados_ws_final.db") as con:
        return con.execute(query, params).fetchone()

async def registrar_comissao_formal(med_id, valor_aposta):
    """Atribui o lucro operacional de R$ 0,10 ao mediador responsável."""
    db_execute("""UPDATE pix SET saldo_acumulado = saldo_acumulado + ?, 
                  total_servicos = total_servicos + 1 WHERE user_id = ?""", (COMISSAO_FIXA, med_id))
    db_execute("INSERT INTO registro_atividades (med_id, valor_partida, timestamp) VALUES (?,?,?)", 
               (med_id, valor_aposta, str(datetime.datetime.now())))

# ==============================================================================
#                         ESTRUTURA DAS FILAS DE APOSTAS
# ==============================================================================
class ViewFilaAposta(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []
        self._configurar_botoes()

    def _configurar_botoes(self):
        """Define os protocolos de interface baseados na modalidade de jogo."""
        self.clear_items()
        
        # Protocolo Exclusivo para Duelos 1v1
        if "1V1" in self.modo.upper():
            btn_normal = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary, custom_id="ws_normal")
            btn_infinito = Button(label="Gelo Infinito", style=discord.ButtonStyle.primary, custom_id="ws_infinito")
            btn_sair = Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="ws_sair")
            
            btn_normal.callback = self.registrar_participacao
            btn_infinito.callback = self.registrar_participacao
            btn_sair.callback = self.remover_participacao
            
            self.add_item(btn_normal)
            self.add_item(btn_infinito)
            self.add_item(btn_sair)
        
        # Protocolo para Modalidades Coletivas (2v2, 3v3, 4v4)
        else:
            btn_entrar = Button(label="Confirmar Participação", style=discord.ButtonStyle.success, custom_id="ws_entrar")
            btn_sair = Button(label="Sair da Fila", style=discord.ButtonStyle.danger, custom_id="ws_sair_coletivo")
            
            btn_entrar.callback = self.registrar_participacao
            btn_sair.callback = self.remover_participacao
            
            self.add_item(btn_entrar)
            self.add_item(btn_sair)

    def gerar_embed(self):
        emb = discord.Embed(title=f"Sessão de Aposta | {self.modo}", color=0x2b2d31)
        emb.set_author(name="WS APOSTAS - GESTÃO DE ATIVOS", icon_url=ICONE_ORG)
        
        emb.add_field(name="📋 Modalidade", value=f"**{self.modo}**", inline=True)
        emb.add_field(name="💰 Valor da Entrada", value=f"**R$ {self.valor}**", inline=True)
        
        lista = "\n".join([f"👤 {j['m']}" for j in self.jogadores]) or "*Aguardando proponentes ativos...*"
        emb.add_field(name="👥 Participantes Inscritos", value=lista, inline=False)
        
        emb.set_image(url=BANNER_URL)
        emb.set_footer(text="© 2026 WS Apostas | Sistema de Alta Disponibilidade")
        return emb

    async def registrar_participacao(self, it: discord.Interaction):
        """Valida e processa a entrada de um proponente na sessão."""
        if db_query("SELECT 1 FROM restricoes WHERE user_id=?", (it.user.id,)):
            return await it.response.send_message("Acesso negado: Sua conta possui restrições administrativas.", ephemeral=True)
        
        if any(j["id"] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Inconsistência: Você já consta na lista de inscritos.", ephemeral=True)
        
        self.jogadores.append({"id": it.user.id, "m": it.user.mention})
        await it.response.edit_message(embed=self.gerar_embed())
        
        # Cálculo de fechamento baseado no primeiro dígito do modo (1v1=2 jogadores, 2v2=4...)
        limite = int(self.modo[0]) * 2
        if len(self.jogadores) >= limite:
            await self.finalizar_sessao(it)

    async def remover_participacao(self, it: discord.Interaction):
        """Remove o proponente da fila atual."""
        self.jogadores = [j for j in self.jogadores if j["id"] != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

    async def finalizar_sessao(self, it):
        """Processa o encerramento da fila e escala o mediador responsável."""
        if not fila_mediadores:
            return await it.channel.send("⚠️ Erro Operacional: Mediadores indisponíveis no momento.", delete_after=5)
        
        mediador_atual = fila_mediadores.pop(0)
        fila_mediadores.append(mediador_atual)
        
        await registrar_comissao_formal(mediador_atual, self.valor)
        
        c_id = db_query("SELECT valor FROM config WHERE chave='canal_th'")
        if c_id:
            canal = bot.get_channel(int(c_id[0]))
            th = await canal.create_thread(name=f"Sessão-{self.valor}", type=discord.ChannelType.public_thread)
            await th.send(content=f"📝 **NOTIFICAÇÃO DE INÍCIO**\nMediador: <@{mediador_atual}>\nValor: R$ {self.valor}\nStatus: Aguardando Sala.")
        
        self.jogadores = []
        await it.message.edit(embed=self.gerar_embed())

# ==============================================================================
#                         GERADOR DE BLOCO OPERACIONAL
# ==============================================================================
class ModalGeradorWS(Modal):
    def __init__(self):
        super().__init__(title="Parametrização de Bloco WS")
        self.modo = TextInput(label="Designação da Modalidade", placeholder="Ex: 1v1, 2v2...", default="1v1")
        self.plataforma = TextInput(label="Plataforma de Acesso", placeholder="Ex: Mobile, Emulador...", default="Mobile")
        self.add_item(self.modo); self.add_item(self.plataforma)

    async def on_submit(self, it: discord.Interaction):
        valores_escopo = ["100,00", "80,00", "60,00", "50,00", "30,00", "15,00", "13,00", "10,00", "5,00", "3,00", "2,00", "1,00", "0,50"]
        await it.response.send_message(f"Gerando {len(valores_escopo)} instâncias operacionais...", ephemeral=True)
        
        formato = f"{self.modo.value.upper()} | {self.plataforma.value.upper()}"
        for valor in valores_escopo:
            view = ViewFilaAposta(formato, valor)
            await it.channel.send(embed=view.gerar_embed(), view=view)
            await asyncio.sleep(0.8)

# ==============================================================================
#                         PAINÉIS DE GESTÃO E COMANDOS
# ==============================================================================
@bot.command()
async def fila(ctx):
    """Instancia o painel administrativo para geração de filas profissionais."""
    if not ctx.author.guild_permissions.administrator: return
    class Painel(View):
        @discord.ui.button(label="Gerar Bloco WS (13 Filas)", style=discord.ButtonStyle.danger)
        async def iniciar(self, it, b): await it.response.send_modal(ModalGeradorWS())
    await ctx.send("### CENTRAL DE COMANDO WS\nInicie a geração das sessões de apostas via protocolo administrativo.", view=Painel())

@bot.command()
async def Pix(ctx):
    """Painel formal para parametrização de dados bancários."""
    from discord.ui import View
    class ViewFinanceiroWS(View):
        @discord.ui.button(label="Cadastrar Dados PIX", style=discord.ButtonStyle.success)
        async def cad(self, it, b):
            modal = Modal(title="Formulário Bancário")
            n = TextInput(label="Nome do Titular"); c = TextInput(label="Chave PIX"); q = TextInput(label="QR Code (URL)", required=False)
            modal.add_item(n); modal.add_item(c); modal.add_item(q)
            async def cb(inter):
                db_execute("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode) VALUES (?,?,?,?)", (inter.user.id, n.value, c.value, q.value))
                await inter.response.send_message("Dados registrados no sistema central.", ephemeral=True)
            modal.on_submit = cb; await it.response.send_modal(modal)

    emb = discord.Embed(title="Gestão de Recebimentos", description="Configure os dados para o repasse de seus proventos.", color=0x2b2d31)
    await ctx.send(embed=emb, view=ViewFinanceiroWS())

@bot.command()
async def canal_fila(ctx):
    """Define o destino oficial para a criação de tópicos de partida."""
    if not ctx.author.guild_permissions.administrator: return
    view = View(); seletor = ChannelSelect(placeholder="Selecione o canal oficial")
    async def callback(it):
        db_execute("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(seletor.values[0].id),))
        await it.response.send_message(f"O canal {seletor.values[0].mention} foi parametrizado com sucesso.", ephemeral=True)
    seletor.callback = callback; view.add_item(seletor); await ctx.send("Configuração de Destino:", view=view)

@bot.command()
async def mediar(ctx):
    """Gerencia a escala ativa de mediadores para rotação automática."""
    if not ctx.author.guild_permissions.manage_messages: return
    class ViewMediar(View):
        def gerar_embed(self):
            desc = "Abaixo constam os mediadores em escala ativa.\n\n"
            desc += "\n".join([f"**{i+1}** - <@{uid}>" for i, uid in enumerate(fila_mediadores)]) or "*Nenhum mediador em plantão.*"
            return discord.Embed(title="Escala Operacional WS", description=desc, color=0x36393f)
        @discord.ui.button(label="Iniciar Plantão", style=discord.ButtonStyle.success)
        async def entrar(self, it, b):
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
        @discord.ui.button(label="Encerrar Plantão", style=discord.ButtonStyle.danger)
        async def sair(self, it, b):
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.event
async def on_ready():
    init_db()
    print(f"WS APOSTAS | Sistema estabilizado e operando formalmente.\nVersão: 5.1.0 | Linhas: ~520")

if TOKEN: bot.run(TOKEN)
    
