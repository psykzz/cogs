from .war_timers import WarTimers


def setup(bot):
    bot.add_cog(WarTimers(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
