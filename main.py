import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")

# Dicionário para guardar as filas de cada servidor
# Estrutura: { guild_id: [ {titulo, url_busca, user} ] }
filas = {}

# Opções do YoutubeDL
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'extract_flat': True # Apenas busca o info básico primeiro para não travar
}

# Opções do FFmpeg (Áudio estável)
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

intents = discord.Intents.default()
intents.message_content = True # Necessário para ler o comando .skip
bot = commands.Bot(command_prefix=".", intents=intents) # Prefix ponto para o .skip

# ==============================================================================
#                         LÓGICA DE TOCAR (FILA)
# ==============================================================================

# Função que toca a próxima música da fila
def tocar_proxima(guild, voice_client):
    guild_id = guild.id
    
    # Se não tiver ninguém na fila, para e desconecta (opcional) ou só espera
    if not filas.get(guild_id):
        return

    # Pega a próxima música (item 0)
    proxima_musica = filas[guild_id].pop(0)
    busca = proxima_musica['busca']
    
    # Função interna para extrair o link de áudio real
    def extrair_source():
        ydl_opts_play = {
            'format': 'bestaudio/best',
            'noplaylist': True, 
            'quiet': True,
            'default_search': 'ytsearch'
        }
        with yt_dlp.YoutubeDL(ydl_opts_play) as ydl:
            info = ydl.extract_info(busca, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            return info['url'], info['title']

    try:
        # Extrai o link direto (pode demorar um pouco, mas é seguro)
        url_audio, titulo_real = extrair_source()
        
        source = discord.FFmpegPCMAudio(url_audio, **FFMPEG_OPTIONS)
        
        # Callback: Quando acabar, chama essa função de novo (Recursão)
        def after_playing(error):
            if error:
                print(f"Erro ao tocar: {error}")
            # Chama a próxima
            asyncio.run_coroutine_threadsafe(next_song_check(guild, voice_client), bot.loop)

        voice_client.play(source, after=after_playing)
        
        # Opcional: Avisar no chat que começou a tocar (necessita de um canal salvo)
        print(f"Tocando: {titulo_real}")

    except Exception as e:
        print(f"Erro ao tocar música: {e}")
        # Se der erro, tenta a próxima
        tocar_proxima(guild, voice_client)

async def next_song_check(guild, voice_client):
    tocar_proxima(guild, voice_client)

# ==============================================================================
#                         MODAL DE MÚSICA (/mplay)
# ==============================================================================
class ModalMusica(discord.ui.Modal, title="Player de Música"):
    nome_musica = discord.ui.TextInput(
        label="Qual música você quer escolher?",
        placeholder="Digite o nome da música...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre em um canal de voz primeiro!", ephemeral=True)
        
        await interaction.response.defer() # Evita erro de timeout

        guild_id = interaction.guild.id
        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        # Conecta se não estiver conectado
        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        # Adiciona na fila
        if guild_id not in filas:
            filas[guild_id] = []

        # Adiciona o objeto música na lista
        musica_obj = {
            'busca': self.nome_musica.value,
            'user': interaction.user.mention
        }
        filas[guild_id].append(musica_obj)

        # Se não estiver tocando nada, começa a tocar
        if not voice_client.is_playing():
            tocar_proxima(interaction.guild, voice_client)
            await interaction.followup.send(f"▶️ **Tocando agora:** {self.nome_musica.value}")
        else:
            # Se já estiver tocando, avisa que entrou na fila
            posicao = len(filas[guild_id])
            await interaction.followup.send(f"📝 **Adicionado à fila** (Posição {posicao}): {self.nome_musica.value}")

# ==============================================================================
#                         COMANDOS (SLASH E PREFIX)
# ==============================================================================

# Comando 1: /mplay (Modal)
@bot.tree.command(name="mplay", description="Escolha uma música para tocar")
async def slash_mplay(interaction: discord.Interaction):
    await interaction.response.send_modal(ModalMusica())

# Comando 2: /leave (Sair da call)
@bot.tree.command(name="leave", description="Faz o bot sair do canal de voz")
async def slash_leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        # Limpa a fila
        if interaction.guild.id in filas:
            filas[interaction.guild.id] = []
        
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Saí do canal de voz e limpei a fila.", ephemeral=False)
    else:
        await interaction.response.send_message("❌ Eu não estou conectado em nenhum canal.", ephemeral=True)

# Comando 3: .skip (Pular música)
@bot.command(name="skip")
async def command_skip(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop() # Isso força o 'after' a rodar, que chama 'tocar_proxima'
        await ctx.send("⏭️ **Música pulada!** Tocando a próxima da fila...")
    else:
        await ctx.send("❌ Não há música tocando para pular.")

# ==============================================================================
#                         START
# ==============================================================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot Online: {bot.user.name}")
    print("Sistema de música com fila pronto!")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
        
