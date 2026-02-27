Import discord
from discord.ext import commands
import os
import asyncio
import re
import random 

# ==========================================
# CONFIGURAÇÃO DO BOT
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True

bot = commands.Bot(command_prefix='.', intents=intents)

# ==========================================
# BANCOS DE DADOS TEMPORÁRIOS (Em memória)
# ==========================================
lista_mediadores = [] 
pix_db = {}           
canais_topico_db = [] 

# NOVAS VARIÁVEIS GLOBAIS
taxa_fixa_db = 0.0  
banner_db = 'https://i.imgur.com/SUY8L4o.jpeg' 

# ==========================================
# FUNÇÃO DA MENSAGEM DE SUCESSO
# ==========================================
def gerar_embed_sucesso(usuario):
    embed = discord.Embed(
        description=f"{usuario.mention}, a sua operação foi concluída com êxito.\n↪ Você entrou ou saiu da fila com sucesso.",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_author(name="✅ Ação realizada com sucesso!")
    return embed

# ==========================================
# NOVOS MENUS E BOTÕES DO TÓPICO CONFIRMADO
# ==========================================
class MenuMediadorSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Vitória Jogador 1", emoji="🏆", description="Dá a vitória para o 1º jogador"),
            discord.SelectOption(label="Vitória Jogador 2", emoji="🏆", description="Dá a vitória para o 2º jogador"),
            discord.SelectOption(label="Cancelar Partida", emoji="❌", description="Cancela a partida e devolve valores")
        ]
        super().__init__(placeholder="Menu Mediador", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Opção selecionada: **{self.values[0]}** (Função em desenvolvimento)", ephemeral=True)

class MenuMediadorView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MenuMediadorSelect())

class RegrasView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label='Regras', style=discord.ButtonStyle.link, url='https://discord.gg/seulink', emoji='<:regras:1234567890>'))

# ==========================================
# BOTÕES DE DENTRO DO TÓPICO (CONFIRMAÇÃO)
# ==========================================
class ThreadConfirmacaoView(discord.ui.View):
    def __init__(self, jogador1, jogador2, modo, valor_aposta, mediador_id):
        super().__init__(timeout=None)
        self.jogador1 = jogador1
        self.jogador2 = jogador2
        self.modo = modo
        self.valor_aposta = valor_aposta
        self.mediador_id = mediador_id
        
        self.confirmados = set()
        self.msg_aviso = None

    @discord.ui.button(label='Confirmar', style=discord.ButtonStyle.success, custom_id='btn_confirmar_partida')
    async def btn_confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.jogador1.id, self.jogador2.id]:
            return await interaction.response.send_message("❌ Apenas os jogadores da partida podem confirmar!", ephemeral=True)

        if interaction.user.id in self.confirmados:
            return await interaction.response.send_message("⚠️ Você já confirmou a partida, aguarde o oponente!", ephemeral=True)

        self.confirmados.add(interaction.user.id)

        if len(self.confirmados) == 1:
            await interaction.response.defer() 
            self.msg_aviso = await interaction.channel.send(f"✅ {interaction.user.mention} confirmou a aposta! Aguardando o oponente...")
        
        elif len(self.confirmados) == 2:
            await interaction.response.defer() 
            
            try:
                await interaction.message.delete()
                if self.msg_aviso:
                    await self.msg_aviso.delete()
            except:
                pass

            # MATEMÁTICA ATUALIZADA DA TAXA
            valor_sala = taxa_fixa_db 
            
            # Soma as duas apostas + a taxa fixa (Ex: 5 + 5 + 0.20 = 10.20)
            valor_pagar = (self.valor_aposta * 2) + valor_sala 
            
            pix_info = pix_db.get(self.mediador_id, {"chave": "Não configurada", "tipo": "-", "nome": "Não informado"})

            embed_confirmada = discord.Embed(
                title="Partida Confirmada",
                color=discord.Color.from_str('#3b2c28') 
            )
            embed_confirmada.add_field(name="🎮 Estilo de Jogo", value=f"1v1 {self.modo}", inline=False)
            
            mediador_mention = f"<@{self.mediador_id}>" if self.mediador_id else "Nenhum"
            embed_confirmada.add_field(name="ℹ️ Informações da Aposta", value=f"Taxa da Sala: R$ {valor_sala:.2f}\nMediador: {mediador_mention}", inline=False)
            embed_confirmada.add_field(name="💠 Valor da Aposta (Cada)", value=f"R$ {self.valor_aposta:.2f}", inline=False)
            embed_confirmada.add_field(name="👥 Jogadores", value=f"{self.jogador1.mention}\n{self.jogador2.mention}", inline=False)
            
            # Puxa o banner dinâmico
            embed_confirmada.set_thumbnail(url=banner_db)

            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={pix_info['chave']}"
            
            texto_pix = (
                f"{pix_info['nome']}\n"
                f"{pix_info['chave']}\n"
                f"↪ Total a pagar na chave: {valor_pagar:.2f}"
            )
            
            embed_pix = discord.Embed(color=discord.Color.from_str('#2b2d31'))
            embed_pix.set_image(url=qr_url) 
            embed_pix.description = texto_pix 

            await interaction.channel.send(
                content=f"{self.jogador1.mention}, {self.jogador2.mention}, <@{self.mediador_id}>",
                embed=embed_confirmada,
                view=MenuMediadorView()
            )
            await interaction.channel.send(
                embed=embed_pix,
                view=RegrasView()
            )

    @discord.ui.button(label='Recusar', style=discord.ButtonStyle.danger, custom_id='btn_recusar_partida')
    async def btn_recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.jogador1.id, self.jogador2.id]:
            return await interaction.response.send_message("❌ Apenas os jogadores podem interagir.", ephemeral=True)
        await interaction.response.send_message(f"❌ {interaction.user.mention} recusou a partida. A aposta foi cancelada.")

    @discord.ui.button(label='Combinar Regras', style=discord.ButtonStyle.secondary, custom_id='btn_combinar_regras', emoji='🏳️')
    async def btn_regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📝 {interaction.user.mention} quer combinar regras. Usem este chat para conversar!")

