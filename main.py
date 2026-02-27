import discord
from discord.ext import commands
import os
import asyncio
import re
import random
import io

# ==========================================
# CONFIGURAÇÃO DO BOT E VARIÁVEIS GLOBAIS
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True

bot = commands.Bot(command_prefix='.', intents=intents)

# Bancos de Dados em Memória
lista_mediadores = [] 
pix_db = {}           
canais_topico_db = [] 
taxa_fixa_db = 0.0  
banner_db = 'https://i.imgur.com/SUY8L4o.jpeg' 
stats_db = {} 
contador_partidas = 0 

# NOVOS: Cargos e Histórico (Logs)
cargos_db = {'perfil': None, 'mediador': None, 'admin': None, 'pix': None, 'logs': None}
historico_db = {} # Formato: {user_id: [{'modo': '1v1', 'partida': 'Mobile-1', 'valor': 5, 'topico_id': 123}]}

# ==========================================
# FUNÇÕES DE APOIO
# ==========================================
def gerar_embed_sucesso(usuario):
    embed = discord.Embed(
        description=f"{usuario.mention}, a sua operação foi concluída com êxito.\n↪ Você entrou ou saiu da fila com sucesso.",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_author(name="✅ Ação realizada com sucesso!")
    return embed

def tem_permissao(membro, chave):
    if membro.guild_permissions.administrator: return True
    cargo_id = cargos_db.get(chave)
    if not cargo_id: return True # Se não configurou, todos podem usar
    return any(r.id == cargo_id for r in membro.roles)

    # ==========================================
# MENSAGEM AUTOMÁTICA
# ==========================================
class EnviarMensagemView(discord.ui.View):
    def __init__(self, mensagem_texto):
        super().__init__(timeout=None)
        self.mensagem_texto = mensagem_texto
        self.canais_selecionados = []

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Selecione os canais...", max_values=10)
    async def select_canais(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.canais_selecionados = select.values
        await interaction.response.defer()

    @discord.ui.button(label='Enviar Mensagens', style=discord.ButtonStyle.success, row=1)
    async def btn_enviar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.canais_selecionados:
            return await interaction.response.send_message("❌ Selecione ao menos um canal!", ephemeral=True)
        
        await interaction.response.send_message("✅ Enviando mensagens...", ephemeral=True)
        for canal in self.canais_selecionados:
            try: await canal.send(self.mensagem_texto)
            except: pass

class MensagemAutoModal(discord.ui.Modal, title='Mensagem Automática'):
    msg = discord.ui.TextInput(label='Hi, qual vai ser a mensagem de hoje?', style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        view = EnviarMensagemView(self.msg.value)
        await interaction.response.send_message("📢 **Mensagem salva!** Agora selecione abaixo em quais canais deseja enviá-la:", view=view, ephemeral=True)

# ==========================================
# CONFIGURAÇÃO DE CARGOS
# ==========================================
class ConfigCargosView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode usar .p?", row=0)
    async def s_perfil(self, interaction, select):
        cargos_db['perfil'] = select.values[0].id
        await interaction.response.send_message(f"✅ Cargo para `.p` definido para {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode entrar na fila mediador?", row=1)
    async def s_med(self, interaction, select):
        cargos_db['mediador'] = select.values[0].id
        await interaction.response.send_message(f"✅ Cargo para Mediador definido!", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode mexer no Bot?", row=2)
    async def s_admin(self, interaction, select):
        cargos_db['admin'] = select.values[0].id
        await interaction.response.send_message(f"✅ Cargo Admin definido!", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode configurar o Pix?", row=3)
    async def s_pix(self, interaction, select):
        cargos_db['pix'] = select.values[0].id
        await interaction.response.send_message(f"✅ Cargo de PIX definido!", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode puxar as logs?", row=4)
    async def s_logs(self, interaction, select):
        cargos_db['logs'] = select.values[0].id
        await interaction.response.send_message(f"✅ Cargo de Logs definido!", ephemeral=True)

# ==========================================
# MENUS DE VITÓRIA E MEDIAÇÃO
# ==========================================
class EscolherVencedorSelect(discord.ui.Select):
    def __init__(self, j1, j2, tipo_vitoria):
        self.j1, self.j2, self.tipo_vitoria = j1, j2, tipo_vitoria
        options = [
            discord.SelectOption(label=j1.name, value=str(j1.id), emoji="🎮"),
            discord.SelectOption(label=j2.name, value=str(j2.id), emoji="🎮")
        ]
        super().__init__(placeholder="Selecione o vencedor...", options=options)

    async def callback(self, interaction: discord.Interaction):
        vencedor_id = int(self.values[0])
        vencedor = self.j1 if vencedor_id == self.j1.id else self.j2
        perdedor = self.j2 if vencedor_id == self.j1.id else self.j1

        for u in [vencedor, perdedor]:
            if u.id not in stats_db: stats_db[u.id] = {'vitorias': 0, 'derrotas': 0, 'consecutivas': 0, 'total': 0, 'coins': 0}

        stats_db[vencedor.id]['vitorias'] += 1
        stats_db[vencedor.id]['total'] += 1
        stats_db[vencedor.id]['consecutivas'] += 1
        stats_db[perdedor.id]['derrotas'] += 1
        stats_db[perdedor.id]['total'] += 1
        stats_db[perdedor.id]['consecutivas'] = 0

        if self.tipo_vitoria == "normal":
            stats_db[vencedor.id]['coins'] += 10
            await interaction.response.send_message(f"🏆 {vencedor.mention} venceu a partida e ganhou +10 Coins!")
        else:
            await interaction.response.send_message(f"❗ {vencedor.mention} venceu por W.O!")

class MenuMediadorSelect(discord.ui.Select):
    def __init__(self, j1, j2):
        self.j1, self.j2 = j1, j2
        options = [
            discord.SelectOption(label="Dar vitória a um jogador", emoji="🏆", value="normal"),
            discord.SelectOption(label="Vitória por W.O", emoji="❗", value="wo"),
            discord.SelectOption(label="Finalizar partida", emoji="❌", description="Fecha o tópico", value="finalizar")
        ]
        super().__init__(placeholder="Menu Mediador", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "finalizar":
            await interaction.response.send_message("🔒 Partida finalizada! O tópico será fechado em 3 segundos...")
            await asyncio.sleep(3)
            try: await interaction.channel.edit(archived=True, locked=True)
            except: pass
        elif self.values[0] == "normal":
            await interaction.response.send_message("🏆 **Quem ganhou?**", view=discord.ui.View().add_item(EscolherVencedorSelect(self.j1, self.j2, "normal")), ephemeral=True)
        elif self.values[0] == "wo":
            await interaction.response.send_message("❗ **Ganhou por W.O?**", view=discord.ui.View().add_item(EscolherVencedorSelect(self.j1, self.j2, "wo")), ephemeral=True)

class MenuMediadorView(discord.ui.View):
    def __init__(self, j1, j2):
        super().__init__(timeout=None)
        self.add_item(MenuMediadorSelect(j1, j2))

class RegrasView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='Regras', style=discord.ButtonStyle.link, url='https://discord.gg/seulink'))

# ==========================================
# CONFIRMAÇÃO E REGISTRO DE HISTÓRICO
# ==========================================
class ThreadConfirmacaoView(discord.ui.View):
    def __init__(self, j1, j2, modo, valor, med_id, nome_f):
        super().__init__(timeout=None)
        self.j1, self.j2, self.modo, self.valor, self.med_id, self.nome_f = j1, j2, modo, valor, med_id, nome_f
        self.conf = set()
        self.msg_aviso = None

    @discord.ui.button(label='Confirmar', style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        global contador_partidas
        if interaction.user.id not in [self.j1.id, self.j2.id]: return await interaction.response.send_message("❌ Apenas jogadores!", ephemeral=True)
        if interaction.user.id in self.conf: return await interaction.response.send_message("⚠️ Já confirmou!", ephemeral=True)

        self.conf.add(interaction.user.id)
        if len(self.conf) == 1:
            self.msg_aviso = await interaction.channel.send(f"✅ {interaction.user.mention} confirmou!")
        elif len(self.conf) == 2:
            await interaction.response.defer() 
            try:
                await interaction.message.delete()
                if self.msg_aviso: await self.msg_aviso.delete()
            except: pass

            contador_partidas += 1
            novo_nome = f"{self.nome_f.replace(' ', '')}-1v1-{contador_partidas}"
            try: await interaction.channel.edit(name=novo_nome)
            except: pass

            # SALVA NO HISTÓRICO DE LOGS DOS DOIS JOGADORES
            registro = {'modo': self.modo, 'partida': novo_nome, 'valor': self.valor, 'topico_id': interaction.channel.id}
            historico_db.setdefault(self.j1.id, []).append(registro)
            historico_db.setdefault(self.j2.id, []).append(registro)

            val_p = (self.valor * 2) + taxa_fixa_db 
            pix = pix_db.get(self.med_id, {"chave": "Não configurada", "tipo": "-", "nome": "Não informado"})

            emb = discord.Embed(title="Partida Confirmada", color=discord.Color.from_str('#3b2c28'))
            emb.add_field(name="🎮 Estilo de Jogo", value=f"1v1 {self.modo}", inline=False)
            emb.add_field(name="ℹ️ Info", value=f"Taxa: R$ {taxa_fixa_db:.2f}\nMediador: <@{self.med_id}>", inline=False)
            emb.add_field(name="💠 Aposta", value=f"R$ {self.valor:.2f}", inline=False)
            emb.set_thumbnail(url=banner_db)

            qr = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={pix['chave']}"
            e_pix = discord.Embed(color=0x2b2d31).set_image(url=qr)
            e_pix.description = f"**Nome:** {pix['nome']}\n**Chave:** `{pix['chave']}`\n**Total a pagar:** R$ {val_p:.2f}"

            await interaction.channel.send(content=f"{self.j1.mention} {self.j2.mention}, <@{self.med_id}>", embed=emb, view=MenuMediadorView(self.j1, self.j2))
            await interaction.channel.send(embed=e_pix, view=RegrasView())

    @discord.ui.button(label='Recusar', style=discord.ButtonStyle.danger)
    async def btn_recusar(self, i, b): await i.response.send_message(f"❌ {i.user.mention} recusou a partida.")

    # ==========================================
# PAINEL DA FILA (MATCHMAKING)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self, emb, nome, val):
        super().__init__(timeout=None)
        self.jogs, self.emb, self.nome, self.val = [], emb, nome, val

    def atualizar_visual(self):
        v_str = f"{self.val:.2f}".replace('.', ',')
        desc = f"👑 **Modo**\n1v1 {self.nome.upper()}\n\n💎 **Valor**\nR$ {v_str}\n\n⚡ **Jogadores**\n"
        desc += "Nenhum jogador na fila" if not self.jogs else "\n".join([f"{j['user'].mention} - {j['modo']}" for j in self.jogs])
        self.emb.description = desc
        self.emb.set_image(url=banner_db)

    async def processar_clique(self, i: discord.Interaction, modo: str):
        if not lista_mediadores: return await i.response.send_message("❌ | NÃO TEM NENHUM MEDIADOR NA FILA!", ephemeral=True)
        for j in self.jogs:
            if j['user'].id == i.user.id:
                if j['modo'] == modo: return await i.response.send_message("⚠️ Você já está nesta fila!", ephemeral=True)
                j['modo'] = modo
                self.atualizar_visual()
                await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
                return await i.message.edit(embed=self.emb, view=self)

        op = next((j for j in self.jogs if j['modo'] == modo), None)
        if op:
            self.jogs.remove(op)
            self.atualizar_visual()
            await i.response.edit_message(embed=self.emb, view=self)

            med = lista_mediadores.pop(0)
            lista_mediadores.append(med)

            canal_alvo = i.guild.get_channel(random.choice(canais_topico_db)) if canais_topico_db else i.channel
            try:
                topico = await canal_alvo.create_thread(name="aguardando-confirmaçao", auto_archive_duration=60)
                await topico.send(content=f"Chamando: {op['user'].mention} {i.user.mention}\nMediador: <@{med}>", view=ThreadConfirmacaoView(op['user'], i.user, modo, self.val, med, self.nome))
                await i.followup.send(f"✅ Partida no canal: {canal_alvo.mention}", ephemeral=True)
            except: pass
        else:
            self.jogs.append({"user": i.user, "modo": modo})
            self.atualizar_visual()
            await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
            await i.message.edit(embed=self.emb, view=self)

    @discord.ui.button(label='Gel Normal', style=discord.ButtonStyle.secondary)
    async def n(self, i, b): await self.processar_clique(i, "Gel Normal")
    @discord.ui.button(label='Gel Infinito', style=discord.ButtonStyle.secondary)
    async def inf(self, i, b): await self.processar_clique(i, "Gel Infinito")
    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger)
    async def s(self, i, b):
        self.jogs = [j for j in self.jogs if j['user'].id != i.user.id]
        self.atualizar_visual()
        await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
        await i.message.edit(embed=self.emb, view=self)

# ==========================================
# PUXAR LOGS E MODAIS SECUNDÁRIOS
# ==========================================
class BotaoPuxarLogView(discord.ui.View):
    def __init__(self, topico_id):
        super().__init__(timeout=None)
        self.topico_id = topico_id

    @discord.ui.button(label="Conversa do tópico!", style=discord.ButtonStyle.primary, emoji="📄")
    async def btn_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not tem_permissao(interaction.user, 'logs'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        canal = interaction.guild.get_thread(self.topico_id)
        if not canal: return await interaction.followup.send("⚠️ Tópico excluído ou não encontrado.", ephemeral=True)
        
        msgs = [m async for m in canal.history(limit=200, oldest_first=True)]
        txt = "\n".join([f"[{m.created_at.strftime('%d/%m %H:%M')}] {m.author.name}: {m.content}" for m in msgs])
        arquivo = discord.File(io.BytesIO(txt.encode('utf-8')), filename=f"log_{self.topico_id}.txt")
        await interaction.followup.send("📄 Aqui está o histórico da conversa:", file=arquivo, ephemeral=True)

class SelectMatchLog(discord.ui.Select):
    def __init__(self, historico):
        ops = [discord.SelectOption(label=f"Modo: {h['modo']}", description=f"Partida: {h['partida']} | R$ {h['valor']}", value=str(idx)) for idx, h in enumerate(historico[-25:])]
        super().__init__(placeholder="Selecione uma partida recente...", options=ops)
        self.historico = historico[-25:]

    async def callback(self, interaction: discord.Interaction):
        if not tem_permissao(interaction.user, 'logs'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        h = self.historico[int(self.values[0])]
        emb = discord.Embed(title="Detalhes da Partida", description=f"**Modo:** {h['modo']}\n**Partida:** {h['partida']}\n**Valor:** R$ {h['valor']}", color=0x2b2d31)
        await interaction.response.send_message(embed=emb, view=BotaoPuxarLogView(h['topico_id']), ephemeral=True)

class FilaModal(discord.ui.Modal, title='Criar Filas'):
    n = discord.ui.TextInput(label='Nome da fila', required=True)
    v = discord.ui.TextInput(label='Valores (Separe por vírgula)', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Gerando filas...", ephemeral=True)
        for val_raw in re.split(r'[;,\n]', self.v.value.replace(' ', '')):
            if val_raw:
                try:
                    val = float(val_raw.replace('R$', '').replace(',', '.'))
                    emb = discord.Embed(title=f"1v1 | SPACE {val:g}K", description=f"👑 **Modo**\n1v1 {self.n.value.upper()}\n\n💎 **Valor**\nR$ {val:.2f}\n\n⚡ **Jogadores**\nNenhum", color=0x2b2d31).set_image(url=banner_db)
                    await interaction.channel.send(embed=emb, view=FilaView(emb, self.n.value, val))
                except: pass

class MudarTaxaModal(discord.ui.Modal, title='Mudar Taxa'):
    t = discord.ui.TextInput(label='Valor da taxa? (Ex: 0,20)')
    async def on_submit(self, i):
        global taxa_fixa_db
        taxa_fixa_db = float(self.t.value.replace(',', '.'))
        await i.response.send_message(f"✅ Taxa: R$ {taxa_fixa_db:.2f}", ephemeral=True)

class MudarBannerModal(discord.ui.Modal, title='Mudar Banner'):
    b = discord.ui.TextInput(label='Link da Imagem')
    async def on_submit(self, i):
        global banner_db
        banner_db = self.b.value.strip()
        await i.response.send_message("✅ Banner atualizado!", ephemeral=True)

# ==========================================
# PAINEL PIX, MEDIADOR E COMANDOS
# ==========================================
class CadastrarPixModal(discord.ui.Modal, title='Configurar PIX'):
    nome = discord.ui.TextInput(label='Nome Completo')
    chave = discord.ui.TextInput(label='Chave PIX')
    tipo = discord.ui.TextInput(label='Tipo (CPF, etc)')
    async def on_submit(self, i):
        pix_db[i.user.id] = {'chave': self.chave.value, 'tipo': self.tipo.value, 'nome': self.nome.value}
        await i.response.send_message("✅ Chave PIX salva!", ephemeral=True)

@bot.tree.command(name="configurar_cargos", description="Abre o painel de configuração de permissões")
async def config_cargos(i):
    if not i.user.guild_permissions.administrator: return await i.response.send_message("❌ Apenas Administradores.", ephemeral=True)
    await i.response.send_message("⚙️ **Configuração de Cargos**", view=ConfigCargosView(), ephemeral=True)

@bot.tree.command(name="enviar_mensangem_automatica", description="Envia avisos automáticos para múltiplos canais")
async def msg_auto(i):
    if not tem_permissao(i.user, 'admin'): return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
    await i.response.send_modal(MensagemAutoModal())

@bot.tree.command(name="mudar_taxa")
async def mudar_taxa(i): await i.response.send_modal(MudarTaxaModal())

@bot.tree.command(name="banner_da_fila")
async def banner_da_fila(i): await i.response.send_modal(MudarBannerModal())

@bot.tree.command(name="criar_filas")
async def criar_filas(i):
    if not tem_permissao(i.user, 'admin'): return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
    await i.response.send_modal(FilaModal())

@bot.tree.command(name="mediador")
async def cmd_med(i):
    emb = discord.Embed(title="Painel Controladora", description="*Vazio*", color=0x2b2d31).set_thumbnail(url=banner_db)
    v = discord.ui.View()
    @discord.ui.button(label='Entrar', style=discord.ButtonStyle.success)
    async def ent(it, b):
        if not tem_permissao(it.user, 'mediador'): return await it.response.send_message("❌ Sem permissão.", ephemeral=True)
        if it.user.id not in lista_mediadores: lista_mediadores.append(it.user.id)
        await it.response.send_message(embed=gerar_embed_sucesso(it.user), ephemeral=True)
    @discord.ui.button(label='Sair', style=discord.ButtonStyle.danger)
    async def sai(it, b):
        if it.user.id in lista_mediadores: lista_mediadores.remove(it.user.id)
        await it.response.send_message(embed=gerar_embed_sucesso(it.user), ephemeral=True)
    v.add_item(ent); v.add_item(sai)
    await i.response.send_message(embed=emb, view=v)

@bot.tree.command(name="pix")
async def cmd_pix(i):
    if not tem_permissao(i.user, 'pix'): return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
    emb = discord.Embed(title="Painel PIX", description="Configure a chave.", color=0x2b2d31).set_thumbnail(url=banner_db)
    v = discord.ui.View()
    @discord.ui.button(label='Chave pix', style=discord.ButtonStyle.success)
    async def cad(it, b): await it.response.send_modal(CadastrarPixModal())
    v.add_item(cad)
    await i.response.send_message(embed=emb, view=v)

@bot.command(name="logs")
async def puxar_logs(ctx, membro: discord.Member = None):
    if not tem_permissao(ctx.author, 'logs'): return await ctx.reply("❌ Você não tem o cargo de puxar logs!")
    if not membro: return await ctx.reply("Mencione um usuário! Ex: `.logs @jogador`")
    
    h = historico_db.get(membro.id, [])
    if not h: return await ctx.reply(f"O jogador {membro.name} não possui partidas registradas.")
    
    view = discord.ui.View().add_item(SelectMatchLog(h))
    await ctx.reply(f"📜 Logs de {membro.name} encontrados. Selecione uma partida abaixo:", view=view)

@bot.command(name="p")
async def perfil(ctx, membro: discord.Member = None):
    if not tem_permissao(ctx.author, 'perfil'): return await ctx.reply("❌ Sem permissão para ver perfis.")
    u = membro or ctx.author
    if ctx.message.reference:
        try: u = (await ctx.channel.fetch_message(ctx.message.reference.message_id)).author
        except: pass

    s = stats_db.get(u.id, {'vitorias': 0, 'derrotas': 0, 'consecutivas': 0, 'total': 0, 'coins': 0})
    emb = discord.Embed(description=f"🎮 **Estatísticas**\n\nVitórias: {s['vitorias']}\nDerrotas: {s['derrotas']}\nConsecutivas: {s['consecutivas']}\nTotal: {s['total']}\n\n💎 **Coins**: {s['coins']}", color=0x2b2d31)
    emb.set_author(name=u.name, icon_url=u.display_avatar.url)
    emb.set_thumbnail(url=u.display_avatar.url)
    await ctx.reply(embed=emb)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Bot Full HD Online!")

bot.run(os.environ.get('TOKEN'))
    
