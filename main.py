import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect
import sqlite3
import os
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES GERAIS
# ==============================================================================
# Tente pegar do ambiente ou coloque sua string direta aqui para testes (Cuidado ao compartilhar)
TOKEN = os.getenv("TOKEN") 

# Cores e Imagens
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_VERMELHO = 0xe74c3c
COR_CONFIRMADO = 0x2ecc71

# Imagens (Substitua por links permanentes se estes expirarem)
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache em memória (Reinicia se o bot desligar)
fila_mediadores = []

# ==============================================================================
#                         BANCO DE DADOS (SQLite)
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS pix_saldo (user_id INTEGER PRIMARY KEY, saldo REAL DEFAULT 0.0)")
        con.execute("CREATE TABLE IF NOT EXISTS counters (tipo TEXT PRIMARY KEY, contagem INTEGER DEFAULT 0)")

def db_exec(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute(query, params)
        con.commit()

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
#           VIEW: CONFIRMAÇÃO DA PARTIDA (DENTRO DO TÓPICO)
# ==============================================================================
class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor, modo_completo):
        super().__init__(timeout=None)
        self.jogadores = jogadores
        self.med_id = med_id
        self.valor = valor
        self.modo_completo = modo_completo
        self.confirms = []

    @discord.ui.button(label="Confirmar Partida", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, it: discord.Interaction, btn: Button):
        # Verifica se quem clicou está na partida
        if it.user.id not in [j['id'] for j in self.jogadores]: 
            return await it.response.send_message("Você não está nesta partida.", ephemeral=True)
        
        # Verifica se já confirmou
        if it.user.id in self.confirms: 
            return await it.response.send_message("Você já confirmou.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        await it.channel.send(f"✅ **{it.user.mention}** confirmou a partida! ({len(self.confirms)}/{len(self.jogadores)})")

        # Se todos confirmaram
        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            self.clear_items() # Remove botões
            
            # Lógica de renomear o canal/tópico
            modo_upper = self.modo_completo.upper()
            prefixo = "Sala"
            tipo_db = "geral"

            if "MOBILE" in modo_upper: prefixo, tipo_db = "Mobile", "mobile"
            elif "MISTO" in modo_upper: prefixo, tipo_db = "Misto", "misto"
            elif "FULL" in modo_upper: prefixo, tipo_db = "Full", "full"
            elif "EMU" in modo_upper: prefixo, tipo_db = "Emu", "emu"

            num = db_increment_counter(tipo_db)
            
            try: 
                await it.channel.edit(name=f"{prefixo}-{num}", locked=True)
            except: 
                pass # Pode falhar se não tiver permissão
            
            # Formatar estilo
            try: 
                estilo = f"{self.modo_completo.split('|')[0].strip()} Gel Normal"
            except: 
                estilo = self.modo_completo

            # Embed Final
            e = discord.Embed(title=f"Partida Iniciada #{num}", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            e.add_field(name="🎮 Estilo", value=estilo, inline=True)
            
            # Calculo taxa
            try:
                v_clean = self.valor.replace("R$","").replace(" ","").replace(".","").replace(",",".")
                v_f = float(v_clean)
                taxa = max(v_f * 0.10, 0.10) # 10% ou minimo 10 centavos
                taxa_str = f"R$ {taxa:.2f}".replace(".",",")
            except: 
                taxa_str = "R$ ???"

            e.add_field(name="ℹ️ Info", value=f"Taxa Sala: **{taxa_str}**\nMediador: <@{self.med_id}>", inline=True)
            e.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=False)
            
            lista_jogadores = "\n".join([f"• {j['m']}" for j in self.jogadores])
            e.add_field(name="👥 Jogadores", value=lista_jogadores, inline=False)
            
            # Menciona todos
            mentions = f"<@{self.med_id}> " + " ".join([j['m'] for j in self.jogadores])
            await it.channel.send(content=mentions, embed=e)
            
            # Paga o mediador no banco de dados (simbolico)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Cancelar/Recusar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores] or it.user.id == self.med_id:
            await it.channel.send(f"🚫 Partida cancelada por {it.user.mention}. Fechando tópico...")
            self.stop()
            await asyncio.sleep(3)
            await it.channel.delete()
        else:
            await it.response.send_message("Apenas jogadores ou o mediador podem cancelar.", ephemeral=True)

# ==============================================================================
#           VIEW: FILA DE ESPERA (BOTÃO DE ENTRAR)
# ==============================================================================
class ViewFila(View):
    def __init__(self, modo_str, valor):
        super().__init__(timeout=None)
        self.modo_str = modo_str
        self.valor = valor
        self.jogadores = [] # Lista de dicionarios {'id': int, 'm': mention, 't': tipo}
        self._btns()

    def _btns(self):
        self.clear_items()
        # Se for 1v1, mostra opções de Gelo, senão botão normal
        if "1V1" in self.modo_str.upper():
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary, custom_id=f"gn_{self.valor}_{self.modo_str}")
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, custom_id=f"gi_{self.valor}_{self.modo_str}")
            b1.callback = lambda i: self.join(i, "Gel Normal")
            b2.callback = lambda i: self.join(i, "Gel Infinito")
            self.add_item(b1)
            self.add_item(b2)
        else:
            b = Button(label="Entrar na Fila", style=discord.ButtonStyle.success, emoji="🎮", custom_id=f"entrar_{self.valor}_{self.modo_str}")
            b.callback = lambda i: self.join(i, "Padrão")
            self.add_item(b)
        
        bs = Button(label="Sair", style=discord.ButtonStyle.danger, custom_id=f"sair_{self.valor}_{self.modo_str}")
        bs.callback = self.leave
        self.add_item(bs)

    def emb(self):
        e = discord.Embed(title=f"Aposta | {self.modo_str.replace('|', ' ')}", color=COR_EMBED)
        e.set_author(name="SISTEMA DE APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="📋 Modalidade", value=f"**{self.modo_str.replace('|', ' ')}**", inline=True)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        
        lista_visual = []
        for j in self.jogadores:
            tipo = f" ({j['t']})" if "1V1" in self.modo_str.upper() else ""
            lista_visual.append(f"👤 {j['m']}{tipo}")
            
        e.add_field(name=f"👥 Fila ({len(self.jogadores)})", value="\n".join(lista_visual) or "*Aguardando jogadores...*", inline=False)
        e.set_image(url=BANNER_URL)
        e.set_footer(text="WS Apostas System")
        return e

    async def join(self, it: discord.Interaction, tipo: str):
        if any(j['id'] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Você já está nesta fila!", ephemeral=True)
        
        self.jogadores.append({'id': it.user.id, 'm': it.user.mention, 't': tipo})
        await it.response.edit_message(embed=self.emb(), view=self)
        
        # Define limite baseado no modo (ex: 1v1 = 2, 4v4 = 8)
        try:
            primeiro_char = self.modo_str.split('v')[0].strip() # Pega o "1" de "1v1" ou "4" de "4v4"
            limite = int(primeiro_char) * 2
        except:
            limite = 2 # Padrão
            
        if len(self.jogadores) >= limite:
            # Verifica Mediador
            if not fila_mediadores:
                await it.channel.send(f"⚠️ {it.user.mention} A sala encheu, mas **não há mediadores online**! Aguardem.", delete_after=10)
                return
            
            # Verifica Canal de Tópicos
            cid = db_get_config("canal_th")
            if not cid:
                await it.channel.send("❌ Erro: Canal de tópicos não configurado (/canal).")
                return
            
            canal_alvo = bot.get_channel(int(cid))
            if not canal_alvo:
                await it.channel.send("❌ Erro: Canal de tópicos não encontrado.")
                return

            # Pega Mediador
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) # Coloca no final da fila (rotativo)

            # Cria Tópico
            nome_thread = f"confirmar-{self.modo_str}-{len(self.jogadores)}p"
            th = await canal_alvo.create_thread(name=nome_thread, type=discord.ChannelType.public_thread)
            
            # Embed de boas vindas no tópico
            ew = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE)
            ew.set_thumbnail(url=IMAGEM_BONECA)
            ew.add_field(name="👑 Modo", value=f"{self.modo_str} | {self.jogadores[0]['t']}", inline=False)
            ew.add_field(name="💎 Valor", value=f"R$ {self.valor}", inline=False)
            ew.add_field(name="👮 Mediador", value=f"<@{med_id}>", inline=False)
            ew.description = "```✨ SEJAM MUITO BEM-VINDOS ✨\n\n• Regras adicionais podem ser combinadas.\n• Obrigatório print do acordo.```"
            
            view_conf = ViewConfirmacao(self.jogadores[:], med_id, self.valor, self.modo_str)
            await th.send(content=" ".join([j['m'] for j in self.jogadores]) + f" <@{med_id}>", embed=ew, view=view_conf)
            
            # Limpa fila principal
            self.jogadores = []
            await it.message.edit(embed=self.emb(), view=self)
            await it.channel.send(f"✅ Sala criada em {th.mention}!", delete_after=10)

    async def leave(self, it: discord.Interaction):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.emb(), view=self)

