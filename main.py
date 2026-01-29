import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput, RoleSelect, ChannelSelect, Select
import sqlite3
import os
import asyncio
import aiohttp
import re

# ================= CONFIGURAÇÕES =================
TOKEN = os.getenv("DISCORD_TOKEN")
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
LOGO_URL = "https://cdn.discordapp.com/emojis/1234567890.png" 

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix=".", intents=intents)

fila_mediadores = [] 
filas_partida = {} 
partidas_ativas = {}

# ================= BANCO DE DADOS =================
def init_db():
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS pix (user_id INTEGER PRIMARY KEY, nome TEXT, chave TEXT, qr TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS config (chave TEXT PRIMARY KEY, valor TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats 
                      (user_id INTEGER PRIMARY KEY, vitorias INTEGER DEFAULT 0, 
                       derrotas INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, coins INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def db_execute(query, params=()):
    conn = sqlite3.connect("dados.db")
    cursor = conn.cursor()
    cursor.execute(query, params)
    res = cursor.fetchone()
    conn.commit()
    conn.close()
    return res

def salvar_config(chave, valor):
    db_execute("INSERT OR REPLACE INTO config VALUES (?, ?)", (chave, str(valor)))

def puxar_config(chave):
    res = db_execute("SELECT valor FROM config WHERE chave = ?", (chave,))
    return res[0] if res else None

def tem_permissao(member, chave_config):
    role_id = puxar_config(chave_config)
    if not role_id: return member.guild_permissions.administrator
    role = member.guild.get_role(int(role_id))
    return role in member.roles or member.guild_permissions.administrator

# ================= PAINEL PIX (ESTILO ORG FIRE) =================

class ViewPainelPix(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Chave pix", style=discord.ButtonStyle.green, emoji="💠")
    async def cadastrar(self, it, btn):
        class ModalPix(Modal, title="Configurar Chave PIX"):
            n = TextInput(label="Nome do Titular", placeholder="Nome completo")
            c = TextInput(label="Chave PIX", placeholder="CPF, Celular, Email ou Aleatória")
            q = TextInput(label="Link do QR Code (Opcional)", required=False)
            async def on_submit(self, m_it):
                db_execute("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (m_it.user.id, self.n.value, self.c.value, self.q.value))
                await m_it.response.send_message("✅ Chave PIX configurada!", ephemeral=True)
        await it.response.send_modal(ModalPix())

    @discord.ui.button(label="Sua Chave", style=discord.ButtonStyle.green, emoji="🔍")
    async def ver_sua(self, it, btn):
        res = db_execute("SELECT nome, chave FROM pix WHERE user_id = ?", (it.user.id,))
        if res: await it.response.send_message(f"📌 **Seus Dados:**\nTitular: {res[0]}\nChave: `{res[1]}`", ephemeral=True)
        else: await it.response.send_message("❌ Nenhuma chave cadastrada.", ephemeral=True)

# ================= FILA CONTROLADORA (MEDIADORES) =================

class ViewFilaControladora(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def gerar_embed(self):
        embed = discord.Embed(title="Painel da fila controladora", description="**Entre na fila para começar a mediar suas filas**\n\n", color=0x2b2d31)
        if fila_mediadores:
            lista_str = "".join([f"{i+1} • <@{uid}> {uid}\n" for i, uid in enumerate(fila_mediadores)])
            embed.description += lista_str
        else:
            embed.description += "*Nenhum mediador na fila.*"
        embed.set_thumbnail(url=LOGO_URL)
        return embed

    @discord.ui.button(label="Entrar na fila", style=discord.ButtonStyle.green, emoji="🟢")
    async def entrar(self, it, btn):
        if not tem_permissao(it.user, "cargo_mediador"): return await it.response.send_message("❌ Sem permissão.", ephemeral=True)
        if it.user.id not in fila_mediadores: fila_mediadores.append(it.user.id)
        await it.response.edit_message(embed=await self.gerar_embed())

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red, emoji="🔴")
    async def sair(self, it, btn):
        if it.user.id in fila_mediadores: fila_mediadores.remove(it.user.id)
        await it.response.edit_message(embed=await self.gerar_embed())

# ================= FILA DE APOSTA (JOGADORES) =================

class ViewFilaAposta(View):
    def __init__(self, chave, valor, modo_nome):
        super().__init__(timeout=None)
        self.chave = chave
        self.valor = valor
        self.modo_nome = modo_nome

    async def atualizar(self, msg):
        lista = filas_partida.get(self.chave, [])
        jogadores_str = "\n".join([f"{u.mention} - {m}" for u, m in lista]) if lista else "Vazio"
        valor_formatado = f"{self.valor:.2f}".replace(".", ",")
        
        embed = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71)
        embed.add_field(name="🕹️ Modo", value=f"`{self.modo_nome}`", inline=False)
        embed.add_field(name="Valor", value=f"R$ {valor_formatado}", inline=False)
        embed.add_field(name="Jogadores na Fila", value=jogadores_str, inline=False)
        embed.set_image(url=BANNER_URL)
        await msg.edit(embed=embed, view=self)

    @discord.ui.button(label="Gelo normal", style=discord.ButtonStyle.gray)
    async def g1(self, it, b): await self.processar(it, "gelo normal")

    @discord.ui.button(label="Gelo infinito", style=discord.ButtonStyle.gray)
    async def g2(self, it, b): await self.processar(it, "gelo infinito")

    @discord.ui.button(label="Sair da fila", style=discord.ButtonStyle.red)
    async def sair(self, it, b):
        filas_partida[self.chave] = [x for x in filas_partida.get(self.chave, []) if x[0].id != it.user.id]
        await it.response.send_message("✅ Saiu da fila.", ephemeral=True); await self.atualizar(it.message)

    async def processar(self, it, modo):
        if not fila_mediadores: return await it.response.send_message("❌ Sem mediadores ativos!", ephemeral=True)
        if self.chave not in filas_partida: filas_partida[self.chave] = []
        if any(x[0].id == it.user.id for x in filas_partida[self.chave]): return await it.response.send_message("❌ Já está na fila!", ephemeral=True)

        filas_partida[self.chave].append((it.user, modo))
        match = [x for x in filas_partida[self.chave] if x[1] == modo]

        if len(match) >= 2:
            p1, p2 = match[0][0], match[1][0]
            filas_partida[self.chave].remove(match[0]); filas_partida[self.chave].remove(match[1])
            med_id = fila_mediadores.pop(0); fila_mediadores.append(med_id)
            canal_id = puxar_config("canal_destino")
            if not canal_id: return await it.response.send_message("❌ Canal de partidas não configurado!", ephemeral=True)
            
            canal = bot.get_channel(int(canal_id))
            thread = await canal.create_thread(name=f"⚔️-{p1.name}-vs-{p2.name}")
            partidas_ativas[thread.id] = {"jogadores": [p1, p2], "confirmados": [], "mediador_id": med_id, "modo": self.modo_nome}
            
            emb = discord.Embed(title="Aguardando Confirmação", color=0x2ecc71)
            emb.add_field(name="🕹️ Modo", value=f"{self.modo_nome} | {modo}", inline=False)
            emb.add_field(name="👮 Mediador", value=f"<@{med_id}>", inline=False)
            emb.add_field(name="⚡ Jogadores", value=f"{p1.mention}\n{p2.mention}", inline=False)
            
            msg = await thread.send(content=f"{p1.mention} {p2.mention} | <@{med_id}>", embed=emb)
            await msg.edit(view=ViewConfirmarPartida(thread.id, med_id, msg.id))
            await it.response.send_message("✅ Partida criada!", ephemeral=True); await self.atualizar(it.message)
        else:
            await it.response.send_message(f"✅ Entrou como {modo}!", ephemeral=True); await self.atualizar(it.message)

# ================= CONFIRMAÇÃO E PIX =================

class ViewConfirmarPartida(View):
    def __init__(self, tid, med_id, msg_id):
        super().__init__(timeout=None); self.tid = tid; self.med_id = med_id; self.msg_id = msg_id

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def c(self, it, b):
        dados = partidas_ativas.get(self.tid)
        if it.user in dados["jogadores"] and it.user not in dados["confirmados"]:
            dados["confirmados"].append(it.user)
            await it.response.send_message(f"✅ {it.user.mention} confirmou!", delete_after=2)
            if len(set(dados["confirmados"])) >= 2:
                try: m = await it.channel.fetch_message(self.msg_id); await m.delete()
                except: pass
                res = db_execute("SELECT nome, chave, qr FROM pix WHERE user_id = ?", (self.med_id,))
                if res:
                    emb = discord.Embed(title="🏦 PAGAMENTO", color=0x2ecc71)
                    emb.add_field(name="Titular", value=res[0], inline=False); emb.add_field(name="Chave", value=f"`{res[1]}`", inline=False)
                    if res[2]: emb.set_image(url=res[2])
                    await it.channel.send(content="@everyone", embed=emb)
        else: await it.response.send_message("❌ Ação negada.", ephemeral=True)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def r(self, it, b): await it.channel.delete()

    @discord.ui.button(label="Combinar Regras", style=discord.ButtonStyle.gray, emoji="📝")
    async def reg(self, it, b): await it.response.send_message("📝 Utilizem o chat para as regras.", ephemeral=True)

# ================= COMANDO .AUX E FINALIZAÇÃO =================

class ViewAuxiliar(View):
    def __init__(self, thread):
        super().__init__(timeout=None); self.thread = thread

    async def finalizar(self, it, motivo):
        if not tem_permissao(it.user, "cargo_aux"): return
        dados = partidas_ativas.get(self.thread.id)
        if not dados: return
        
        options = [discord.SelectOption(label=j.display_name, value=str(j.id)) for j in dados["jogadores"]]
        sel = Select(placeholder="Escolha quem venceu", options=options)
        
        async def callback(interaction):
            v_id = int(sel.values[0])
            db_execute("UPDATE stats SET vitorias = vitorias + 1, coins = coins + 1 WHERE user_id = ?", (v_id,))
            await interaction.response.send_message(f"🏆 **{motivo}**\n1 coins adicionados para <@{v_id}>!\n*Limpando tópico...*")
            await asyncio.sleep(5)
            for j in dados["jogadores"]: await self.thread.remove_user(j)
            med = await bot.fetch_user(dados["mediador_id"]); await self.thread.remove_user(med)
            await self.thread.edit(locked=True, archived=True)

        sel.callback = callback
        v = View(); v.add_item(sel); await it.response.send_message("Selecione:", view=v, ephemeral=True)

    @discord.ui.button(label="Escolher vencedor", style=discord.ButtonStyle.green)
    async def v1(self, it, b): await self.finalizar(it, "Vencedor Escolhido")
    @discord.ui.button(label="Finalizar aposta", style=discord.ButtonStyle.blurple)
    async def v2(self, it, b): await self.finalizar(it, "Aposta Finalizada")
    @discord.ui.button(label="Vitória por W.O", style=discord.ButtonStyle.danger)
    async def v3(self, it, b): await self.finalizar(it, "Vitória por W.O")

# ================= DETECÇÃO DE SALA E COMANDOS =================

@bot.event
async def on_message(message):
    if message.author.bot: return
    if isinstance(message.channel, discord.Thread) and message.channel.id in partidas_ativas:
        nums = re.findall(r'\d+', message.content)
        if len(nums) >= 2:
            dados = partidas_ativas[message.channel.id]
            jogadores = " vs ".join([p.mention for p in dados["jogadores"]])
            await message.delete()
            await message.channel.send(
                f"**Sala criada 3 a 5 minutos e da go!**\n\n"
                f"**Modo:** `{dados['modo']}`\n"
                f"**Jogadores:** {jogadores}\n\n"
                f"**Id da sala:** `{nums[0]}`\n"
                f"**Senha da sala:** `{nums[1]}`"
            )
    await bot.process_commands(message)

@bot.command()
async def pix(ctx):
    if not tem_permissao(ctx.author, "cargo_pix"): return
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie sua chave PIX para as filas.", color=0x2b2d31)
    embed.set_thumbnail(url=LOGO_URL)
    await ctx.send(embed=embed, view=ViewPainelPix())

@bot.command()
async def mediar(ctx):
    v = ViewFilaControladora(); await ctx.send(embed=await v.gerar_embed(), view=v)

@bot.command()
async def fila(ctx, v: str, modo: str = "1v1-mobile"):
    try:
        val = float(v.replace(",", "."))
    except ValueError:
        return await ctx.send("❌ Use um valor numérico válido. Ex: `.fila 10` ou `.fila 10 emulador`")
    
    view = ViewFilaAposta(f"f_{val}_{modo}", val, modo)
    val_txt = f"{val:.2f}".replace(".", ",")
    emb = discord.Embed(title="🎮 WS APOSTAS", color=0x2ecc71).set_image(url=BANNER_URL)
    emb.add_field(name="🕹️ Modo", value=f"`{modo}`", inline=False)
    emb.add_field(name="Valor", value=f"R$ {val_txt}", inline=False)
    emb.add_field(name="Jogadores na Fila", value="Vazio", inline=False)
    await ctx.send(embed=emb, view=view)

@bot.command()
async def aux(ctx):
    if tem_permissao(ctx.author, "cargo_aux"): await ctx.send("🛠️ **Painel Auxiliar**", view=ViewAuxiliar(ctx.channel))

@bot.command()
@commands.has_permissions(administrator=True)
async def botconfig(ctx):
    class ConfigV(View):
        @discord.ui.select(cls=RoleSelect, placeholder="Quem usa comandos", row=0)
        async def s1(self, it, sel): salvar_config("cargo_comandos", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem usa .aux", row=1)
        async def s2(self, it, sel): salvar_config("cargo_aux", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem cadastra Pix", row=2)
        async def s3(self, it, sel): salvar_config("cargo_pix", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
        @discord.ui.select(cls=RoleSelect, placeholder="Quem é Mediador", row=3)
        async def s4(self, it, sel): salvar_config("cargo_mediador", sel.values[0].id); await it.response.send_message("✅", ephemeral=True)
    await ctx.send("⚙️ **Configuração de Cargos**", view=ConfigV())

@bot.command()
@commands.has_permissions(administrator=True)
async def canal(ctx):
    class CV(View):
        @discord.ui.select(cls=ChannelSelect, placeholder="Selecionar Canal")
        async def s(self, it, sel): salvar_config("canal_destino", sel.values[0].id); await it.response.send_message("✅ Canal definido!", ephemeral=True)
    await ctx.send("Onde as partidas serão criadas?", view=CV())

@bot.event
async def on_ready(): init_db(); print(f"✅ {bot.user} Online")

bot.run(TOKEN)
    
