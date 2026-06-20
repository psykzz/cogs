from .api import EmptyVoices

__red_end_user_data_statement__ = (
    "This cog stores user IDs temporarily while they occupy a managed voice channel."
)


async def setup(bot):
    await bot.add_cog(EmptyVoices(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
