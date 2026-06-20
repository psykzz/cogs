from .user import User

__red_end_user_data_statement__ = (
    "This cog does not persistently store any end user data."
)


async def setup(bot):
    await bot.add_cog(User(bot))


__version__ = "1.0.0"
__author__ = "PsyKzz"
