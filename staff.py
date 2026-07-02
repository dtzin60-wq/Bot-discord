from discord.ext import commands
import discord

class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        if not ctx.author.guild_permissions.ban_members:
            return await ctx.send("❌ Sem permissão.")

        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member} foi banido.")

    @commands.command()
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        if not ctx.author.guild_permissions.kick_members:
            return await ctx.send("❌ Sem permissão.")

        await member.kick(reason=reason)
        await ctx.send(f"👢 {member} foi expulso.")

async def setup(bot):
    await bot.add_cog(Staff(bot))
