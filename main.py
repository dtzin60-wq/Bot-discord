import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging
import datetime

# ==============================================================================
#                               CONFIGURAÇÕES TÉCNICAS
# ==============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

TOKEN = os.getenv("TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Estados Globais
fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ==============================================================================
#                               BANCO DE DADOS
# ==============================================================================

def init_db():
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            chave TEXT,
            qrcode TEXT,
            partidas_feitas INTEGER DEFAULT 0
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )""")
        con.commit()

def db_execute(query, params=()):
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(query, params)
        con.commit()

def pegar_config(chave):
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

def buscar_mediador(user_id):
    with sqlite3.connect("dados_bot.db") as con:
        return con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (user_id,)).fetchone()

# ==============================================================================
#                             VISUAL DO COMANDO .Pix
# ==============================================================================

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Cadastrar Minha Chave", 
        style=discord.ButtonStyle.green, 
        emoji="💠", 
        custom_id="btn_pix_cad_v15"
    )
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Configuração de Recebimento WS")
        nome = TextInput(label="Nome do Titular", placeholder="Nome que aparece no banco", min_length=3)
        chave = TextInput(label="Chave Pix", placeholder="CPF, E-mail, Telefone ou Aleatória")
        qr = TextInput(label="Link do QR Code (Opcional)", placeholder="URL da imagem do QR Code", required=False)

        modal.add_item(nome); modal.add_item(chave); modal.add_item(qr)

        async def on_submit(it: discord.Interaction):
            db_execute(
                "INSERT OR REPLACE INTO pix (user_id, nome, chave, qrcode, partidas_feitas) VALUES (?,?,?,?, (SELECT partidas_feitas FROM pix WHERE user_id=?))",
                (it.user.id, nome.value, chave.value, qr.value, it.user.id)
            )
            emb = discord.Embed(title="✅ Dados Salvos!", description=f"**Titular:** {nome.value}\n**Chave:** `{chave.value}`", color=0x2ecc71)
            await it.response.send_message(embed=emb, ephemeral=True)

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Ver Minha Chave Pix", 
        style=discord.ButtonStyle.secondary, 
        emoji="🔍", 
        custom_id="btn_pix_ver_v15"
    )
    async def ver_chave(self, interaction: discord.Interaction, button: Button):
        r = buscar_mediador(interaction.user.id)
        if not r:
            return await interaction.response.send_message("❌ Você ainda não tem uma chave cadastrada!", ephemeral=True)
        
        emb = discord.Embed(title="💠 Seus Dados Cadastrados", color=0x3498db)
        emb.add_field(name="👤 Titular", value=r[0], inline=True)
        emb.add_field(name="🔑 Chave", value=f"`{r[1]}`", inline=True)
        if r[2]: emb.set_image(url=r[2])
        
        await interaction.response.send_message(embed=emb, ephemeral=True)

# ==============================================================================
#                          VISUAL DO COMANDO .mediar
# ==============================================================================

class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        lista = ""
        if fila_mediadores:
            for i, u_id in enumerate(fila_mediadores):
                r = buscar_mediador(u_id)
                nome = r[0] if r else "Mediador sem Nome"
                lista += f"**{i+1} •** {nome} (<@{u_id}>)\n"
        else:
            lista = "*Nenhum mediador disponível no momento.*"
            
        emb = discord.Embed(
            title="🛡️ Painel da Fila Controladora", 
            description=f"__Entre para mediar apostas__\n\n{lista}", 
            color=0x2b2d31
        )
        emb.set_thumbnail(url=bot.user.display_avatar.url)
        emb.set_footer(text="WS Apostas - Sistema de Mediação")
        return emb

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢", custom_id="btn_medin_v15")
    async def entrar(self, it, b):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("⚠️ Você já está na fila!", ephemeral=True)

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴", custom_id="btn_medout_v15")
    async def sair(self, it, b):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.response.edit_message(embed=self.gerar_embed())
        else:
            await it.response.send_message("⚠️ Você não está na fila!", ephemeral=True)

# ==============================================================================
#                          LÓGICA DA FILA E TÓPICOS
# ==============================================================================

class ViewConfirmacaoFoto(View):
    def __init__(self, p1, p2, med, valor, modo):
        super().__init__(timeout=None)
        self.p1, self.p2, self.med = p1, p2, med
        self.valor, self.modo = valor, modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, custom_id="btn_conf_v15")
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.p1, self.p2]:
            return await interaction.response.send_message("❌ Apenas jogadores confirmam.", ephemeral=True)

        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou!", delete_after=2)

        if len(self.confirmados) == 2:
            await asyncio.sleep(1)
            await interaction.channel.purge(limit=10)

            r = buscar_mediador(self.med)
            nome_med = r[0] if r else "Pendente"

            try:
                v_limpo = self.valor.replace('R$', '').replace(',', '.').strip()
                v_final = f"{(float(v_limpo) + 0.10):.2f}".replace('.', ',')
            except: v_final = self.valor

            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)
            emb.add_field(name="👤 Titular", value=f"**{nome_med}**", inline=True)
            emb.add_field(name="💠 Chave Pix", value=f"`{r[1]}`" if r else "Pendente", inline=True)
            emb.add_field(name="💰 Valor com Taxa", value=f"R$ {v_final}", inline=False)
            if r and r[2]: emb.set_image(url=r[2])

            await interaction.channel.send(content=f"🔔 <@{self.med}> | <@{self.p1}> <@{self.p2}>", embed=emb)
            db_execute("UPDATE pix SET partidas_feitas = partidas_feitas + 1 WHERE user_id=?", (self.med,))

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, custom_id="btn_rec_v15")
    async def recusar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.p1, self.p2]: return
        await interaction.channel.send(f"❌ Partida cancelada por {interaction.user.mention}.")
        await asyncio.sleep(3); await interaction.channel.delete()

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo, self.valor, self.jogadores, self.message = modo, valor, [], None

    def gerar_embed(self):
        emb = discord.Embed(color=0x3498DB)
        emb.set_author(name="🎮 FILA DE APOSTAS", icon_url=bot.user.display_avatar.url)
        emb.add_field(name="💰 **Valor**", value=f"{self.valor}", inline=False)
        emb.add_field(name="🏆 **Modo**", value=f"{self.modo}", inline=False)
        lista = "\n".join([f"👤 {j['mention']} - `{j['gelo']}`" for j in self.jogadores]) if self.jogadores else "Nenhum jogador na fila"
        emb.add_field(name="⚡ **Jogadores**", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def atualizar(self):
        try: await self.message.edit(embed=self.gerar_embed(), view=self)
        except: pass

    @discord.ui.button(label="Gelo Normal", emoji="❄️", style=discord.ButtonStyle.secondary)
    async def g_n(self, it, b): await self.add(it, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", emoji="♾️", style=discord.ButtonStyle.secondary)
    async def g_i(self, it, b): await self.add(it, "Gelo Infinito")

    @discord.ui.button(label="Sair da Fila", style=discord.ButtonStyle.danger, emoji="🚪")
    async def sair(self, it, b):
        self.jogadores = [j for j in self.jogadores if j["id"] != it.user.id]
        await it.response.send_message("🚪 Saiu da fila.", ephemeral=True); await self.atualizar()

    async def add(self, it, gelo):
        if any(j["id"] == it.user.id for j in self.jogadores):
            return await it.response.send_message("⚠️ Já está na fila.", ephemeral=True)
        self.jogadores.append({"id": it.user.id, "mention": it.user.mention, "gelo": gelo})
        await it.response.send_message(f"✅ Entrou como {gelo}.", ephemeral=True); await self.atualizar()

        if len(self.jogadores) == 2:
            if not fila_mediadores:
                self.jogadores = []; await self.atualizar()
                return await it.channel.send("❌ Sem mediadores online.", delete_after=5)

            j1, j2 = self.jogadores
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            c_id = pegar_config("canal_th")
            canal = bot.get_channel(int(c_id)) if c_id else it.channel
            th = await canal.create_thread(name=f"Partida-R${self.valor}", type=discord.ChannelType.public_thread)
            
            emb_th = discord.Embed(title="Aguardando Confirmações", color=0x2ecc71)
            emb_th.set_thumbnail(url=FOTO_BONECA)
            emb_th.add_field(name="👑 **Modo:**", value=f"```\n{self.modo}\n```", inline=False)
            emb_th.add_field(name="⚡ **Jogadores:**", value=f"{j1['mention']} - `{j1['gelo']}`\n{j2['mention']} - `{j2['gelo']}`", inline=False)
            emb_th.add_field(name="💸 **Valor da aposta:**", value=f"```\nR$ {self.valor}\n```", inline=False)
            
            r_med = buscar_mediador(med_id)
            nome_disp = r_med[0] if r_med else "Mediador"
            emb_th.add_field(name="👮 **Mediador:**", value=f"```\n{nome_disp} (@{med_id})\n```", inline=False)

            await th.send(content=f"🔔 <@{med_id}> | {j1['mention']} {j2['mention']}", embed=emb_th, view=ViewConfirmacaoFoto(j1["id"], j2["id"], med_id, self.valor, self.modo))
            partidas_ativas[th.id] = {'med': med_id, 'p1': j1['id'], 'p2': j2['id'], 'modo': self.modo}
            self.jogadores = []; await self.atualizar()

# ==============================================================================
#                               COMANDOS
# ==============================================================================

@bot.command()
async def Pix(ctx):
    embed = discord.Embed(
        title="⚙️ CONFIGURAÇÃO DE PAGAMENTOS",
        description=(
            "Olá mediador! Use os botões abaixo para gerenciar seus dados.\n\n"
            "**Instruções:**\n"
            "1. Clique em 'Cadastrar' para salvar seu Pix.\n"
            "2. Clique em 'Ver Minha Chave' para conferir o que está salvo.\n\n"
            "*Lembre-se: O bot soma R$ 0,10 automaticamente ao valor.*"
        ),
        color=0x2b2d31
    )
    embed.set_footer(text="WS Apostas - Painel do Mediador")
    await ctx.send(embed=embed, view=ViewPix())

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    view = ViewMediar()
    await ctx.send(embed=view.gerar_embed(), view=view)

@bot.command()
async def fila(ctx, modo: str, valor: str):
    if not ctx.author.guild_permissions.administrator: return
    view = ViewFila(modo, valor); msg = await ctx.send(embed=view.gerar_embed(), view=view); view.message = msg

@bot.command()
async def canal(ctx):
    if not ctx.author.guild_permissions.administrator: return
    v = View(); sel = ChannelSelect()
    async def cb(it):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await it.response.send_message("✅ Canal configurado!", ephemeral=True)
    sel.callback = cb; v.add_item(sel); await ctx.send("Escolha o canal alvo:", view=v)

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id in partidas_ativas:
        d = partidas_ativas[message.channel.id]
        if message.author.id == d['med'] and message.content.isdigit():
            if message.channel.id not in temp_dados_sala:
                temp_dados_sala[message.channel.id] = message.content
                await message.delete(); await message.channel.send("✅ ID salvo! Mande a **Senha**.", delete_after=2)
            else:
                s = message.content; i = temp_dados_sala.pop(message.channel.id); await message.delete()
                e = discord.Embed(title="🚀 DADOS DA SALA", color=0x2ecc71)
                e.description = f"**ID:** `{i}`\n**Senha:** `{s}`\n**Modo:** {d['modo']}"; e.set_image(url=BANNER_URL)
                await message.channel.send(content=f"<@{d['p1']}> <@{d['p2']}>", embed=e)
    await bot.process_commands(message)

@bot.event
async def on_ready():
    init_db(); bot.add_view(ViewPix()); bot.add_view(ViewMediar()); print(f"✅ WS Online: {bot.user}")

if TOKEN: bot.run(TOKEN)
        
