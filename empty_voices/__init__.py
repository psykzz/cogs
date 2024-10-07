from .api import EmptyVoices

async def setup(bot):
    await bot.add_cog(EmptyVoices(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
