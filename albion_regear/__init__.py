from .regear import AlbionRegear


async def setup(bot):
    await bot.add_cog(AlbionRegear(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
