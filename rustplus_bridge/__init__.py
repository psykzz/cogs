from .rustplus_bridge import RustPlusBridge


async def setup(bot):
    await bot.add_cog(RustPlusBridge(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
