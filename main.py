import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, UserSelect
import sqlite3
import os
import datetime
import asyncio

# ==============================================================================
#                         CONFIGURAÇÕES E ESTÉTICA
# ==============================================================================
TOKEN = os.getenv("TOKEN")

# Cores e Ícones baseados nos seus prints
COR_EMBED_PADRAO = 0x2b2d31 # Cinza escuro (fundo discord)
COR_CONFIRMACAO = 0x2ecc71  # Verde lateral
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache em Memória
fila_mediadores = [] # Lista de IDs
confirmacoes_sala = {} # Controle de confirmação dentro da thread

# ==============================================================================
#                         BANCO DE DADOS (PERSISTÊNCIA)
# ==============================================================================
def init_db():
    with sqlite3.connect("ws_system_pro.db") as con:
        # Tabela PIX
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY, 
            nome TEXT, 
            chave TEXT,
            saldo REAL DEFAULT 0.0
        )""")
        # Configurações
        con.execute("CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)")
        # Restrições (Blacklist)
        con.execute("CREATE TABLE IF NOT EXISTS restricoes (user_id INTEGER PRIMARY KEY, motivo TEXT)")
        # Logs
        con.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            acao TEXT, 
            detalhes TEXT, 
            data TEXT
        )""")
        con.commit()

