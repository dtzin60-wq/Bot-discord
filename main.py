import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect
import sqlite3
import os
import asyncio
import traceback

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
# Se estiver no Railway, ele pega do Variables. Se for local, coloque seu token.
TOKEN = os.getenv("TOKEN") 

# Cores e Imagens (Edite conforme necessário)
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71
COR_ERRO = 0xff0000

# LINKS DAS IMAGENS (Substitua pelos seus links REAIS do Discord/Imgur)
BANNER_URL = "https://i.imgur.com/Xw0yYgH.png" 
ICONE_ORG = "https://i.imgur.com/Xw0yYgH.png"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache Global
fila_mediadores = []
partidas_ativas = {} 

# ==============================================================================
#                         BANCO DE DADOS (SQLite)
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0)")
        con.execute("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INTEGER DEFAULT 0)")
        con.execute("CREATE TABLE IF NOT EXISTS stats (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, derrotas INTEGER DEFAULT 0, consecutivas INTEGER DEFAULT 0)")

def db_exec(query, params=()):
    try:
        with sqlite3.connect("ws_database_final.db") as con:
            con.execute(query, params); con.commit()
    except Exception as e:
        print(f"Erro DB Exec: {e}")

def db_query(query, params=()):
    try:
        with sqlite3.connect("ws_database_final.db") as con:
            return con.execute(query, params).fetchone()
    except Exception as e:
        print(f"Erro DB Query: {e}")
        return None

def db_increment_counter(tipo):
    with sqlite3.connect("ws_database_final.db") as con:
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO counters (tipo, contagem) VALUES (?, 0)", (tipo,))
        cur.execute("UPDATE counters SET contagem = contagem + 1 WHERE tipo = ?", (tipo,))
        con.commit()
        res = cur.execute("SELECT contagem FROM counters WHERE tipo = ?", (tipo,)).fetchone()
        return res[0]

# ==============================================================================
#           VIEWS (BOTÕES) - BLINDADOS COM DEFER
# ==============================================================================

