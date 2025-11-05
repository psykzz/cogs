from .user import User


async def setup(bot):
    await bot.add_cog(User(bot))


__version__ = "1.0.0"
__author__ = "PsyKzz"
