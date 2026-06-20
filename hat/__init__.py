from .hat import Hat

__red_end_user_data_statement__ = (
    "This cog stores user IDs and their hat style preferences."
)


async def setup(bot):
    await bot.add_cog(Hat(bot))


__version__ = "1.0.0"
__author__ = "PsyKzz"
