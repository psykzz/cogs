from .user import User


def setup(bot):
    bot.add_cog(User(bot))


__version__ = "1.0.0"
__author__ = "PsyKzz"
