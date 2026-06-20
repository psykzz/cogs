from .api import EmptyVoices

__red_end_user_data_statement__ = (
    "This cog does not persistently store any end user data. "
    "Only voice channel IDs are tracked, not individual user IDs."
)


async def setup(bot):
    await bot.add_cog(EmptyVoices(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
