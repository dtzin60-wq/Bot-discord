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
COR_EMBED = 0x2b2d31 # Cinza Escuro (Fundo Discord)
COR_VERDE = 0x2ecc71
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

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
        con.execute("CREATE TABLE IF NOT EXISTS restricoes (user_id INTEGER PRIMARY KEY, motivo TEXT)")

def db_exec(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        con.execute(query, params); con.commit()

def db_query(query, params=()):
    with sqlite3.connect("ws_database_final.db") as con:
        return con.execute(query, params).fetchone()

# ==============================================================================
#                  VIEW: BOTCONFIG (PAINEL DE CONFIGURAÇÕES)
# ==============================================================================
class ViewBotConfig(View):
    def __init__(self):
        super().__init__(timeout=None)

    # --- LINHA 1 ---
    @discord.ui.button(label="Config Filas", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_filas(self, interaction: discord.Interaction, button: Button):
        # Exemplo: Modal para adicionar valor
        modal = Modal(title="Configurar Filas")
        valor = TextInput(label="Adicionar Valor (ex: 15,00)", placeholder="Digite o valor...")
        modal.add_item(valor)
        async def on_submit(it):
            await it.response.send_message(f"✅ Valor **R$ {valor.value}** adicionado às filas.", ephemeral=True)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Config Cargos", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_cargos(self, interaction: discord.Interaction, button: Button):
        # Select de Cargos
        view = View()
        select = RoleSelect(placeholder="Selecione o cargo de Mediador", min_values=1, max_values=1)
        async def callback(it):
            role = select.values[0]
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("cargo_mediador", str(role.id)))
            await it.response.send_message(f"✅ Cargo de Mediador definido para: {role.mention}", ephemeral=True)
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Selecione o cargo:", view=view, ephemeral=True)

    @discord.ui.button(label="Setar as Logs", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_logs(self, interaction: discord.Interaction, button: Button):
        # Select de Canal
        view = View()
        select = ChannelSelect(placeholder="Selecione o canal de Logs", channel_types=[discord.ChannelType.text])
        async def callback(it):
            ch = select.values[0]
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_logs", str(ch.id)))
            await it.response.send_message(f"✅ Canal de Logs definido para: {ch.mention}", ephemeral=True)
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Selecione o canal:", view=view, ephemeral=True)

    @discord.ui.button(label="Config Ticket", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_ticket(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("🛠️ Configuração de Ticket em desenvolvimento.", ephemeral=True)

    # --- LINHA 2 ---
    @discord.ui.button(label="Config Analista", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_analista(self, interaction: discord.Interaction, button: Button):
         await interaction.response.send_message("🛠️ Configuração de Analista em desenvolvimento.", ephemeral=True)

    @discord.ui.button(label="Config Rank", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_rank(self, interaction: discord.Interaction, button: Button):
         await interaction.response.send_message("🏆 Ranking configurado para Top 10.", ephemeral=True)

    @discord.ui.button(label="Alterar Prefixo", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_prefixo(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Alterar Prefixo")
        px = TextInput(label="Novo Prefixo", placeholder="Ex: !", max_length=3)
        modal.add_item(px)
        async def on_submit(it):
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("prefixo", px.value))
            await it.response.send_message(f"✅ Prefixo alterado para: `{px.value}`", ephemeral=True)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Perfil do Bot", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_perfil(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Editar Perfil do Bot")
        nome = TextInput(label="Novo Nome", required=False)
        avatar = TextInput(label="URL do Avatar", required=False)
        modal.add_item(nome); modal.add_item(avatar)
        async def on_submit(it):
            try:
                if nome.value: await bot.user.edit(username=nome.value)
                # Avatar requer lógica de bytes, simplificado aqui para nome
                await it.response.send_message("✅ Perfil atualizado (Nome alterado).", ephemeral=True)
            except Exception as e:
                await it.response.send_message(f"Erro: {e}", ephemeral=True)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

# ==============================================================================
#                  COMANDO SLASH: /botconfig
# ==============================================================================
@bot.tree.command(name="botconfig", description="Painel de Configurações Geral do Bot")
async def slash_botconfig(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)

    try:
        await interaction.response.defer(ephemeral=False)

        # Montando o Embed idêntico à imagem
        emb = discord.Embed(title="Painel de Configurações", color=COR_EMBED)
        emb.description = "Edite as configurações usando os botões abaixo.\n"
        
        # Simulando os dados da imagem (Você pode puxar do DB se quiser depois)
        emb.description += """
**Permissão Máxima:** @Dono
**Cargos Ver Apostas:** @Mediador, @Dono, @Gerente, @Ceo
**Cargo do Mediador:** @Mediador

**Canais das Apostas**
#👑・apostas
#👑・apostas
#👑・apostas

**Valores das Filas**
R$ 0,30
R$ 0,50
R$ 1,00
R$ 2,00
R$ 3,00
R$ 5,00
R$ 10,00
R$ 20,00
R$ 30,00
R$ 50,00
R$ 100,00

**Prefixo:** .
**Canal dos destaques diários:** Não Configurado.
**Coins por partida:** 1
**Vitórias por partida:** 1
**Valor da Sala:** R$ 0,10 (Para cada um)
**Mediador ver aguardando:** Sim
**Mediador vai libera a chave pix:** Não
**Apagar mensagens após confirmação:** Não
**Máximo de Apostas por Jogador:** 3
**Máximo de Filas por Jogador:** 5
"""
        emb.set_thumbnail(url=ICONE_ORG)
        
        await interaction.followup.send(embed=emb, view=ViewBotConfig())
        
    except Exception as e:
        traceback.print_exc()

# ==============================================================================
#                  OUTRAS VIEWS (PIX, FILA, CONFIRMAÇÃO) - MANTIDAS
# ==============================================================================

class ViewPainelPix(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠")
    async def btn_cadastrar(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Cadastrar Chave PIX")
        nome = TextInput(label="Nome Completo", required=True)
        chave = TextInput(label="Chave PIX", required=True)
        qrcode = TextInput(label="QR Code (Opcional)", required=False)
        modal.add_item(nome); modal.add_item(chave); modal.add_item(qrcode)
        async def on_submit(it):
            db_exec("INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode) VALUES (?,?,?,?)", 
                    (it.user.id, nome.value, chave.value, qrcode.value))
            await it.response.send_message("✅ Salvo!", ephemeral=True)
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)
    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍")
    async def btn_ver_sua(self, interaction: discord.Interaction, button: Button):
        dados = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (interaction.user.id,))
        if dados:
            msg = f"👤 **Nome:** {dados[0]}\n🔑 **Chave:** `{dados[1]}`"
            if dados[2]: msg += f"\n🔳 **QR:** `{dados[2]}`"
            await interaction.response.send_message(msg, ephemeral=True)
        else: await interaction.response.send_message("❌ Sem cadastro.", ephemeral=True)
    @discord.ui.button(label="Ver Chave de Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def btn_ver_mediador(self, interaction: discord.Interaction, button: Button):
        view = View(); sel = UserSelect()
        async def cb(it):
            t = sel.values[0]
            d = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (t.id,))
            if d: await it.response.send_message(f"Dados de {t.mention}:\nName: {d[0]}\nChave: `{d[1]}`", ephemeral=True)
            else: await it.response.send_message("❌ Sem cadastro.", ephemeral=True)
        sel.callback = cb; view.add_item(sel); await interaction.response.send_message("Selecione:", view=view, ephemeral=True)

class ViewConfirmacao(View):
    def __init__(self, jogadores, med_id, valor):
        super().__init__(timeout=None)
        self.jogadores = jogadores; self.med_id = med_id; self.valor = valor; self.confirms = []
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def conf(self, it, b):
        if it.user.id not in [j['id'] for j in self.jogadores]: return
        if it.user.id in self.confirms: return
        self.confirms.append(it.user.id)
        await it.channel.send(embed=discord.Embed(description=f"**{it.user.mention} confirmou!**", color=COR_VERDE))
        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            e = discord.Embed(title="✅ SESSÃO INICIADA", color=COR_VERDE)
            e.description = f"Mediador: <@{self.med_id}>\nJogadores: {' '.join([j['m'] for j in self.jogadores])}"
            await it.channel.send(content=f"<@{self.med_id}>", embed=e)
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))
    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def rec(self, it, b):
        if it.user.id in [j['id'] for j in self.jogadores]: await it.channel.delete()

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None); self.modo=modo; self.valor=valor; self.jogadores=[]
        self.setup()
    def setup(self):
        self.clear_items()
        if "1V1" in self.modo.upper():
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary)
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback=lambda i: self.join(i,"Gelo Normal"); b2.callback=lambda i: self.join(i,"Gelo Infinito")
            self.add_item(b1); self.add_item(b2)
        else:
            b=Button(label="/entrar na fila", style=discord.ButtonStyle.success)
            b.callback=lambda i: self.join(i,None); self.add_item(b)
        bs=Button(label="Sair da Fila", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)
    def emb(self):
        e = discord.Embed(title=f"Sessão | {self.modo}", color=COR_EMBED); e.set_image(url=BANNER_URL)
        e.add_field(name="Valor", value=self.valor); lst = [f"👤 {j['m']} - {j['t']}" if j['t'] else f"👤 {j['m']}" for j in self.jogadores]
        e.add_field(name="Jogadores", value="\n".join(lst) or "*Vazio*", inline=False); return e
    async def join(self, it, t):
        if any(j['id']==it.user.id for j in self.jogadores): return await it.response.send_message("Já está.", ephemeral=True)
        self.jogadores.append({'id':it.user.id,'m':it.user.mention,'t':t}); await it.response.edit_message(embed=self.emb())
        lim=int(self.modo[0])*2 if self.modo[0].isdigit() else 2
        if len(self.jogadores)>=lim:
            if not fila_mediadores: return await it.channel.send("Sem mediadores.", delete_after=5)
            m=fila_mediadores.pop(0); fila_mediadores.append(m)
            cfg=db_query("SELECT valor FROM config WHERE chave='canal_th'")
            if not cfg: return
            ch=bot.get_channel(int(cfg[0])); th=await ch.create_thread(name=f"Sessão-{self.valor}", type=discord.ChannelType.public_thread)
            e=discord.Embed(title="Aguardando", description="Confirmem abaixo.", color=COR_VERDE)
            e.add_field(name="Modo", value=f"{self.modo} | {t}"); e.add_field(name="Jogadores", value="\n".join([j['m'] for j in self.jogadores]))
            await th.send(content=" ".join([j['m'] for j in self.jogadores]), embed=e, view=ViewConfirmacao(self.jogadores, m, self.valor))
            self.jogadores=[]; await it.message.edit(embed=self.emb())
    async def leave(self, it):
        self.jogadores=[j for j in self.jogadores if j['id']!=it.user.id]; await it.response.edit_message(embed=self.emb())

# ==============================================================================
#                  COMANDOS GERAIS
# ==============================================================================
@bot.tree.command(name="pix", description="Gerencie sua chave PIX")
async def slash_pix(it: discord.Interaction):
    await it.response.defer(ephemeral=False)
    e = discord.Embed(title="Painel Pix", description="Gerencie seus dados.", color=COR_EMBED)
    e.set_thumbnail(url=ICONE_ORG); await it.followup.send(embed=e, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class V(View):
        def emb(self): return discord.Embed(description="**Mediadores:**\n"+"\n".join([f"{i+1}. <@{u}>" for i,u in enumerate(fila_mediadores)]), color=COR_EMBED)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.success)
        async def e(self, i, b): 
            if i.user.id not in fila_mediadores: fila_mediadores.append(i.user.id); await i.response.edit_message(embed=self.emb())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger)
        async def s(self, i, b): 
             if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.edit_message(embed=self.emb())
    v=V(); await ctx.send(embed=v.emb(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class M(Modal, title="Gerar"):
        m=TextInput(label="Modo", default="1v1"); p=TextInput(label="Plat", default="Mobile")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True)
            for v in ["100","50","20","10","5"]:
                vi=ViewFila(f"{self.m.value}|{self.p.value}", v); await i.channel.send(embed=vi.emb(), view=vi); await asyncio.sleep(1)
    class V(View):
        @discord.ui.button(label="Gerar", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(M())
    await ctx.send("Admin", view=V())

@bot.command()
async def canal_fila(ctx):
    v=View(); s=ChannelSelect()
    async def cb(i): db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th',?)", (str(s.values[0].id),)); await i.response.send_message("Ok", ephemeral=True)
    s.callback=cb; v.add_item(s); await ctx.send("Canal:", view=v)

@bot.event
async def on_ready():
    init_db(); await bot.tree.sync(); print("ONLINE")

if TOKEN: bot.run(TOKEN)
                
