from .ideas import Ideas


async def setup(bot):
    await bot.add_cog(Ideas(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
