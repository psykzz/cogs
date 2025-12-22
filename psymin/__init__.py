from .psymin import Psymin

__red_end_user_data_statement__ = (
    "This cog does not store any user data."
)


async def setup(bot):
    await bot.add_cog(Psymin(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
