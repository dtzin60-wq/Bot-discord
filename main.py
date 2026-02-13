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

# Configurações do Youtube (DL) e FFmpeg
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'default_search': 'ytsearch', # Pesquisa automática no YT
    'quiet': True
}

# Configurações para não travar o áudio
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==============================================================================
#                         MODAL DE MÚSICA
# ==============================================================================
class ModalMusica(discord.ui.Modal, title="Player de Música"):
    # O campo de texto onde você digita o nome
    nome_musica = discord.ui.TextInput(
        label="Qual música você quer escolher?",
        placeholder="Digite o nome da música ou link...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Verifica se o usuário está em um canal de voz
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Você precisa entrar em um canal de voz primeiro!", ephemeral=True)
        
        # Avisa que está processando (para não dar erro de tempo limite)
        await interaction.response.defer()

        try:
            channel = interaction.user.voice.channel
            voice_client = interaction.guild.voice_client

            # 2. Conecta ou move o bot para o canal
            if voice_client and voice_client.is_connected():
                if voice_client.channel.id != channel.id:
                    await voice_client.move_to(channel)
            else:
                voice_client = await channel.connect()

            # 3. Para a música atual se estiver tocando
            if voice_client.is_playing():
                voice_client.stop()

            # 4. Busca a música
            msg_busca = await interaction.followup.send(f"🔎 Procurando por: **{self.nome_musica.value}**...", ephemeral=True)
            
            loop = asyncio.get_event_loop()
            # Roda o download em uma thread separada para não travar o bot
            data = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YDL_OPTIONS).extract_info(self.nome_musica.value, download=False))

            # Se for uma pesquisa, pega o primeiro resultado
            if 'entries' in data:
                data = data['entries'][0]
            
            url = data['url']
            titulo = data['title']

            # 5. Toca a música
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            voice_client.play(source)

            await interaction.followup.send(f"🎵 Tocando agora: **{titulo}**")

        except Exception as e:
            print(e)
            await interaction.followup.send("❌ Ocorreu um erro ao tentar tocar a música. Verifique se o link é válido.", ephemeral=True)

# ==============================================================================
#                         COMANDO SLASH
# ==============================================================================
@bot.tree.command(name="mplay", description="Escolha uma música para tocar")
async def slash_mplay(interaction: discord.Interaction):
    await interaction.response.send_modal(ModalMusica())

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot Online: {bot.user.name}")
    print("Sistema de música pronto!")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
                
