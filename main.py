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

# Bancos de Dados
lista_mediadores = [] 
pix_db = {}           
canais_topico_db = [] 
taxa_fixa_db = 0.0  
banner_db = 'https://i.imgur.com/SUY8L4o.jpeg' 
stats_db = {} 
contador_partidas = 0 
cargos_db = {'perfil': None, 'mediador': None, 'admin': None, 'pix': None, 'logs': None}
historico_db = {} 

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
    if not cargo_id: return True 
    return any(r.id == cargo_id for r in membro.roles)

# ==========================================
# MENSAGEM AUTOMÁTICA E CARGOS
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
        if not self.canais_selecionados: return await interaction.response.send_message("❌ Selecione um canal!", ephemeral=True)
        await interaction.response.send_message("✅ Enviando...", ephemeral=True)
        for canal in self.canais_selecionados:
            try: await canal.send(self.mensagem_texto)
            except: pass

class MensagemAutoModal(discord.ui.Modal, title='Mensagem Automática'):
    msg = discord.ui.TextInput(label='Hi, qual vai ser a mensagem de hoje?', style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("📢 **Mensagem salva!** Selecione os canais abaixo:", view=EnviarMensagemView(self.msg.value), ephemeral=True)

class ConfigCargosView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode usar .p?", row=0)
    async def s_perfil(self, i, s): cargos_db['perfil'] = s.values[0].id; await i.response.send_message("✅ Cargo atualizado!", ephemeral=True)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode entrar na fila mediador?", row=1)
    async def s_med(self, i, s): cargos_db['mediador'] = s.values[0].id; await i.response.send_message("✅ Cargo atualizado!", ephemeral=True)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode mexer no Bot?", row=2)
    async def s_admin(self, i, s): cargos_db['admin'] = s.values[0].id; await i.response.send_message("✅ Cargo atualizado!", ephemeral=True)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode configurar o Pix?", row=3)
    async def s_pix(self, i, s): cargos_db['pix'] = s.values[0].id; await i.response.send_message("✅ Cargo atualizado!", ephemeral=True)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode puxar as logs?", row=4)
    async def s_logs(self, i, s): cargos_db['logs'] = s.values[0].id; await i.response.send_message("✅ Cargo atualizado!", ephemeral=True)

    # ==========================================
# MENUS DE VITÓRIA E MEDIAÇÃO
# ==========================================
class EscolherVencedorSelect(discord.ui.Select):
    def __init__(self, j1, j2, tipo_vitoria):
        self.j1, self.j2, self.tipo_vitoria = j1, j2, tipo_vitoria
        ops = [discord.SelectOption(label=j1.name, value=str(j1.id), emoji="🎮"), discord.SelectOption(label=j2.name, value=str(j2.id), emoji="🎮")]
        super().__init__(placeholder="Selecione o vencedor...", options=ops)

    async def callback(self, interaction: discord.Interaction):
        v_id = int(self.values[0])
        vencedor = self.j1 if v_id == self.j1.id else self.j2
        perdedor = self.j2 if v_id == self.j1.id else self.j1

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
        ops = [
            discord.SelectOption(label="Dar vitória a um jogador", emoji="🏆", value="normal"),
            discord.SelectOption(label="Vitória por W.O", emoji="❗", value="wo"),
            discord.SelectOption(label="Finalizar partida", emoji="❌", description="Fecha o tópico", value="finalizar")
        ]
        super().__init__(placeholder="Menu Mediador", options=ops)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "finalizar":
            await interaction.response.send_message("🔒 Partida finalizada! O tópico será fechado em 3 segundos...")
            await asyncio.sleep(3)
            try: await interaction.channel.edit(archived=True, locked=True)
            except: pass
        elif self.values[0] == "normal":
            await interaction.response.send_message("🏆 **Quem ganhou?**", view=discord.ui.View().add_item(EscolherVencedorSelect(self.j1, self.j2, "normal")), ephemeral=True)
        elif self.values[0] == "wo":
            await interaction.response.send_message("❗ **Quem ganhou por W.O?**", view=discord.ui.View().add_item(EscolherVencedorSelect(self.j1, self.j2, "wo")), ephemeral=True)

class MenuMediadorView(discord.ui.View):
    def __init__(self, j1, j2):
        super().__init__(timeout=None)
        self.add_item(MenuMediadorSelect(j1, j2))

class RegrasView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='Regras', style=discord.ButtonStyle.link, url='https://discord.gg/seulink'))

        # ==========================================
