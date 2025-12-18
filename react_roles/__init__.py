from .react_roles import RoleReacts


async def setup(bot):
    await bot.add_cog(RoleReacts(bot))


__version__ = "1.0.0"
__author__ = "psykzz"
