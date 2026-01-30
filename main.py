import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3, os, asyncio

# --- CONFIGURAÇÕES ---
TOKEN = "TEU_TOKEN_AQUI"
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=".", intents=intents)

# Memória Temporária
fila_mediadores = [] 
partidas_ativas = {} 
temp_dados_sala = {} 

# ================= BANCO DE DADOS =================
def init_db():
    con = sqlite3.connect("dados_bot.db")
    c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qrcode TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
    con.commit()
    con.close()

def db_execute(q, p=()):
    con = sqlite3.connect("dados_bot.db")
    con.execute(q, p)
    con.commit()
    con.close()

def pegar_config(ch):
    con = sqlite3.connect("dados_bot.db")
    r = con.execute("SELECT valor FROM config WHERE chave=?", (ch,)).fetchone()
    con.close()
    return r[0] if r else None

# ================= SISTEMA .Pix =================
class ModalPix(Modal, title="Configurar Dados PIX"):
    n = TextInput(label="Nome do Titular", placeholder="Nome do dono da conta")
    c = TextInput(label="Chave PIX", placeholder="CPF, Telemóvel, Email ou Aleatória")
    q = TextInput(label="Link do QR Code (Imagem)", placeholder="URL da imagem do QR Code", required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (interaction.user.id, self.n.value, self.c.value, self.q.value))
        await interaction.response.send_message("✅ **Dados PIX guardados com sucesso!**", ephemeral=True)

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠", custom_id="btn_pix_cad")
    async def cadastrar(self, it: discord.Interaction, b):
        await it.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍", custom_id="btn_pix_ver")
    async def ver(self, it: discord.Interaction, b):
        con = sqlite3.connect("dados_bot.db")
        r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (it.user.id,)).fetchone(); con.close()
        if not r: return await it.response.send_message("❌ Não tens uma chave cadastrada.", ephemeral=True)
        emb = discord.Embed(title="Teus Dados PIX", description=f"**Titular:** `{r[0]}`\n**Chave:** `{r[1]}`", color=0x2ecc71)
        if r[2]: emb.set_image(url=r[2])
        await it.response.send_message(embed=emb, ephemeral=True)

# ================= SISTEMA .mediar / .mediat =================
class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    def gerar_embed(self):
        desc = "A fila está vazia." if not fila_mediadores else "\n".join([f"**{i+1} •** <@{uid}>" for i, uid in enumerate(fila_mediadores)])
        emb = discord.Embed(title="Painel da fila controladora", description=f"__**Entre na fila para começar a mediar**__\n\n{desc}", color=0x2b2d31)
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="btn_med_entrar")
    async def entrar(self, it: discord.Interaction, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Já estás na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="btn_med_sair")
    async def sair(self, it: discord.Interaction, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else: await it.response.send_message("⚠️ Não estás na fila.", ephemeral=True)

# ================= SISTEMA .fila (MATCHMAKING) =================
class ViewMatchmaking(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []

    def gerar_embed(self):
        txt = "Vago..." if not self.jogadores else "\n".join([f"👤 {d['u'].mention} - `{d['gelo']}`" for d in self.jogadores])
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="💰 Valor", value=f"R$ {self.valor}", inline=True)
        emb.add_field(name="🏆 Modo", value=self.modo, inline=True)
        emb.add_field(name="Fila", value=txt, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def adicionar_jogador(self, it, tipo_gelo):
        if any(d['u'].id == it.user.id for d in self.jogadores): 
            return await it.response.send_message("⚠️ Já estás nesta fila!", ephemeral=True)
        
        self.jogadores.append({'u': it.user, 'gelo': tipo_gelo})
        
        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []
                return await it.response.send_message("❌ Nenhum mediador disponível na fila!", ephemeral=True)
            
            # Rotação do Mediador
            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id)
            
            # Criar Tópico
            canal_id = pegar_config("canal_topicos")
            canal = bot.get_channel(int(canal_id)) if canal_id else it.channel
            thread = await canal.create_thread(name=f"Aposta R$ {self.valor}", type=discord.ChannelType.public_thread)
            
            partidas_ativas[thread.id] = {
                'med': med_id, 
                'p1': self.jogadores[0]['u'].id, 
                'p2': self.jogadores[1]['u'].id,
                'modo': f"{self.modo} ({self.jogadores[0]['gelo']} vs {self.jogadores[1]['gelo']})"
            }
            
            emb_th = discord.Embed(title="Nova Partida Criada", color=0x2b2d31)
            emb_th.description = f"**Modo:** {self.modo}\n**Valor:** R$ {self.valor}\n**Mediador:** <@{med_id}>\n\nEsperando confirmação dos jogadores."
            await thread.send(content=f"<@{self.jogadores[0]['u'].id}> <@{self.jogadores[1]['u'].id}>", 
                             embed=emb_th, 
                             view=ViewConfirmacao(self.jogadores[0]['u'].id, self.jogadores[1]['u'].id, med_id, self.valor))
            
            self.jogadores = []
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.edit_message(embed=self.gerar_embed())

    @discord.ui.button(label="Gelo Normal", style=discord.ButtonStyle.secondary, emoji="❄️")
    async def gelo_n(self, it, b): await self.adicionar_jogador(it, "Gelo Normal")
    
    @discord.ui.button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, emoji="♾️")
    async def gelo_i(self, it, b): await self.adicionar_jogador(it, "Gelo Infinito")
    
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="🚪")
    async def sair(self, it, b):
        self.jogadores = [d for d in self.jogadores if d['u'].id != it.user.id]
        await it.response.edit_message(embed=self.gerar_embed())

