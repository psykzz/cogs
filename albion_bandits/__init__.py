from .bandits import AlbionBandits


async def setup(bot):
    await bot.add_cog(AlbionBandits(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