class ViewCopiarID(View):
    def __init__(self, id_sala):
        super().__init__(timeout=None)
        self.id_sala = id_sala

    @discord.ui.button(label="Copiar ID", style=discord.ButtonStyle.secondary, emoji="📋")
    async def copiar(self, it: discord.Interaction, btn: Button):
        # Ephemeral = Só você vê
        await it.response.send_message(f"{self.id_sala}", ephemeral=True)

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
        # BLINDAGEM: Defer adia a resposta para não dar timeout
        await it.response.defer()

        if it.user.id not in [j['id'] for j in self.jogadores]: 
            return await it.followup.send("Você não está nesta partida.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.followup.send("Você já confirmou.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        await it.channel.send(f"✅ **{it.user.mention}** confirmou!", delete_after=3)

        if len(self.confirms) >= len(self.jogadores):
            self.stop() # Para de escutar os botões
            
            # --- 1. CONFIGURAR NOME E CONTADORES ---
            modo_upper = self.modo_completo.upper()
            prefixo, tipo_db = "Sala", "geral"
            if "MOBILE" in modo_upper: prefixo, tipo_db = "Mobile", "mobile"
            elif "MISTO" in modo_upper: prefixo, tipo_db = "Misto", "misto"
            elif "FULL" in modo_upper: prefixo, tipo_db = "Full", "full"
            elif "EMU" in modo_upper: prefixo, tipo_db = "Emu", "emu"

            num = db_increment_counter(tipo_db)
            try: await it.channel.edit(name=f"{prefixo}-{num}")
            except: pass
            
            # --- 2. SALVAR DADOS (Para o mediador usar depois) ---
            partidas_ativas[it.channel.id] = {
                "modo": self.modo_completo,
                "jogadores": [j['m'] for j in self.jogadores],
                "mediador": self.med_id
            }

            # --- 3. BUSCAR PIX DO MEDIADOR ---
            dados_pix = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med_id,))
            msg_pix = ""
            if dados_pix:
                nome_med, chave_med, qr_med = dados_pix
                msg_pix = f"\n\n**💠 PAGAMENTO AO MEDIADOR**\n**Nome:** {nome_med}\n**Chave PIX:** `{chave_med}`"
                if qr_med and qr_med != "N/A": msg_pix += f"\n**QR Code:** {qr_med}"
            else:
                msg_pix = "\n\n⚠️ Mediador sem PIX cadastrado."

            # --- 4. LIMPEZA ---
            try: await it.channel.purge(limit=20)
            except: pass

            # --- 5. EMBED FINAL ---
            e = discord.Embed(title="Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            e.add_field(name="🎮 Estilo de Jogo", value=self.modo_completo, inline=False)
            
            try:
                v_f = float(self.valor.replace("R$","").replace(",",".").strip())
                taxa = max(v_f * 0.10, 0.10)
                taxa_str = f"R$ {taxa:.2f}".replace(".",",")
            except: taxa_str = "R$ 0,10"

            e.add_field(name="ℹ️ Informações", value=f"Valor Da Sala: {taxa_str}\nMediador: <@{self.med_id}>{msg_pix}", inline=False)
            e.add_field(name="💎 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            e.set_footer(text="Aguardando ID e Senha do Mediador...")
            
            await it.channel.send(content=f"<@{self.med_id}> {' '.join([j['m'] for j in self.jogadores])}", embed=e)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        await it.response.defer() # Blindagem
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.followup.send("🚫 Recusada. Fechando a sala...")
            await asyncio.sleep(2)
            await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it: discord.Interaction, btn: Button):
        await it.response.send_message(f"🏳️ {it.user.mention} sugeriu combinar regras.", ephemeral=False)

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

    async def join(self, it: discord.Interaction, tipo):
        # BLINDAGEM: Evita erro se o processamento for lento
        await it.response.defer()
        
        if any(j['id']==it.user.id for j in self.jogadores): 
            return await it.followup.send("Você já está na fila.", ephemeral=True)
            
        self.jogadores.append({'id':it.user.id,'m':it.user.mention,'t':tipo})
        await it.message.edit(embed=self.emb()) # Edita a mensagem da fila
        
        # Lógica de Limite de Jogadores
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        if len(self.jogadores)>=lim:
            if not fila_mediadores: 
                # Remove o último para não travar a fila se não tiver mediador
                self.jogadores.pop()
                await it.message.edit(embed=self.emb())
                return await it.followup.send("⚠️ Sem mediadores online no momento!", ephemeral=True)
            
            med = fila_mediadores.pop(0); fila_mediadores.append(med)
            
            cid = db_get_config("canal_th")
            if not cid: return await it.followup.send("❌ Admin: Use /canal para configurar onde criar os tópicos.")
            
            try:
                ch = bot.get_channel(int(cid))
                th = await ch.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.public_thread)
            except Exception as e:
                return await it.followup.send(f"Erro ao criar tópico: {e}", ephemeral=True)
            
            ew = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE); ew.set_thumbnail(url=IMAGEM_BONECA)
            ew.add_field(name="👑 Modo:", value=f"{self.modo_str.split('|')[0]} | {self.jogadores[0]['t'] or 'Padrão'}", inline=False)
            ew.add_field(name="💎 Valor:", value=f"R$ {self.valor}", inline=False)
            ew.add_field(name="⚡ Jogadores:", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            
            await th.send(content=" ".join([j['m'] for j in self.jogadores]), embed=ew, view=ViewConfirmacao(self.jogadores, med, self.valor, self.modo_str))
            
            # Limpa fila visualmente
            self.jogadores=[]
            await it.message.edit(embed=self.emb())

    async def leave(self, it: discord.Interaction):
        await it.response.defer()
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]
        await it.message.edit(embed=self.emb())

