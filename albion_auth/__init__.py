from .auth import AlbionAuth

__red_end_user_data_statement__ = (
    "This cog stores user IDs mapped to Albion Online character names for "
    "guild authentication and daily verification. Nicknames may be modified "
    "on behalf of users."
)


async def setup(bot):
    await bot.add_cog(AlbionAuth(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