# CONFIRMAÇÃO E REGISTRO
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
            novo_nome = f"{self.nome_f.replace(' ', '')}-{contador_partidas}"
            try: await interaction.channel.edit(name=novo_nome)
            except: pass

            registro = {'modo': self.modo, 'partida': novo_nome, 'valor': self.valor, 'topico_id': interaction.channel.id}
            historico_db.setdefault(self.j1.id, []).append(registro)
            historico_db.setdefault(self.j2.id, []).append(registro)

            val_p = (self.valor * 2) + taxa_fixa_db 
            pix = pix_db.get(self.med_id, {"chave": "Não configurada", "tipo": "-", "nome": "Não informado"})

            emb = discord.Embed(title="Partida Confirmada", color=discord.Color.from_str('#3b2c28'))
            emb.add_field(name="🎮 Estilo de Jogo", value=f"{self.nome_f} ({self.modo})", inline=False)
            emb.add_field(name="ℹ️ Informações", value=f"Taxa da Sala: R$ {taxa_fixa_db:.2f}\nMediador: <@{self.med_id}>", inline=False)
            emb.add_field(name="💠 Valor da Aposta (Cada)", value=f"R$ {self.valor:.2f}", inline=False)
            emb.add_field(name="👥 Jogadores", value=f"{self.j1.mention}\n{self.j2.mention}", inline=False)
            emb.set_thumbnail(url=banner_db)

            qr = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={pix['chave']}"
            e_pix = discord.Embed(color=0x2b2d31).set_image(url=qr)
            e_pix.description = f"**Nome:** {pix['nome']}\n**Chave:** `{pix['chave']}`\n**Total a pagar:** R$ {val_p:.2f}"

            await interaction.channel.send(content=f"{self.j1.mention} {self.j2.mention}, <@{self.med_id}>", embed=emb, view=MenuMediadorView(self.j1, self.j2))
            await interaction.channel.send(embed=e_pix, view=RegrasView())

    @discord.ui.button(label='Recusar', style=discord.ButtonStyle.danger)
    async def btn_recusar(self, i, b): await i.response.send_message(f"❌ {i.user.mention} recusou a partida.")

    # ==========================================
# PAINEL DA FILA (DINÂMICO)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self, emb, nome, val):
        super().__init__(timeout=None)
        self.jogs = []
        self.emb = emb
        self.nome = nome
        self.val = val

        # Sistema que verifica se a fila é 2v2 para mudar os botões
        if "2v2" in nome.lower():
            b_entrar = discord.ui.Button(label='Entrar na fila', style=discord.ButtonStyle.success)
            b_entrar.callback = self.n_2v2
            self.add_item(b_entrar)
        else:
            b_n = discord.ui.Button(label='Gel Normal', style=discord.ButtonStyle.secondary)
            b_n.callback = self.n_normal
            self.add_item(b_n)
            
            b_inf = discord.ui.Button(label='Gel Infinito', style=discord.ButtonStyle.secondary)
            b_inf.callback = self.n_infinito
            self.add_item(b_inf)

        b_sair = discord.ui.Button(label='Sair da fila', style=discord.ButtonStyle.danger)
        b_sair.callback = self.s_fila
        self.add_item(b_sair)

    def atualizar_visual(self):
        v_str = f"{self.val:.2f}".replace('.', ',')
        desc = f"👑 **Modo**\n{self.nome.upper()}\n\n💎 **Valor**\nR$ {v_str}\n\n⚡ **Jogadores**\n"
        if not self.jogs: desc += "Nenhum jogador na fila"
        else:
            for j in self.jogs: desc += f"{j['user'].mention} - {j['modo']}\n"
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

    # Callbacks dos botões dinâmicos
    async def n_2v2(self, i): await self.processar_clique(i, "2v2")
    async def n_normal(self, i): await self.processar_clique(i, "Gel Normal")
    async def n_infinito(self, i): await self.processar_clique(i, "Gel Infinito")
    async def s_fila(self, i):
        self.jogs = [j for j in self.jogs if j['user'].id != i.user.id]
        self.atualizar_visual()
        await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
        await i.message.edit(embed=self.emb, view=self)

