from .api import TGMC

async def setup(bot):
    await bot.add_cog(TGMC(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
