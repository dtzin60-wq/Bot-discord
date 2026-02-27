import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True 
intents.members = True

bot = commands.Bot(command_prefix='.', intents=intents)

quantidade_de_filas_ativas = 0

# ==========================================
# BOTÕES DE DENTRO DO TÓPICO (CONFIRMAÇÃO)
# ==========================================
class ThreadConfirmacaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Confirmar', style=discord.ButtonStyle.success, custom_id='btn_confirmar_partida')
    async def btn_confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Apenas manda uma mensagem avisando que o cara confirmou
        await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou a aposta!")

    @discord.ui.button(label='Recusar', style=discord.ButtonStyle.danger, custom_id='btn_recusar_partida')
    async def btn_recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"❌ {interaction.user.mention} recusou a partida.")

    @discord.ui.button(label='Combinar Regras', style=discord.ButtonStyle.secondary, custom_id='btn_combinar_regras', emoji='🏳️')
    async def btn_regras(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"📝 {interaction.user.mention} quer combinar regras. Usem este chat para conversar!")

# ==========================================
# CLASSE DOS BOTÕES DA FILA (MATCHMAKING)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self, embed_base, nome_fila, valor_fila):
        super().__init__(timeout=None)
        self.jogadores = [] 
        self.embed_base = embed_base 
        self.nome_fila = nome_fila
        self.valor_fila = valor_fila
        self.banner_padrao = 'https://i.imgur.com/SUY8L4o.jpeg' 
        self.banner_match = 'https://i.imgur.com/SUY8L4o.jpeg' 

    def atualizar_visual(self):
        desc = f"👑 **Modo**\n1v1 {self.nome_fila.upper()}\n\n💎 **Valor**\nR$ {self.valor_fila:.2f}\n\n⚡ **Jogadores**\n"
        
        if len(self.jogadores) == 0:
            desc += "Nenhum jogador na fila"
            self.embed_base.set_image(url=self.banner_padrao) 
        else:
            for j in self.jogadores:
                desc += f"{j['user'].mention} - {j['modo']}\n"
                
        self.embed_base.description = desc

    async def processar_clique(self, interaction: discord.Interaction, modo: str):
        # 1. Verifica se o jogador já está na fila
        for j in self.jogadores:
            if j['user'].id == interaction.user.id:
                if j['modo'] == modo:
                    return await interaction.response.send_message("⚠️ Você já está na fila aguardando neste modo!", ephemeral=True)
                else:
                    j['modo'] = modo
                    self.atualizar_visual()
                    return await interaction.response.edit_message(embed=self.embed_base, view=self)

        # 2. Verifica se já existe um oponente NO MESMO MODO
        oponente = next((j for j in self.jogadores if j['modo'] == modo), None)

        if oponente:
            # ======= MATCH ENCONTRADO! =======
            self.jogadores.remove(oponente) 
            self.embed_base.set_image(url=self.banner_match)
            self.atualizar_visual()
            await interaction.response.edit_message(embed=self.embed_base, view=self)

            # Cria o tópico
            try:
                msg_painel = interaction.message
                topico = await msg_painel.create_thread(
                    name=f"🎮 {oponente['user'].name} vs {interaction.user.name}",
                    auto_archive_duration=60 
                )
                
                # ==== MENSAGENS DENTRO DO TÓPICO IGUAL A SUA IMAGEM ====
                embed_aguardando = discord.Embed(
                    title="Aguardando Confirmações",
                    description=f"👑 **Modo:**\n1v1 | {modo}\n\n💎 **Valor da aposta:**\nR$ {self.valor_fila:.2f}\n\n⚡ **Jogadores:**\n{oponente['user'].mention}\n{interaction.user.mention}",
                    color=discord.Color.from_str('#2ecc71') # Verde da borda
                )
                # Coloquei a URL da boneca do round 6 aqui como exemplo
                embed_aguardando.set_thumbnail(url='https://i.imgur.com/SUY8L4o.jpeg') 

                embed_regras = discord.Embed(
                    description="✨ **SEJAM MUITO BEM-VINDOS** ✨\n\n• Regras adicionais podem ser combinadas entre os participantes.\n• Se a regra combinada não existir no regulamento oficial da organização, é obrigatório tirar print do acordo antes do início da partida.",
                    color=discord.Color.from_str('#3498db') # Azulzinho da borda
                )

                # Manda as duas embeds e os botões de confirmar no tópico
                await topico.send(
                    content=f"Chamando jogadores: {oponente['user'].mention} {interaction.user.mention}",
                    embeds=[embed_aguardando, embed_regras],
                    view=ThreadConfirmacaoView()
                )

            except Exception as e:
                print(f"Erro ao criar tópico: {e}")
                await interaction.followup.send("⚠️ Partida confirmada, mas o bot não tem permissão de 'Criar Tópicos' neste canal!", ephemeral=True)
                
        else:
            # ======= ENTRA NA FILA =======
            self.jogadores.append({"user": interaction.user, "modo": modo})
            self.atualizar_visual()
            await interaction.response.edit_message(embed=self.embed_base, view=self)

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
                return await interaction.response.edit_message(embed=self.embed_base, view=self)
        
        await interaction.response.send_message("❌ Você não está em nenhuma fila!", ephemeral=True)


# ==========================================
# CLASSE DO MODAL (AGORA ACEITA QUALQUER NOME)
# ==========================================
class FilaModal(discord.ui.Modal, title='Criar Fila de X1'):
    # Alterei o label para indicar que pode qualquer nome
    nome = discord.ui.TextInput(label='Nome da fila (Ex: Mobile, 4v4, etc)', style=discord.TextStyle.short, required=True)
    valor = discord.ui.TextInput(label='Valor da aposta (Máximo R$ 100)', style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global quantidade_de_filas_ativas

        if quantidade_de_filas_ativas >= 15:
            return await interaction.response.send_message('⚠️ Limite de 15 filas ativas atingido!', ephemeral=True)

        # Pegamos o nome digitado como a pessoa escreveu (sem a trava de segurança)
        nome_digitado = self.nome.value.strip()

        try:
            valor_num = float(self.valor.value.replace(',', '.'))
        except ValueError:
            return await interaction.response.send_message('❌ Valor inválido!', ephemeral=True)

        quantidade_de_filas_ativas += 1

        embed = discord.Embed(
            title=f"1v1 | SPACE APOSTAS {valor_num:g}K",
            description=f"👑 **Modo**\n1v1 {nome_digitado.upper()}\n\n💎 **Valor**\nR$ {valor_num:.2f}\n\n⚡ **Jogadores**\nNenhum jogador na fila",
            color=discord.Color.from_str('#2b2d31')
        )
        embed.set_image(url='https://i.imgur.com/SUY8L4o.jpeg')

        view = FilaView(embed_base=embed, nome_fila=nome_digitado, valor_fila=valor_num)
        await interaction.response.send_message(embed=embed, view=view)


# ==========================================
# EVENTOS, COMANDOS E LOGIN
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ Bot online como {bot.user}')
    await bot.tree.sync()

@bot.tree.command(name="criar_filas", description="Abre o painel de criar fila")
async def criar_filas(interaction: discord.Interaction):
    await interaction.response.send_modal(FilaModal())

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


# --- SEGURANÇA E INICIALIZAÇÃO DA RAILWAY ---
meu_token = os.environ.get('TOKEN')

if not meu_token:
    print("❌ ERRO: Token não encontrado na Railway!")
else:
    bot.run(meu_token)
    
