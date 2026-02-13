import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=".", intents=intents)
tree = bot.tree

queues = {}

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
}

FFMPEG_OPTIONS = {
    "options": "-vn"
}


class MusicModal(discord.ui.Modal, title="Qual música você quer escolher"):
    musica = discord.ui.TextInput(
        label="Música:",
        placeholder="Digite o nome da música ou link do YouTube",
        required=True,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        query = self.musica.value
        guild = interaction.guild

        if not interaction.user.voice:
            await interaction.response.send_message(
                "Você precisa estar em uma call de voz!", ephemeral=True
            )
            return

        voice_channel = interaction.user.voice.channel
        vc = guild.voice_client

        if vc is None:
            vc = await voice_channel.connect()
        elif vc.channel != voice_channel:
            await vc.move_to(voice_channel)

        if guild.id not in queues:
            queues[guild.id] = []

        queues[guild.id].append(query)

        await interaction.response.send_message(
            f"🎶 Adicionado à fila: {query}"
        )

        if not vc.is_playing():
            await play_next(guild)


async def play_next(guild):
    vc = guild.voice_client

    if guild.id not in queues or len(queues[guild.id]) == 0:
        return

    query = queues[guild.id].pop(0)

    loop = asyncio.get_event_loop()

    def extract():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)["entries"][0]
            return info["url"], info["title"]

    url, title = await loop.run_in_executor(None, extract)

    source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)

    def after_playing(error):
        fut = asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)
        try:
            fut.result()
        except:
            pass

    vc.play(source, after=after_playing)


@tree.command(name="mplay", description="Tocar música na call")
async def mplay(interaction: discord.Interaction):
    modal = MusicModal()
    await interaction.response.send_modal(modal)


@tree.command(name="leave", description="Fazer o bot sair da call")
async def leave(interaction: discord.Interaction):
    vc = interaction.guild.voice_client

    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Saí da call!")
    else:
        await interaction.response.send_message(
            "Não estou em nenhuma call!", ephemeral=True
        )


@bot.command(name="skip")
async def skip(ctx):
    vc = ctx.guild.voice_client

    if not vc or not vc.is_playing():
        await ctx.send("Não tem música tocando!")
        return

    vc.stop()
    await ctx.send("⏭️ Pulando para a próxima música da fila!")


@bot.event
async def on_ready():
    await tree.sync()
    print(f"Bot online como {bot.user}")


bot.run(TOKEN)
