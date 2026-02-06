import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect, ChannelSelect, RoleSelect
import sqlite3
import os
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES GERAIS
# ==============================================================================
TOKEN = os.getenv("TOKEN")
ID_SERVIDOR_PERMITIDO = 1465929927206375527 

# Cores
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71

# ✅ BANNER (Garantido em todas as telas)
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache de Controle
partidas_andamento = {} # Controla o fluxo de ID/Senha nos canais
fila_mediadores = []    # Lista de staff online

# ==============================================================================
#                         BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0)")
        con.execute("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INTEGER DEFAULT 0)")

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
#           VIEW: FINAL (ID, SENHA E BOTÃO COPIAR)
# ==============================================================================
class ViewCredenciais(View):
    def __init__(self, sala_id):
        super().__init__(timeout=None)
        self.sala_id = sala_id

    # BOTÃO CINZA (Secondary) EXATAMENTE COMO PEDIU
    @discord.ui.button(label="Copiar id", style=discord.ButtonStyle.secondary, emoji="📋")
    async def copiar_id(self, it: discord.Interaction, btn: Button):
        # Envia o ID limpo apenas para quem clicou
        await it.response.send_message(f"{self.sala_id}", ephemeral=True)

# ==============================================================================
#           VIEW: CONFIRMAÇÃO (DENTRO DO TÓPICO)
# ==============================================================================
class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor, modo_completo):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.med_id = med_id
        self.valor = valor
        self.modo_completo = modo_completo
        self.confirms = []

    @discord.ui.button(label="Confirmar Presença", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, it: discord.Interaction, btn: Button):
        if it.user.id not in [j['id'] for j in self.jogadores]: 
            return await it.response.send_message("❌ O senhor(a) não consta na lista desta partida.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.response.send_message("⚠️ Sua presença já foi confirmada.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        await it.channel.send(f"✅ **{it.user.mention}** confirmou presença.")

        # Quando todos confirmarem
        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            
            # 1. Renomeia o canal para Sala-X
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
            
            # 2. Ativa o "modo escuta" para pegar ID e Senha
            partidas_andamento[it.channel.id] = {
                "mediador": self.med_id,
                "valor": self.valor,
                "step": 0, # 0 = esperando ID, 1 = esperando Senha
                "room_id": None,
                "modo_str": self.modo_completo,
                "jogadores_str": "\n".join([j['m'] for j in self.jogadores])
            }

            # 3. Aviso Formal para o Mediador
            e = discord.Embed(title="Aguardando Credenciais", color=COR_CONFIRMADO)
            e.description = (
                f"Prezado Mediador <@{self.med_id}>,\n\n"
                f"Os jogadores confirmaram presença.\n"
                f"Por favor, proceda com o envio das credenciais no seguinte formato:\n\n"
                f"1️⃣ Envie apenas o **ID** da sala (numérico).\n"
                f"2️⃣ Em seguida, envie a **SENHA**."
            )
            e.set_image(url=BANNER_URL)
            
            await it.channel.send(content=f"<@{self.med_id}>", embed=e)
            
            # Paga comissão do mediador
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Cancelar Partida", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.channel.send("🚫 Partida cancelada pelos participantes."); await asyncio.sleep(2); await it.channel.delete()

# ==============================================================================
#           VIEW: FILA (BANNER AQUI)
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
            b=Button(label="Entrar na Fila", style=discord.ButtonStyle.success); b.callback=lambda i: self.join(i,None); self.add_item(b)
        bs=Button(label="Sair", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)

    def emb(self):
        titulo = f"Aposta | {self.modo_str.replace('|', ' ')}"
        e = discord.Embed(title=titulo, color=COR_EMBED)
        e.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="📋 Modalidade", value=f"**{self.modo_str.replace('|', ' ')}**", inline=True)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        
        lista = "\n".join([f"👤 {j['m']}" for j in self.jogadores])
        if not lista: lista = "*Aguardando...*"
        
        e.add_field(name="👥 Jogadores", value=lista, inline=False)
        e.set_image(url=BANNER_URL) # Banner na Fila
        return e

    async def join(self, it, tipo):
        if any(j['id']==it.user.id for j in self.jogadores): return await it.response.send_message("O senhor(a) já se encontra na fila.", ephemeral=True)
        self.jogadores.append({'id':it.user.id,'m':it.user.mention,'t':tipo}); await it.response.edit_message(embed=self.emb())
        
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        
        if len(self.jogadores)>=lim:
            if not fila_mediadores: return await it.channel.send("⚠️ **Aviso:** Nenhum mediador disponível no momento.", delete_after=5)
            med = fila_mediadores.pop(0); fila_mediadores.append(med)
            
            cid = db_get_config("canal_th")
            if not cid: return await it.channel.send("❌ Sistema não configurado (/canal).")
            
            ch = bot.get_channel(int(cid))
            th = await ch.create_thread(name="aguardando-inicio", type=discord.ChannelType.public_thread)
            
            # --- MENSAGEM DE BOAS VINDAS FORMAL ---
            msg_formal = (
                f"Prezados Senhores,\n\n"
                f"Sejam cordialmente bem-vindos à **WS APOSTAS**.\n"
                f"Solicitamos a gentileza de aguardarem as instruções do mediador <@{med}>.\n"
                f"Mantenham a postura e o respeito durante todo o procedimento.\n\n"
                f"**Informações da Partida:**\n"
                f"• Modalidade: {self.modo_str}\n"
                f"• Valor: R$ {self.valor}"
            )
            
            ew = discord.Embed(description=msg_formal, color=COR_EMBED)
            ew.set_image(url=BANNER_URL) # Banner no Boas-vindas
            
            await th.send(content=f"{' '.join([j['m'] for j in self.jogadores])} <@{med}>", embed=ew, view=ViewConfirmacao(self.jogadores, med, self.valor, self.modo_str))
            self.jogadores=[]; await it.message.edit(embed=self.emb())

    async def leave(self, it):
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]; await it.response.edit_message(embed=self.emb())

