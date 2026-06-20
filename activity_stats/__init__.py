from .activity_stats import ActivityStats

__red_end_user_data_statement__ = (
    "This cog stores user IDs and associated activity/game statistics."
)


async def setup(bot):
    await bot.add_cog(ActivityStats(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
