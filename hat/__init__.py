from .hat import Hat


async def setup(bot):
    await bot.add_cog(Hat(bot))


__version__ = "1.0.0"
__author__ = "PsyKzz"
