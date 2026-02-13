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

# Pega o FFmpeg instalado pela biblioteca (garante que existe)
FFMPEG_EXECUTAVEL = imageio_ffmpeg.get_ffmpeg_exe()
print(f"✅ FFmpeg detectado em: {FFMPEG_EXECUTAVEL}")

# --- CONFIGURAÇÃO YOUTUBE ANTI-BLOQUEIO ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch', # VOLTOU PARA YOUTUBE
    'quiet': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'no_warnings': True,
    'logtostderr': False,
    # Truque para evitar o erro "Sign in to confirm":
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios'], # Finge ser celular
            'skip': ['hls', 'dash'], 
        }
    }
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
        # Busca no YouTube
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(busca, download=False)
            except Exception as e:
                # Se falhar a busca normal, tenta direto sem extração plana
                print(f"Erro busca simples: {e}")
                raise e

            if 'entries' in info:
                info = info['entries'][0]
            
            url = info['url']
            titulo = info['title']

        # TOCA A MÚSICA (Usando o FFmpeg garantido)
        source = discord.FFmpegPCMAudio(url, executable=FFMPEG_EXECUTAVEL, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error: print(f"Erro Player: {error}")
            asyncio.run_coroutine_threadsafe(next_song(guild, voice_client, text_channel), bot.loop)

        voice_client.play(source, after=after_playing)
        await text_channel.send(f"🎶 **Tocando (YouTube):** {titulo}")

    except Exception as e:
        erro_msg = str(e)
        if "Sign in" in erro_msg:
            await text_channel.send("⚠️ **Bloqueio do YouTube:** O IP do Railway foi bloqueado. Tente usar um link do SoundCloud ou espere algumas horas.")
        else:
            await text_channel.send(f"❌ Erro ao tocar: `{erro_msg}`")
        
        await next_song(guild, voice_client, text_channel)

async def next_song(guild, voice_client, text_channel):
    await tocar_proxima(guild, voice_client, text_channel)

# ==============================================================================
#                         MODAL E BOTÕES
# ==============================================================================

class ModalMusica(Modal, title="YouTube Player"):
    nome_musica = TextInput(label="Nome ou Link do YouTube", placeholder="Digite aqui...", required=True)

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

        if interaction.guild.id not in filas: filas[interaction.guild.id] = []
        filas[interaction.guild.id].append({'busca': self.nome_musica.value})

        if not voice_client.is_playing():
            await tocar_proxima(interaction.guild, voice_client, interaction.channel)
        else:
            await interaction.followup.send(f"📝 **Na fila:** {self.nome_musica.value}")

class ViewBotaoMusica(View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Pedir Música (YouTube)", style=discord.ButtonStyle.danger, emoji="▶️")
    async def abrir_modal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ModalMusica())

# ==============================================================================
#                         COMANDOS
# ==============================================================================

@bot.command(name="mplay")
async def cmd_mplay(ctx):
    await ctx.send("Clique para buscar no YouTube:", view=ViewBotaoMusica())

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
        await ctx.send("👋 Saí da call e limpei a fila.")
    else:
        await ctx.send("❌ Não estou conectado.")

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
        
