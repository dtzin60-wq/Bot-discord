from discord.ext import commands

class Pix(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def pix(self, ctx):
        await ctx.send("💰 Chave PIX: 000.000.000-00")

async def setup(bot):
    await bot.add_cog(Pix(bot))
