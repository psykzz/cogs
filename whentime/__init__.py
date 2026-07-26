__red_end_user_data_statement__ = (
    "This cog stores guild settings, message IDs, and bot reply IDs to keep "
    "timestamp replies synchronized after edits. "
    "It does not persistently store personal user data."
)


async def setup(bot):
    from .cog import WhenCog

    await bot.add_cog(WhenCog(bot))
