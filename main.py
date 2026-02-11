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
TOKEN = os.getenv("TOKEN") 

# Cores
COR_EMBED = 0x2b2d31 
COR_VERDE = 0x2ecc71 
COR_VERMELHO = 0xe74c3c
COR_CONFIRMADO = 0x2ecc71 # Verde da confirmação
COR_DISCORD = 0x5865F2 # Azul/Roxo do Discord (Ação realizada)

# Imagens
BANNER_URL = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
ICONE_ORG = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg"
IMAGEM_BONECA = "https://cdn.discordapp.com/attachments/1465930366916231179/1465940841217658923/IMG_20260128_021230.jpg" 

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# Cache em memória
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
#           VIEW: CONFIRMAÇÃO DA PARTIDA (DESIGN ATUALIZADO)
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
        
        # Feedback visual que alguém confirmou
        await it.channel.send(f"✅ **{it.user.mention}** confirmou! ({len(self.confirms)}/{len(self.jogadores)})", delete_after=5)

        # === LÓGICA FINAL QUANDO TODOS CONFIRMAM ===
        if len(self.confirms) >= len(self.jogadores):
            self.stop()
            
            # 1. Apaga a mensagem antiga (botões e "aguardando") para limpar o chat
            try:
                await it.message.delete()
            except:
                pass # Se não der pra apagar, ignora

            # 2. Prepara dados do banco
            pix_data = db_query("SELECT nome, chave, qrcode FROM pix WHERE user_id=?", (self.med_id,))
            
            # Renomeia Canal
            modo_upper = self.modo_completo.upper()
            prefixo, tipo_db = "Sala", "geral"
            if "MOBILE" in modo_upper: prefixo, tipo_db = "Mobile", "mobile"
            elif "MISTO" in modo_upper: prefixo, tipo_db = "Misto", "misto"
            elif "FULL" in modo_upper: prefixo, tipo_db = "Full", "full"
            elif "EMU" in modo_upper: prefixo, tipo_db = "Emu", "emu"

            num = db_increment_counter(tipo_db)
            try: await it.channel.edit(name=f"{prefixo}-{num}", locked=True)
            except: pass 
            
            # 3. Calcula Taxa (Valor da Sala)
            try:
                v_clean = self.valor.replace("R$","").replace(" ","").replace(".","").replace(",",".")
                v_f = float(v_clean)
                taxa = max(v_f * 0.10, 0.10) # 10%
                taxa_str = f"R$ {taxa:.2f}".replace(".",",")
            except: 
                taxa_str = "R$ ???"

            # 4. Formata Estilo
            estilo = self.modo_completo.split('|')[0].strip() if '|' in self.modo_completo else self.modo_completo
            if "1v1" in self.modo_str_clean().lower() and "gel" not in estilo.lower():
                # Tenta pegar o tipo (Gel Normal/Infinito) do primeiro jogador
                try: estilo = f"{estilo} {self.jogadores[0]['t']}"
                except: pass

            # === MONTAGEM DO EMBED (IGUAL A FOTO 2) ===
            e = discord.Embed(title="Partida Confirmada", color=COR_CONFIRMADO)
            e.set_thumbnail(url=IMAGEM_BONECA)
            
            # Campo 1: Estilo
            e.add_field(name="🎮 Estilo de Jogo", value=estilo, inline=False)
            
            # Campo 2: Info da Aposta (Valor da Sala e Mediador)
            e.add_field(name="ℹ️ Informações da Aposta", 
                        value=f"Valor Da Sala: {taxa_str}\nMediador: <@{self.med_id}>", 
                        inline=False)
            
            # Campo 3: Valor da Aposta
            e.add_field(name="💎 Valor da Aposta", value=f"R$ {self.valor}", inline=False)
            
            # Campo 4: Jogadores
            lista_jogadores = "\n".join([f"{j['m']}" for j in self.jogadores])
            e.add_field(name="👥 Jogadores", value=lista_jogadores, inline=False)

            # Campo 5: PIX (Abaixo dos nomes, como pedido)
            if pix_data:
                nome_pix, chave_pix, qr_pix = pix_data
                msg_pix = f"**Titular:** {nome_pix}\n**Chave:** ```{chave_pix}```"
                if qr_pix: msg_pix += f"\n[QR Code]({qr_pix})"
                e.add_field(name="💸 PAGAMENTO (PIX)", value=msg_pix, inline=False)
            else:
                e.add_field(name="⚠️ PIX INDISPONÍVEL", value=f"O mediador <@{self.med_id}> não cadastrou Pix.", inline=False)

            # Envia a nova mensagem limpa
            mentions = f"<@{self.med_id}> " + " ".join([j['m'] for j in self.jogadores])
            await it.channel.send(content=mentions, embed=e)
            
            # Registra comissão
            db_exec("UPDATE pix_saldo SET saldo = saldo + 0.10 WHERE user_id=?", (self.med_id,))

    def modo_str_clean(self):
        return self.modo_completo.split('|')[0]

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def recusar(self, it: discord.Interaction, btn: Button):
        if it.user.id in [j['id'] for j in self.jogadores] or it.user.id == self.med_id:
            await it.channel.send(f"🚫 Partida cancelada por {it.user.mention}. Deletando...")
            self.stop()
            await asyncio.sleep(2)
            await it.channel.delete()
        else:
            await it.response.send_message("Sem permissão.", ephemeral=True)

