import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True 
intents.members = True

bot = commands.Bot(command_prefix='.', intents=intents)

quantidade_de_filas_ativas = 0

# ==========================================
# CLASSE DOS BOTÕES (COM LÓGICA DE MATCHMAKING)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self, embed_base, nome_fila, valor_fila):
        super().__init__(timeout=None)
        self.jogadores = [] # Lista para guardar quem está na fila
        self.embed_base = embed_base # Guarda o visual base do painel
        self.nome_fila = nome_fila
        self.valor_fila = valor_fila
        self.banner_padrao = 'https://i.imgur.com/SUY8L4o.jpeg' # Imagem normal da fila
        self.banner_match = 'https://i.imgur.com/SUY8L4o.jpeg' # AQUI VOCÊ PODE COLOCAR OUTRA IMAGEM PRA QUANDO FECHAR PARTIDA

    def atualizar_visual(self):
        # Refaz a descrição do painel com os jogadores atuais
        desc = f"👑 **Modo**\n1v1 {self.nome_fila.upper()}\n\n💎 **Valor**\nR$ {self.valor_fila:.2f}\n\n⚡ **Jogadores**\n"
        
        if len(self.jogadores) == 0:
            desc += "Nenhum jogador na fila"
            self.embed_base.set_image(url=self.banner_padrao) # Volta pro banner padrão
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
                    # Se ele clicou no outro modo, a gente atualiza a escolha dele
                    j['modo'] = modo
                    self.atualizar_visual()
                    return await interaction.response.edit_message(embed=self.embed_base, view=self)

        # 2. Verifica se já existe um oponente aguardando NO MESMO MODO
        oponente = next((j for j in self.jogadores if j['modo'] == modo), None)

        if oponente:
            # ======= MATCH ENCONTRADO! =======
            # Remove o oponente da fila (já que achou partida)
            self.jogadores.remove(oponente) 
            
            # Atualiza a imagem do banner temporariamente (opcional)
            self.embed_base.set_image(url=self.banner_match)
            self.atualizar_visual()
            await interaction.response.edit_message(embed=self.embed_base, view=self)

            # Cria o tópico (Thread) na própria mensagem do painel
            try:
                msg_painel = interaction.message
                topico = await msg_painel.create_thread(
                    name=f"🎮 {oponente['user'].name} vs {interaction.user.name}",
                    auto_archive_duration=60 # Tópico fecha sozinho após 1 hora de inatividade
                )
                
                # Manda mensagem marcando os dois no tópico
                await topico.send(f"✅ **PARTIDA CONFIRMADA!**\n{oponente['user'].mention} 🆚 {interaction.user.mention}\n\n**Modo:** {modo}\n**Valor:** R$ {self.valor_fila:.2f}\n\nMandem print do PIX e boa sorte!")
            except Exception as e:
                print(f"Erro ao criar tópico: {e}")
                await interaction.followup.send("⚠️ Partida confirmada, mas o bot não tem permissão de 'Criar Tópicos' neste canal!", ephemeral=True)
                
        else:
            # ======= ENTRA NA FILA =======
            self.jogadores.append({"user": interaction.user, "modo": modo})
            self.atualizar_visual()
            await interaction.response.edit_message(embed=self.embed_base, view=self)

    # BOTÃO GELO NORMAL
    @discord.ui.button(label='Gelo Normal', style=discord.ButtonStyle.secondary, custom_id='btn_gel_normal')
    async def btn_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar_clique(interaction, "Gelo Normal")

    # BOTÃO GELO INFINITO
    @discord.ui.button(label='Gelo Infinito', style=discord.ButtonStyle.secondary, custom_id='btn_gel_infinito')
    async def btn_infinito(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.processar_clique(interaction, "Gelo Infinito")

    # BOTÃO SAIR DA FILA
    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger, custom_id='btn_sair_fila')
    async def btn_sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        for j in self.jogadores:
            if j['user'].id == interaction.user.id:
                self.jogadores.remove(j)
                self.atualizar_visual()
                return await interaction.response.edit_message(embed=self.embed_base, view=self)
        
        await interaction.response.send_message("❌ Você não está em nenhuma fila!", ephemeral=True)


# ==========================================
# CLASSE DO MODAL
# ==========================================
class FilaModal(discord.ui.Modal, title='Criar Fila de X1'):
    nome = discord.ui.TextInput(label='Tipo (mobile, misto, emulador, Full soco)', style=discord.TextStyle.short, required=True)
    valor = discord.ui.TextInput(label='Valor da aposta (Máximo R$ 100)', style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        global quantidade_de_filas_ativas

        if quantidade_de_filas_ativas >= 15:
            return await interaction.response.send_message('⚠️ Limite de 15 filas ativas atingido!', ephemeral=True)

        nome_digitado = self.nome.value.strip().lower()
        if nome_digitado not in ['mobile', 'misto', 'emulador', 'full soco']:
            return await interaction.response.send_message('❌ Nome inválido!', ephemeral=True)

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

        # Passamos o embed e as infos da fila para a View agora
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
    