# ==========================================
# CLASSE DOS BOTÕES DA FILA (MATCHMAKING)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self, embed_base, nome_fila, valor_float):
        super().__init__(timeout=None)
        self.jogadores = [] 
        self.embed_base = embed_base 
        self.nome_fila = nome_fila
        self.valor_float = valor_float

    def atualizar_visual(self):
        valor_formatado = f"{self.valor_float:.2f}".replace('.', ',')
        desc = f"👑 **Modo**\n1v1 {self.nome_fila.upper()}\n\n💎 **Valor**\nR$ {valor_formatado}\n\n⚡ **Jogadores**\n"
        
        if len(self.jogadores) == 0:
            desc += "Nenhum jogador na fila"
            self.embed_base.set_image(url=banner_db) 
        else:
            for j in self.jogadores:
                desc += f"{j['user'].mention} - {j['modo']}\n"
                
        self.embed_base.description = desc

    async def processar_clique(self, interaction: discord.Interaction, modo: str):
        if len(lista_mediadores) == 0:
            return await interaction.response.send_message("❌ | NÃO TEM NENHUM MEDIADOR NA FILA!", ephemeral=True)

        for j in self.jogadores:
            if j['user'].id == interaction.user.id:
                if j['modo'] == modo:
                    return await interaction.response.send_message("⚠️ Você já está na fila aguardando neste modo!", ephemeral=True)
                else:
                    j['modo'] = modo
                    self.atualizar_visual()
                    await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
                    return await interaction.message.edit(embed=self.embed_base, view=self)

        oponente = next((j for j in self.jogadores if j['modo'] == modo), None)

        if oponente:
            self.jogadores.remove(oponente) 
            self.embed_base.set_image(url=banner_db)
            self.atualizar_visual()
            await interaction.response.edit_message(embed=self.embed_base, view=self)

            mediador_atual = lista_mediadores.pop(0)
            lista_mediadores.append(mediador_atual)

            canal_alvo = interaction.channel 
            
            if len(canais_topico_db) > 0:
                id_sorteado = random.choice(canais_topico_db)
                canal_encontrado = interaction.guild.get_channel(id_sorteado)
                if canal_encontrado:
                    canal_alvo = canal_encontrado

            try:
                topico = await canal_alvo.create_thread(
                    name=f"🎮 {oponente['user'].name} vs {interaction.user.name}",
                    type=discord.ChannelType.public_thread,
                    auto_archive_duration=60 
                )
                
                valor_str = f"{self.valor_float:.2f}".replace('.', ',')
                embed_aguardando = discord.Embed(
                    title="Aguardando Confirmações",
                    description=f"👑 **Modo:**\n1v1 | {modo}\n\n💎 **Valor da aposta:**\nR$ {valor_str}\n\n⚡ **Jogadores:**\n{oponente['user'].mention}\n{interaction.user.mention}",
                    color=discord.Color.from_str('#2ecc71')
                )
                embed_aguardando.set_thumbnail(url=banner_db) 

                embed_regras = discord.Embed(
                    description="✨ **SEJAM MUITO BEM-VINDOS** ✨\n\n• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra combinada não existir no regulamento oficial da organização, é obrigatório tirar print do acordo antes do início da partida.",
                    color=discord.Color.from_str('#3498db')
                )

                aviso_mediador = f"Mediador designado: <@{mediador_atual}>"

                view_confirma = ThreadConfirmacaoView(
                    jogador1=oponente['user'], 
                    jogador2=interaction.user, 
                    modo=modo, 
                    valor_aposta=self.valor_float, 
                    mediador_id=mediador_atual
                )

                await topico.send(
                    content=f"Chamando jogadores: {oponente['user'].mention} {interaction.user.mention}\n{aviso_mediador}",
                    embeds=[embed_aguardando, embed_regras],
                    view=view_confirma
                )

                await interaction.followup.send(f"✅ **Partida encontrada!** O tópico foi criado no canal: {canal_alvo.mention}", ephemeral=True)

            except Exception as e:
                print(f"Erro ao criar tópico: {e}")
                await interaction.followup.send("⚠️ Partida confirmada, mas o bot não tem permissão para criar tópicos no canal sorteado!", ephemeral=True)
                
        else:
            self.jogadores.append({"user": interaction.user, "modo": modo})
            self.atualizar_visual()
            await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
            await interaction.message.edit(embed=self.embed_base, view=self)

    @discord.ui.button(label='Gel Normal', style=discord.ButtonStyle.secondary, custom_id='btn_gel_normal')
    async def btn_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar_clique(interaction, "Gel Normal")

    @discord.ui.button(label='Gel Infinito', style=discord.ButtonStyle.secondary, custom_id='btn_gel_infinito')
    async def btn_infinito(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar_clique(interaction, "Gel Infinito")

    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger, custom_id='btn_sair_fila')
    async def btn_sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        for j in self.jogadores:
            if j['user'].id == interaction.user.id:
                self.jogadores.remove(j)
                self.atualizar_visual()
                await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
                return await interaction.message.edit(embed=self.embed_base, view=self)
        
        await interaction.response.send_message("❌ Você não está em nenhuma fila!", ephemeral=True)

