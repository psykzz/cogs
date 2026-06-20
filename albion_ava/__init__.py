from .ava import AlbionAva

__red_end_user_data_statement__ = (
    "This cog does not persistently store any end user data."
)


async def setup(bot):
    await bot.add_cog(AlbionAva(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
