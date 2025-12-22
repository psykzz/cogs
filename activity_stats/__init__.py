from .activity_stats import ActivityStats


async def setup(bot):
    await bot.add_cog(ActivityStats(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
