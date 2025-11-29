from .game_embed import GameEmbed


async def setup(bot):
    await bot.add_cog(GameEmbed(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
