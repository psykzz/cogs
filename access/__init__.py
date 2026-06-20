from .access import Access

__red_end_user_data_statement__ = (
    "This cog does not persistently store any end user data. "
    "Permission overrides are applied directly via the Discord API and "
    "are not stored in the bot's own data store."
)


async def setup(bot):
    await bot.add_cog(Access(bot))
