import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, UserSelect
import sqlite3
import os
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
# ⚠️ COLOQUE SEU TOKEN AQUI OU NO ARQUIVO .ENV
TOKEN = os.getenv("TOKEN") 

# Cores e Imagens
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_CONFIRMADO = 0x2ecc71

# 📸 SUBSTITUA PELOS SEUS LINKS REAIS
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://i.imgur.com/Xw0yYgH.png" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Cache Global
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
#           VIEW: CONFIRMAÇÃO (THREAD)
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
            return await it.response.send_message("❌ Você não está nesta partida.", ephemeral=True)
        
        if it.user.id in self.confirms: 
            return await it.response.send_message("⚠️ Você já confirmou.", ephemeral=True)
        
        self.confirms.append(it.user.id)
        await it.channel.send(f"✅ **{it.user.mention}** confirmou a partida!")

        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            
            # Lógica de renomear o canal
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

            e = discord.Embed(title="✅ Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            e.add_field(name="🎮 Estilo de Jogo", value=estilo, inline=False)
            
            try:
                v_f = float(self.valor.replace("R$","").replace(",",".").strip())
                taxa = max(v_f * 0.10, 0.10)
                taxa_str = f"R$ {taxa:.2f}".replace(".",",")
            except: taxa_str = "R$ 0,10"

            e.add_field(name="ℹ️ Informações", value=f"Valor Da Sala: {taxa_str}\nMediador: <@{self.med_id}>", inline=False)
            e.add_field(name="💎 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            e.add_field(name="👥 Jogadores", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            
            await it.channel.send(content=f"<@{self.med_id}> {' '.join([j['m'] for j in self.jogadores])}", embed=e)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores]:
            await it.channel.send("🚫 **Partida Recusada.** Fechando thread..."); await asyncio.sleep(2); await it.channel.delete()

    @discord.ui.button(label="Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, it: discord.Interaction, btn: Button):
        await it.response.send_message(f"🏳️ {it.user.mention} sugeriu combinar regras no chat.", ephemeral=False)
        # ==============================================================================
#           VIEW: FILA (COM BANNER)
# ==============================================================================
class ViewFila(View):
    def __init__(self, modo_str, valor):
        super().__init__(timeout=None)
        self.modo_str = modo_str
        self.valor = valor
        self.jogadores = []
        self._btns()

    def _btns(self):
        self.clear_items()
        if "1V1" in self.modo_str.upper():
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback = lambda i: self.join(i, "Gel Normal")
            b2.callback = lambda i: self.join(i, "Gel Infinito")
            self.add_item(b1)
            self.add_item(b2)
        else:
            b = Button(label="Entrar na Fila", style=discord.ButtonStyle.success)
            b.callback = lambda i: self.join(i, None)
            self.add_item(b)
        
        bs = Button(label="Sair", style=discord.ButtonStyle.danger)
        bs.callback = self.leave
        self.add_item(bs)

    def emb(self):
        # Criação do Embed da Fila
        titulo_formatado = f"Aposta | {self.modo_str.replace('|', ' ')}"
        e = discord.Embed(title=titulo_formatado, color=COR_EMBED)
        e.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        e.add_field(name="📋 Modalidade", value=f"**{self.modo_str.replace('|', ' ')}**", inline=True)
        e.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        
        lst = [f"👤 {j['m']} - {j['t']}" if j['t'] else f"👤 {j['m']}" for j in self.jogadores]
        e.add_field(name="👥 Jogadores na Fila", value="\n".join(lst) or "*Aguardando...*", inline=False)
        
        # AQUI ESTÁ O BANNER RESTAURADO
        e.set_image(url=BANNER_URL) 
        
        e.set_footer(text="Clique nos botões abaixo para participar")
        return e

    async def join(self, it, tipo):
        if any(j['id'] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("⚠️ Você já está na fila.", ephemeral=True)
        
        self.jogadores.append({'id': it.user.id, 'm': it.user.mention, 't': tipo})
        await it.response.edit_message(embed=self.emb())
        
        lim = int(self.modo_str[0])*2 if self.modo_str[0].isdigit() else 2
        
        if len(self.jogadores) >= lim:
            if not fila_mediadores: 
                return await it.channel.send("⚠️ **Atenção:** Nenhum mediador online no momento!", delete_after=10)
            
            med = fila_mediadores.pop(0)
            fila_mediadores.append(med)
            
            cid = db_get_config("canal_th")
            if not cid: return await it.channel.send("❌ Erro: Canal de threads não configurado. Use /canal")
            
            ch = bot.get_channel(int(cid))
            if not ch: return await it.channel.send("❌ Erro: Canal de threads não encontrado.")

            th = await ch.create_thread(name="aguardando-confirmacao", type=discord.ChannelType.public_thread)
            
            ew = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE)
            ew.set_thumbnail(url=IMAGEM_BONECA)
            ew.add_field(name="👑 Modo:", value=f"{self.modo_str.split('|')[0]} | {self.jogadores[0]['t'] or 'Padrão'}", inline=False)
            ew.add_field(name="💎 Valor:", value=f"R$ {self.valor}", inline=False)
            ew.add_field(name="⚡ Jogadores:", value="\n".join([j['m'] for j in self.jogadores]), inline=False)
            ew.add_field(name="\u200b", value="```✨ SEJAM MUITO BEM-VINDOS ✨\n\n• Regras adicionais podem ser combinadas.\n• Obrigatório print do acordo.```", inline=False)
            
            await th.send(content=f"<@{med}> " + " ".join([j['m'] for j in self.jogadores]), embed=ew, view=ViewConfirmacao(self.jogadores, med, self.valor, self.modo_str))
            
            self.jogadores = []
            await it.message.edit(embed=self.emb())

    async def leave(self, it):
        if not any(j['id'] == it.user.id for j in self.jogadores):
             return await it.response.send_message("Você não está nesta fila.", ephemeral=True)
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.emb())

# ==============================================================================
#           PAINÉIS GERAIS
# ==============================================================================
class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Cadastrar Chave", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m = Modal(title="Cadastrar Pix")
        n = TextInput(label="Seu Nome Completo")
        c = TextInput(label="Sua Chave Pix")
        q = TextInput(label="Link do QR Code (Opcional)", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        
        async def sub(i): 
            db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value))
            await i.response.send_message("✅ Pix salvo com sucesso.", ephemeral=True)
        m.on_submit = sub
        await it.response.send_modal(m)

    @discord.ui.button(label="Minha Chave", style=discord.ButtonStyle.primary, emoji="🔍")
    async def ver(self, it, b):
        d = db_query("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        if d: await it.response.send_message(f"👤 **Nome:** {d[1]}\n🔑 **Chave:** `{d[2]}`\n🖼️ **QR:** {d[3] or 'N/A'}", ephemeral=True)
        else: await it.response.send_message("❌ Você não tem chave cadastrada.", ephemeral=True)

    @discord.ui.button(label="Pix Mediador", style=discord.ButtonStyle.secondary, emoji="🕵️")
    async def vermed(self, it, b):
        v = View()
        s = UserSelect(placeholder="Selecione o mediador...")
        async def cb(i):
            d = db_query("SELECT * FROM pix WHERE user_id=?",(s.values[0].id,))
            if d: await i.response.send_message(f"💸 **Pix de {s.values[0].mention}:**\nNome: {d[1]}\nChave: `{d[2]}`", ephemeral=True)
            else: await i.response.send_message("❌ Esse usuário não tem Pix cadastrado.", ephemeral=True)
        s.callback = cb
        v.add_item(s)
        await it.response.send_message("Selecione o usuário:", view=v, ephemeral=True)

class ViewMediarPainel(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        desc = "**Fila de Mediadores Ativos**\n\n"
        if not fila_mediadores: 
            desc += "*A lista está vazia no momento.*"
        else:
            for i, uid in enumerate(fila_mediadores): 
                desc += f"**{i+1}º** - <@{uid}>\n"
        
        desc += "\nUse os botões abaixo para entrar ou sair."
        emb = discord.Embed(title="👮 Painel de Controle: Mediadores", description=desc, color=COR_EMBED)
        emb.set_thumbnail(url=ICONE_ORG)
        return emb

    @discord.ui.button(label="Entrar na Fila", style=discord.ButtonStyle.success, emoji="✅")
    async def entrar(self, it, b): 
        if it.user.id not in fila_mediadores: 
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🏃")
    async def sair(self, it, b): 
        if it.user.id in fila_mediadores: 
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("Você não está na fila.", ephemeral=True)

    @discord.ui.button(label="Remover (Staff)", style=discord.ButtonStyle.secondary, emoji="🛠️")
    async def remover(self, it: discord.Interaction, b: Button):
        if not it.user.guild_permissions.manage_messages: 
            return await it.response.send_message("Sem permissão.", ephemeral=True)
        
        view_rem = View()
        select = UserSelect(placeholder="Selecione quem remover da fila")
        
        async def cb_remover(interacao):
            alvo = select.values[0]
            if alvo.id in fila_mediadores:
                fila_mediadores.remove(alvo.id)
                await it.message.edit(embed=self.gerar_embed())
                await interacao.response.send_message(f"✅ **{alvo.name}** foi removido da fila.", ephemeral=True)
            else: 
                await interacao.response.send_message("❌ Usuário não está na fila.", ephemeral=True)
        
        select.callback = cb_remover
        view_rem.add_item(select)
        await it.response.send_message("Quem você quer remover?", view=view_rem, ephemeral=True)
    # ==============================================================================
#           SLASH COMMANDS
# ==============================================================================

@bot.tree.command(name="pix", description="💸 Configurar ou visualizar chaves Pix")
async def slash_pix(it: discord.Interaction):
    e = discord.Embed(title="Gerenciamento de Pix", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG)
    e.description = "Utilize os botões abaixo para cadastrar seu Pix ou consultar chaves."
    await it.response.send_message(embed=e, view=ViewPainelPix())

@bot.tree.command(name="botconfig", description="⚙️ Configurações administrativas do Bot")
async def slash_botconfig(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: 
        return await it.response.send_message("❌ Apenas administradores.", ephemeral=True)
    
    view = View()
    btn = Button(label="Instruções de Fila", style=discord.ButtonStyle.secondary, emoji="ℹ️")
    async def cb(i, b): await i.response.send_message("Use /painel_apostas para criar filas.", ephemeral=True)
    btn.callback = cb; view.add_item(btn)
    
    e = discord.Embed(title="Painel Admin", color=COR_EMBED)
    e.description = "Configurações gerais do sistema."
    await it.response.send_message(embed=e, view=view)

@bot.tree.command(name="canal", description="📺 Definir o canal para criação das salas (Threads)")
@app_commands.describe(canal="O canal de texto onde as threads serão abertas")
async def slash_canal(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator: 
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_th", str(canal.id)))
    await interaction.response.send_message(f"✅ Canal de salas definido para: {canal.mention}", ephemeral=True)

@bot.tree.command(name="mediadores", description="👮 Painel para entrar/sair da fila de mediadores")
async def slash_mediadores(it: discord.Interaction):
    if not it.user.guild_permissions.manage_messages:
        return await it.response.send_message("❌ Apenas Staff pode acessar esse painel.", ephemeral=True)
    
    painel = ViewMediarPainel()
    await it.response.send_message(embed=painel.gerar_embed(), view=painel)

@bot.tree.command(name="painel_apostas", description="🎰 Gerar o painel de apostas com botões")
async def slash_painel_apostas(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: 
        return await it.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    # Botão que abre o Modal
    class ViewGerar(View):
        @discord.ui.button(label="Configurar Novas Filas", style=discord.ButtonStyle.primary, emoji="📝")
        async def configurar(self, i: discord.Interaction, b: Button):
            await i.response.send_modal(ModalFila())

    # Modal para digitar os valores
    class ModalFila(Modal, title="Criar Filas de Aposta"):
        modo = TextInput(label="Modo de Jogo", default="1v1", placeholder="Ex: 1v1, 4v4")
        plat = TextInput(label="Plataforma", default="Mobile", placeholder="Mobile, Emu, Misto")
        vals = TextInput(label="Valores (Separe por ESPAÇO)", 
                         default="5,00 10,00 20,00",
                         style=discord.TextStyle.paragraph,
                         placeholder="Ex: 5,00 10,00 20,00")

        async def on_submit(self, i: discord.Interaction):
            await i.response.send_message("🔄 Gerando painéis...", ephemeral=True)
            
            # Lógica de Separação por Espaço
            raw_valores = self.vals.value.split()
            lista_valores = []
            
            for v in raw_valores:
                v_limpo = v.strip()
                if not v_limpo: continue
                if ',' not in v_limpo: v_limpo += ",00"
                lista_valores.append(v_limpo)

            modo_formatado = f"{self.modo.value}|{self.plat.value}"
            
            for valor in lista_valores:
                view_fila = ViewFila(modo_formatado, valor)
                await i.channel.send(embed=view_fila.emb(), view=view_fila)
                await asyncio.sleep(1) # Delay para evitar rate limit

    e = discord.Embed(title="Gerador de Filas", description="Clique abaixo para criar os painéis de aposta.", color=COR_EMBED)
    await it.response.send_message(embed=e, view=ViewGerar())

# ==============================================================================
#           EVENTOS E INICIALIZAÇÃO
# ==============================================================================
@bot.event
async def on_ready():
    init_db()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Bot Online! {len(synced)} comandos Slash sincronizados.")
    except Exception as e:
        print(f"❌ Erro ao sincronizar comandos: {e}")

if TOKEN:
    bot.run(TOKEN)
                       
