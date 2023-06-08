from .quotedb import QuoteDB

async def setup(bot):
    bot.add_cog(QuoteDB(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