# ==============================================================================
#           VIEW: FILA (MANTIDA - LIMITE 2)
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
            b1 = Button(label="Gelo Normal", style=discord.ButtonStyle.secondary, custom_id=f"gn_{self.valor}_{self.modo_str}")
            b2 = Button(label="Gelo Infinito", style=discord.ButtonStyle.secondary, custom_id=f"gi_{self.valor}_{self.modo_str}")
            b1.callback = lambda i: self.join(i, "Gel Normal")
            b2.callback = lambda i: self.join(i, "Gel Infinito")
            self.add_item(b1); self.add_item(b2)
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
            
        e.add_field(name=f"👥 Fila ({len(self.jogadores)}/2)", value="\n".join(lista_visual) or "*Aguardando...*", inline=False)
        e.set_image(url=BANNER_URL)
        return e

    async def join(self, it: discord.Interaction, tipo: str):
        if any(j['id'] == it.user.id for j in self.jogadores): 
            return await it.response.send_message("Já está na fila!", ephemeral=True)
        
        self.jogadores.append({'id': it.user.id, 'm': it.user.mention, 't': tipo})
        await it.response.edit_message(embed=self.emb(), view=self)
        
        if len(self.jogadores) >= 2: # Limite 2
            if not fila_mediadores:
                await it.channel.send(f"⚠️ {it.user.mention} Sem mediadores online!", delete_after=5)
                return
            
            cid = db_get_config("canal_th")
            if not cid:
                return await it.channel.send("❌ Configure o canal (/canal).")
            
            canal_alvo = bot.get_channel(int(cid))
            if not canal_alvo: return await it.channel.send("❌ Canal não encontrado.")

            med_id = fila_mediadores.pop(0)
            fila_mediadores.append(med_id) 

            nome_thread = f"confirmar-{self.modo_str}-{len(self.jogadores)}p"
            th = await canal_alvo.create_thread(name=nome_thread, type=discord.ChannelType.public_thread)
            
            ew = discord.Embed(title="Aguardando Confirmações", color=COR_VERDE)
            ew.set_thumbnail(url=IMAGEM_BONECA)
            ew.add_field(name="👑 Info", value=f"{self.modo_str} | R$ {self.valor}", inline=False)
            ew.add_field(name="👮 Mediador", value=f"<@{med_id}>", inline=False)
            ew.description = "```Clique em ✅ para confirmar.```"
            
            view_conf = ViewConfirmacao(self.jogadores[:], med_id, self.valor, self.modo_str)
            await th.send(content=" ".join([j['m'] for j in self.jogadores]) + f" <@{med_id}>", embed=ew, view=view_conf)
            
            self.jogadores = []
            await it.message.edit(embed=self.emb(), view=self)
            await it.channel.send(f"✅ Sala criada em {th.mention}!", delete_after=5)

    async def leave(self, it: discord.Interaction):
        self.jogadores = [j for j in self.jogadores if j['id'] != it.user.id]
        await it.response.edit_message(embed=self.emb(), view=self)

