import discord
from discord.ext import commands
import os
import config

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")

# carrega automaticamente todos os módulos (exceto main e config)
for file in os.listdir("./"):
    if file.endswith(".py") and file not in ["main.py", "config.py"]:
        try:
            bot.load_extension(file[:-3])
            print(f"Carregado: {file}")
        except Exception as e:
            print(f"Erro ao carregar {file}: {e}")

bot.run(config.TOKEN)