# ==============================================================================
#           MODAIS E PAINÉIS
# ==============================================================================

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m=Modal(title="Cadastrar Pix"); n=TextInput(label="Nome Completo"); c=TextInput(label="Chave Pix"); q=TextInput(label="Link/Texto QR Code", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def sub(i): 
            db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value))
            await i.response.send_message("✅ Pix salvo com sucesso!", ephemeral=True)
        m.on_submit=sub; await it.response.send_modal(m)
    @discord.ui.button(label="Ver Minha Chave", style=discord.ButtonStyle.primary, emoji="🔍")
    async def ver(self, it, b):
        await it.response.defer(ephemeral=True)
        d=db_query("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        if d: await it.followup.send(f"**Seus Dados:**\nNome: {d[1]}\nChave: `{d[2]}`", ephemeral=True)
        else: await it.followup.send("❌ Nenhum dado encontrado.", ephemeral=True)

class ViewBotConfig(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Como Criar Filas", style=discord.ButtonStyle.secondary, emoji="❓")
    async def btn_filas(self, it, b): await it.response.send_message("Use o comando `.fila` no chat.", ephemeral=True)

# ==============================================================================
#           COMANDOS
# ==============================================================================

@bot.command(name="p")
async def perfil_stats(ctx):
    try:
        # Busca Saldo
        saldo_data = db_query("SELECT saldo FROM pix_saldo WHERE user_id=?", (ctx.author.id,))
        saldo = f"{saldo_data[0]:.2f}".replace(".", ",") if saldo_data else "0,00"

        # Busca Stats
        stats = db_query("SELECT vitorias, derrotas, consecutivas FROM stats WHERE user_id=?", (ctx.author.id,))
        v, d, c = stats if stats else (0, 0, 0)
        total = v + d

        embed = discord.Embed(color=COR_VERDE)
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        embed.add_field(name="🎮 Estatísticas", value=f"Vitórias: {v}\nDerrotas: {d}\nConsecutivas: {c}\nTotal de Partidas: {total}", inline=False)
        embed.add_field(name="💎 Coins", value=f"Coins: {saldo}", inline=False)
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Erro ao gerar perfil: {e}")

@bot.tree.command(name="pix", description="Painel Pix")
async def slash_pix(it: discord.Interaction):
    e=discord.Embed(title="Painel Pix", description="Cadastre sua chave PIX para receber pagamentos como mediador.", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG)
    await it.response.send_message(embed=e, view=ViewPainelPix())

@bot.tree.command(name="botconfig", description="Painel Config")
async def slash_botconfig(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    await it.response.send_message("Painel de Configuração", view=ViewBotConfig())

@bot.tree.command(name="canal", description="Definir canal de criação de tópicos")
async def slash_canal(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator: return
    db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_th", str(canal.id)))
    await interaction.response.send_message(f"✅ Canal definido: {canal.mention}", ephemeral=True)

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class ViewMediar(View):
        def gerar_embed(self):
            desc = "**Lista de Mediadores Online:**\n" + ("\n".join([f"• <@{uid}>" for uid in fila_mediadores]) if fila_mediadores else "*Vazia*")
            return discord.Embed(title="Painel de Mediadores", description=desc, color=COR_EMBED)
        @discord.ui.button(label="Entrar/Sair da Fila", style=discord.ButtonStyle.primary)
        async def toggle(self, it, b): 
            await it.response.defer()
            if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
            else: fila_mediadores.append(it.user.id)
            await it.message.edit(embed=self.gerar_embed())
    v = ViewMediar(); await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class ModalFila(Modal, title="Criar Filas de Aposta"):
        m = TextInput(label="Modo (ex: 4v4)", default="1v1")
        p = TextInput(label="Plataforma", default="Mobile")
        v = TextInput(label="Valores (Separe por ESPAÇO)", default="10 20 50", style=discord.TextStyle.paragraph)
        async def on_submit(self, i):
            await i.response.send_message("✅ Criando filas...", ephemeral=True)
            for val in self.v.value.split():
                if ',' not in val: val += ",00"
                # Cria a View e Embed
                view_f = ViewFila(f"{self.m.value}|{self.p.value}", val)
                await i.channel.send(embed=view_f.emb(), view=view_f)
                await asyncio.sleep(1)
    class V(View):
        @discord.ui.button(label="Gerar Filas", style=discord.ButtonStyle.success)
        async def g(self, i, b): await i.response.send_modal(ModalFila())
    await ctx.send("Painel Admin - Gerar Filas", view=V())

# ==============================================================================
#           EVENTOS (AUTOMÁTICOS)
# ==============================================================================

@bot.event
async def on_message(message):
    if message.author.bot: return
    await bot.process_commands(message) 

    # --- LÓGICA DO MEDIADOR (ID E SENHA) ---
    if message.channel.id in partidas_ativas:
        try:
            dados = partidas_ativas[message.channel.id]
            
            # Se quem digitou é o mediador
            if message.author.id == dados["mediador"]:
                conteudo = message.content.strip().split()
                
                # Verifica se parece ID e Senha (ex: "12345 55")
                if len(conteudo) >= 2 and conteudo[0].isdigit():
                    sala_id = conteudo[0]
                    sala_senha = conteudo[1]

                    # Apaga a mensagem feia do mediador
                    try: await message.delete()
                    except: pass

                    # Cria Embed Bonita
                    embed = discord.Embed(title="Sala Criada", color=COR_VERDE)
                    embed.set_thumbnail(url=IMAGEM_BONECA)
                    
                    embed.add_field(name="Modo", value=dados['modo'], inline=False)
                    embed.add_field(name="Jogadores", value="\n".join(dados['jogadores']), inline=False)
                    
                    embed.add_field(name="🆔 ID", value=f"```{sala_id}```", inline=True)
                    embed.add_field(name="🔒 Senha", value=f"```{sala_senha}```", inline=True)

                    # Botão de Copiar
                    await message.channel.send(embed=embed, view=ViewCopiarID(sala_id))
                    
                    # (Opcional) Remove da memória se quiser encerrar a automação aqui
                    # del partidas_ativas[message.channel.id]
        except Exception as e:
            print(f"Erro no Auto-Mediador: {e}")

@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print(f"Bot Online: {bot.user} - ID: {bot.user.id}")

if TOKEN:
    bot.run(TOKEN)
        
