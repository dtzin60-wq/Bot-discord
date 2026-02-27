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
nome_base_fila = 'SPACE APOSTAS' # Variável do nome da fila
stats_db = {} 
contador_partidas = 0 
historico_db = {} 

cargos_db = {
    'perfil': None, 
    'mediador': None, 
    'admin': None, 
    'pix': None, 
    'logs': None
}

def gerar_embed_sucesso(usuario):
    embed = discord.Embed(
        description=f"{usuario.mention}, a sua operação foi concluída com êxito.\n↪ Você entrou ou saiu da fila com sucesso.",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_author(name="✅ Ação realizada com sucesso!")
    return embed

def tem_permissao(membro, chave):
    if membro.guild_permissions.administrator:
        return True
    
    cargo_id = cargos_db.get(chave)
    
    if not cargo_id:
        return True 
        
    for r in membro.roles:
        if r.id == cargo_id:
            return True
            
    return False

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
        if not self.canais_selecionados:
            await interaction.response.send_message("❌ Selecione um canal!", ephemeral=True)
            return
            
        await interaction.response.send_message("✅ Enviando mensagens...", ephemeral=True)
        for canal in self.canais_selecionados:
            try:
                await canal.send(self.mensagem_texto)
            except Exception as e:
                print(f"Erro ao enviar para o canal: {e}")

class MensagemAutoModal(discord.ui.Modal, title='Mensagem Automática'):
    msg = discord.ui.TextInput(
        label='Hi, qual vai ser a mensagem de hoje?', 
        style=discord.TextStyle.paragraph, 
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        view = EnviarMensagemView(self.msg.value)
        await interaction.response.send_message(
            "📢 **Mensagem salva!** Selecione os canais abaixo:", 
            view=view, 
            ephemeral=True
        )

class ConfigCargosView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode usar .p?", row=0)
    async def s_perfil(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        cargos_db['perfil'] = select.values[0].id
        await interaction.response.send_message("✅ Cargo atualizado!", ephemeral=True)
        
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode entrar na fila mediador?", row=1)
    async def s_med(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        cargos_db['mediador'] = select.values[0].id
        await interaction.response.send_message("✅ Cargo atualizado!", ephemeral=True)
        
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode mexer no Bot?", row=2)
    async def s_admin(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        cargos_db['admin'] = select.values[0].id
        await interaction.response.send_message("✅ Cargo atualizado!", ephemeral=True)
        
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode configurar o Pix?", row=3)
    async def s_pix(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        cargos_db['pix'] = select.values[0].id
        await interaction.response.send_message("✅ Cargo atualizado!", ephemeral=True)
        
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Qual cargo pode puxar as logs?", row=4)
    async def s_logs(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        cargos_db['logs'] = select.values[0].id
        await interaction.response.send_message("✅ Cargo atualizado!", ephemeral=True)

        # ==========================================
# MENUS DE VITÓRIA E MEDIAÇÃO
# ==========================================
class EscolherVencedorSelect(discord.ui.Select):
    def __init__(self, j1, j2, tipo_vitoria):
        self.j1 = j1
        self.j2 = j2
        self.tipo_vitoria = tipo_vitoria
        opcoes = [
            discord.SelectOption(label=j1.name, value=str(j1.id), emoji="🎮"),
            discord.SelectOption(label=j2.name, value=str(j2.id), emoji="🎮")
        ]
        super().__init__(placeholder="Selecione o vencedor...", options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        vencedor_id = int(self.values[0])
        
        if vencedor_id == self.j1.id:
            vencedor = self.j1
            perdedor = self.j2
        else:
            vencedor = self.j2
            perdedor = self.j1

        for usuario in [vencedor, perdedor]:
            if usuario.id not in stats_db:
                stats_db[usuario.id] = {'vitorias': 0, 'derrotas': 0, 'consecutivas': 0, 'total': 0, 'coins': 0}

        # Atualiza Status do Vencedor
        stats_db[vencedor.id]['vitorias'] += 1
        stats_db[vencedor.id]['total'] += 1
        stats_db[vencedor.id]['consecutivas'] += 1
        
        # Atualiza Status do Perdedor
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
        self.j1 = j1
        self.j2 = j2
        opcoes = [
            discord.SelectOption(label="Dar vitória a um jogador", emoji="🏆", value="normal"),
            discord.SelectOption(label="Vitória por W.O", emoji="❗", value="wo"),
            discord.SelectOption(label="Finalizar partida", emoji="❌", description="Fecha o tópico", value="finalizar")
        ]
        super().__init__(placeholder="Menu Mediador", min_values=1, max_values=1, options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        escolha = self.values[0]
        
        if escolha == "finalizar":
            await interaction.response.send_message("🔒 Partida finalizada! O tópico será fechado em 3 segundos...")
            await asyncio.sleep(3)
            try:
                await interaction.channel.edit(archived=True, locked=True)
            except Exception as e:
                print(f"Erro ao fechar: {e}")
                
        elif escolha == "normal":
            view_vencedor = discord.ui.View()
            view_vencedor.add_item(EscolherVencedorSelect(self.j1, self.j2, "normal"))
            await interaction.response.send_message("🏆 **Quem ganhou?**", view=view_vencedor, ephemeral=True)
            
        elif escolha == "wo":
            view_wo = discord.ui.View()
            view_wo.add_item(EscolherVencedorSelect(self.j1, self.j2, "wo"))
            await interaction.response.send_message("❗ **Quem ganhou por W.O?**", view=view_wo, ephemeral=True)

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
        self.j1 = j1
        self.j2 = j2
        self.modo = modo
        self.valor = valor
        self.med_id = med_id
        self.nome_f = nome_f
        self.conf = set()
        self.msg_aviso = None

    @discord.ui.button(label='Confirmar', style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        global contador_partidas
        
        if interaction.user.id not in [self.j1.id, self.j2.id]:
            await interaction.response.send_message("❌ Apenas jogadores!", ephemeral=True)
            return
            
        if interaction.user.id in self.conf:
            await interaction.response.send_message("⚠️ Já confirmou!", ephemeral=True)
            return

        self.conf.add(interaction.user.id)
        
        if len(self.conf) == 1:
            self.msg_aviso = await interaction.channel.send(f"✅ {interaction.user.mention} confirmou!")
            
        elif len(self.conf) == 2:
            await interaction.response.defer() 
            
            try:
                await interaction.message.delete()
                if self.msg_aviso:
                    await self.msg_aviso.delete()
            except Exception:
                pass

            contador_partidas += 1
            novo_nome = f"{self.nome_f.replace(' ', '')}-1v1-{contador_partidas}"
            try:
                await interaction.channel.edit(name=novo_nome)
            except Exception:
                pass

            registro = {
                'modo': self.modo, 
                'partida': novo_nome, 
                'valor': self.valor, 
                'topico_id': interaction.channel.id
            }
            
            if self.j1.id not in historico_db: historico_db[self.j1.id] = []
            if self.j2.id not in historico_db: historico_db[self.j2.id] = []
            
            historico_db[self.j1.id].append(registro)
            historico_db[self.j2.id].append(registro)

            val_p = (self.valor * 2) + taxa_fixa_db 
            pix = pix_db.get(self.med_id, {"chave": "Não configurada", "tipo": "-", "nome": "Não informado"})

            emb = discord.Embed(title="Partida Confirmada", color=discord.Color.from_str('#3b2c28'))
            emb.add_field(name="🎮 Estilo de Jogo", value=f"{self.nome_f} ({self.modo})", inline=False)
            emb.add_field(name="ℹ️ Informações", value=f"Taxa da Sala: R$ {taxa_fixa_db:.2f}\nMediador: <@{self.med_id}>", inline=False)
            emb.add_field(name="💠 Valor da Aposta (Cada)", value=f"R$ {self.valor:.2f}", inline=False)
            emb.add_field(name="👥 Jogadores", value=f"{self.j1.mention}\n{self.j2.mention}", inline=False)
            emb.set_thumbnail(url=banner_db)

            qr = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={pix['chave']}"
            e_pix = discord.Embed(color=discord.Color.from_str('#2b2d31'))
            e_pix.set_image(url=qr)
            e_pix.description = f"**Nome:** {pix['nome']}\n**Chave:** `{pix['chave']}`\n**Total a pagar:** R$ {val_p:.2f}"

            await interaction.channel.send(
                content=f"{self.j1.mention} {self.j2.mention}, <@{self.med_id}>", 
                embed=emb, 
                view=MenuMediadorView(self.j1, self.j2)
            )
            await interaction.channel.send(embed=e_pix, view=RegrasView())

    @discord.ui.button(label='Recusar', style=discord.ButtonStyle.danger)
    async def btn_recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"❌ {interaction.user.mention} recusou a partida.")

# ==========================================
# PAINEL DA FILA (MATCHMAKING)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self, emb, nome, val):
        super().__init__(timeout=None)
        self.jogs = []
        self.emb = emb
        self.nome = nome
        self.val = val

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
        
        if len(self.jogs) == 0:
            desc += "Nenhum jogador na fila"
        else:
            for j in self.jogs:
                desc += f"{j['user'].mention} - {j['modo']}\n"
                
        self.emb.description = desc
        self.emb.set_image(url=banner_db)

    async def processar_clique(self, i: discord.Interaction, modo: str):
        if len(lista_mediadores) == 0:
            await i.response.send_message("❌ | NÃO TEM NENHUM MEDIADOR NA FILA!", ephemeral=True)
            return

        for j in self.jogs:
            if j['user'].id == i.user.id:
                if j['modo'] == modo:
                    await i.response.send_message("⚠️ Você já está nesta fila!", ephemeral=True)
                    return
                j['modo'] = modo
                self.atualizar_visual()
                await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
                await i.message.edit(embed=self.emb, view=self)
                return

        op = None
        for j in self.jogs:
            if j['modo'] == modo:
                op = j
                break

        if op:
            self.jogs.remove(op)
            self.atualizar_visual()
            await i.response.edit_message(embed=self.emb, view=self)

            med = lista_mediadores.pop(0)
            lista_mediadores.append(med)

            canal_alvo = i.channel
            if len(canais_topico_db) > 0:
                id_sorteado = random.choice(canais_topico_db)
                canal_encontrado = i.guild.get_channel(id_sorteado)
                if canal_encontrado:
                    canal_alvo = canal_encontrado

            try:
                topico = await canal_alvo.create_thread(name="aguardando-confirmaçao", auto_archive_duration=60)
                view_confirma = ThreadConfirmacaoView(op['user'], i.user, modo, self.val, med, self.nome)
                await topico.send(content=f"Chamando: {op['user'].mention} {i.user.mention}\nMediador: <@{med}>", view=view_confirma)
                await i.followup.send(f"✅ Partida no canal: {canal_alvo.mention}", ephemeral=True)
            except Exception as e:
                print(e)
        else:
            self.jogs.append({"user": i.user, "modo": modo})
            self.atualizar_visual()
            await i.response.send_message(embed=gerar_embed_sucesso(i.user), ephemeral=True)
            await i.message.edit(embed=self.emb, view=self)

    async def n_2v2(self, interaction):
        await self.processar_clique(interaction, "2v2")
        
    async def n_normal(self, interaction):
        await self.processar_clique(interaction, "Gel Normal")
        
    async def n_infinito(self, interaction):
        await self.processar_clique(interaction, "Gel Infinito")
        
    async def s_fila(self, interaction):
        for j in self.jogs:
            if j['user'].id == interaction.user.id:
                self.jogs.remove(j)
                
        self.atualizar_visual()
        await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
        await interaction.message.edit(embed=self.emb, view=self)

# ==========================================
# LOGS E MODAIS SECUNDÁRIOS
# ==========================================
class BotaoPuxarLogView(discord.ui.View):
    def __init__(self, topico_id, autor_id):
        super().__init__(timeout=None)
        self.topico_id = topico_id
        self.autor_id = autor_id

    @discord.ui.button(label="Conversa do tópico!", style=discord.ButtonStyle.primary, emoji="📄")
    async def btn_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Apenas quem puxou a log pode abrir.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        canal = interaction.guild.get_thread(self.topico_id)
        
        if not canal:
            await interaction.followup.send("⚠️ Tópico excluído ou inacessível.", ephemeral=True)
            return
        
        msgs = [m async for m in canal.history(limit=200, oldest_first=True)]
        
        linhas = []
        for m in msgs:
            hora = m.created_at.strftime('%d/%m %H:%M')
            linhas.append(f"[{hora}] {m.author.name}: {m.content}")
            
        txt = "\n".join(linhas)
        arquivo = discord.File(io.BytesIO(txt.encode('utf-8')), filename=f"log_{self.topico_id}.txt")
        await interaction.followup.send("📄 Histórico da conversa:", file=arquivo, ephemeral=True)

class SelectMatchLog(discord.ui.Select):
    def __init__(self, historico, autor_id):
        self.historico = historico[-25:]
        self.autor_id = autor_id
        
        ops = []
        for idx, h in enumerate(self.historico):
            opcao = discord.SelectOption(
                label=f"Modo: {h['modo']}", 
                description=f"{h['partida']} | R$ {h['valor']}", 
                value=str(idx)
            )
            ops.append(opcao)
            
        super().__init__(placeholder="Selecione uma partida recente...", options=ops)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("❌ Apenas quem puxou a log pode abrir.", ephemeral=True)
            return
            
        h = self.historico[int(self.values[0])]
        emb = discord.Embed(
            title="Detalhes da Partida", 
            description=f"**Modo:** {h['modo']}\n**Partida:** {h['partida']}\n**Valor:** R$ {h['valor']}", 
            color=discord.Color.from_str('#2b2d31')
        )
        await interaction.response.send_message(embed=emb, view=BotaoPuxarLogView(h['topico_id'], self.autor_id), ephemeral=True)

class FilaModal(discord.ui.Modal, title='Criar Filas'):
    n = discord.ui.TextInput(
        label='Nome da fila (Ex: Mobile ou 2v2)', 
        required=True
    )
    v = discord.ui.TextInput(
        label='Valores (Separe por vírgula)', 
        style=discord.TextStyle.paragraph
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Gerando filas...", ephemeral=True)
        texto_limpo = self.v.value.replace(' ', '')
        lista_raw = re.split(r'[;,\n]', texto_limpo)
        
        for val_raw in lista_raw:
            if val_raw:
                try:
                    val = float(val_raw.replace('R$', '').replace(',', '.'))
                    emb = discord.Embed(
                        title=f"{nome_base_fila} {val:g}K", 
                        description=f"👑 **Modo**\n{self.n.value.upper()}\n\n💎 **Valor**\nR$ {val:.2f}\n\n⚡ **Jogadores**\nNenhum jogador na fila", 
                        color=discord.Color.from_str('#2b2d31')
                    )
                    emb.set_image(url=banner_db)
                    await interaction.channel.send(embed=emb, view=FilaView(emb, self.n.value, val))
                except Exception as e:
                    pass
# ==========================================
# CONFIGURAÇÕES E VIEWS DO PAINEL
# ==========================================
class MudarNomeFilaModal(discord.ui.Modal, title='Mudar Nome Base da Fila'):
    novo_nome = discord.ui.TextInput(
        label='Novo nome (Ex: Tropa, LBFF)', 
        style=discord.TextStyle.short, 
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        global nome_base_fila
        nome_base_fila = self.novo_nome.value.strip()
        await interaction.response.send_message(f"✅ O título das próximas filas será: **{nome_base_fila}**", ephemeral=True)

class MudarTaxaModal(discord.ui.Modal, title='Mudar Taxa da Sala'):
    t = discord.ui.TextInput(label='Qual vai ser o valor agora campeão?', placeholder='Ex: 0,20')
    
    async def on_submit(self, interaction: discord.Interaction):
        global taxa_fixa_db
        try:
            taxa_fixa_db = float(self.t.value.replace(',', '.'))
            await interaction.response.send_message(f"✅ Taxa atualizada: R$ {taxa_fixa_db:.2f}", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ Erro no número.", ephemeral=True)

class MudarBannerModal(discord.ui.Modal, title='Mudar Banner da Fila'):
    b = discord.ui.TextInput(label='Link da Nova Imagem (URL)')
    
    async def on_submit(self, interaction: discord.Interaction):
        global banner_db
        banner_db = self.b.value.strip()
        await interaction.response.send_message("✅ Banner atualizado!", ephemeral=True)

class ConfigurarCanaisModal(discord.ui.Modal, title='Canais para Tópicos de Apostas'):
    canal1 = discord.ui.TextInput(label='ID do Canal 1', required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        global canais_topico_db
        canais_topico_db.clear()
        if self.canal1.value.strip().isdigit():
            canais_topico_db.append(int(self.canal1.value.strip()))
        await interaction.response.send_message("✅ Canal configurado com sucesso!", ephemeral=True)

class MediadorView(discord.ui.View):
    def __init__(self, embed_base):
        super().__init__(timeout=None)
        self.embed_base = embed_base

    def atualizar_embed(self):
        desc = "Entre na fila para começar a mediar suas filas\n\n"
        if len(lista_mediadores) == 0:
            desc += "*Nenhum mediador na fila.*"
        else:
            for idx, user_id in enumerate(lista_mediadores, 1):
                desc += f"{idx} • <@{user_id}> {user_id}\n"
        self.embed_base.description = desc

    @discord.ui.button(label='Entrar na fila', style=discord.ButtonStyle.success, emoji='🟢')
    async def btn_entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not tem_permissao(interaction.user, 'mediador'):
            await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
            return
            
        if interaction.user.id not in lista_mediadores:
            lista_mediadores.append(interaction.user.id)
            self.atualizar_embed()
            await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
            await interaction.message.edit(embed=self.embed_base)

    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger, emoji='🔴')
    async def btn_sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in lista_mediadores:
            lista_mediadores.remove(interaction.user.id)
            self.atualizar_embed()
            await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
            await interaction.message.edit(embed=self.embed_base)

    @discord.ui.button(label='Remover Mediador', style=discord.ButtonStyle.secondary, emoji='⚙️')
    async def btn_remover(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔧 Função em desenvolvimento.", ephemeral=True)

    @discord.ui.button(label='Painel Staff', style=discord.ButtonStyle.secondary, emoji='⚙️')
    async def btn_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Painel Staff em desenvolvimento.", ephemeral=True)

class CadastrarPixModal(discord.ui.Modal, title='Configurar Chave PIX'):
    nome = discord.ui.TextInput(label='Seu Nome Completo', required=True)
    chave = discord.ui.TextInput(label='Sua Chave PIX', required=True)
    tipo = discord.ui.TextInput(label='Tipo (CPF, Email, etc)', required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            'chave': self.chave.value, 
            'tipo': self.tipo.value, 
            'nome': self.nome.value
        }
        await interaction.response.send_message("✅ Chave PIX salva com sucesso!", ephemeral=True)

class PixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='Chave pix', style=discord.ButtonStyle.success, emoji='💠')
    async def btn_cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CadastrarPixModal())
    
    @discord.ui.button(label='Sua Chave', style=discord.ButtonStyle.success, emoji='🔍')
    async def btn_ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        p = pix_db.get(interaction.user.id)
        if p:
            await interaction.response.send_message(f"🔐 **Chave:** `{p['chave']}`\n**Nome:** {p['nome']}", ephemeral=True)
        else:
            await interaction.response.send_message("🔐 Você não tem chave cadastrada.", ephemeral=True)
        
    @discord.ui.button(label='Ver Chave de Mediador', style=discord.ButtonStyle.secondary, emoji='🔍')
    async def btn_mediador(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Em breve: Escolha um mediador para ver a chave dele.", ephemeral=True)

# ==========================================
# TODOS OS COMANDOS E FINALIZAÇÃO
# ==========================================
@bot.tree.command(name="mudar_nome_da_fila", description="Muda o título padrão que aparece nas filas")
async def mudar_nome_da_fila(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await interaction.response.send_modal(MudarNomeFilaModal())

@bot.tree.command(name="configurar_cargos", description="Abre o painel de configuração de permissões")
async def configurar_cargos(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas Administradores.", ephemeral=True)
        return
    await interaction.response.send_message("⚙️ **Configuração de Cargos**", view=ConfigCargosView(), ephemeral=True)

@bot.tree.command(name="enviar_mensangem_automatica", description="Envia avisos automáticos para múltiplos canais")
async def enviar_mensangem_automatica(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await interaction.response.send_modal(MensagemAutoModal())

@bot.tree.command(name="mudar_taxa", description="Define o valor fixo da taxa da sala")
async def mudar_taxa(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await interaction.response.send_modal(MudarTaxaModal())

@bot.tree.command(name="banner_da_fila", description="Altera a imagem principal dos cards de aposta")
async def banner_da_fila(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await interaction.response.send_modal(MudarBannerModal())

@bot.tree.command(name="escolher_canais_pra_criar_topico", description="Escolha até 3 canais para o bot criar os tópicos")
async def escolher_canais_pra_criar_topico(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await interaction.response.send_modal(ConfigurarCanaisModal())

@bot.tree.command(name="criar_filas", description="Gera painéis de aposta com vários valores")
async def criar_filas(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'admin'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
    await interaction.response.send_modal(FilaModal())

@bot.tree.command(name="mediador", description="Abre o painel da fila controladora")
async def mediador(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'mediador'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="Painel da fila controladora", 
        description="Entre na fila para começar a mediar suas filas\n\n*Nenhum mediador na fila.*", 
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_thumbnail(url=banner_db)
    await interaction.response.send_message(embed=embed, view=MediadorView(embed))

@bot.tree.command(name="pix", description="Abre o painel para configurar a chave PIX")
async def pix_comando(interaction: discord.Interaction):
    if not tem_permissao(interaction.user, 'pix'):
        await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="Painel Para Configurar Chave PIX", 
        description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.", 
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_thumbnail(url=banner_db)
    await interaction.response.send_message(embed=embed, view=PixView())

@bot.command(name="logs")
async def puxar_logs(ctx, membro: discord.Member = None):
    if not tem_permissao(ctx.author, 'logs'):
        await ctx.reply("❌ Você não tem o cargo de puxar logs!")
        return
        
    if not membro:
        await ctx.reply("Mencione um usuário! Ex: `.logs @jogador`")
        return
    
    h = historico_db.get(membro.id, [])
    if not h:
        await ctx.reply(f"O jogador {membro.name} não possui partidas registradas.")
        return
    
    view_logs = discord.ui.View()
    view_logs.add_item(SelectMatchLog(h, ctx.author.id))
    
    await ctx.reply(f"📜 Logs de {membro.name} encontrados. Selecione uma partida abaixo:", view=view_logs)

@bot.command(name="p")
async def perfil(ctx, membro: discord.Member = None):
    if not tem_permissao(ctx.author, 'perfil'):
        await ctx.reply("❌ Sem permissão para ver perfis.")
        return
        
    # Funciona para `.p` e `.p @user`
    usuario_alvo = membro
    if usuario_alvo is None:
        usuario_alvo = ctx.author

    if ctx.message.reference:
        try:
            mensagem_ref = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            usuario_alvo = mensagem_ref.author
        except Exception:
            pass

    s = stats_db.get(usuario_alvo.id, {'vitorias': 0, 'derrotas': 0, 'consecutivas': 0, 'total': 0, 'coins': 0})
    
    embed = discord.Embed(
        description=f"🎮 **Estatísticas**\n\nVitórias: {s['vitorias']}\nDerrotas: {s['derrotas']}\nConsecutivas: {s['consecutivas']}\nTotal de Partidas: {s['total']}\n\n💎 **Coins**\n\nCoins: {s['coins']}", 
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_author(name=usuario_alvo.name, icon_url=usuario_alvo.display_avatar.url)
    embed.set_thumbnail(url=usuario_alvo.display_avatar.url)
    
    await ctx.reply(embed=embed)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print("✅ Bot Full HD Online!")

bot.run(os.environ.get('TOKEN'))
    
