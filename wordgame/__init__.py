from .wordgame import WordGame

__red_end_user_data_statement__ = (
    "This cog stores user IDs and guess history for active word game sessions."
)


async def setup(bot):
    await bot.add_cog(WordGame(bot))
