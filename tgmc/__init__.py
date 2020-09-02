from .api import TGMC

def setup(bot):
    bot.add_cog(TGMC(bot))

__version__ = "1.0.0"
__author__ = "psykzz"