from .assign_roles import AssignRoles


def setup(bot):
    bot.add_cog(AssignRoles(bot))
