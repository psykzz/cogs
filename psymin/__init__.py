from .psymin import Psymin


async def setup(bot):
    await bot.add_cog(Psymin(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
