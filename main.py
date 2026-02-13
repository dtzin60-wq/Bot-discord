import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import yt_dlp
import asyncio
import os
import shutil

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")

filas = {}

# MUDANÇA CRUCIAL: 'default_search': 'scsearch' (Busca no SoundCloud)
# Isso evita o bloqueio "Sign in" do YouTube.
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'scsearch', 
    'quiet': True,
    'no_warnings': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# Opções para garantir que o áudio não trave
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ==============================================================================
#                         SISTEMA DE MÚSICA
# ==============================================================================

async def tocar_proxima(guild, voice_client, text_channel):
    guild_id = guild.id
    if not filas.get(guild_id):
        return

    # Pega a música da fila
    proxima_musica = filas[guild_id].pop(0)
    busca = proxima_musica['busca']
    
    # Função para extrair o link do áudio
    def extrair_url():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                # Tenta buscar. Se for link do YT, ele usa YT. Se for nome, usa SoundCloud.
                info = ydl.extract_info(busca, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info['url'], info['title']
            except Exception as e:
                raise e

    try:
        url_audio, titulo = extrair_url()
        
        # Verificação silenciosa do FFmpeg (Obrigatório, mas automático no Railway)
        if not shutil.which("ffmpeg"):
            await text_channel.send("⚠️ **Erro de Configuração:** O FFmpeg não foi detectado. Verifique o arquivo `nixpacks.toml`.")
            return

        source = discord.FFmpegPCMAudio(url_audio, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            # Chama a próxima música quando acabar
            fut = asyncio.run_coroutine_threadsafe(next_song(guild, voice_client, text_channel), bot.loop)
            try: fut.result()
            except: pass

        voice_client.play(source, after=after_playing)
        await text_channel.send(f"🎶 **Tocando Agora:** {titulo}")

    except Exception as e:
        print(f"Erro: {e}")
        await text_channel.send(f"❌ Não consegui tocar essa música. Tente outro nome.\nErro: `{e}`")
        await next_song(guild, voice_client, text_channel)

async def next_song(guild, voice_client, text_channel):
    await tocar_proxima(guild, voice_client, text_channel)

# ==============================================================================
#                         MODAL E BOTÕES
# ==============================================================================

class ModalMusica(Modal, title="Player de Música"):
    nome_musica = TextInput(label="Nome da Música", placeholder="Digite o nome da música...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre na call primeiro!", ephemeral=True)
        
        await interaction.response.defer()
        
        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        # Conecta na call
        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        # Adiciona na fila
        if interaction.guild.id not in filas: 
            filas[interaction.guild.id] = []

        filas[interaction.guild.id].append({'busca': self.nome_musica.value})

        # Se não estiver tocando, toca agora
        if not voice_client.is_playing():
            await tocar_proxima(interaction.guild, voice_client, interaction.channel)
        else:
            await interaction.followup.send(f"📝 **Adicionado à fila:** {self.nome_musica.value}")

class ViewBotaoMusica(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Escolher Música", style=discord.ButtonStyle.primary, emoji="🎵")
    async def abrir_modal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ModalMusica())

# ==============================================================================
#                         COMANDOS
# ==============================================================================

@bot.command(name="mplay")
async def cmd_mplay(ctx):
    await ctx.send("Clique para pedir música:", view=ViewBotaoMusica())

@bot.command(name="skip")
async def cmd_skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Pulada!")

@bot.command(name="leave")
async def cmd_leave(ctx):
    if ctx.voice_client:
        filas[ctx.guild.id] = []
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Saí.")

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
                    
