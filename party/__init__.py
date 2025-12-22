from .party import Party

__red_end_user_data_statement__ = (
    "This cog stores user IDs for party participation tracking."
)


async def setup(bot):
    await bot.add_cog(Party(bot))
