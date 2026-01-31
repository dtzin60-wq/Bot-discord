import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect
import sqlite3
import aiohttp
import os
import datetime
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES GERAIS
# ==============================================================================
TOKEN = os.getenv("TOKEN")

# Imagens e Cores baseadas nos seus prints
# Cor verde lateral do embed da Imagem 1 e 2
COR_CONFIRMACAO = 0x2ecc71 
# Cor do embed de "Partida Confirmada" da Imagem 3 (Verde escuro)
COR_SUCESSO = 0x2ecc71 
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache
fila_mediadores = [] 
confirmacoes_ativas = {} # Armazena quem já confirmou em cada thread

# ==============================================================================
#                         BANCO DE DADOS
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_sistema_vip.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, 
            saldo REAL DEFAULT 0.0)""")
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS restricoes (user_id INTEGER PRIMARY KEY, motivo TEXT)")
        con.commit()

def db_exec(query, params=()):
    with sqlite3.connect("ws_sistema_vip.db") as con:
        con.execute(query, params); con.commit()

def db_get(query, params=()):
    with sqlite3.connect("ws_sistema_vip.db") as con:
        return con.execute(query, params).fetchone()

# ==============================================================================
#                         VIEW DE CONFIRMAÇÃO (IMAGENS 1, 2 E 3)
# ==============================================================================
class ViewConfirmacaoPartida(View):
    """
    Painel enviado DENTRO do tópico assim que a fila enche.
    Réplica exata da Imagem 1 e 2.
    """
    def __init__(self, modo, valor, jogadores, mediador_id):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = jogadores # Lista de dicionários {'id': int, 'm': mention}
        self.mediador_id = mediador_id
        self.confirmados = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        # Verifica se o usuário faz parte da partida
        if interaction.user.id not in [j['id'] for j in self.jogadores]:
            return await interaction.response.send_message("Você não está nesta partida.", ephemeral=True)
        
        # Verifica se já confirmou
        if interaction.user.id in self.confirmados:
            return await interaction.response.send_message("Você já confirmou.", ephemeral=True)

        self.confirmados.append(interaction.user.id)
        
        # --- GERAÇÃO DA MENSAGEM DA IMAGEM 3 ---
        # "Partida Confirmada... @User confirmou a aposta..."
        embed_conf = discord.Embed(
            description=f"**{interaction.user.mention} confirmou a aposta!**\n↳ O outro jogador precisa confirmar para continuar.",
            color=COR_SUCESSO
        )
        embed_conf.set_author(name="| Partida Confirmada", icon_url="https://cdn-icons-png.flaticon.com/512/190/190411.png") # Ícone de check
        await interaction.channel.send(embed=embed_conf)
        
        # Se todos confirmaram
        if len(self.confirmados) >= len(self.jogadores):
            await self.iniciar_partida_oficial(interaction)
        else:
            await interaction.response.defer() # Apenas confirma o clique sem mensagem extra

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def recusar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [j['id'] for j in self.jogadores]: return
        await interaction.channel.send(f"🚫 {interaction.user.mention} recusou a partida. Sessão cancelada.")
        await interaction.channel.delete() # Ou arquivar

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            f"{interaction.user.mention} deseja combinar regras específicas. Discutam no chat acima.", 
            ephemeral=False
        )

    async def iniciar_partida_oficial(self, interaction):
        """Chamado quando ambos confirmam."""
        self.stop() # Para de escutar botões
        
        # Menciona o mediador e os jogadores
        mentions = " ".join([j['m'] for j in self.jogadores])
        
        embed_final = discord.Embed(title="✅ SESSÃO INICIADA", color=0x00ff00)
        embed_final.description = f"Todos os jogadores confirmaram!\n\n👮 **Mediador:** <@{self.mediador_id}>\n💰 **Valor:** R$ {self.valor}\n👥 **Jogadores:** {mentions}"
        
        await interaction.channel.send(content=f"<@{self.mediador_id}> {mentions}", embed=embed_final)
        
        # Registra comissão (R$ 0,10)
        db_exec("UPDATE pix SET saldo = saldo + 0.10 WHERE user_id=?", (self.mediador_id,))

# ==============================================================================
#                         VIEW DE ENTRADA NA FILA (PRINCIPAL)
# ==============================================================================
class ViewFilaPrincipal(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []
        self._setup_btns()

    def _setup_btns(self):
        self.clear_items()
        if "1V1" in self.modo.upper():
            # Botões Cinza para Gelo (Secondary)
            b_norm = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            b_inf = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            
            b_norm.callback = lambda i: self.entrar(i, "Gelo Normal")
            b_inf.callback = lambda i: self.entrar(i, "Gelo Infinito")
            
            self.add_item(b_norm); self.add_item(b_inf)
        else:
            b_ent = Button(label="/entrar na fila", style=discord.ButtonStyle.success)
            b_ent.callback = lambda i: self.entrar(i, None)
            self.add_item(b_ent)
            
        b_sair = Button(label="Sair da Fila", style=discord.ButtonStyle.danger)
        b_sair.callback = self.sair
        self.add_item(b_sair)

    def gerar_embed_fila(self):
        emb = discord.Embed(title=f"Sessão de Aposta | {self.modo}", color=0x2b2d31)
        emb.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        emb.add_field(name="📋 Modalidade", value=f"**{self.modo}**", inline=True)
        emb.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        
        lista = "\n".join([f"👤 {j['m']}" for j in self.jogadores]) or "*Aguardando...*"
        emb.add_field(name="👥 Inscritos", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def entrar(self, it: discord.Interaction, tipo_gelo):
        if any(j['id'] == it.user.id for j in self.jogadores):
            return await it.response.send_message("Você já está na fila!", ephemeral=True)
        
        if tipo_gelo:
            await it.channel.send(f"{it.user.mention}-{tipo_gelo}")

        self.jogadores.append({'id': it.user.id, 'm': it.user.mention})
        await it.message.edit(embed=self.gerar_embed_fila())
        
        # Verifica lotação
        limite = int(self.modo[0]) * 2 if self.modo[0].isdigit() else 2
        if len(self.jogadores) >= limite:
            await self.criar_topico(it, tipo_gelo)

    async def sair(self, it):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.message.edit(embed=self.gerar_embed_fila())

    async def criar_topico(self, it, tipo_gelo_escolhido):
        if not fila_mediadores:
            return await it.channel.send("⚠️ Sem mediadores na escala.", delete_after=5)
        
        med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
        
        c_id = db_get("SELECT valor FROM config WHERE chave='canal_th'")
        if not c_id: return await it.channel.send("❌ Canal de tópicos não configurado.")
        
        canal = bot.get_channel(int(c_id[0]))
        nome_thread = f"Sessão-{self.valor}-{it.user.name}"
        thread = await canal.create_thread(name=nome_thread, type=discord.ChannelType.public_thread)
        
        # --- CRIAÇÃO DO EMBED DA IMAGEM 1 e 2 (DENTRO DO TÓPICO) ---
        modo_formatado = f"{self.modo} | {tipo_gelo_escolhido if tipo_gelo_escolhido else 'Padrão'}"
        
        embed_topico = discord.Embed(title="Aguardando Confirmações", color=COR_CONFIRMACAO)
        embed_topico.set_thumbnail(url=ICONE_ORG) # Boneca ou ícone da org
        
        embed_topico.add_field(name="👑 Modo:", value=f"```{modo_formatado}```", inline=False)
        embed_topico.add_field(name="💎 Valor da aposta:", value=f"```R$ {self.valor}```", inline=False)
        
        jogadores_formatados = "\n".join([j['m'] for j in self.jogadores])
        embed_topico.add_field(name="⚡ Jogadores:", value=jogadores_formatados, inline=False)
        
        # Texto do Rodapé idêntico à Imagem 1
        footer_text = (
            "✨ SEJAM MUITO BEM-VINDOS ✨\n\n"
            "• Regras adicionais podem ser combinadas entre os participantes.\n"
            "• Se a regra combinada não existir no regulamento oficial da organização, "
            "é obrigatório tirar print do acordo antes do início da partida."
        )
        embed_topico.description = f"```{footer_text}```"
        
        # Envia o Embed com os botões de confirmação
        view_conf = ViewConfirmacaoPartida(self.modo, self.valor, self.jogadores, med_id)
        await thread.send(content=" ".join([j['m'] for j in self.jogadores]), embed=embed_topico, view=view_conf)
        
        # Limpa fila principal
        self.jogadores = []
        await it.message.edit(embed=self.gerar_embed_fila())

# ==============================================================================
#                         COMANDOS EXECUTIVOS
# ==============================================================================
@bot.command()
async def Pix(ctx):
    """Comando Pix com visual restaurado."""
    class ModalPix(Modal, title="Dados Bancários"):
        n = TextInput(label="Nome Titular"); c = TextInput(label="Chave PIX")
        async def on_submit(self, it):
            db_exec("INSERT OR REPLACE INTO pix (user_id, nome, chave) VALUES (?,?,?)", (it.user.id, n.value, c.value))
            await it.response.send_message("✅ Salvo!", ephemeral=True)
            
    class ViewP(View):
        @discord.ui.button(label="Cadastrar Dados PIX", style=discord.ButtonStyle.success)
        async def c(self, it, b): await it.response.send_modal(ModalPix())
        
    e = discord.Embed(title="Gestão Financeira", description="Configure seus dados de recebimento.", color=0x2b2d31)
    await ctx.send(embed=e, view=ViewP())

@bot.command()
async def mediar(ctx):
    """Comando Mediar com visual de lista."""
    if not ctx.author.guild_permissions.manage_messages: return
    class VM(View):
        def emb(self):
            t = "Mediadores em escala:\n\n" + ("\n".join([f"**{i+1}.** <@{u}>" for i,u in enumerate(fila_mediadores)]) or "Vazio")
            return discord.Embed(title="Escala", description=t, color=0x2b2d31)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.success)
        async def e(self, i, b): 
            if i.user.id not in fila_mediadores: fila_mediadores.append(i.user.id); await i.response.edit_message(embed=self.emb())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger)
        async def s(self, i, b): 
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.edit_message(embed=self.emb())
    v = VM(); await ctx.send(embed=v.emb(), view=v)

@bot.command()
async def canal_fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v=View(); s=ChannelSelect()
    async def cb(i): 
        db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(s.values[0].id),))
        await i.response.send_message("Canal configurado.", ephemeral=True)
    s.callback=cb; v.add_item(s); await ctx.send("Selecione o canal:", view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class M(Modal, title="Gerar"):
        m = TextInput(label="Modo", default="1v1"); p = TextInput(label="Plat", default="Mobile")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True)
            for v in ["100,00","50,00","20,00","10,00","5,00","2,00","1,00","0,50"]:
                vi = ViewFilaPrincipal(f"{self.m.value} | {self.p.value}", v)
                await i.channel.send(embed=vi.gerar_embed_fila(), view=vi)
                await asyncio.sleep(1)
    class V(View):
        @discord.ui.button(label="Gerar Filas", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(M())
    await ctx.send("Painel Admin", view=V())

@bot.event
async def on_ready():
    init_db()
    print("WS VIP ONLINE")

if TOKEN: bot.run(TOKEN)
            