# ==========================================
# MODAIS DE CONFIGURAÇÃO E NOVAS FUNÇÕES
# ==========================================
class MudarTaxaModal(discord.ui.Modal, title='Mudar Taxa da Sala'):
    nova_taxa = discord.ui.TextInput(label='Qual vai ser o valor agora campeão?', style=discord.TextStyle.short, placeholder='Ex: 0,20 ou 1,50', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global taxa_fixa_db
        try:
            valor_num = float(self.nova_taxa.value.replace('R$', '').replace(',', '.'))
            taxa_fixa_db = valor_num
            await interaction.response.send_message(f"✅ **Taxa atualizada!** Agora as salas cobrarão R$ {taxa_fixa_db:.2f} de taxa fixa.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ **Erro:** Você deve digitar um número válido (ex: 0,20).", ephemeral=True)

class MudarBannerModal(discord.ui.Modal, title='Mudar Banner da Fila'):
    novo_banner = discord.ui.TextInput(label='Link da Nova Imagem (URL)', style=discord.TextStyle.short, placeholder='https://...', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global banner_db
        if self.novo_banner.value.startswith('http'):
            banner_db = self.novo_banner.value.strip()
            await interaction.response.send_message("✅ **Banner atualizado!** As próximas filas já sairão com a nova imagem.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ **Erro:** O link deve começar com http ou https.", ephemeral=True)

class ConfigurarCanaisModal(discord.ui.Modal, title='Canais para Tópicos de Apostas'):
    canal1 = discord.ui.TextInput(label='ID do Canal 1', style=discord.TextStyle.short, placeholder='Cole o ID do canal aqui', required=True)
    canal2 = discord.ui.TextInput(label='ID do Canal 2 (Opcional)', style=discord.TextStyle.short, placeholder='Deixe em branco se não quiser', required=False)
    canal3 = discord.ui.TextInput(label='ID do Canal 3 (Opcional)', style=discord.TextStyle.short, placeholder='Deixe em branco se não quiser', required=False)

    async def on_submit(self, interaction: discord.Interaction):
        global canais_topico_db
        canais_topico_db.clear() 

        for c in [self.canal1.value, self.canal2.value, self.canal3.value]:
            if c.strip().isdigit():
                canais_topico_db.append(int(c.strip()))

        if len(canais_topico_db) > 0:
            await interaction.response.send_message(f"✅ **Sucesso!** Os tópicos serão distribuídos aleatoriamente em {len(canais_topico_db)} canal(is) configurado(s).", ephemeral=True)
        else:
            await interaction.response.send_message("❌ **Erro:** Você não digitou nenhum ID de canal válido!", ephemeral=True)


class FilaModal(discord.ui.Modal, title='Criar Filas de X1'):
    nome = discord.ui.TextInput(label='Nome da fila (Ex: Mobile, 4v4, etc)', style=discord.TextStyle.short, required=True)
    valores = discord.ui.TextInput(label='Valores (Separe por vírgula, Máx 15)', style=discord.TextStyle.paragraph, placeholder='Ex: 0,50, 1,00, 2,00', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        nome_digitado = self.nome.value.strip()
        texto_valores = self.valores.value.replace(' ', '') 
        lista_raw = re.split(r'[;,\n]', texto_valores)
        
        valores_validos = []
        for v in lista_raw:
            if v:
                try:
                    v_num = float(v.replace('R$', '').replace(',', '.'))
                    valores_validos.append(v_num)
                except ValueError:
                    pass
        
        if not valores_validos:
            return await interaction.response.send_message('❌ Nenhum valor válido encontrado! Digite números como 0,50.', ephemeral=True)

        valores_validos = valores_validos[:15]
        await interaction.response.send_message(f"✅ Gerando {len(valores_validos)} filas...", ephemeral=True)

        for valor in valores_validos:
            valor_str = f"{valor:.2f}".replace('.', ',')
            
            embed = discord.Embed(
                title=f"1v1 | SPACE APOSTAS {valor_str}K",
                description=f"👑 **Modo**\n1v1 {nome_digitado.upper()}\n\n💎 **Valor**\nR$ {valor_str}\n\n⚡ **Jogadores**\nNenhum jogador na fila",
                color=discord.Color.from_str('#2b2d31')
            )
            embed.set_image(url=banner_db) # Usa a variável do banner configurado!

            view = FilaView(embed_base=embed, nome_fila=nome_digitado, valor_float=valor)
            await interaction.channel.send(embed=embed, view=view)
            await asyncio.sleep(0.5)

# ==========================================
# SISTEMA DO MEDIADOR E PIX
# ==========================================
class MediadorView(discord.ui.View):
    def __init__(self, embed_base):
        super().__init__(timeout=None)
        self.embed_base = embed_base

    def atualizar_embed(self):
        desc = "Entre na fila para começar a mediar suas filas\n\n"
        if len(lista_mediadores) == 0:
            desc += "*Nenhum mediador na fila.*"
        else:
            for idx, user_id in enumerate(lista_mediadores, start=1):
                desc += f"{idx} • <@{user_id}> {user_id}\n"
        self.embed_base.description = desc

    @discord.ui.button(label='Entrar na fila', style=discord.ButtonStyle.success, emoji='🟢', custom_id='btn_med_entrar')
    async def btn_entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in lista_mediadores:
            lista_mediadores.append(interaction.user.id)
            self.atualizar_embed()
            await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
            await interaction.message.edit(embed=self.embed_base, view=self)
        else:
            await interaction.response.send_message("⚠️ Você já está na fila de mediadores!", ephemeral=True)

    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger, emoji='🔴', custom_id='btn_med_sair')
    async def btn_sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in lista_mediadores:
            lista_mediadores.remove(interaction.user.id)
            self.atualizar_embed()
            await interaction.response.send_message(embed=gerar_embed_sucesso(interaction.user), ephemeral=True)
            await interaction.message.edit(embed=self.embed_base, view=self)
        else:
            await interaction.response.send_message("❌ Você não está na fila!", ephemeral=True)

    @discord.ui.button(label='Remover Mediador', style=discord.ButtonStyle.secondary, emoji='⚙️', custom_id='btn_med_remover')
    async def btn_remover(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔧 Função de remover em desenvolvimento.", ephemeral=True)

    @discord.ui.button(label='Painel Staff', style=discord.ButtonStyle.secondary, emoji='⚙️', custom_id='btn_med_staff')
    async def btn_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Painel Staff em desenvolvimento.", ephemeral=True)

class CadastrarPixModal(discord.ui.Modal, title='Configurar Chave PIX'):
    nome = discord.ui.TextInput(label='Seu Nome Completo', style=discord.TextStyle.short, placeholder='Ex: João da Silva', required=True)
    chave = discord.ui.TextInput(label='Sua Chave PIX', style=discord.TextStyle.short, placeholder='Ex: 123.456.789-00', required=True)
    tipo = discord.ui.TextInput(label='Tipo (CPF, Email, Telefone, Aleatória)', style=discord.TextStyle.short, placeholder='Ex: CPF', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        pix_db[interaction.user.id] = {
            'chave': self.chave.value,
            'tipo': self.tipo.value,
            'nome': self.nome.value
        }
        await interaction.response.send_message(f"✅ **Sucesso!**\nSua Chave PIX foi salva e aparecerá automaticamente nas partidas que você mediar.", ephemeral=True)

class PixView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Chave pix', style=discord.ButtonStyle.success, emoji='💠', custom_id='btn_pix_cadastrar')
    async def btn_cadastrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CadastrarPixModal())

    @discord.ui.button(label='Sua Chave', style=discord.ButtonStyle.success, emoji='🔍', custom_id='btn_pix_ver')
    async def btn_ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        pix = pix_db.get(interaction.user.id)
        if pix:
            await interaction.response.send_message(f"🔐 **Sua Chave Atual:**\n**Nome:** {pix['nome']}\n**Chave:** `{pix['chave']}` ({pix['tipo']})", ephemeral=True)
        else:
            await interaction.response.send_message("🔐 **Sua Chave:** *(Você ainda não tem chave cadastrada)*", ephemeral=True)

    @discord.ui.button(label='Ver Chave de Mediador', style=discord.ButtonStyle.secondary, emoji='🔍', custom_id='btn_pix_mediador')
    async def btn_mediador(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🛠️ Em breve: Escolha um mediador para ver a chave dele.", ephemeral=True)

# ==========================================
# EVENTOS E COMANDOS PRINCIPAIS
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ Bot online como {bot.user}')
    await bot.tree.sync()

@bot.tree.command(name="mudar_taxa", description="Define o valor fixo da taxa da sala")
async def mudar_taxa(interaction: discord.Interaction):
    await interaction.response.send_modal(MudarTaxaModal())

@bot.tree.command(name="banner_da_fila", description="Altera a imagem principal dos cards de aposta")
async def banner_da_fila(interaction: discord.Interaction):
    await interaction.response.send_modal(MudarBannerModal())

@bot.tree.command(name="escolher_canais_pra_criar_topico", description="Escolha até 3 canais para o bot criar os tópicos")
async def configurar_canais(interaction: discord.Interaction):
    await interaction.response.send_modal(ConfigurarCanaisModal())

@bot.tree.command(name="criar_filas", description="Gera painéis de aposta com vários valores")
async def criar_filas(interaction: discord.Interaction):
    await interaction.response.send_modal(FilaModal())

@bot.tree.command(name="mediador", description="Abre o painel da fila controladora")
async def mediador(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Painel da fila controladora",
        description="Entre na fila para começar a mediar suas filas\n\n*Nenhum mediador na fila.*",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_thumbnail(url=banner_db) 
    view = MediadorView(embed_base=embed)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="pix", description="Abre o painel para configurar a chave PIX")
async def pix_comando(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Painel Para Configurar Chave PIX",
        description="Gerencie de forma rápida a chave PIX utilizada nas suas filas.\n\nSelecione uma das opções abaixo para cadastrar, visualizar ou editar sua chave PIX.",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_thumbnail(url=banner_db) 
    view = PixView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.command(name="p")
async def perfil(ctx, membro: discord.Member = None):
    target_user = membro or ctx.author
    if ctx.message.reference:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            target_user = msg.author
        except: pass

    stats = {'vitorias': 0, 'derrotas': 2, 'consecutivas': 0, 'total': 2, 'coins': 0}
    embed = discord.Embed(
        description=f"🎮 **Estatísticas**\n\nVitórias: {stats['vitorias']}\nDerrotas: {stats['derrotas']}\nConsecutivas: {stats['consecutivas']}\nTotal de Partidas: {stats['total']}\n\n💎 **Coins**\n\nCoins: {stats['coins']}",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_author(name=target_user.name, icon_url=target_user.display_avatar.url)
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await ctx.reply(embed=embed)

# ==========================================
# INICIALIZAÇÃO E SEGURANÇA
# ==========================================
meu_token = os.environ.get('TOKEN')

if not meu_token:
    print("❌ ERRO: Token não encontrado na Railway!")
else:
    bot.run(meu_token)
