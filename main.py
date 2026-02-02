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
COR_EMBED = 0x2b2d31 # Cinza Escuro
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

def db_get_config(chave, default=None):
    res = db_query("SELECT valor FROM config WHERE chave=?", (chave,))
    return res[0] if res else default

# ==============================================================================
#                  VIEW: BOTCONFIG (PAINEL FUNCIONAL)
# ==============================================================================
class ViewBotConfig(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def atualizar_painel(self, interaction):
        """Re-gera o Embed com os dados atualizados do Banco de Dados"""
        
        # Recupera dados salvos
        cargo_med_id = db_get_config("cargo_mediador", "Não Configurado")
        canal_logs_id = db_get_config("canal_logs", "Não Configurado")
        prefixo = db_get_config("prefixo", ".")
        valores_salvos = db_get_config("lista_valores", "100,00 | 80,00 | 50,00 | ...")
        
        # Formata menções para o Embed
        cargo_mention = f"<@&{cargo_med_id}>" if cargo_med_id.isdigit() else cargo_med_id
        canal_mention = f"<#{canal_logs_id}>" if canal_logs_id.isdigit() else canal_logs_id

        emb = discord.Embed(title="Painel de Configurações", color=COR_EMBED)
        emb.description = "Edite as configurações usando os botões abaixo.\n\n"
        
        emb.description += f"**Permissão Máxima:** @Dono\n"
        emb.description += f"**Cargo do Mediador:** {cargo_mention}\n\n"
        
        emb.description += f"**Canal de Logs:** {canal_mention}\n"
        emb.description += f"**Prefixo:** `{prefixo}`\n\n"
        
        emb.description += f"**Valores das Filas (Atuais):**\n`{valores_salvos}`\n\n"
        
        emb.description += "**Outras Configurações:**\n"
        emb.description += "Coins: 1 | Vitórias: 1 | Taxa: R$ 0,10"
        
        emb.set_thumbnail(url=ICONE_ORG)
        await interaction.message.edit(embed=emb, view=self)

    # --- BOTÕES FUNCIONAIS ---

    @discord.ui.button(label="Config Filas", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_filas(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Configurar Valores das Filas")
        valores = TextInput(
            label="Valores (separados por vírgula)", 
            placeholder="Ex: 100,00, 80,00, 50,00",
            default="100,00, 80,00, 60,00, 50,00, 30,00, 20,00, 10,00, 5,00",
            style=discord.TextStyle.paragraph
        )
        modal.add_item(valores)
        
        async def on_submit(it):
            # Limpa e formata a string para salvar
            lista_limpa = [v.strip() for v in valores.value.split(',')]
            string_salva = ", ".join(lista_limpa)
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("lista_valores", string_salva))
            
            await it.response.send_message(f"✅ Valores atualizados!", ephemeral=True)
            await self.atualizar_painel(interaction)
            
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Config Cargos", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_cargos(self, interaction: discord.Interaction, button: Button):
        view = View()
        select = RoleSelect(placeholder="Selecione o cargo de Mediador")
        
        async def callback(it):
            role = select.values[0]
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("cargo_mediador", str(role.id)))
            await it.response.send_message(f"✅ Cargo definido: {role.mention}", ephemeral=True)
            await self.atualizar_painel(interaction)
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Selecione o cargo:", view=view, ephemeral=True)

    @discord.ui.button(label="Setar as Logs", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
    async def btn_logs(self, interaction: discord.Interaction, button: Button):
        view = View()
        select = ChannelSelect(placeholder="Selecione o canal de Logs", channel_types=[discord.ChannelType.text])
        
        async def callback(it):
            ch = select.values[0]
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("canal_logs", str(ch.id)))
            await it.response.send_message(f"✅ Logs definidas para: {ch.mention}", ephemeral=True)
            await self.atualizar_painel(interaction)
            
        select.callback = callback
        view.add_item(select)
        await interaction.response.send_message("Selecione o canal:", view=view, ephemeral=True)

    @discord.ui.button(label="Alterar Prefixo", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_prefixo(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Novo Prefixo")
        px = TextInput(label="Prefixo", placeholder="Ex: !", max_length=3)
        modal.add_item(px)
        
        async def on_submit(it):
            db_exec("INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)", ("prefixo", px.value))
            bot.command_prefix = px.value
            await it.response.send_message(f"✅ Prefixo alterado para: `{px.value}`", ephemeral=True)
            await self.atualizar_painel(interaction)
            
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Perfil do Bot", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_perfil(self, interaction: discord.Interaction, button: Button):
        modal = Modal(title="Perfil do Bot")
        nome = TextInput(label="Novo Nome", required=False)
        modal.add_item(nome)
        
        async def on_submit(it):
            if nome.value: await bot.user.edit(username=nome.value)
            await it.response.send_message("✅ Perfil atualizado.", ephemeral=True)
            
        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

# ==============================================================================
#                  COMANDO SLASH: /botconfig
# ==============================================================================
@bot.tree.command(name="botconfig", description="Painel de Configurações Geral")
async def slash_botconfig(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

    try:
        await interaction.response.defer(ephemeral=False)
        
        # Recupera configurações atuais para exibir
        cargo = db_get_config("cargo_mediador", "@Mediador")
        logs = db_get_config("canal_logs", "#logs")
        prefix = db_get_config("prefixo", ".")
        
        # Formata se for ID
        if cargo.isdigit(): cargo = f"<@&{cargo}>"
        if logs.isdigit(): logs = f"<#{logs}>"

        emb = discord.Embed(title="Painel de Configurações", color=COR_EMBED)
        emb.description = f"""
Edite as configurações usando os botões abaixo.

**Cargos e Permissões:**
Cargo do Mediador: {cargo}

**Canais:**
Canal de Logs: {logs}

**Sistema:**
Prefixo: `{prefix}`
Taxa da Sala: R$ 0,10

**Use os botões abaixo para editar.**
"""
        emb.set_thumbnail(url=ICONE_ORG)
        await interaction.followup.send(embed=emb, view=ViewBotConfig())
        
    except Exception as e:
        traceback.print_exc()

# ==============================================================================
#                  SISTEMA DE FILAS E APOSTAS
# ==============================================================================

class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m=Modal(title="Cadastrar Pix"); n=TextInput(label="Nome"); c=TextInput(label="Chave"); q=TextInput(label="QR Code", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def sub(i): db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value)); await i.response.send_message("Salvo.", ephemeral=True)
        m.on_submit=sub; await it.response.send_modal(m)
    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.success, emoji="🔍")
    async def ver(self, it, b):
        d=db_query("SELECT * FROM pix WHERE user_id=?",(it.user.id,))
        if d: await it.response.send_message(f"Nome: {d[1]}\nChave: `{d[2]}`\nQR: {d[3] or 'N/A'}", ephemeral=True)
        else: await it.response.send_message("Sem dados.", ephemeral=True)
    @discord.ui.button(label="Ver Chave Mediador", style=discord.ButtonStyle.secondary, emoji="🔍")
    async def vermed(self, it, b):
        v=View(); s=UserSelect()
        async def cb(i):
            d=db_query("SELECT * FROM pix WHERE user_id=?",(s.values[0].id,))
            if d: await i.response.send_message(f"Dados de {s.values[0].mention}:\nNome: {d[1]}\nChave: `{d[2]}`", ephemeral=True)
            else: await i.response.send_message("Sem dados.", ephemeral=True)
        s.callback=cb; v.add_item(s); await it.response.send_message("Selecione:", view=v, ephemeral=True)

class ViewConfirmacao(View):
    def __init__(self, jog, med, val): super().__init__(timeout=None); self.jog=jog; self.med=med; self.val=val; self.cnf=[]
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def c(self, it, b):
        if it.user.id in [j['id'] for j in self.jog] and it.user.id not in self.cnf:
            self.cnf.append(it.user.id); await it.channel.send(embed=discord.Embed(description=f"**{it.user.mention} confirmou!**", color=COR_VERDE))
            if len(self.cnf)>=len(self.jog):
                self.stop(); await it.channel.send(content=f"<@{self.med}>", embed=discord.Embed(title="✅ SESSÃO INICIADA", description=f"Mediador: <@{self.med}>\nValor: {self.val}", color=COR_VERDE))
                db_exec("UPDATE pix_saldo SET saldo=saldo+0.10 WHERE user_id=?",(self.med,))
    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def r(self, it, b): 
        if it.user.id in [j['id'] for j in self.jog]: await it.channel.delete()

class ViewFila(View):
    def __init__(self, m, v): super().__init__(timeout=None); self.m=m; self.v=v; self.j=[]
    def _stup(self):
        self.clear_items()
        if "1V1" in self.m.upper():
            b1=Button(label="Gelo Normal", style=discord.ButtonStyle.secondary); b2=Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary)
            b1.callback=lambda i: self.join(i,"Gelo Normal"); b2.callback=lambda i: self.join(i,"Gelo Infinito"); self.add_item(b1); self.add_item(b2)
        else:
            b=Button(label="/entrar na fila", style=discord.ButtonStyle.success); b.callback=lambda i: self.join(i,None); self.add_item(b)
        bs=Button(label="Sair da Fila", style=discord.ButtonStyle.danger); bs.callback=self.leave; self.add_item(bs)
    def emb(self):
        e=discord.Embed(title=f"Sessão | {self.m}", color=COR_EMBED); e.set_image(url=BANNER_URL); e.add_field(name="Valor", value=self.v)
        lst=[f"👤 {p['m']} - {p['t']}" if p['t'] else f"👤 {p['m']}" for p in self.j]
        e.add_field(name="Jogadores", value="\n".join(lst) or "Aguardando...", inline=False); return e
    async def join(self, it, t):
        if any(x['id']==it.user.id for x in self.j): return await it.response.send_message("Já está.", ephemeral=True)
        self.j.append({'id':it.user.id,'m':it.user.mention,'t':t}); await it.response.edit_message(embed=self.emb())
        lim=int(self.m[0])*2 if self.m[0].isdigit() else 2
        if len(self.j)>=lim:
            if not fila_mediadores: return await it.channel.send("Sem mediadores.", delete_after=5)
            md=fila_mediadores.pop(0); fila_mediadores.append(md); cf=db_query("SELECT valor FROM config WHERE chave='canal_th'")
            if cf:
                ch=bot.get_channel(int(cf[0])); th=await ch.create_thread(name=f"Sessão-{self.v}", type=discord.ChannelType.public_thread)
                e=discord.Embed(title="Aguardando", description="Confirmem.", color=COR_VERDE); e.add_field(name="Jogadores", value="\n".join([x['m'] for x in self.j]))
                await th.send(content=" ".join([x['m'] for x in self.j]), embed=e, view=ViewConfirmacao(self.j, md, self.v))
            self.j=[]; await it.message.edit(embed=self.emb())
    async def leave(self, it): self.j=[x for x in self.j if x['id']!=it.user.id]; await it.response.edit_message(embed=self.emb())

# ==============================================================================
#                  COMANDOS
# ==============================================================================
@bot.tree.command(name="pix", description="Painel Pix")
async def slash_pix(it: discord.Interaction):
    await it.response.defer(ephemeral=False); e=discord.Embed(title="Painel Pix", color=COR_EMBED); e.set_thumbnail(url=ICONE_ORG); await it.followup.send(embed=e, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    if not ctx.author.guild_permissions.manage_messages: return
    class V(View):
        def e(self): return discord.Embed(description="**Mediadores:**\n"+"\n".join([f"{i+1}. <@{u}>" for i,u in enumerate(fila_mediadores)]), color=COR_EMBED)
        @discord.ui.button(label="Entrar", style=discord.ButtonStyle.success)
        async def en(self,i,b): 
            if i.user.id not in fila_mediadores: fila_mediadores.append(i.user.id); await i.response.edit_message(embed=self.e())
        @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger)
        async def sa(self,i,b): 
            if i.user.id in fila_mediadores: fila_mediadores.remove(i.user.id); await i.response.edit_message(embed=self.e())
    v=V(); await ctx.send(embed=v.e(), view=v)

@bot.command()
async def fila(ctx):
    if not ctx.author.guild_permissions.administrator: return
    class M(Modal, title="Gerar"):
        m=TextInput(label="Modo", default="1v1"); p=TextInput(label="Plat", default="Mobile")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True)
            # RECUPERA VALORES DO DB OU USA O PADRÃO SOLICITADO
            db_vals = db_get_config("lista_valores")
            if db_vals:
                vals = [v.strip() for v in db_vals.split(',')]
            else:
                # LISTA PADRÃO SOLICITADA (Valores Altos Primeiro)
                vals = ["100,00", "80,00", "60,00", "50,00", "40,00", "30,00", "20,00", "10,00", "5,00", "2,00"]
            
            for v in vals:
                vi=ViewFila(f"{self.m.value}|{self.p.value}", v); vi._stup()
                await i.channel.send(embed=vi.emb(), view=vi); await asyncio.sleep(1)
    class V(View):
        @discord.ui.button(label="Gerar", style=discord.ButtonStyle.danger)
        async def g(self, i, b): await i.response.send_modal(M())
    await ctx.send("Admin", view=V())

@bot.command()
async def canal_fila(ctx):
    v=View(); s=ChannelSelect()
    async def cb(i): db_exec("INSERT OR REPLACE INTO config VALUES ('canal_th',?)", (str(s.values[0].id),)); await i.response.send_message("Salvo", ephemeral=True)
    s.callback=cb; v.add_item(s); await ctx.send("Canal:", view=v)

@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print("ONLINE - CONFIG ATIVA")

if TOKEN: bot.run(TOKEN)
    
