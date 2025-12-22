from .server_status import ServerStatus


async def setup(bot):
    await bot.add_cog(ServerStatus(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
