import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect, ChannelSelect, RoleSelect
import sqlite3
import os
import asyncio
import traceback

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")

# Cores e Imagens
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache
fila_mediadores = []

# ==============================================================================
#                         BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0)")
        con.execute("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INTEGER DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS restricoes (user_id INTEGER PRIMARY KEY, motivo TEXT)")

def db_exec(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        return con.execute(query, params).fetchone()

def db_get_config(chave, default=None):
    res = db_query("SELECT valor FROM config WHERE chave=?", (chave,))
    return res[0] if res else default

def db_increment_counter(tipo):
    """Incrementa e retorna o número da sala para o tipo específico"""
    with sqlite3.connect("ws_database_final.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?, 0)", (tipo,))
        cur.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo = ?", (tipo,))
        con.commit()
        res = cur.execute("SELECT contagem FROM counters WHERE tipo = ?", (tipo,)).fetchone()
        return res[0]

# ==============================================================================
#           VIEW: CONFIRMAÇÃO (Lógica de Renomear Tópico Aqui)
# ==============================================================================
class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor, modo_completo):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.med_id = med_id
        self.valor = valor
        self.modo_completo = modo_completo # Ex: "1v1|Mobile"
        self.confirms = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, it: discord.Interaction, btn: Button):
        if it.user.id not in [j['id'] for j in self.jogadores]: 
            return await it.response.send_message("Você não está nesta partida.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.response.send_message("Você já confirmou, aguarde o oponente.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        
        # Feedback rápido
        await it.channel.send(f"✅ **{it.user.mention}** confirmou a partida!")

        # SE AMBOS CONFIRMAREM
        if len(self.confirms) >= len(self.jogadores):
            self.stop() # Para os botões
            
            # --- 1. LÓGICA DE RENOMEAR O TÓPICO ---
            modo_upper = self.modo_completo.upper()
            prefixo = "Sala"
            tipo_db = "geral"

            if "MOBILE" in modo_upper:
                prefixo = "Mobile"
                tipo_db = "mobile"
            elif "MISTO" in modo_upper:
                prefixo = "Misto"
                tipo_db = "misto"
            elif "FULL" in modo_upper:
                prefixo = "Full"
                tipo_db = "full"
            elif "EMULADOR" in modo_upper or "EMU" in modo_upper:
                prefixo = "Emu"
                tipo_db = "emu"

            # Pega o próximo número e renomeia
            numero = db_increment_counter(tipo_db)
            novo_nome = f"{prefixo}-{numero}"
            
            try:
                await it.channel.edit(name=novo_nome)
            except:
                pass # Ignora erro se não tiver perm ou rate limit
            
            # --- 2. GERAÇÃO DO EMBED FINAL (FOTO 2) ---
            try:
                partes = self.modo_completo.split('|')
                estilo_jogo = f"{partes[0].strip()} Gel Normal"
            except:
                estilo_jogo = self.modo_completo

            e = discord.Embed(title="Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            
            e.add_field(name="🎮 Estilo de Jogo", value=estilo_jogo, inline=False)
            
            # Cálculo de taxa visual
            try:
                val_float = float(self.valor.replace("R$", "").replace(",", ".").strip())
                taxa = val_float * 0.10
                if taxa < 0.10: taxa = 0.10
                taxa_str = f"R$ {taxa:.2f}".replace(".", ",")
            except:
                taxa_str = "R$ 0,30"

            info_text = f"Valor Da Sala: {taxa_str}\nMediador: <@{self.med_id}>"
            e.add_field(name="ℹ️ Informações da Aposta", value=info_text, inline=False)
            
            e.add_field(name="💎 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            
            lista_jog = "\n".join([f"{j['m']}" for j in self.jogadores])
            e.add_field(name="👥 Jogadores", value=lista_jog, inline=False)
            
            mentions = f"<@{self.med_id}> " + " ".join([j['m'] for j in self.jogadores])
            await it.channel.send(content=mentions, embed=e)
            
            # Paga comissão
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.channel.send("🚫 Partida recusada. Encerrando sala...")
            await asyncio.sleep(2)
            await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it: discord.Interaction, btn: Button):
        await it.response.send_message(f"🏳️ {it.user.mention} sugeriu combinar regras.", ephemeral=False)

# ==============================================================================
#           VIEW: FILA (CRIA TÓPICO COMO "AGUARDANDO")
# ==============================================================================
class ViewFila(View):
    def __init__(self, modo_str, valor):
        super().__init__(timeout=None)
        self.modo_str = modo_str 
        self.valor = valor
        self.jogadores = []
        self._setup_buttons()

    def _setup_buttons(self):
        self.clear_items()
        if "1V1" in self.modo_str.upper():
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback = lambda i: self.join(i, "Gel Normal")
            b2.callback = lambda i: self.join(i, "Gel Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b = Button(label="/entrar na fila", style=discord.ButtonStyle.success)
            b.callback = lambda i: self.join(i, None)
            self.add_item(b)
        
        bs = Button(label="Sair da Fila", style=discord.ButtonStyle.danger)
        bs.callback = self.leave
        self.add_item(bs)

    def embed_painel(self):
        e = discord.Embed(title=f"Sessão de Aposta | {self.modo_str}", color=COR_EMBED)
        e.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="📋 Modalidade", value=f"**{self.modo_str}**", inline=True)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        
        lista = []
        if not self.jogadores: lista.append("*Aguardando...*")
        else:
            for p in self.jogadores:
                extra = f" - {p['t']}" if p['t'] else ""
                lista.append(f"👤 {p['m']}{extra}")
        
        e.add_field(name="👥 Jogadores", value="\n".join(lista), inline=False)
        e.set_image(url=BANNER_URL)
        return e

    async def join(self, it: discord.Interaction, tipo_gelo):
        if any(j['id'] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Você já está na fila.", ephemeral=True)
        
        self.jogadores.append({'id': it.user.id, 'm': it.user.mention, 't': tipo_gelo})
        await it.response.edit_message(embed=self.embed_painel())
        
        limite = int(self.modo_str[0]) * 2 if self.modo_str[0].isdigit() else 2
        
        if len(self.jogadores) >= limite:
            await self.criar_sala(it)

    async def criar_sala(self, it):
        if not fila_mediadores: 
            return await it.channel.send("⚠️ **Fila cheia, mas sem mediadores online!**", delete_after=5)
        
        mediador_id = fila_mediadores.pop(0)
        fila_mediadores.append(mediador_id) 
        
        config_canal = db_get_config("canal_th")
        if not config_canal: return await it.channel.send("❌ Canal de tópicos não configurado.")
        
        canal_pai = bot.get_channel(int(config_canal))
        
        # --- MUDANÇA AQUI: NOME INICIAL FIXO ---
        thread = await canal_pai.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.public_thread)

        gelo_txt = self.jogadores[0]['t'] if self.jogadores[0]['t'] else "Padrão"
        
        emb_wait = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE)
        emb_wait.set_thumbnail(url=IMAGEM_BONECA)
        
        emb_wait.add_field(name="👑 Modo:", value=f"{self.modo_str.split('|')[0]} | {gelo_txt}", inline=False)
        emb_wait.add_field(name="💎 Valor da aposta:", value=f"R$ {self.valor}", inline=False)
        
        lista_jogs = "\n".join([j['m'] for j in self.jogadores])
        emb_wait.add_field(name="⚡ Jogadores:", value=lista_jogs, inline=False)
        
        rodape = """✨ SEJAM MUITO BEM-VINDOS ✨

• Regras adicionais podem ser combinadas entre os participantes.
• Se a regra combinada não existir no regulamento oficial da organização, é obrigatório tirar print do acordo antes do início da partida."""
        
        emb_wait.add_field(name="\u200b", value=f"```{rodape}```", inline=False)

        view_conf = ViewConfirmacao(self.jogadores, mediador_id, self.valor, self.modo_str)
        await thread.send(content=" ".join([j['m'] for j in self.jogadores]), embed=emb_wait, view=view_conf)
        
        self.jogadores = []
        await it.message.edit(embed=self.embed_painel())

    async def leave(self, it):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.embed_painel())

