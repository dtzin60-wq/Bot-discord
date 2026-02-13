import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import yt_dlp
import asyncio
import os

# ==============================================================================
#                         CONFIGURAÇÕES
# ==============================================================================
TOKEN = os.getenv("TOKEN")

filas = {}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch',
    'quiet': True,
    'extract_flat': True
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# Define o prefixo como PONTO (.)
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ==============================================================================
#                         SISTEMA DE MÚSICA
# ==============================================================================

def tocar_proxima(guild, voice_client):
    guild_id = guild.id
    if not filas.get(guild_id):
        return

    proxima_musica = filas[guild_id].pop(0)
    busca = proxima_musica['busca']
    
    def extrair_source():
        opts = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'default_search': 'ytsearch'}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(busca, download=False)
            if 'entries' in info: info = info['entries'][0]
            return info['url'], info['title']

    try:
        url_audio, titulo_real = extrair_source()
        source = discord.FFmpegPCMAudio(url_audio, **FFMPEG_OPTIONS)
        
        def after_playing(error):
            asyncio.run_coroutine_threadsafe(next_song_check(guild, voice_client), bot.loop)

        voice_client.play(source, after=after_playing)
    except Exception as e:
        print(f"Erro: {e}")
        tocar_proxima(guild, voice_client)

async def next_song_check(guild, voice_client):
    tocar_proxima(guild, voice_client)

# ==============================================================================
#                         MODAL E BOTÕES
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
            tocar_proxima(interaction.guild, voice_client)
            await interaction.followup.send(f"▶️ **Tocando:** {self.nome_musica.value}")
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
#                         COMANDOS COM PONTO (.)
# ==============================================================================

@bot.command(name="mplay")
async def cmd_mplay(ctx):
    # Envia o botão para abrir o modal
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
            
