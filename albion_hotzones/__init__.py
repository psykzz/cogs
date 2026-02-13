from .hotzones import AlbionHotZones


async def setup(bot):
    await bot.add_cog(AlbionHotZones(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
