from .misc import Misc


async def setup(bot):
    await bot.add_cog(Misc(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