# ================= CONFIRMAÇÃO E LIMPEZA =================
class ViewConfirmacao(View):
    def __init__(self, p1, p2, med, val):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med, self.val = p1, p2, med, val
        self.confirmados = set()

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green)
    async def confirmar(self, it: discord.Interaction, b):
        if it.user.id not in [self.p1, self.p2]: return
        self.confirmados.add(it.user.id)
        await it.response.send_message(f"✅ <@{it.user.id}> confirmou!", delete_after=2)
        
        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await it.channel.purge(limit=50) # Limpa o chat
            
            # Buscar PIX do Mediador
            con = sqlite3.connect("dados_bot.db")
            r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone(); con.close()
            
            # Cálculo da Taxa (+ R$ 0,10)
            try: v_total = f"{(float(self.val.replace(',','.')) + 0.10):.2f}".replace('.',',')
            except: v_total = self.val
            
            emb_pix = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb_pix.add_field(name="👤 Titular", value=r[0] if r else "Não cadastrado", inline=True)
            emb_pix.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "N/A", inline=True)
            emb_pix.add_field(name="💰 Valor com Taxa", value=f"R$ {v_total}", inline=False)
            if r and r[2]: emb_pix.set_image(url=r[2])
            
            await it.channel.send(content=f"<@{self.p1}> <@{self.p2}>", embed=emb_pix)
            await it.channel.send("📍 Mediador, envie o **ID da Sala** e depois a **Senha**.")

# ================= COMANDOS E EVENTOS =================
@bot.command()
async def Pix(ctx):
    await ctx.send(embed=discord.Embed(title="Configuração de PIX", description="Gere seus pagamentos automaticamente.", color=0x2b2d31), view=ViewPix())

@bot.command(aliases=['mediat'])
async def mediar(ctx):
    await ctx.send(embed=ViewMediar().gerar_embed(), view=ViewMediar())

@bot.command()
async def fila(ctx, modo, valor):
    await ctx.send(embed=ViewMatchmaking(modo, valor).gerar_embed(), view=ViewMatchmaking(modo, valor))

@bot.command()
async def set_canal(ctx):
    v = View(); sel = ChannelSelect(placeholder="Selecione o canal para tópicos")
    async def cb(i):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_topicos", str(sel.values[0].id)))
        await i.response.send_message("✅ Canal definido!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Configuração:", view=v)

@bot.event
async def on_message(message):
    if message.author.bot: return
    # Lógica de IDs e Senhas (apenas números)
    if message.channel.id in partidas_ativas:
        dados = partidas_ativas[message.channel.id]
        if message.author.id == dados['med'] and message.content.isdigit():
            cid = message.channel.id
            if cid not in temp_dados_sala:
                temp_dados_sala[cid] = message.content
                await message.delete()
                await message.channel.send("✅ ID capturado. Agora envie a **Senha**.", delete_after=2)
            else:
                senha = message.content
                id_sala = temp_dados_sala.pop(cid)
                await message.delete()
                
                emb_sala = discord.Embed(title="🚀 SALA PRONTA", color=0x2ecc71)
                emb_sala.description = f"**ID:** `{id_sala}`\n**Senha:** `{senha}`\n**Modo:** {dados['modo']}"
                emb_sala.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{dados['p1']}> <@{dados['p2']}>", embed=emb_sala)
                
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db()
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    print(f"✅ {bot.user.name} está online com todas as funções!")

bot.run(TOKEN)
        
