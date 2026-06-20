from .quotedb import QuoteDB

__red_end_user_data_statement__ = (
    "This cog stores user IDs and usernames as part of saved quotes."
)


async def setup(bot):
    await bot.add_cog(QuoteDB(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
