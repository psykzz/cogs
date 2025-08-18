import discord

from redbot.core import commands  # Changed from discord.ext
from redbot.core import checks, Config
from redbot.core.bot import Red

class AssignRoles(commands.Cog):
    """Authorise one role to give another role"""
    __author__ = "#s#8059"

    BIN = ":put_litter_in_its_place: "
    DONE = ":white_check_mark: "
    ERROR = ":x: Error: "

    ASSIGN_ADDED = DONE + "Successfully assigned the `{}` role."
    ASSIGN_REMOVED = BIN + "Successfully removed the `{}` role."
    ASSIGN_NO_EVERYONE = ERROR + "You cannot give someone the Everyone role!"
    AUTHORISE_EXISTS = ERROR + "The role you want to authorised is already authorised to give this role."
    AUTHORISE_EMPTY = ERROR + "`{}` is not authorised to be assigned by any other roles."
    AUTHORISE_MISMATCH = ERROR + "`{}` is not currently authorised to give the `{}` role."
    AUTHORISE_NO_EVERYONE = ERROR + "You cannot authorise everyone to give a role!"
    AUTHORISE_NO_HIGHER = ERROR + "You cannot authorise a role that is not below your highest role!"
    AUTHORISE_NOT_DEFAULT = ERROR + "The Everyone role cannot be given out!"
    AUTHORISE_SUCCESS = DONE + "Successfully authorised `{}` to assign the `{}` role."
    CLEAN_SUCCESS = DONE + "Successfully cleaned the role authorisations."
    DEAUTHORISE_SUCCESS = BIN + "Successfully de-authorised `{}` to assign the `{}` role."
    LIST_DESC_NORMAL = "The roles below can be given by the mentioned roles."
    LIST_DESC_EMPTY = "No roles are authorised to give other roles."

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, identifier=73600, force_registration=True)
        self.config.register_guild(roles={})

    # Events

    # Commands
    @commands.guild_only()
    @commands.group(name="assign", invoke_without_command=True)
    async def _assign(self, ctx, role: discord.Role, user: discord.Member = None):
        """Assign a role to a user"""
        author = ctx.author
        if user is None:
            user = author
        role_id = str(role.id)
        server_dict = await self.config.guild(ctx.guild).roles()

        if role.is_default():
            notice = self.ASSIGN_NO_EVERYONE
        elif role_id not in server_dict:  # No role authorised to give this role.
            notice = self.AUTHORISE_EMPTY.format(role.name)
        # Check if any of the author's roles is authorised to grant the role.
        elif not any(str(r.id) in server_dict[role_id] for r in author.roles):
            notice = self.AUTHORISE_MISMATCH.format(author.mention, role.name)
        else:  # Role "transaction" is valid.
            if role in user.roles:
                await user.remove_roles(role)
                notice = self.ASSIGN_REMOVED.format(role.name)
            else:
                await user.add_roles(role)
                notice = self.ASSIGN_ADDED.format(role.name)
        await ctx.send(notice)

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @_assign.command(aliases=["authorize"])
    async def authorise(self, ctx, authorised_role: discord.Role, giveable_role: discord.Role):
        """Authorise one role to give another role

        Allows all members with the role `authorised_role` to give the role `giveable_role` to everyone.
        In order to authorise, your highest role must be strictly above the `authorised_role` (except for the owner).
        """
        gld = ctx.guild
        server_dict = await self.config.guild(gld).roles()

        author_max_role = max(r for r in ctx.author.roles)
        authorised_id = str(authorised_role.id)
        giveable_id = str(giveable_role.id)

        if authorised_role.is_default():  # Role to be authorised should not be @everyone.
            notice = self.AUTHORISE_NO_EVERYONE
        elif giveable_role.is_default():  # Same goes for role to be given.
            notice = self.AUTHORISE_NOT_DEFAULT
        elif authorised_role >= author_max_role and ctx.author != gld.owner:  # Hierarchical role order check.
            notice = self.AUTHORISE_NO_HIGHER
        # Check if "pair" already exists.
        elif giveable_id in server_dict and authorised_id in server_dict[giveable_id]:
            notice = self.AUTHORISE_EXISTS
        else:  # Role authorisation is valid.
            server_dict.setdefault(giveable_id, []).append(authorised_id)
            await self.config.guild(gld).roles.set(server_dict)
            notice = self.AUTHORISE_SUCCESS.format(authorised_role.name, giveable_role.name)
        await ctx.send(notice)

    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    @_assign.command(aliases=["deauthorize"])
    async def deauthorise(self, ctx, authorised_role: discord.Role, giveable_role: discord.Role):
        """Deauthorise one role to give another role

        In order to deauthorise, your highest role must be strictly above the `authorised_role` (except for the owner).
        """
        gld = ctx.guild
        server_dict = await self.config.guild(gld).roles()

        author_max_role = max(r for r in ctx.author.roles)
        authorised_id = str(authorised_role.id)
        giveable_id = str(giveable_role.id)

        if authorised_role.is_default():  # Role to be de-authorised should not be @everyone.
            notice = self.AUTHORISE_NO_EVERYONE
        elif giveable_role.is_default():  # Same goes for role to be given.
            notice = self.AUTHORISE_NOT_DEFAULT
        elif authorised_role >= author_max_role and ctx.author != gld.owner:  # Hierarchical role order check.
            notice = self.AUTHORISE_NO_HIGHER
        elif giveable_id not in server_dict:
            notice = self.AUTHORISE_EMPTY.format(giveable_role.name)
        elif authorised_id not in server_dict[giveable_id]:
            notice = self.AUTHORISE_MISMATCH.format(authorised_role.name, giveable_role.name)
        else:  # Role de-authorisation is valid.
            server_dict[giveable_id].remove(authorised_id)
            await self.config.guild(gld).roles.set(server_dict)
            notice = self.DEAUTHORISE_SUCCESS.format(authorised_role.name, giveable_role.name)
        await ctx.send(notice)

    @commands.guild_only()
    @checks.mod_or_permissions(manage_guild=True)
    @_assign.command()
    async def list(self, ctx):
        """Send an embed showing which roles can be given by other roles"""
        gld = ctx.guild
        server_dict = await self.config.guild(gld).roles()
        embed = discord.Embed(colour=0x00D8FF, title="Assign authorisations")

        for role_id, auth_list in server_dict.items():
            role = discord.utils.get(gld.roles, id=int(role_id))
            if role is not None:
                auth_roles = (discord.utils.get(gld.roles, id=int(i)) for i in auth_list)
                mentions_str = ", ".join(r.mention for r in auth_roles if r is not None)
                if len(mentions_str) > 0:  # Prevent empty fields from being sent.
                    embed.add_field(name=role.name, value=mentions_str)
        embed.description = self.LIST_DESC_EMPTY if len(embed.fields) == 0 else self.LIST_DESC_NORMAL
        await ctx.send(embed=embed)

    # Utilities

    # Config
