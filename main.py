import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import yt_dlp
import asyncio
import os
import imageio_ffmpeg # A biblioteca que salva vidas

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")

filas = {}

# Pega o caminho REAL do executável FFmpeg baixado pelo Python
FFMPEG_EXECUTAVEL = imageio_ffmpeg.get_ffmpeg_exe()
print(f"✅ FFmpeg detectado em: {FFMPEG_EXECUTAVEL}")

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'scsearch', # SoundCloud (Sem bloqueio)
    'quiet': True,
    'no_warnings': True,
}

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

    proxima_musica = filas[guild_id].pop(0)
    busca = proxima_musica['busca']
    
    try:
        # Busca o link
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(busca, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            url = info['url']
            titulo = info['title']

        # TOCA A MÚSICA USANDO O CAMINHO CORRETO DO FFMPEG
        source = discord.FFmpegPCMAudio(url, executable=FFMPEG_EXECUTAVEL, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Erro interno no player: {error}")
            asyncio.run_coroutine_threadsafe(next_song(guild, voice_client, text_channel), bot.loop)

        voice_client.play(source, after=after_playing)
        await text_channel.send(f"🎶 **Tocando:** {titulo}")

    except Exception as e:
        print(f"Erro ao tocar: {e}") # Mostra no log do Railway
        await text_channel.send(f"❌ Erro: `{str(e)}`")
        await next_song(guild, voice_client, text_channel)

async def next_song(guild, voice_client, text_channel):
    await tocar_proxima(guild, voice_client, text_channel)

# ==============================================================================
#                         MODAL E BOTÕES
# ==============================================================================

class ModalMusica(Modal, title="Player de Música"):
    nome_musica = TextInput(label="Nome da Música", placeholder="Digite o nome...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre na call primeiro!", ephemeral=True)
        
        await interaction.response.defer()
        
        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        if interaction.guild.id not in filas: filas[interaction.guild.id] = []
        filas[interaction.guild.id].append({'busca': self.nome_musica.value})

        if not voice_client.is_playing():
            await tocar_proxima(interaction.guild, voice_client, interaction.channel)
        else:
            await interaction.followup.send(f"📝 **Na fila:** {self.nome_musica.value}")

class ViewBotaoMusica(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Escolher Música", style=discord.ButtonStyle.primary, emoji="🎵")
    async def abrir_modal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ModalMusica())

@bot.command(name="mplay")
async def cmd_mplay(ctx):
    await ctx.send("Clique para pedir:", view=ViewBotaoMusica())

@bot.command(name="skip")
async def cmd_skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Pulei!")

@bot.command(name="leave")
async def cmd_leave(ctx):
    if ctx.voice_client:
        filas[ctx.guild.id] = []
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Saí.")
    else:
        await ctx.send("❌ Não estou conectado.")

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
                          
