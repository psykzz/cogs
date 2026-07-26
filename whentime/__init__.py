__red_end_user_data_statement__ = (
    "This cog stores guild settings, message IDs, bot reply IDs, and "
    "guild-specific user preferences to keep timestamp replies synchronized "
    "after edits and honor reply opt-outs."
)


async def setup(bot):
    from .cog import WhenCog

    await bot.add_cog(WhenCog(bot))
