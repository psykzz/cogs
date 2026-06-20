from .access import Access

__red_end_user_data_statement__ = (
    "This cog stores user IDs and role IDs for per-channel permission overrides."
)


async def setup(bot):
    await bot.add_cog(Access(bot))
