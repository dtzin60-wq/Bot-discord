import discord
from discord.ext import commands
import os

# Configurando permissões (Intents)
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True

# Criando o bot com o prefixo "."
bot = commands.Bot(command_prefix='.', intents=intents)

# Contador de filas (zera se a Railway reiniciar)
quantidade_de_filas_ativas = 0

# ==========================================
# CLASSE DOS BOTÕES (VIEW)
# ==========================================
class FilaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Gel Normal', style=discord.ButtonStyle.secondary, custom_id='btn_gel_normal')
    async def btn_normal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer() 

    @discord.ui.button(label='Gel Infinito', style=discord.ButtonStyle.secondary, custom_id='btn_gel_infinito')
    async def btn_infinito(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label='Sair da fila', style=discord.ButtonStyle.danger, custom_id='btn_sair_fila')
    async def btn_sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

# ==========================================
# CLASSE DO MODAL
# ==========================================
class FilaModal(discord.ui.Modal, title='Criar Fila de X1'):
    nome = discord.ui.TextInput(
        label='Tipo (mobile, misto, emulador, Full soco)',
        style=discord.TextStyle.short,
        placeholder='Ex: mobile',
        required=True
    )
    
    valor = discord.ui.TextInput(
        label='Valor da aposta (Máximo R$ 100)',
        style=discord.TextStyle.short,
        placeholder='Ex: 15',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        global quantidade_de_filas_ativas

        if quantidade_de_filas_ativas >= 15:
            return await interaction.response.send_message('⚠️ O limite máximo de 15 filas ativas já foi atingido!', ephemeral=True)

        nome_digitado = self.nome.value.strip().lower()
        nomes_permitidos = ['mobile', 'misto', 'emulador', 'full soco']

        if nome_digitado not in nomes_permitidos:
            return await interaction.response.send_message('❌ Nome inválido! Digite apenas: mobile, misto, emulador ou full soco.', ephemeral=True)

        try:
            valor_num = float(self.valor.value.replace(',', '.'))
        except ValueError:
            return await interaction.response.send_message('❌ Valor inválido! O valor deve ser um número.', ephemeral=True)

        if valor_num <= 0 or valor_num > 100:
            return await interaction.response.send_message('❌ Valor inválido! O valor deve ser entre 1 e 100 reais.', ephemeral=True)

        quantidade_de_filas_ativas += 1

        embed = discord.Embed(
            title=f"1v1 | SPACE APOSTAS {valor_num:g}K",
            description=f"👑 **Modo**\n1v1 {nome_digitado.upper()}\n\n💎 **Valor**\nR$ {valor_num:.2f}\n\n⚡ **Jogadores**\nNenhum jogador na fila",
            color=discord.Color.from_str('#2b2d31')
        )
        embed.set_image(url='https://i.imgur.com/SUY8L4o.jpeg')

        view = FilaView()
        await interaction.response.send_message(embed=embed, view=view)

# ==========================================
# EVENTOS E COMANDOS
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ Bot online como {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} comando(s) de barra sincronizado(s).')
    except Exception as e:
        print(f'❌ Erro ao sincronizar comandos: {e}')

@bot.tree.command(name="criar_filas", description="Abre o painel para criar uma nova fila de aposta")
async def criar_filas(interaction: discord.Interaction):
    await interaction.response.send_modal(FilaModal())

@bot.command(name="p")
async def perfil(ctx, membro: discord.Member = None):
    target_user = membro or ctx.author

    if ctx.message.reference:
        try:
            msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            target_user = msg.author
        except:
            pass

    stats = {'vitorias': 0, 'derrotas': 2, 'consecutivas': 0, 'total': 2, 'coins': 0}

    embed = discord.Embed(
        description=f"🎮 **Estatísticas**\n\nVitórias: {stats['vitorias']}\nDerrotas: {stats['derrotas']}\nConsecutivas: {stats['consecutivas']}\nTotal de Partidas: {stats['total']}\n\n💎 **Coins**\n\nCoins: {stats['coins']}",
        color=discord.Color.from_str('#2b2d31')
    )
    embed.set_author(name=target_user.name, icon_url=target_user.display_avatar.url)
    embed.set_thumbnail(url=target_user.display_avatar.url)

    await ctx.reply(embed=embed)

# ==========================================
# VERIFICAÇÃO DE SEGURANÇA E LOGIN
# ==========================================
meu_token = os.environ.get('TOKEN')

if not meu_token:
    print("❌ ERRO FATAL: O Token não foi encontrado!")
    print("👉 Vá na aba 'Variables' da Railway, crie uma variável chamada TOKEN e cole o token do bot lá.")
else:
    bot.run(meu_token)
        
