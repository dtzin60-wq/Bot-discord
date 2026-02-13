import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import yt_dlp
import asyncio
import os
import imageio_ffmpeg

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")
filas = {}

# Detecta automaticamente o executável do FFmpeg instalado pela biblioteca
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# Opções para evitar o bloqueio do YouTube usando SoundCloud como busca padrão
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'scsearch', # Busca no SoundCloud para evitar erro de "Sign in"
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

async def tocar_proxima(guild, vc, channel):
    if not filas.get(guild.id): return
    
    musica = filas[guild.id].pop(0)
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(musica['busca'], download=False)
            if 'entries' in info: info = info['entries'][0]
            url = info['url']
            titulo = info['title']

        source = discord.FFmpegPCMAudio(url, executable=FFMPEG_EXE, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            asyncio.run_coroutine_threadsafe(tocar_proxima(guild, vc, channel), bot.loop)

        vc.play(source, after=after_playing)
        await channel.send(f"🎶 **Tocando Agora:** {titulo}")

    except Exception as e:
        await channel.send(f"❌ Erro: `{str(e)[:100]}`")
        await tocar_proxima(guild, vc, channel)

# ==============================================================================
#                         INTERFACE E COMANDOS
# ==============================================================================

class ModalMusica(Modal, title="Player de Música"):
    musica = TextInput(label="Música", placeholder="Digite o nome da música...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre na call!", ephemeral=True)
        
        await interaction.response.defer()
        vc = interaction.guild.voice_client
        if not vc: vc = await interaction.user.voice.channel.connect()
        
        if interaction.guild.id not in filas: filas[interaction.guild.id] = []
        filas[interaction.guild.id].append({'busca': self.musica.value})

        if not vc.is_playing():
            await tocar_proxima(interaction.guild, vc, interaction.channel)
        else:
            await interaction.followup.send(f"📝 **Fila:** {self.musica.value}")

@bot.command(name="mplay")
async def cmd_mplay(ctx):
    view = View(); btn = Button(label="Escolher Música", style=discord.ButtonStyle.primary, emoji="🎵")
    async def cb(it): await it.response.send_modal(ModalMusica())
    btn.callback = cb; view.add_item(btn)
    await ctx.send("Clique abaixo para escolher a música:", view=view)

@bot.command(name="skip")
async def cmd_skip(ctx):
    if ctx.voice_client: ctx.voice_client.stop()
    await ctx.send("⏭️ Pulada.")

@bot.command(name="leave")
async def cmd_leave(ctx):
    if ctx.voice_client:
        filas[ctx.guild.id] = []
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Saí da call.")
    else:
        await ctx.send("❌ Não estou conectado.")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot Online: {bot.user}")

if __name__ == "__main__":
    bot.run(TOKEN)
        
