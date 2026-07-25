__red_end_user_data_statement__ = (
    "This cog stores guild settings for enabled channels and timezones. "
    "It does not persistently store personal user data."
)


async def setup(bot):
    from .when_cog import WhenCog

    await bot.add_cog(WhenCog(bot))
