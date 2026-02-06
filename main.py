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
ID_SERVIDOR_PERMITIDO = 1465929927206375527 

# Cores e Imagens
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71

# ✅ BANNER GARANTIDO (Aparecerá grande)
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache para controlar o fluxo de ID e Senha nos tópicos
# Formato: {id_do_canal: {"mediador": id_user, "valor": "20,00", "step": 0, "room_id": None}}
partidas_andamento = {}
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
#           VIEW: CREDENCIAIS (FINAL DA LOGICA ID/SENHA)
# ==============================================================================
class ViewCredenciais(View):
    def __init__(self, sala_id, sala_senha):
        super().__init__(timeout=None)
        self.sala_id = sala_id
        self.sala_senha = sala_senha

    @discord.ui.button(label="Copiar ID", style=discord.ButtonStyle.secondary, emoji="📋")
    async def copiar_id(self, it: discord.Interaction, btn: Button):
        # O Discord não permite copiar direto para a área de transferência via botão nativo,
        # então enviamos uma mensagem efêmera (só a pessoa vê) com o ID limpo.
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
            return await it.response.send_message("❌ Você não está escalado para esta partida.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.response.send_message("⚠️ Você já confirmou sua presença.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        await it.channel.send(f"✅ **{it.user.mention}** confirmou presença!")

        # Se todos confirmarem
        if len(self.confirms) >= len(self.jogadores):
            self.stop() # Para os botões
            
            # 1. Renomear Tópico Inicial
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
            
            # 2. Registrar no sistema de "Escuta" para ID/Senha
            partidas_andamento[it.channel.id] = {
                "mediador": self.med_id,
                "valor": self.valor,
                "step": 0,      # 0 = esperando ID, 1 = esperando Senha
                "room_id": None
            }

            # 3. Embed Bonita de Instruções
            e = discord.Embed(title="🎮 Partida Iniciada", color=COR_CONFIRMADO)
            e.description = (
                f"A partida foi confirmada com sucesso.\n\n"
                f"👤 **Mediador Responsável:** <@{self.med_id}>\n"
                f"💰 **Valor Apostado:** R$ {self.valor}\n\n"
                f"ℹ️ **Instruções para o Mediador:**\n"
                f"> 1. Digite o **ID** da sala no chat.\n"
                f"> 2. Em seguida, digite a **SENHA**.\n"
                f"> *O sistema formatará automaticamente.*"
            )
            e.set_image(url=BANNER_URL) # Banner aqui também
            
            await it.channel.send(content=f"<@{self.med_id}>", embed=e)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.channel.send("🚫 A partida foi cancelada por um jogador."); await asyncio.sleep(2); await it.channel.delete()

    @discord.ui.button(label="Regras", style=discord.ButtonStyle.secondary, emoji="📜")
    async def regras(self, it: discord.Interaction, btn: Button):
        await it.response.send_message(f"📜 {it.user.mention} solicitou a revisão das regras.", ephemeral=False)

# ==============================================================================
#           VIEW: FILA PRINCIPAL
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
        
        lista_jog = "\n".join([f"👤 {j['m']}" for j in self.jogadores])
        if not lista_jog: lista_jog = "*Aguardando jogadores...*"
        
        e.add_field(name="👥 Jogadores na Fila", value=lista_jog, inline=False)
        e.set_image(url=BANNER_URL) # Banner na Fila
        return e

    async def join(self, it, tipo):
        if any(j['id']==it.user.id for j in self.jogadores): return await it.response.send_message("Você já está na fila!", ephemeral=True)
        self.jogadores.append({'id':it.user.id,'m':it.user.mention,'t':tipo}); await it.response.edit_message(embed=self.emb())
        
        # Limite de jogadores (ex: 1v1 = 2, 4v4 = 8)
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        
        if len(self.jogadores)>=lim:
            if not fila_mediadores: return await it.channel.send("⚠️ **Atenção:** Nenhum mediador online no momento!", delete_after=5)
            
            med = fila_mediadores.pop(0); fila_mediadores.append(med)
            cid = db_get_config("canal_th")
            if not cid: return await it.channel.send("❌ Canal de tópicos não configurado.")
            
            ch = bot.get_channel(int(cid))
            # Cria o tópico
            th = await ch.create_thread(name="aguardando-inicio", type=discord.ChannelType.public_thread)
            
            # --- MENSAGEM DE BOAS VINDAS FORMAL ---
            texto_boas_vindas = (
                f"Prezados {', '.join([j['m'] for j in self.jogadores])} e mediador <@{med}>,\n\n"
                f"Sejam cordialmente bem-vindos à sala de apostas da **WS APOSTAS**.\n"
                f"Solicitamos que mantenham a cordialidade e aguardem as instruções.\n\n"
                f"**Detalhes da Partida:**\n"
                f"• Modalidade: {self.modo_str}\n"
                f"• Valor: R$ {self.valor}"
            )
            
            e_welcome = discord.Embed(description=texto_boas_vindas, color=COR_EMBED)
            e_welcome.set_image(url=BANNER_URL) # Banner na mensagem de boas vindas
            
            await th.send(content=" ".join([j['m'] for j in self.jogadores]), embed=e_welcome, view=ViewConfirmacao(self.jogadores, med, self.valor, self.modo_str))
            
            self.jogadores=[]; await it.message.edit(embed=self.emb())

    async def leave(self, it):
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]; await it.response.edit_message(embed=self.emb())

