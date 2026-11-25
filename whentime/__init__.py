__red_end_user_data_statement__ = (
    "This cog stores guild settings, source message IDs, bot reply IDs, manual "
    "timestamp overrides, and guild-specific user opt-out preferences."
)


async def setup(bot):
    from .cog import WhenCog

    await bot.add_cog(WhenCog(bot))
