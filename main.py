Import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect, ChannelSelect, RoleSelect
import sqlite3
import os
import asyncio
import traceback

# ==============================================================================
#                         CONFIGURAÇÕES DE SEGURANÇA
# ==============================================================================
TOKEN = os.getenv("TOKEN")

# 🔒 COLOQUE AQUI O ID DO SEU SERVIDOR (1465929927206375527)
# Para pegar o ID: Ative o modo desenvolvedor no Discord, clique com botão direito no nome do servidor > Copiar ID
ID_SERVIDOR_PERMITIDO = 123456789012345678  # <--- TROQUE ISSO PELO ID DO SEU SERVIDOR

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
    with sqlite3.connect("ws_database_final.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?, 0)", (tipo,))
        cur.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo = ?", (tipo,))
        con.commit()
        res = cur.execute("SELECT contagem FROM counters WHERE tipo = ?", (tipo,)).fetchone()
        return res[0]

# ==============================================================================
#           VIEW: CONFIRMAÇÃO
# ==============================================================================
class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor, modo_completo):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.med_id = med_id
        self.valor = valor
        self.modo_completo = modo_completo
        self.confirms = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, it: discord.Interaction, btn: Button):
        if it.user.id not in [j['id'] for j in self.jogadores]: 
            return await it.response.send_message("Você não está nesta partida.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.response.send_message("Você já confirmou.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        await it.channel.send(f"✅ **{it.user.mention}** confirmou a partida!")

        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            
            # Renomear Tópico
            modo_upper = self.modo_completo.upper()
            prefixo = "Sala"
            tipo_db = "geral"

            if "MOBILE" in modo_upper: prefixo, tipo_db = "Mobile", "mobile"
            elif "MISTO" in modo_upper: prefixo, tipo_db = "Misto", "misto"
            elif "FULL" in modo_upper: prefixo, tipo_db = "Full", "full"
            elif "EMU" in modo_upper: prefixo, tipo_db = "Emu", "emu"

            num = db_increment_counter(tipo_db)
            try: await it.channel.edit(name=f"{prefixo}-{num}")
            except: pass
            
            # Embed Final
            try: estilo = f"{self.modo_completo.split('|')[0].strip()} Gel Normal"
            except: estilo = self.modo_completo

            e = discord.Embed(title="Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            e.add_field(name="🎮 Estilo de Jogo", value=estilo, inline=False)
            
            try:
                v_f = float(self.valor.replace("R$","").replace(",",".").strip())
                taxa = max(v_f * 0.10, 0.10)
                taxa_str = f"R$ {taxa:.2f}".replace(".",",")
            except: taxa_str = "R$ 0,10"

            e.add_field(name="ℹ️ Informações da Aposta", value=f"Valor Da Sala: {taxa_str}\nMediador: <@{self.med_id}>", inline=False)
            e.add_field(name="💎 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            
            await it.channel.send(content=f"<@{self.med_id}> {' '.join([j['m'] for j in self.jogadores])}", embed=e)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.channel.send("🚫 Recusada. Fechando..."); await asyncio.sleep(2); await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it: discord.Interaction, btn: Button):
        await it.response.send_message(f"🏳️ {it.user.mention} sugeriu combinar regras.", ephemeral=False)

# ==============================================================================
#           VIEW: FILA
# ==============================================================================
class ViewFila(View):
    def __init__(self, modo_str, valor):
        super().__init__(timeout=None); self.modo_str=modo_str; self.valor=valor; self.jogadores=[]
        self._btns()

    def _btns(self):
        self.clear_items()
        if "1V1" in self.modo_str.upper():
            b1=Button(label="Gelo Normal", style=discord.ButtonStyle.secondary); b2=Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback=lambda i: self.join(i,"Gel Normal"); b2.callback=lambda i: self.join(i,"Gel Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b=Button(label="/entrar na fila", style=discord.ButtonStyle.success); b.callback=lambda i: self.join(i,None); self.add_item(b)
        bs=Button(label="Sair da Fila", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)

    def emb(self):
        titulo_formatado = f"Aposta | {self.modo_str.replace('|', ' ')}"
        e = discord.Embed(title=titulo_formatado, color=COR_EMBED)
        e.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="📋 Modalidade", value=f"**{self.modo_str.replace('|', ' ')}**", inline=True)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        lst = [f"👤 {j['m']} - {j['t']}" if j['t'] else f"👤 {j['m']}" for j in self.jogadores]
        e.add_field(name="👥 Jogadores", value="\n".join(lst) or "*Aguardando...*", inline=False)
        e.set_image(url=BANNER_URL); return e

    async def join(self, it, tipo):
        if any(j['id']==it.user.id for j in self.jogadores): return await it.response.send_message("Já está na fila.", ephemeral=True)
        self.jogadores.append({'id':it.user.id,'m':it.user.mention,'t':tipo}); await it.response.edit_message(embed=self.emb())
        
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        if len(self.jogadores)>=lim:
            if not fila_mediadores: return await it.channel.send("⚠️ Sem mediadores!", delete_after=5)
            med = fila_mediadores.pop(0); fila_mediadores.append(med)
            
            cid = db_get_config("canal_th")
            if not cid: return await it.channel.send("❌ Use /canal para configurar.")
            
            ch = bot.get_channel(int(cid)); th = await ch.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.public_thread)
            
            ew = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE); ew.set_thumbnail(url=IMAGEM_BONECA)
            ew.add_field(name="👑 Modo:", value=f"{self.modo_str.split('|')[0]} | {self.jogadores[0]['t'] or 'Padrão'}", inline=False)
            ew.add_field(name="💎 Valor:", value=f"R$ {self.valor}", inline=False)
            ew.add_field(name="⚡ Jogadores:", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            ew.add_field(name="\u200b", value="```✨ SEJAM MUITO BEM-VINDOS ✨\n\n• Regras adicionais podem ser combinadas.\n• Obrigatório print do acordo.```", inline=False)
            
            await th.send(content=" ".join([j['m'] for j in self.jogadores]), embed=ew, view=ViewConfirmacao(self.jogadores, med, self.valor, self.modo_str))
            self.jogadores=[]; await it.message.edit(embed=self.emb())

    async def leave(self, it):
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]; await it.response.edit_message(embed=self.emb())