# ==============================================================================
#                  OUTRAS VIEWS E COMANDOS (MANTIDOS)
# ==============================================================================

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m=Modal(title="Cadastrar Pix"); n=TextInput(label="Nome"); c=TextInput(label="Chave"); q=TextInput(label="QR Code", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def sub(i): db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value)); await i.response.send_message("Salvo.", ephemeral=True)
        m.on_submit=sub; await it.response.send_modal(m)
    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍")
    async def ver(self, it, b):
        d=db_query("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        if d: await it.response.send_message(f"Nome: {d[1]}\nChave: `{d[2]}`\nQR: {d[3] or 'N/A'}", ephemeral=True)
        else: await it.response.send_message("Sem dados.", ephemeral=True)
    @discord.ui.button(label="Ver Chave Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def vermed(self, it, b):
        v=View(); s=UserSelect()
        async def cb(i):
            d=db_query("SELECT * FROM pix WHERE user_id=?",(s.values[0].id,))
            if d: await i.response.send_message(f"Dados de {s.values[0].mention}:\nNome: {d[1]}\nChave: `{d[2]}`", ephemeral=True)
            else: await i.response.send_message("Sem dados.", ephemeral=True)
        s.callback=cb; v.add_item(s); await it.response.send_message("Selecione:", view=v, ephemeral=True)

class ViewBotConfig(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Config Filas", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_filas(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Configurar Valores")
        val = TextInput(label="Valores", default="100,00, 50,00, 20,00, 10,00, 5,00", style=discord.TextStyle.paragraph)
        modal.add_item(val)
        async def sub(it):
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("lista_valores", val.value))
            await it.response.send_message("Valores salvos!", ephemeral=True)
        modal.on_submit = sub; await interaction.response.send_modal(modal)
    # Adicione os outros botões de config aqui se necessário (Cargos, Logs, etc)

@bot.tree.command(name="botconfig", description="Painel Config")
async def slash_botconfig(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    await it.response.defer(ephemeral=False)
    e = discord.Embed(title="Painel Config", color=COR_EMBED); e.set_thumbnail(url=ICONE_ORG)
    e.description = "**Painel Geral**\nUse os botões para editar."
    await it.followup.send(embed=e, view=ViewBotConfig())

@bot.tree.command(name="pix", description="Painel Pix")
async def slash_pix(it: discord.Interaction):
    await it.response.defer(ephemeral=False); e=discord.Embed(title="Painel Pix", color=COR_EMBED); e.set_thumbnail(url=ICONE_ORG); await it.followup.send(embed=e, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class V(View):
        def e(self): return discord.Embed(description="**Mediadores:**\n"+"\n".join([f"{i+1}. <@{u}>" for i,u in enumerate(fila_mediadores)]), color=COR_EMBED)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.success)
        async def en(self,i,b): 
            if i.user.id not in fila_mediadores: fila_mediadores.append(i.user.id); await i.response.edit_message(embed=self.e())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger)
        async def sa(self,i,b): 
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.edit_message(embed=self.e())
    v=V(); await ctx.send(embed=v.e(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class M(Modal, title="Gerar Filas"):
        m=TextInput(label="Modo (Ex: 1v1, 4v4)", default="1v1")
        p=TextInput(label="Plataforma (Ex: Mobile, Emu)", default="Mobile")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True)
            db_vals = db_get_config("lista_valores")
            vals = [v.strip() for v in db_vals.split(',')] if db_vals else ["100,00","80,00","60,00","50,00","10,00","5,00"]
            modo_formatado = f"{self.m.value}|{self.p.value}" 
            for v in vals:
                vi=ViewFila(modo_formatado, v)
                await i.channel.send(embed=vi.embed_painel(), view=vi); await asyncio.sleep(1)
    class V(View):
        @discord.ui.button(label="Gerar", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(M())
    await ctx.send("Admin", view=V())

@bot.command()
async def canal_fila(ctx):
    v=View(); s=ChannelSelect()
    async def cb(i): db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th',?)", (str(s.values[0].id),)); await i.response.send_message("Canal salvo.", ephemeral=True)
    s.callback=cb; v.add_item(s); await ctx.send("Selecione o canal onde os tópicos serão criados:", view=v)

@bot.event
async def on_ready():
    init_db(); await bot.tree.sync(); print("ONLINE - V.FINAL COM RENOMEAÇÃO DE TÓPICOS")

if TOKEN: bot.run(TOKEN)
        
