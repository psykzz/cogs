from .assign_roles import AssignRoles


async def setup(bot):
    await bot.add_cog(AssignRoles(bot))
