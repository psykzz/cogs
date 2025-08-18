from .server_status import ServerStatus

def setup(bot):
    bot.add_cog(ServerStatus(bot))

__version__ = "1.0.0"
__author__ = "psykzz"