# ==============================================================================
#           PAINÉIS AUXILIARES (PIX, STAFF, ETC)
# ==============================================================================

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m = Modal(title="Cadastrar Pix")
        n = TextInput(label="Nome Completo")
        c = TextInput(label="Chave Pix")
        q = TextInput(label="Link QR Code (Opcional)", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        
        async def sub(i):
            db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value))
            await i.response.send_message("✅ Pix salvo com sucesso!", ephemeral=True)
        
        m.on_submit = sub
        await it.response.send_modal(m)

    @discord.ui.button(label="Ver Seu Pix", style=discord.ButtonStyle.primary, emoji="👁️")
    async def ver(self, it, b):
        d = db_query("SELECT * FROM pix WHERE user_id=?", (it.user.id,))
        if d: 
            await it.response.send_message(f"👤 **Nome:** {d[1]}\n🔑 **Chave:** `{d[2]}`\n🖼️ **QR:** {d[3] or 'N/A'}", ephemeral=True)
        else: 
            await it.response.send_message("❌ Você não tem pix cadastrado.", ephemeral=True)

class ViewMediadorFila(View):
    def __init__(self): super().__init__(timeout=None)

    def gerar_embed(self):
        desc = "**Fila de Mediadores Ativos**\n\n"
        if not fila_mediadores: 
            desc += "*Nenhum mediador online no momento.*"
        else:
            for i, uid in enumerate(fila_mediadores): 
                desc += f"**{i+1}º** <@{uid}>\n"
        
        emb = discord.Embed(title="Painel de Controle - Mediadores", description=desc, color=COR_EMBED)
        emb.set_thumbnail(url=ICONE_ORG)
        emb.set_footer(text=f"Total: {len(fila_mediadores)}")
        return emb

    @discord.ui.button(label="Entrar na Fila (Work)", style=discord.ButtonStyle.success, emoji="🟢")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed(), view=self)
        else:
            await it.response.send_message("Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da Fila (Sleep)", style=discord.ButtonStyle.danger, emoji="🔴")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed(), view=self)
        else:
            await it.response.send_message("Você não está na fila.", ephemeral=True)

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, it, b):
        await it.response.edit_message(embed=self.gerar_embed(), view=self)