# ==========================================
# LOGS E MODAIS DE CONFIGURAÇÃO
# ==========================================
class BotaoPuxarLogView(discord.ui.View):
    def __init__(self, topico_id, autor_id):
        super().__init__(timeout=None)
        self.topico_id = topico_id
        self.autor_id = autor_id

    @discord.ui.button(label="Conversa do tópico!", style=discord.ButtonStyle.primary, emoji="📄")
    async def btn_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id: return await interaction.response.send_message("❌ Apenas quem puxou a log pode abrir.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        canal = interaction.guild.get_thread(self.topico_id)
        if not canal: return await interaction.followup.send("⚠️ Tópico excluído ou inacessível.", ephemeral=True)
        
        msgs = [m async for m in canal.history(limit=200, oldest_first=True)]
        txt = "\n".join([f"[{m.created_at.strftime('%d/%m %H:%M')}] {m.author.name}: {m.content}" for m in msgs])
        arquivo = discord.File(io.BytesIO(txt.encode('utf-8')), filename=f"log_{self.topico_id}.txt")
        await interaction.followup.send("📄 Histórico da conversa:", file=arquivo, ephemeral=True)

class SelectMatchLog(discord.ui.Select):
    def __init__(self, historico, autor_id):
        ops = [discord.SelectOption(label=f"Modo: {h['modo']}", description=f"{h['partida']} | R$ {h['valor']}", value=str(idx)) for idx, h in enumerate(historico[-25:])]
        super().__init__(placeholder="Selecione uma partida recente...", options=ops)
        self.historico = historico[-25:]
        self.autor_id = autor_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id: return await interaction.response.send_message("❌ Apenas quem puxou a log pode abrir.", ephemeral=True)
        h = self.historico[int(self.values[0])]
        emb = discord.Embed(title="Detalhes da Partida", description=f"**Modo:** {h['modo']}\n**Partida:** {h['partida']}\n**Valor:** R$ {h['valor']}", color=0x2b2d31)
        await interaction.response.send_message(embed=emb, view=BotaoPuxarLogView(h['topico_id'], self.autor_id), ephemeral=True)

class FilaModal(discord.ui.Modal, title='Criar Filas'):
    n = discord.ui.TextInput(label='Nome da fila (Ex: Mobile ou 2v2)', required=True)
    v = discord.ui.TextInput(label='Valores (Separe por vírgula)', style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Gerando filas...", ephemeral=True)
        for val_raw in re.split(r'[;,\n]', self.v.value.replace(' ', '')):
            if val_raw:
                try:
                    val = float(val_raw.replace('R$', '').replace(',', '.'))
                    emb = discord.Embed(title=f"SPACE APOSTAS {val:g}K", description=f"👑 **Modo**\n{self.n.value.upper()}\n\n💎 **Valor**\nR$ {val:.2f}\n\n⚡ **Jogadores**\nNenhum jogador na fila", color=0x2b2d31).set_image(url=banner_db)
                    await interaction.channel.send(embed=emb, view=FilaView(emb, self.n.value, val))
                except: pass

class MudarTaxaModal(discord.ui.Modal, title='Mudar Taxa da Sala'):
    t = discord.ui.TextInput(label='Qual vai ser o valor agora campeão?', placeholder='Ex: 0,20')
    async def on_submit(self, i):
        global taxa_fixa_db
        try:
            taxa_fixa_db = float(self.t.value.replace(',', '.'))
            await i.response.send_message(f"✅ Taxa: R$ {taxa_fixa_db:.2f}", ephemeral=True)
        except: await i.response.send_message("❌ Erro no número.", ephemeral=True)

class MudarBannerModal(discord.ui.Modal, title='Mudar Banner da Fila'):
    b = discord.ui.TextInput(label='Link da Nova Imagem (URL)')
    async def on_submit(self, i):
        global banner_db
        banner_db = self.b.value.strip()
        await i.response.send_message("✅ Banner atualizado!", ephemeral=True)

class ConfigurarCanaisModal(discord.ui.Modal, title='Canais para Tópicos de Apostas'):
    canal1 = discord.ui.TextInput(label='ID do Canal 1', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        global canais_topico_db
        canais_topico_db.clear()
        if self.canal1.value.strip().isdigit(): canais_topico_db.append(int(self.canal1.value.strip()))
        await interaction.response.send_message("✅ Canal configurado!", ephemeral=True)

# ==========================================
# VIEWS ORIGINAIS DE PAINEL
# ==========================================
class MediadorView(discord.ui.View):
    def __init__(self, embed_base):
        super().__init__(timeout=None)
        self.embed_base = embed_base

    def atualizar_embed(self):
        desc = "Entre na fila para começar a mediar suas filas\n\n"
        if not lista_mediadores: desc += "*Nenhum mediador na fila.*"
        else:
            for idx, user_id in enumerate(lista_mediadores, 1): desc += f"{idx} • <@{user_id}> {user_id}\n"
        self.embed_base.description = desc

    @discord.ui.button(label='Entrar na fila', style=discord.ButtonStyle.success, emoji='🟢')
    async def btn_entrar(self, i: discord.Interaction, b):
        if not tem_permissao(i.user, 'mediador'): return await i.response.send_message("❌ Sem permissão.", ephemeral=True)
        if i.user.id not in lista_mediadores:
            lista_mediadores.append(i.user.id)
            self.atualizar_embed()
            await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
            await i.message.edit(embed=self.embed_base)

    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger, emoji='🔴')
    async def btn_sair(self, i: discord.Interaction, b):
        if i.user.id in lista_mediadores:
            lista_mediadores.remove(i.user.id)
            self.atualizar_embed()
            await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
            await i.message.edit(embed=self.embed_base)

    @discord.ui.button(label='Remover Mediador', style=discord.ButtonStyle.secondary, emoji='⚙️')
    async def btn_remover(self, i: discord.Interaction, b): await i.response.send_message("🔧 Função em desenvolvimento.", ephemeral=True)

    @discord.ui.button(label='Painel Staff', style=discord.ButtonStyle.secondary, emoji='⚙️')
    async def btn_staff(self, i: discord.Interaction, b): await i.response.send_message("🛠️ Painel Staff em desenvolvimento.", ephemeral=True)

class CadastrarPixModal(discord.ui.Modal, title='Configurar Chave PIX'):
    nome = discord.ui.TextInput(label='Seu Nome Completo', required=True)
    chave = discord.ui.TextInput(label='Sua Chave PIX', required=True)
    tipo = discord.ui.TextInput(label='Tipo (CPF, Email, etc)', required=True)
    async def on_submit(self, i):
        pix_db[i.user.id] = {'chave': self.chave.value, 'tipo': self.tipo.value, 'nome': self.nome.value}
        await i.response.send_message("✅ Chave PIX salva!", ephemeral=True)

class PixView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label='Chave pix', style=discord.ButtonStyle.success, emoji='💠')
    async def btn_cadastrar(self, i, b): await i.response.send_modal(CadastrarPixModal())
    
    @discord.ui.button(label='Sua Chave', style=discord.ButtonStyle.success, emoji='🔍')
    async def btn_ver(self, i, b):
        p = pix_db.get(i.user.id)
        if p: await i.response.send_message(f"🔐 **Chave:** `{p['chave']}`\n**Nome:** {p['nome']}", ephemeral=True)
        else: await i.response.send_message("🔐 Você não tem chave cadastrada.", ephemeral=True)
        
    @discord.ui.button(label='Ver Chave de Mediador', style=discord.ButtonStyle.secondary, emoji='🔍')
    async def btn_mediador(self, i, b): await i.response.send_message("🛠️ Em breve: Escolha um mediador para ver a chave dele.", ephemeral=True)

    # ==========================================
# TODOS OS COMANDOS E FINALIZAÇÃO
# ==========================================
@bot.tree.command(name="configurar_cargos", description="Abre o painel de configuração de permissões")
async def configurar_cargos(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator: return await interaction.response.send_message("❌ Apenas Administradores.", ephemeral=True)
    await interaction.response.send_message("⚙️ **Configuração de Cargos**", view=ConfigCargosView(), ephemeral=True)

@bot.tree.command(name="enviar_mensangem_automatica", description="Envia avisos automáticos para múltiplos canais")
async def enviar_mensangem_automatica(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_modal(MensagemAutoModal())

@bot.tree.command(name="mudar_taxa", description="Define o valor fixo da taxa da sala")
async def mudar_taxa(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_modal(MudarTaxaModal())

@bot.tree.command(name="banner_da_fila", description="Altera a imagem principal dos cards de aposta")
async def banner_da_fila(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_modal(MudarBannerModal())

@bot.tree.command(name="escolher_canais_pra_criar_topico", description="Escolha até 3 canais para o bot criar os tópicos")
async def escolher_canais_pra_criar_topico(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_modal(ConfigurarCanaisModal())

@bot.tree.command(name="criar_filas", description="Gera painéis de aposta com vários valores")
async def criar_filas(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_modal(FilaModal())

@bot.tree.command(name="mediador", description="Abre o painel da fila controladora")
async def mediador(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'mediador'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    embed = discord.Embed(title="Painel da fila controladora", description="Entre na fila para começar a mediar suas filas\n\n*Nenhum mediador na fila.*", color=discord.Color.from_str('#2b2d31'))
    embed.set_thumbnail(url=banner_db)
    await interaction.response.send_message(embed=embed, view=MediadorView(embed))

@bot.tree.command(name="pix", description="Abre o painel para configurar a chave PIX")
async def pix_comando(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'pix'): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    embed = discord.Embed(title="Painel Para Configurar Chave PIX", description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.", color=discord.Color.from_str('#2b2d31'))
    embed.set_thumbnail(url=banner_db)
    await interaction.response.send_message(embed=embed, view=PixView())

@bot.command(name="logs")
async def puxar_logs(ctx, membro: discord.Member = None):
    if not tem_permissao(ctx.author, 'logs'): return await ctx.reply("❌ Você não tem o cargo de puxar logs!")
    if not membro: return await ctx.reply("Mencione um usuário! Ex: `.logs @jogador`")
    
    h = historico_db.get(membro.id, [])
    if not h: return await ctx.reply(f"O jogador {membro.name} não possui partidas registradas.")
    
    view = discord.ui.View().add_item(SelectMatchLog(h, ctx.author.id))
    await ctx.reply(f"📜 Logs de {membro.name} encontrados. Selecione uma partida abaixo:", view=view)

@bot.command(name="p")
async def perfil(ctx, membro: discord.Member = None):
    if not tem_permissao(ctx.author, 'perfil'): return await ctx.reply("❌ Sem permissão para ver perfis.")
    # Se mencionar, usa a menção. Se não mencionar (membro for None), usa quem mandou a mensagem
    u = membro or ctx.author 

    if ctx.message.reference:
        try: u = (await ctx.channel.fetch_message(ctx.message.reference.message_id)).author
        except: pass

    s = stats_db.get(u.id, {'vitorias': 0, 'derrotas': 0, 'consecutivas': 0, 'total': 0, 'coins': 0})
    emb = discord.Embed(description=f"🎮 **Estatísticas**\n\nVitórias: {s['vitorias']}\nDerrotas: {s['derrotas']}\nConsecutivas: {s['consecutivas']}\nTotal de Partidas: {s['total']}\n\n💎 **Coins**\n\nCoins: {s['coins']}", color=discord.Color.from_str('#2b2d31'))
    emb.set_author(name=u.name, icon_url=u.display_avatar.url)
    emb.set_thumbnail(url=u.display_avatar.url)
    await ctx.reply(embed=emb)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Bot Full Configurado e Online!")

bot.run(os.environ.get('TOKEN'))
    
