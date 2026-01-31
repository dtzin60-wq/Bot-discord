import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect, ChannelSelect
import sqlite3
import os
import asyncio
import traceback

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")

# Cores e Imagens
COR_EMBED = 0x2b2d31 # Cinza Escuro
COR_VERDE = 0x2ecc71 # Verde Sucesso
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache
fila_mediadores = []

# ==============================================================================
#                         BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0)")
        con.execute("CREATE TABLE IF NOT EXISTS restricoes (user_id INTEGER PRIMARY KEY, motivo TEXT)")

def db_exec(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        return con.execute(query, params).fetchone()

# ==============================================================================
#                         VIEW: PAINEL PIX (CORRIGIDO)
# ==============================================================================
class ViewPainelPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    # CORREÇÃO AQUI: Troquei o emoji inválido por 💠
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠")
    async def btn_cadastrar(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Cadastrar Chave PIX")
        nome = TextInput(label="Nome Completo", placeholder="Digite seu nome...")
        chave = TextInput(label="Chave PIX", placeholder="CPF, Email, Telefone...")
        modal.add_item(nome); modal.add_item(chave)
        
        async def on_submit(it: discord.Interaction):
            db_exec("INSERT OR REPLACE INTO pix (user_id, nome, chave) VALUES (?,?,?)", 
                    (it.user.id, nome.value, chave.value))
            await it.response.send_message("✅ **Sucesso!** Seus dados foram salvos.", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍")
    async def btn_ver_sua(self, interaction: discord.Interaction, button: Button):
        dados = db_query("SELECT nome, chave FROM pix WHERE user_id=?", (interaction.user.id,))
        if dados:
            await interaction.response.send_message(f"👤 **Nome:** {dados[0]}\n🔑 **Chave:** `{dados[1]}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Você não tem chave cadastrada.", ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def btn_ver_mediador(self, interaction: discord.Interaction, button: Button):
        view = View()
        select = UserSelect(placeholder="Selecione o mediador...")
        
        async def callback(it: discord.Interaction):
            target = select.values[0]
            dados = db_query("SELECT nome, chave FROM pix WHERE user_id=?", (target.id,))
            if dados:
                await it.response.send_message(f"Dados de {target.mention}:\n👤 **Nome:** {dados[0]}\n🔑 **Chave:** `{dados[1]}`", ephemeral=True)
            else:
                await it.response.send_message(f"❌ {target.mention} não possui chave cadastrada.", ephemeral=True)
        
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Selecione o mediador abaixo:", view=view, ephemeral=True)

# ==============================================================================
#                         VIEW: CONFIRMAÇÃO DA PARTIDA
# ==============================================================================
class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.med_id = med_id
        self.valor = valor
        self.confirms = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, it: discord.Interaction, btn: Button):
        # Verifica se é jogador
        if it.user.id not in [j['id'] for j in self.jogadores]: 
            return await it.response.send_message("Você não está jogando.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.response.send_message("Já confirmado.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        
        emb = discord.Embed(color=COR_VERDE)
        emb.set_author(name="| Partida Confirmada", icon_url="https://cdn-icons-png.flaticon.com/512/148/148767.png")
        emb.description = f"**{it.user.mention} confirmou a aposta!**\n↳ O outro jogador precisa confirmar para continuar."
        await it.channel.send(embed=emb)

        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            emb_start = discord.Embed(title="✅ SESSÃO INICIADA", color=COR_VERDE)
            emb_start.description = f"Mediador: <@{self.med_id}>\nJogadores: {' '.join([j['m'] for j in self.jogadores])}"
            await it.channel.send(content=f"<@{self.med_id}>", embed=emb_start)
            # Add comissão
            db_exec("INSERT OR REPLACE INTO pix_saldo (user_id, saldo) VALUES (?, COALESCE((SELECT saldo FROM pix_saldo WHERE user_id=?), 0) + 0.10)", (self.med_id, self.med_id))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.channel.send("🚫 Partida recusada.")
            await it.channel.edit(locked=True, archived=True)

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it: discord.Interaction, btn: Button):
        await it.response.send_message(f"🏳️ {it.user.mention} quer combinar regras.", ephemeral=False)

# ==============================================================================
#                         VIEW: FILA PRINCIPAL
# ==============================================================================
class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []
        self._setup()

    def _setup(self):
        self.clear_items()
        if "1V1" in self.modo.upper():
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback = lambda i: self.join(i, "Gelo Normal")
            b2.callback = lambda i: self.join(i, "Gelo Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b = Button(label="/entrar na fila", style=discord.ButtonStyle.success)
            b.callback = lambda i: self.join(i, None)
            self.add_item(b)
        
        bs = Button(label="Sair da Fila", style=discord.ButtonStyle.danger)
        bs.callback = self.leave
        self.add_item(bs)

    def embed(self):
        emb = discord.Embed(title=f"Sessão de Aposta | {self.modo}", color=COR_EMBED)
        emb.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        emb.add_field(name="📋 Modalidade", value=f"**{self.modo}**", inline=True)
        emb.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        
        lista = []
        if not self.jogadores: lista.append("*Aguardando...*")
        else:
            for p in self.jogadores:
                # Exibe o tipo de gelo na lista
                extra = f" - {p['t']}" if p['t'] else ""
                lista.append(f"👤 {p['m']}{extra}")
        
        emb.add_field(name="👥 Jogadores", value="\n".join(lista), inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def join(self, it: discord.Interaction, tipo):
        if any(j['id'] == it.user.id for j in self.jogadores): return await it.response.send_message("Já está na fila.", ephemeral=True)
        
        self.jogadores.append({'id': it.user.id, 'm': it.user.mention, 't': tipo})
        await it.response.edit_message(embed=self.embed())
        
        lim = int(self.modo[0]) * 2 if self.modo[0].isdigit() else 2
        if len(self.jogadores) >= lim:
            if not fila_mediadores: return await it.channel.send("⚠️ Sem mediadores.", delete_after=5)
            med = fila_mediadores.pop(0); fila_mediadores.append(med)
            
            cnf = db_query("SELECT valor FROM config WHERE chave='canal_th'")
            if not cnf: return await it.channel.send("❌ Configure o canal com .canal_fila")
            ch = bot.get_channel(int(cnf[0]))
            
            th = await ch.create_thread(name=f"Sessão-{self.valor}", type=discord.ChannelType.public_thread)
            
            emb_th = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE)
            emb_th.set_thumbnail(url=ICONE_ORG)
            emb_th.add_field(name="👑 Modo:", value=f"```{self.modo} | {tipo if tipo else 'Padrão'}```", inline=False)
            emb_th.add_field(name="💎 Valor:", value=f"```{self.valor}```", inline=False)
            emb_th.add_field(name="⚡ Jogadores:", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            emb_th.description = "```✨ SEJAM MUITO BEM-VINDOS ✨\n\n• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra combinada não existir no regulamento oficial da organização, é obrigatório tirar print do acordo antes do início da partida.```"
            
            await th.send(content=" ".join([j['m'] for j in self.jogadores]), embed=emb_th, view=ViewConfirmacao(self.jogadores, med, self.valor))
            self.jogadores = []; await it.message.edit(embed=self.embed())

    async def leave(self, it):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.embed())

# ==============================================================================
#                         COMANDOS
# ==============================================================================

@bot.tree.command(name="pix", description="Gerencie sua chave PIX")
async def slash_pix(interaction: discord.Interaction):
    try:
        # 1. DEFER: Evita timeout do Discord
        await interaction.response.defer(ephemeral=False)
        
        emb = discord.Embed(title="Painel Para Configurar Chave PIX", color=COR_EMBED)
        emb.description = (
            "Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\n"
            "Selecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX."
        )
        emb.set_thumbnail(url=ICONE_ORG)
        
        # 2. FOLLOWUP: Envia a mensagem segura
        await interaction.followup.send(embed=emb, view=ViewPainelPix())
        
    except Exception as e:
        print(f"Erro: {e}")
        await interaction.followup.send("Erro ao carregar painel.", ephemeral=True)

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    
    class ViewMediar(View):
        def emb(self):
            desc = "**Entre na fila para começar a mediar suas filas**\n\n" + ("\n".join([f"**{i+1} •** <@{u}> {u}" for i,u in enumerate(fila_mediadores)]) or "*Vazia*")
            emb = discord.Embed(title="Painel da fila controladora", description=desc, color=COR_EMBED)
            emb.set_thumbnail(url=ICONE_ORG)
            return emb
        
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success)
        async def ent(self, i, b): 
            if i.user.id not in fila_mediadores: fila_mediadores.append(i.user.id); await i.response.edit_message(embed=self.emb())
        
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger)
        async def sai(self, i, b): 
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.edit_message(embed=self.emb())

    v = ViewMediar(); await ctx.send(embed=v.emb(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class M(Modal, title="Gerar"):
        m = TextInput(label="Modo", default="1v1"); p = TextInput(label="Plat", default="Mobile")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True)
            for v in ["100,00","50,00","20,00","10,00","5,00","2,00","1,00","0,50"]:
                vi = ViewFila(f"{self.m.value} | {self.p.value}", v)
                await i.channel.send(embed=vi.embed(), view=vi)
                await asyncio.sleep(1)
    class V(View):
        @discord.ui.button(label="Gerar Bloco WS", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(M())
    await ctx.send("Painel Admin", view=V())

@bot.command()
async def canal_fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v=View(); s=ChannelSelect()
    async def cb(i): 
        db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(s.values[0].id),)); await i.response.send_message("Salvo.", ephemeral=True)
    s.callback=cb; v.add_item(s); await ctx.send("Canal de Tópicos:", view=v)

@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print("WS FINAL ONLINE - COM EMOJI CORRIGIDO")

if TOKEN: bot.run(TOKEN)
        