# ==============================================================================
#           COMANDOS SLASH
# ==============================================================================

@bot.tree.command(name="pix", description="Abre o painel para gerenciar sua chave PIX")
async def slash_pix(it: discord.Interaction):
    await it.response.defer(ephemeral=True)
    e = discord.Embed(title="Gerenciamento Pix", description="Cadastre sua chave para receber pagamentos.", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG)
    await it.followup.send(embed=e, view=ViewPainelPix(), ephemeral=True)

@bot.tree.command(name="canal", description="Define o canal onde os tópicos de aposta serão criados")
async def slash_canal(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Sem permissão.", ephemeral=True)
    
    db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_th", str(canal.id)))
    await interaction.response.send_message(f"✅ Canal de tópicos definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="mediar", description="Abre o painel para STAFF entrar na fila de mediação")
async def slash_mediar(it: discord.Interaction):
    if not it.user.guild_permissions.manage_messages:
        return await it.response.send_message("Apenas Staff.", ephemeral=True)
    
    v = ViewMediadorFila()
    await it.response.send_message(embed=v.gerar_embed(), view=v)

@bot.tree.command(name="fila", description="Gera as mensagens de fila de aposta")
async def slash_fila(it: discord.Interaction):
    if not it.user.guild_permissions.administrator:
        return await it.response.send_message("Sem permissão.", ephemeral=True)

    class ModalGerarFila(Modal, title="Configurar Filas"):
        modo = TextInput(label="Modo (ex: 1v1, 4v4)", default="1v1", placeholder="Digite o modo...")
        plat = TextInput(label="Plataforma (Mobile/Emu)", default="Mobile")
        vals = TextInput(label="Valores (Separe por ESPAÇO)", 
                         default="5,00 10,00 20,00 50,00", 
                         style=discord.TextStyle.paragraph,
                         placeholder="Ex: 5,00 10,00")

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.send_message("⏳ Gerando painéis, aguarde...", ephemeral=True)
            
            # Lógica corrigida do split
            raw_input = self.vals.value
            # Divide por espaços, remove vazios e limpa
            valores_lista = [v.strip() for v in raw_input.split() if v.strip()]
            
            modo_final = f"{self.modo.value}|{self.plat.value}"

            for val in valores_lista:
                # Adiciona ,00 se o usuário digitou apenas numero inteiro
                if "," not in val: val += ",00"
                if "R$" not in val: val_txt = val # O R$ é adicionado na View
                
                vf = ViewFila(modo_final, val)
                await interaction.channel.send(embed=vf.emb(), view=vf)
                await asyncio.sleep(1) # Delay anti-rate limit
            
            await interaction.followup.send("✅ Filas geradas com sucesso!", ephemeral=True)

    await it.response.send_modal(ModalGerarFila())

# ==============================================================================
#           INICIALIZAÇÃO
# ==============================================================================

@bot.event
async def on_ready():
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Bot Online: {bot.user.name}")
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Erro ao sincronizar: {e}")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("ERRO: Token não encontrado. Configure a variável TOKEN.")
            