def db_exec(query, params=()):
    with sqlite3.connect("ws_system_pro.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("ws_system_pro.db") as con:
        return con.execute(query, params).fetchone()

# ==============================================================================
#               SISTEMA DE APOSTA (IMAGEM 1, 2, 3 - FLUXO COMPLETO)
# ==============================================================================

class ViewConfirmacaoThread(View):
    """
    Painel que aparece DENTRO do tópico criado (Imagem 1 e 2).
    """
    def __init__(self, modo, valor, jogadores, mediador_id):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = jogadores
        self.mediador_id = mediador_id
        self.confirmados = []

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success) # Sem emoji no label para ficar limpo como no print
    async def btn_confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [j['id'] for j in self.jogadores]:
            return await interaction.response.send_message("Você não é participante desta partida.", ephemeral=True)
        
        if interaction.user.id in self.confirmados:
            return await interaction.response.send_message("Aguarde o oponente.", ephemeral=True)

        self.confirmados.append(interaction.user.id)
        
        # IMAGEM 3: Embed de feedback de confirmação
        embed_check = discord.Embed(color=0x2ecc71) # Verde
        embed_check.set_author(name="| Partida Confirmada", icon_url="https://cdn-icons-png.flaticon.com/512/148/148767.png")
        embed_check.description = (
            f"**{interaction.user.mention} confirmou a aposta!**\n"
            "↳ O outro jogador precisa confirmar para continuar."
        )
        await interaction.channel.send(embed=embed_check)

        # Se todos confirmaram
        if len(self.confirmados) >= len(self.jogadores):
            self.stop()
            # Início real
            embed_start = discord.Embed(title="✅ SESSÃO INICIADA", color=COR_CONFIRMACAO)
            embed_start.description = f"Mediador: <@{self.mediador_id}>\nJogadores: {' '.join([j['m'] for j in self.jogadores])}"
            await interaction.channel.send(content=f"<@{self.mediador_id}>", embed=embed_start)
            
            # Comissão
            db_exec("UPDATE pix SET saldo = saldo + 0.10 WHERE user_id=?", (self.mediador_id,))
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def btn_recusar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in [j['id'] for j in self.jogadores]:
            await interaction.channel.send(f"🚫 {interaction.user.mention} recusou a partida. Tópico encerrado.")
            await interaction.channel.edit(locked=True, archived=True)

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.secondary, emoji="🏳️")
    async def btn_regras(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(f"🏳️ {interaction.user.mention} sugeriu combinar regras específicas.", ephemeral=False)


class ViewFilaPrincipal(View):
    """
    Botão de entrada na fila (Gelo/Entrar).
    """
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores = modo, valor, []
        self._config_buttons()

    def _config_buttons(self):
        self.clear_items()
        if "1V1" in self.modo.upper():
            # Gelo (Cinza)
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback = lambda i: self.join(i, "Gelo Normal")
            b2.callback = lambda i: self.join(i, "Gelo Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b_ent = Button(label="/entrar na fila", style=discord.ButtonStyle.success)
            b_ent.callback = lambda i: self.join(i, None)
            self.add_item(b_ent)

        b_sair = Button(label="Sair da Fila", style=discord.ButtonStyle.danger)
        b_sair.callback = self.leave
        self.add_item(b_sair)

    def get_embed(self):
        emb = discord.Embed(title=f"Sessão de Aposta | {self.modo}", color=COR_EMBED_PADRAO)
        emb.set_author(name="WS APOSTAS", icon_url=ICONE_ORG)
        emb.add_field(name="📋 Modalidade", value=f"**{self.modo}**", inline=True)
        emb.add_field(name="💰 Valor", value=f"**R$ {self.valor}**", inline=True)
        lst = "\n".join([f"👤 {j['m']}" for j in self.jogadores]) or "*Aguardando...*"
        emb.add_field(name="👥 Inscritos", value=lst, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def join(self, it: discord.Interaction, tipo):
        if any(j['id'] == it.user.id for j in self.jogadores):
            return await it.response.send_message("Já está na fila.", ephemeral=True)
        
        # Menciona gelo se for 1v1
        if tipo: await it.channel.send(f"{it.user.mention}-{tipo}")

        self.jogadores.append({'id': it.user.id, 'm': it.user.mention})
        await it.message.edit(embed=self.get_embed())
        
        limite = int(self.modo[0]) * 2 if self.modo[0].isdigit() else 2
        if len(self.jogadores) >= limite:
            await self.start_thread(it, tipo)

    async def leave(self, it):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.message.edit(embed=self.get_embed())

    async def start_thread(self, it, tipo):
        if not fila_mediadores: return await it.channel.send("⚠️ Sem mediadores.", delete_after=5)
        
        med = fila_mediadores.pop(0); fila_mediadores.append(med)
        
        cid = db_query("SELECT valor FROM config WHERE chave='canal_th'")
        if not cid: return
        
        ch = bot.get_channel(int(cid[0]))
        th = await ch.create_thread(name=f"Sessão-{self.valor}", type=discord.ChannelType.public_thread)
        
        # IMAGEM 1 e 2: Embed dentro do tópico
        embed_topico = discord.Embed(title="Aguardando Confirmações", color=COR_CONFIRMACAO)
        embed_topico.set_thumbnail(url=ICONE_ORG)
        
        modo_txt = f"{self.modo} | {tipo if tipo else 'Padrão'}"
        embed_topico.add_field(name="👑 Modo:", value=f"```{modo_txt}```", inline=False)
        embed_topico.add_field(name="💎 Valor da aposta:", value=f"```R$ {self.valor}```", inline=False)
        
        jog_txt = "\n".join([j['m'] for j in self.jogadores])
        embed_topico.add_field(name="⚡ Jogadores:", value=jog_txt, inline=False)
        
        texto_rodape = (
            "✨ SEJAM MUITO BEM-VINDOS ✨\n\n"
            "• Regras adicionais podem ser combinadas entre os participantes.\n"
            "• Se a regra combinada não existir no regulamento oficial da organização, "
            "é obrigatório tirar print do acordo antes do início da partida."
        )
        embed_topico.description = f"```{texto_rodape}```"

        view_c = ViewConfirmacaoThread(self.modo, self.valor, self.jogadores, med)
        await th.send(content=" ".join([j['m'] for j in self.jogadores]), embed=embed_topico, view=view_c)
        
        self.jogadores = []; await it.message.edit(embed=self.get_embed())

# ==============================================================================
#               PAINEL DE MEDIAÇÃO (IMAGEM 4 - RÉPLICA VISUAL)
# ==============================================================================
class ViewPainelMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        # Reproduzindo Imagem 4
        desc = "**Entre na fila para começar a mediar suas filas**\n\n"
        if not fila_mediadores:
            desc += "*A lista está vazia.*"
        else:
            for i, uid in enumerate(fila_mediadores):
                # Formato exato: 1. <@ID> ID
                desc += f"**{i+1} •** <@{uid}> {uid}\n"
        
        emb = discord.Embed(title="Painel da fila controladora", description=desc, color=COR_EMBED_PADRAO)
        emb.set_thumbnail(url=ICONE_ORG)
        # O Fire Esports logo vai no canto se o user tiver (ICONE_ORG serve aqui)
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.success, emoji="🟢")
    async def btn_entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("Você já está na fila.", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.danger, emoji="🔴")
    async def btn_sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed())
        else:
            await interaction.response.send_message("Você não está na fila.", ephemeral=True)

    @discord.ui.button(label="Remover Mediador", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def btn_remover(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Sem permissão.", ephemeral=True)
        
        # Modal ou Select para remover alguém específico
        # Como o print mostra só o botão, farei um select efêmero
        view_rem = View()
        select = UserSelect(placeholder="Selecione o mediador para remover")
        
        async def cb(it: discord.Interaction):
            target_id = select.values[0].id
            if target_id in fila_mediadores:
                fila_mediadores.remove(target_id)
                # Atualiza a mensagem original
                await interaction.message.edit(embed=self.gerar_embed())
                await it.response.send_message(f"Mediador <@{target_id}> removido.", ephemeral=True)
            else:
                await it.response.send_message("Este usuário não está na fila.", ephemeral=True)
        
        select.callback = cb
        view_rem.add_item(select)
        await interaction.response.send_message("Selecione quem remover:", view=view_rem, ephemeral=True)

    @discord.ui.button(label="Painel Staff", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def btn_staff(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Área restrita à Staff.", ephemeral=True)
        await interaction.response.send_message("Painel Staff acessado (Log de Atividades).", ephemeral=True)

@bot.command()
async def mediar(ctx):
    """Gera o painel da Imagem 4."""
    if not ctx.author.guild_permissions.manage_messages: return
    view = ViewPainelMediar()
    await ctx.send(embed=view.gerar_embed(), view=view)

# ==============================================================================
#               PAINEL PIX (IMAGEM 5 - RÉPLICA VISUAL)
# ==============================================================================
class ViewPainelPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="❖")
    async def btn_chave_pix(self, interaction: discord.Interaction, button: Button):
        # Abre Modal de Cadastro
        modal = Modal(title="Cadastrar Chave PIX")
        nome = TextInput(label="Nome Completo")
        chave = TextInput(label="Chave PIX")
        modal.add_item(nome); modal.add_item(chave)
        
        async def on_submit(it: discord.Interaction):
            db_exec("INSERT OR REPLACE INTO pix (user_id, nome, chave) VALUES (?,?,?)", 
                    (it.user.id, nome.value, chave.value))
            await it.response.send_message("✅ Chave cadastrada com sucesso!", ephemeral=True)
        
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍")
    async def btn_sua_chave(self, interaction: discord.Interaction, button: Button):
        res = db_query("SELECT nome, chave FROM pix WHERE user_id=?", (interaction.user.id,))
        if res:
            await interaction.response.send_message(f"👤 **Titular:** {res[0]}\n🔑 **Chave:** `{res[1]}`", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma chave cadastrada.", ephemeral=True)

    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def btn_ver_chave(self, interaction: discord.Interaction, button: Button):
        # Apenas para quem vai pagar
        view_s = View()
        sel = UserSelect(placeholder="Selecione o mediador")
        async def cb(it):
            res = db_query("SELECT nome, chave FROM pix WHERE user_id=?", (sel.values[0].id,))
            if res:
                await it.response.send_message(f"Dados de {sel.values[0].mention}:\nNome: {res[0]}\nChave: `{res[1]}`", ephemeral=True)
            else:
                await it.response.send_message("Mediador sem chave cadastrada.", ephemeral=True)
        sel.callback = cb
        view_s.add_item(sel)
        await interaction.response.send_message("Selecione o mediador:", view=view_s, ephemeral=True)

@bot.command()
async def Pix(ctx):
    """Gera o painel da Imagem 5."""
    emb = discord.Embed(title="Painel Para Configurar Chave PIX", color=COR_EMBED_PADRAO)
    emb.description = (
        "Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\n"
        "Selecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX."
    )
    emb.set_thumbnail(url=ICONE_ORG)
    await ctx.send(embed=emb, view=ViewPainelPix())

# ==============================================================================
#               ADMINISTRAÇÃO (GERAR FILAS)
# ==============================================================================
@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    
    class ModalFila(Modal, title="Gerar Filas"):
        modo = TextInput(label="Modo", default="1v1")
        plat = TextInput(label="Plataforma", default="Mobile")
        async def on_submit(self, it):
            await it.response.send_message("Gerando...", ephemeral=True)
            vals = ["100,00", "50,00", "20,00", "10,00", "5,00", "2,00", "1,00", "0,50"]
            for v in vals:
                view = ViewFilaPrincipal(f"{self.modo.value} | {self.plat.value}", v)
                await it.channel.send(embed=view.get_embed(), view=view)
                await asyncio.sleep(1)

    class ViewL(View):
        @discord.ui.button(label="Gerar Bloco WS", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(ModalFila())

    await ctx.send("Painel Admin", view=ViewL())

@bot.command()
async def canal_fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); s = ChannelSelect()
    async def cb(i):
        db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th', ?)", (str(s.values[0].id),))
        await i.response.send_message("Canal configurado.", ephemeral=True)
    s.callback = cb; v.add_item(s); await ctx.send("Selecione o canal de tópicos:", view=v)

@bot.event
async def on_ready():
    init_db()
    print("WS SYSTEM V.FINAL - OPERACIONAL")

if TOKEN: bot.run(TOKEN)
            
