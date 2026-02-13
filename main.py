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

# --- AQUI ESTÁ A CORREÇÃO ANTI-BLOQUEIO ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'extract_flat': True,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'no_warnings': True,
    # Fingir ser um Android para burlar o "Sign in to confirm"
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios']
        }
    }
}
# ------------------------------------------

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ==============================================================================
#                         SISTEMA DE MÚSICA
# ==============================================================================

async def enviar_erro(channel, erro):
    if "sign in" in str(erro).lower():
        await channel.send("⚠️ **O YouTube bloqueou temporariamente o IP.** Tente novamente em alguns segundos ou escolha outra música.")
    elif "ffmpeg" in str(erro).lower():
        await channel.send("⚠️ **ERRO CRÍTICO:** FFmpeg não instalado. Verifique o nixpacks.toml.")
    else:
        await channel.send(f"❌ Erro: `{str(erro)[:100]}...`")

def tocar_proxima(guild, voice_client, text_channel):
    guild_id = guild.id
    if not filas.get(guild_id):
        return

    proxima_musica = filas[guild_id].pop(0)
    busca = proxima_musica['busca']
    
    def extrair_source():
        # Usa as novas opções com bypass de cliente
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(busca, download=False)
                if 'entries' in info: info = info['entries'][0]
                return info['url'], info['title']
            except Exception as e:
                raise e

    try:
        url_audio, titulo_real = extrair_source()
        
        if not shutil.which("ffmpeg"):
            raise Exception("Executável 'ffmpeg' não encontrado.")

        source = discord.FFmpegPCMAudio(url_audio, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            if error:
                print(f"Erro Player: {error}")
            asyncio.run_coroutine_threadsafe(next_song_check(guild, voice_client, text_channel), bot.loop)

        voice_client.play(source, after=after_playing)
        asyncio.run_coroutine_threadsafe(text_channel.send(f"🎶 **Tocando Agora:** {titulo_real}"), bot.loop)

    except Exception as e:
        print(f"Erro: {e}")
        asyncio.run_coroutine_threadsafe(enviar_erro(text_channel, e), bot.loop)
        # Tenta a próxima se der erro na atual
        tocar_proxima(guild, voice_client, text_channel)

async def next_song_check(guild, voice_client, text_channel):
    tocar_proxima(guild, voice_client, text_channel)

# ==============================================================================
#                         MODAL E INTERFACE
# ==============================================================================

class ModalMusica(Modal, title="Player de Música"):
    nome_musica = TextInput(label="Nome da Música", placeholder="Digite o nome ou link...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Entre em um canal de voz!", ephemeral=True)
        
        await interaction.response.defer()
        
        guild_id = interaction.guild.id
        channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        if guild_id not in filas: filas[guild_id] = []

        filas[guild_id].append({'busca': self.nome_musica.value, 'user': interaction.user.mention})

        if not voice_client.is_playing():
            tocar_proxima(interaction.guild, voice_client, interaction.channel)
        else:
            pos = len(filas[guild_id])
            await interaction.followup.send(f"📝 **Na fila ({pos}º):** {self.nome_musica.value}")

class ViewBotaoMusica(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Escolher Música", style=discord.ButtonStyle.primary, emoji="🎵")
    async def abrir_modal(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(ModalMusica())

# ==============================================================================
#                         COMANDOS
# ==============================================================================

@bot.command(name="mplay")
async def cmd_mplay(ctx):
    view = ViewBotaoMusica()
    await ctx.send("Clique abaixo para escolher a música:", view=view)

@bot.command(name="skip")
async def cmd_skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ **Pulei!**")
    else:
        await ctx.send("❌ Nada tocando.")

@bot.command(name="leave")
async def cmd_leave(ctx):
    if ctx.voice_client:
        filas[ctx.guild.id] = []
        await ctx.voice_client.disconnect()
        await ctx.send("👋 **Saí da call.**")
    else:
        await ctx.send("❌ Não estou conectado.")

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")

if __name__ == "__main__":
    if TOKEN: bot.run(TOKEN)
    