# ==============================================================================
#           PAINÉIS
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
    @discord.ui.button(label="Config Filas", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def btn_filas(self, it, b): await it.response.send_message("Use o comando .fila para gerar", ephemeral=True)

# ==============================================================================
#           COMANDOS
# ==============================================================================

@bot.tree.command(name="pix", description="Painel Pix")
async def slash_pix(it: discord.Interaction):
    await it.response.defer(ephemeral=False)
    e=discord.Embed(title="Painel Para Configurar Chave PIX", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG)
    e.description = ("Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\n"
                     "Selecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.")
    await it.followup.send(embed=e, view=ViewPainelPix())

@bot.tree.command(name="botconfig", description="Painel Config")
async def slash_botconfig(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    await it.response.defer(ephemeral=False)
    e = discord.Embed(title="Painel Config", color=COR_EMBED); e.set_thumbnail(url=ICONE_ORG)
    e.description = "**Painel Geral**\nUse os botões para editar."
    await it.followup.send(embed=e, view=ViewBotConfig())

@bot.tree.command(name="canal", description="Definir canal onde os tópicos serão criados")
async def slash_canal(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator: return
    db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_th", str(canal.id)))
    await interaction.response.send_message(f"✅ Canal definido: {canal.mention}", ephemeral=True)

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class ViewMediar(View):
        def gerar_embed(self):
            desc = "**Entre na fila para começar a mediar suas filas**\n\n"
            if not fila_mediadores: desc += "*A lista está vazia.*"
            else:
                for i, uid in enumerate(fila_mediadores): desc += f"**{i+1} •** <@{uid}> {uid}\n"
            emb = discord.Embed(title="Painel da fila controladora", description=desc, color=COR_EMBED)
            emb.set_thumbnail(url=ICONE_ORG)
            return emb
        @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢")
        async def entrar(self, it, b): 
            if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
        @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
        async def sair(self, it, b): 
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id); await it.response.edit_message(embed=self.gerar_embed())
        @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️")
        async def remover(self, it: discord.Interaction, b: Button):
            if not it.user.guild_permissions.manage_messages: return
            view_rem = View(); select = UserSelect(placeholder="Selecione o mediador para remover")
            async def cb_remover(interacao):
                alvo = select.values[0]
                if alvo.id in fila_mediadores:
                    fila_mediadores.remove(alvo.id)
                    await it.message.edit(embed=self.gerar_embed())
                    await interacao.response.send_message(f"✅ **{alvo.name}** removido.", ephemeral=True)
                else: await interacao.response.send_message("❌ Usuário não encontrado na fila.", ephemeral=True)
            select.callback = cb_remover; view_rem.add_item(select); await it.response.send_message("Quem remover?", view=view_rem, ephemeral=True)
        @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️")
        async def staff(self, it, b): await it.response.send_message("Log Staff", ephemeral=True)
    v = ViewMediar(); await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    
    class ModalFila(Modal, title="Gerar Filas"):
        m = TextInput(label="Modo", default="1v1")
        p = TextInput(label="Plataforma", default="Mobile")
        v = TextInput(label="Valores (Separe por ESPAÇO)", 
                      default="100,00 50,00 20,00 10,00 5,00",
                      style=discord.TextStyle.paragraph)

        async def on_submit(self, i):
            await i.response.send_message("Gerando filas...", ephemeral=True)
            
            raw_vals = self.v.value.split() 
            vals = []
            for val in raw_vals:
                val = val.strip()
                if ',' not in val: val += ",00"
                vals.append(val)

            if len(vals) > 15: vals = vals[:15]
            
            modo_formatado = f"{self.m.value}|{self.p.value}" 
            
            for val in vals:
                vi = ViewFila(modo_formatado, val)
                await i.channel.send(embed=vi.emb(), view=vi)
                await asyncio.sleep(0.5)
                
    class V(View):
        @discord.ui.button(label="Gerar", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(ModalFila())
    
    await ctx.send("Painel Admin", view=V())

# ==============================================================================
#           EVENTOS DE SEGURANÇA E INICIALIZAÇÃO
# ==============================================================================

# 1. EVENTO QUE IMPEDE O BOT DE ENTRAR EM SERVIDORES DESCONHECIDOS
@bot.event
async def on_guild_join(guild):
    # Se o ID do servidor novo não for o ID permitido, sai imediatamente
    if guild.id != ID_SERVIDOR_PERMITIDO:
        print(f"🚫 Tentativa de adicionar em servidor não autorizado: {guild.name} ({guild.id}). Saindo...")
        await guild.leave()

@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print("ONLINE - MONITORAMENTO DE SERVIDOR ATIVO")
    
    # 2. VARREDURA INICIAL: Se o bot já estiver em servidores errados, ele sai agora.
    for guild in bot.guilds:
        if guild.id != ID_SERVIDOR_PERMITIDO:
            print(f"👋 Saindo de servidor não autorizado detectado: {guild.name} ({guild.id})")
            await guild.leave()

if TOKEN: bot.run(TOKEN)
