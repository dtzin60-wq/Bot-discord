import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, ChannelSelect
import sqlite3
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")

BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
FOTO_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = []
partidas_ativas = {}
temp_dados_sala = {}

# ================= BANCO =================

def init_db():
    with sqlite3.connect("dados_bot.db") as con:
        con.execute("""CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER PRIMARY KEY,
            nome TEXT,
            chave TEXT,
            qrcode TEXT
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )""")
        con.commit()

def db_execute(q, p=()):
    with sqlite3.connect("dados_bot.db") as con:
        con.execute(q, p)
        con.commit()

def pegar_config(chave):
    with sqlite3.connect("dados_bot.db") as con:
        r = con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return r[0] if r else None

# ================= VIEW CONFIRMAÇÃO =================

class ViewConfirmacaoFoto(View):
    def __init__(self, p1, p2, med, valor, modo):
        super().__init__(timeout=None)
        self.p1 = p1
        self.p2 = p2
        self.med = med
        self.valor = valor
        self.modo = modo
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in [self.p1, self.p2]:
            return await interaction.response.send_message("Só jogadores podem confirmar.", ephemeral=True)

        self.confirmados.add(interaction.user.id)
        await interaction.response.send_message("Confirmado!", ephemeral=True)

        if len(self.confirmados) == 2:
            emb = discord.Embed(title="💸 PAGAMENTO AO MEDIADOR", color=0xF1C40F)

            with sqlite3.connect("dados_bot.db") as con:
                r = con.execute("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med,)).fetchone()

            emb.add_field(name="Titular", value=r[0] if r else "Pendente")
            emb.add_field(name="Chave", value=r[1] if r else "Pendente")
            emb.add_field(name="Valor", value=f"R$ {self.valor}")

            if r and r[2]:
                emb.set_image(url=r[2])

            await interaction.channel.send(embed=emb)

# ================= VIEW PIX =================

class ViewPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.green)
    async def cadastrar(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Cadastrar Pix")
        nome = TextInput(label="Nome")
        chave = TextInput(label="Chave Pix")
        qr = TextInput(label="Link QR (opcional)", required=False)

        modal.add_item(nome)
        modal.add_item(chave)
        modal.add_item(qr)

        async def submit(it: discord.Interaction):
            db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)",
                       (it.user.id, nome.value, chave.value, qr.value))
            await it.response.send_message("Pix salvo.", ephemeral=True)

        modal.on_submit = submit
        await interaction.response.send_modal(modal)

# ================= VIEW MEDIADORES =================

class ViewMediar(View):
    def __init__(self):
        super().__init__(timeout=None)

    def gerar_embed(self):
        if fila_mediadores:
            lista = "\n".join([f"{i+1} - <@{u}>" for i, u in enumerate(fila_mediadores)])
        else:
            lista = "Nenhum mediador."

        return discord.Embed(title="Fila de Mediadores", description=lista, color=0x2b2d31)

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green)
    async def entrar(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in fila_mediadores:
            fila_mediadores.append(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in fila_mediadores:
            fila_mediadores.remove(interaction.user.id)
            await interaction.response.edit_message(embed=self.gerar_embed(), view=self)

# ================= VIEW FILA =================

class ViewFila(View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor
        self.jogadores = []
        self.message = None

    def gerar_embed(self):
        emb = discord.Embed(title="🎮 FILA DE APOSTAS", color=0x3498DB)
        emb.add_field(name="Valor", value=f"R$ {self.valor}", inline=False)
        emb.add_field(name="Modo", value=self.modo, inline=False)

        if self.jogadores:
            lista = "\n".join([f"{j['mention']} - `{j['gelo']}`" for j in self.jogadores])
        else:
            lista = "Nenhum jogador."

        emb.add_field(name="Jogadores", value=lista, inline=False)
        emb.set_image(url=BANNER_URL)
        return emb

    async def atualizar(self):
        await self.message.edit(embed=self.gerar_embed(), view=self)

    @discord.ui.button(label="Gelo Normal", emoji="❄️")
    async def gelo_normal(self, interaction: discord.Interaction, button: Button):
        await self.adicionar(interaction, "Gelo Normal")

    @discord.ui.button(label="Gelo Infinito", emoji="♾️")
    async def gelo_inf(self, interaction: discord.Interaction, button: Button):
        await self.adicionar(interaction, "Gelo Infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, interaction: discord.Interaction, button: Button):
        self.jogadores = [j for j in self.jogadores if j["id"] != interaction.user.id]
        await interaction.response.send_message("Saiu da fila.", ephemeral=True)
        await self.atualizar()

    async def adicionar(self, interaction, gelo):
        if any(j["id"] == interaction.user.id for j in self.jogadores):
            return await interaction.response.send_message("Já está na fila.", ephemeral=True)

        self.jogadores.append({
            "id": interaction.user.id,
            "mention": interaction.user.mention,
            "gelo": gelo
        })

        await interaction.response.send_message(f"Entrou como {gelo}.", ephemeral=True)
        await self.atualizar()

        if len(self.jogadores) == 2:
            j1, j2 = self.jogadores

            if j1["gelo"] != j2["gelo"]:
                return

            if not fila_mediadores:
                self.jogadores = []
                await self.atualizar()
                return

            med = fila_mediadores.pop(0)
            fila_mediadores.append(med)

            canal_id = pegar_config("canal_th")
            canal = bot.get_channel(int(canal_id)) if canal_id else interaction.channel
            thread = await canal.create_thread(name=f"Partida-R${self.valor}")

            emb = discord.Embed(title="Aguardando Confirmação", color=0x2ecc71)
            emb.add_field(name="Modo", value=self.modo, inline=False)
            emb.add_field(name="Jogadores",
                          value=f"{j1['mention']} - {j1['gelo']}\n{j2['mention']} - {j2['gelo']}",
                          inline=False)
            emb.add_field(name="Valor", value=f"R$ {self.valor}", inline=False)

            await thread.send(
                content=f"<@{j1['id']}> <@{j2['id']}> <@{med}>",
                embed=emb,
                view=ViewConfirmacaoFoto(j1["id"], j2["id"], med, self.valor, self.modo)
            )

            self.jogadores = []
            await self.atualizar()

# ================= COMANDOS =================

@bot.command()
async def Pix(ctx):
    await ctx.send("Cadastrar Pix:", view=ViewPix())

@bot.command()
async def mediar(ctx):
    v = ViewMediar()
    await ctx.send(embed=v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx, modo: str, valor: str):
    view = ViewFila(modo, valor)
    msg = await ctx.send(embed=view.gerar_embed(), view=view)
    view.message = msg

@bot.command()
async def canal(ctx):
    v = View()
    sel = ChannelSelect()

    async def cb(interaction):
        db_execute("INSERT OR REPLACE INTO config VALUES (?,?)", ("canal_th", str(sel.values[0].id)))
        await interaction.response.send_message("Canal configurado.", ephemeral=True)

    sel.callback = cb
    v.add_item(sel)
    await ctx.send("Escolha o canal:", view=v)

# ================= EVENTOS =================

@bot.event
async def on_ready():
    init_db()
    bot.add_view(ViewPix())
    bot.add_view(ViewMediar())
    print("BOT ONLINE:", bot.user)

bot.run(TOKEN)