# ==============================================================================
#           VIEW: MEDIADOR STAFF (IGUAL A FOTO 1)
# ==============================================================================
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
    
    @discord.ui.button(label="Entrar (Work)", style=discord.ButtonStyle.success, emoji="🟢")
    async def entrar(self, it: discord.Interaction, b: Button):
        if it.user.id not in fila_mediadores:
            fila_mediadores.append(it.user.id)
            await it.message.edit(embed=self.gerar_embed(), view=self)
            
            # --- MENSAGEM DA FOTO 1 ---
            e = discord.Embed(title="✅ Ação realizada com sucesso!", color=COR_DISCORD)
            e.description = f"{it.user.mention}, a sua operação foi concluída com êxito.\n↪ Você entrou na fila com sucesso."
            await it.response.send_message(embed=e, ephemeral=True)
        else:
            await it.response.send_message("Você já está na fila.", ephemeral=True)
    
    @discord.ui.button(label="Sair (Sleep)", style=discord.ButtonStyle.danger, emoji="🔴")
    async def sair(self, it: discord.Interaction, b: Button):
        if it.user.id in fila_mediadores:
            fila_mediadores.remove(it.user.id)
            await it.message.edit(embed=self.gerar_embed(), view=self)
            
            # --- MENSAGEM DA FOTO 1 ---
            e = discord.Embed(title="✅ Ação realizada com sucesso!", color=COR_DISCORD)
            e.description = f"{it.user.mention}, a sua operação foi concluída com êxito.\n↪ Você saiu da fila com sucesso."
            await it.response.send_message(embed=e, ephemeral=True)
        else:
            await it.response.send_message("Você não está na fila.", ephemeral=True)
            
    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, it: discord.Interaction, b: Button):
        await it.response.edit_message(embed=self.gerar_embed(), view=self)

# ==============================================================================
#           PAINEL PIX & COMANDOS
# ==============================================================================
class ViewPainelPix(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Cadastrar Pix", style=discord.ButtonStyle.success, emoji="💠")
    async def cad(self, it, b):
        m = Modal(title="Cadastrar Pix"); n = TextInput(label="Nome Completo"); c = TextInput(label="Chave Pix"); q = TextInput(label="QR Code (Opcional)", required=False)
        m.add_item(n); m.add_item(c); m.add_item(q)
        async def sub(i):
            db_exec("INSERT OR REPLACE INTO pix VALUES (?,?,?,?)", (i.user.id, n.value, c.value, q.value))
            await i.response.send_message("✅ Salvo!", ephemeral=True)
        m.on_submit = sub
        await it.response.send_modal(m)

    @discord.ui.button(label="Ver Pix", style=discord.ButtonStyle.primary, emoji="👁️")
    async def ver(self, it, b):
        d = db_query("SELECT * FROM pix WHERE user_id=?", (it.user.id,))
        if d: await it.response.send_message(f"👤 {d[1]}\n🔑 `{d[2]}`", ephemeral=True)
        else: await it.response.send_message("❌ Sem cadastro.", ephemeral=True)

@bot.tree.command(name="pix", description="Gerenciar Pix")
async def slash_pix(it: discord.Interaction):
    await it.response.send_message(embed=discord.Embed(title="Pix", color=COR_EMBED), view=ViewPainelPix(), ephemeral=True)

@bot.tree.command(name="canal", description="Definir canal")
async def slash_canal(it: discord.Interaction, c: discord.TextChannel):
    if it.user.guild_permissions.administrator:
        db_exec("INSERT OR REPLACE INTO config VALUES (?, ?)", ("canal_th", str(c.id)))
        await it.response.send_message(f"✅ Canal: {c.mention}", ephemeral=True)

@bot.tree.command(name="mediar", description="Painel Staff")
async def slash_mediar(it: discord.Interaction):
    if it.user.guild_permissions.manage_messages:
        v = ViewMediadorFila()
        await it.response.send_message(embed=v.gerar_embed(), view=v)
    else:
        await it.response.send_message("Sem permissão.", ephemeral=True)

@bot.tree.command(name="fila", description="Gerar Filas")
async def slash_fila(it: discord.Interaction):
    if not it.user.guild_permissions.administrator: return
    class M(Modal, title="Filas"):
        m=TextInput(label="Modo", default="1v1"); p=TextInput(label="Plataforma", default="Mobile"); v=TextInput(label="Valores", default="5,00 10,00")
        async def on_submit(self, i):
            await i.response.send_message("Gerando...", ephemeral=True)
            for val in [x.strip() for x in self.v.value.split() if x.strip()]:
                if "," not in val: val+=",00"
                vf=ViewFila(f"{self.m.value}|{self.p.value}", val)
                await i.channel.send(embed=vf.emb(), view=vf); await asyncio.sleep(1)
    await it.response.send_modal(M())

@bot.event
async def on_ready():
    init_db(); await bot.tree.sync(); print(f"Logado como {bot.user}")

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
            
