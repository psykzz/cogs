from .auth import AlbionAuth


async def setup(bot):
    await bot.add_cog(AlbionAuth(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