# ==============================================================================
#           EVENTO DE MENSAGEM (LÓGICA DO ID E SENHA)
# ==============================================================================
@bot.event
async def on_message(message):
    if message.author.bot: return

    # Verifica se o canal está esperando ID/Senha
    if message.channel.id in partidas_andamento:
        dados = partidas_andamento[message.channel.id]
        
        # Só aceita mensagem do mediador daquela partida
        if message.author.id == dados["mediador"]:
            
            # PASSO 1: O MEDIADOR ENVIOU O ID
            if dados["step"] == 0:
                dados["room_id"] = message.content
                dados["step"] = 1 # Avança para esperar a senha
                partidas_andamento[message.channel.id] = dados
                
                # Reage com ✅ para confirmar que pegou o ID
                await message.add_reaction("✅")
            
            # PASSO 2: O MEDIADOR ENVIOU A SENHA
            elif dados["step"] == 1:
                senha = message.content
                room_id = dados["room_id"]
                
                # Tenta apagar a mensagem da senha para não ficar exposta
                try: await message.delete()
                except: pass
                
                # --- MONTA O EMBED FINAL BONITO ---
                e = discord.Embed(color=COR_VERDE)
                e.set_thumbnail(url=IMAGEM_BONECA)
                
                e.add_field(name="Modo:", value=dados['modo_str'], inline=False)
                e.add_field(name="Jogadores:", value=dados['jogadores_str'], inline=False)
                e.add_field(name="Mediador:", value=f"<@{dados['mediador']}>", inline=False)
                
                # Formatação exata que pediu
                e.add_field(name="Id:", value=f"```{room_id}```", inline=False)
                e.add_field(name="Senha:", value=f"```{senha}```", inline=False)
                
                # Banner no final também
                e.set_image(url=BANNER_URL)
                
                # Envia com o botão CINZA "Copiar id"
                await message.channel.send(embed=e, view=ViewCredenciais(room_id))
                
                # Renomeia o canal para pagar-{valor}
                v_limpo = dados['valor'].replace("R$", "").strip().replace(",", ".")
                try: await message.channel.edit(name=f"pagar-{v_limpo}")
                except: pass
                
                # Limpa da memória
                del partidas_andamento[message.channel.id]

    await bot.process_commands(message)

# ==============================================================================
#           MODAL E COMANDOS SLASH
# ==============================================================================
class ModalCriarFila(Modal, title="Criar Fila"):
    m = TextInput(label="Modo", default="1v1", placeholder="Ex: 1v1, 4v4")
    p = TextInput(label="Plataforma", default="Mobile", placeholder="Ex: Mobile, Emu")
    v = TextInput(label="Valores (espaço)", default="10 20 50", placeholder="Ex: 5 10 20")

    async def on_submit(self, i):
        await i.response.send_message("Criando filas...", ephemeral=True)
        for val in self.v.value.split():
            val = val.strip()
            if "," not in val: val += ",00"
            vi = ViewFila(f"{self.m.value}|{self.p.value}", val)
            await i.channel.send(embed=vi.emb(), view=vi)
            await asyncio.sleep(0.5)

@bot.tree.command(name="criar_fila", description="Cria novas filas de aposta")
async def slash_criar(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: 
        return await it.response.send_message("Apenas administradores.", ephemeral=True)
    await it.response.send_modal(ModalCriarFila())

@bot.tree.command(name="pix", description="Configurar Pix")
async def slash_pix(it: discord.Interaction):
    await it.response.send_message("Painel Pix (Em breve)", ephemeral=True)

@bot.tree.command(name="canal", description="Definir canal de tópicos")
async def slash_canal(it: discord.Interaction, canal: discord.TextChannel):
    if not it.user.guild_permissions.administrator: return
    db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_th", str(canal.id)))
    await it.response.send_message(f"✅ Canal definido: {canal.mention}", ephemeral=True)

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class V(View):
        @discord.ui.button(label="Entrar/Sair Staff", style=discord.ButtonStyle.primary)
        async def t(self, i, b):
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.send_message("Saiu da lista de mediadores.", ephemeral=True)
            else: fila_mediadores.append(i.user.id); await i.response.send_message("Entrou na lista de mediadores.", ephemeral=True)
    await ctx.send("Painel Staff", view=V())

# ==============================================================================
#           INICIALIZAÇÃO E SYNC
# ==============================================================================
@bot.event
async def on_guild_join(guild):
    # Sai se não for o servidor permitido
    if guild.id != ID_SERVIDOR_PERMITIDO:
        print(f"Saindo de {guild.name}")
        await guild.leave()

@bot.event
async def on_ready():
    init_db()
    
    # Sincronização rápida para o seu servidor
    try:
        guild_alvo = discord.Object(id=ID_SERVIDOR_PERMITIDO)
        bot.tree.clear_commands(guild=None) # Limpa globais duplicados
        bot.tree.copy_global_to(guild=guild_alvo)
        await bot.tree.sync(guild=guild_alvo)
        print("✅ Comandos Slash Atualizados!")
    except Exception as e:
        print(f"Erro no sync: {e}")
        
    print(f"ONLINE - SERVIDOR: {ID_SERVIDOR_PERMITIDO}")

if TOKEN: bot.run(TOKEN)
            