# ==============================================================================
#           EVENTO PRINCIPAL: ESCUTA O CHAT PARA ID E SENHA
# ==============================================================================
@bot.event
async def on_message(message):
    if message.author.bot: return

    # Verifica se a mensagem está num canal que está esperando ID/Senha
    if message.channel.id in partidas_andamento:
        dados = partidas_andamento[message.channel.id]
        
        # Só o mediador pode mandar
        if message.author.id == dados["mediador"]:
            
            # Verifica se é um número (ID ou Senha geralmente são numéricos)
            # Se quiser aceitar letras também, remova o .isdigit()
            if True: # Aceita qualquer coisa para evitar bugs se a senha tiver letra
                
                # PASSO 1: PEGAR O ID
                if dados["step"] == 0:
                    dados["room_id"] = message.content
                    dados["step"] = 1 # Avança para esperar a senha
                    partidas_andamento[message.channel.id] = dados # Atualiza
                    
                    # Reage com ✅ e apaga a mensagem do mediador para limpar
                    await message.add_reaction("✅")
                
                # PASSO 2: PEGAR A SENHA E FINALIZAR
                elif dados["step"] == 1:
                    senha = message.content
                    room_id = dados["room_id"]
                    valor = dados["valor"]
                    
                    # Apaga a mensagem da senha para segurança (opcional, mas fica limpo)
                    try: await message.delete() 
                    except: pass
                    
                    # Cria o Embed Final Bonito
                    embed_final = discord.Embed(title="Credenciais da Sala", color=COR_VERDE)
                    embed_final.set_thumbnail(url=IMAGEM_BONECA)
                    
                    embed_final.add_field(name="🆔 ID da Sala", value=f"```{room_id}```", inline=True)
                    embed_final.add_field(name="🔒 Senha", value=f"```{senha}```", inline=True)
                    
                    embed_final.set_footer(text="Copie o ID abaixo | Bom jogo a todos!")
                    embed_final.set_image(url=BANNER_URL)
                    
                    # Envia o painel com botão de copiar
                    await message.channel.send(embed=embed_final, view=ViewCredenciais(room_id, senha))
                    
                    # Renomeia o tópico para pagar-{valor}
                    # Remove R$ e espaços para ficar limpo no nome do canal
                    valor_limpo = valor.replace("R$", "").strip().replace(",", ".")
                    try:
                        await message.channel.edit(name=f"pagar-{valor_limpo}")
                    except Exception as e:
                        print(f"Erro ao renomear canal: {e}")
                    
                    # Remove da lista de monitoramento (já acabou o processo)
                    del partidas_andamento[message.channel.id]

    await bot.process_commands(message)

# ==============================================================================
#           MODAL E COMANDOS
# ==============================================================================
class ModalCriarFila(Modal, title="Criar Fila"):
    m = TextInput(label="Modo", default="1v1")
    p = TextInput(label="Plataforma", default="Mobile")
    v = TextInput(label="Valores (espaço)", default="10 20 50")
    async def on_submit(self, i):
        await i.response.send_message("Gerando...", ephemeral=True)
        for val in self.v.value.split():
            val = val.strip()
            if "," not in val: val += ",00"
            vi = ViewFila(f"{self.m.value}|{self.p.value}", val)
            await i.channel.send(embed=vi.emb(), view=vi)
            await asyncio.sleep(0.5)

@bot.tree.command(name="criar_fila")
async def slash_criar(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    await it.response.send_modal(ModalCriarFila())

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class V(View):
        @discord.ui.button(label="Entrar/Sair Fila Staff", style=discord.ButtonStyle.primary)
        async def t(self, i, b):
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.send_message("Saiu.", ephemeral=True)
            else: fila_mediadores.append(i.user.id); await i.response.send_message("Entrou.", ephemeral=True)
    await ctx.send("Painel Staff", view=V())

# ==============================================================================
#           INICIALIZAÇÃO
# ==============================================================================
@bot.event
async def on_guild_join(guild):
    if guild.id != ID_SERVIDOR_PERMITIDO: await guild.leave()

@bot.event
async def on_ready():
    init_db()
    # Sincronia limpa
    bot.tree.clear_commands(guild=None)
    bot.tree.copy_global_to(guild=discord.Object(id=ID_SERVIDOR_PERMITIDO))
    await bot.tree.sync(guild=discord.Object(id=ID_SERVIDOR_PERMITIDO))
    print(f"BOT ONLINE - PROTEGIDO ID: {ID_SERVIDOR_PERMITIDO}")

if TOKEN: bot.run(TOKEN)
                       
