from .ava import AlbionAva


async def setup(bot):
    await bot.add_cog(AlbionAva(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
