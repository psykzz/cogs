import discord
from redbot.core import Config, commands

IDENTIFIER = 1672261474290237490

default_guild = {
    "watching": {},
}


class RoleReacts(commands.Cog):
    "Adds roles to people who react to a message"

    def __init__(self, bot):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(**default_guild)

    @commands.hybrid_command()
    @commands.has_permissions(manage_roles=True)
    async def add_react(
        self,
        ctx,
        channel: discord.TextChannel,
        message_id: str,
        react: discord.Emoji,
        role: discord.Role,
    ):
        """Setup a Reaction role for a specific message

        Parameters
        ----------
        channel : discord.TextChannel
            The channel containing the message
        message_id : str
            The ID of the message to watch
        react : discord.Emoji
            The emoji reaction to watch for
        role : discord.Role
            The role to assign when users react
        """
        await ctx.defer(ephemeral=True)

        guild_config = self.config.guild(ctx.guild)
        watching = await guild_config.watching()
        react_id = str(react.id)

        if message_id in watching and react_id in watching[message_id]:
            await ctx.send("Already monitoring that message / reaction.", ephemeral=True)
            return

        message = await channel.fetch_message(message_id)
        if not message:
            await ctx.send("That message doesn't exist anymore.", ephemeral=True)
            return

        watching.setdefault(message_id, {})

        watching[message_id][react.id] = role.id

        await message.add_reaction(react)
        await guild_config.watching.set(watching)
        await ctx.send("Reaction setup.", ephemeral=True)

    @commands.hybrid_command()
    @commands.has_permissions(manage_roles=True)
    async def remove_react(
        self, ctx, channel: discord.TextChannel, message_id: str, react: discord.Emoji
    ):
        """Removes a Reaction role for a specific message

        Parameters
        ----------
        channel : discord.TextChannel
            The channel containing the message
        message_id : str
            The ID of the message
        react : discord.Emoji
            The emoji reaction to stop watching
        """
        await ctx.defer(ephemeral=True)

        guild_config = self.config.guild(ctx.guild)
        watching = await guild_config.watching()
        react_id = str(react.id)

        message = await channel.fetch_message(message_id)
        if not message:
            await ctx.send("That message doesn't exist anymore.", ephemeral=True)
            return
        if message_id not in watching or react_id not in watching[message_id]:
            await ctx.send("Not monitoring that message, nothing to do.", ephemeral=True)
            return

        del watching[message_id][str(react.id)]
        if len(watching[message_id].keys()) == 0:
            del watching[message_id]

        await guild_config.watching.set(watching)
        await message.remove_reaction(react, ctx.me)
        await ctx.send("Reaction removed.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        guild_config = self.config.guild(guild)
        watching = await guild_config.watching()

        message_id = str(payload.message_id)
        if message_id not in watching:
            return

        reaction_id = str(payload.emoji.id)
        role_id = watching[message_id][reaction_id]
        role = guild.get_role(role_id)
        await payload.member.add_roles(role)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        guild_config = self.config.guild(guild)
        watching = await guild_config.watching()

        message_id = str(payload.message_id)
        if message_id not in watching:
            return

        reaction_id = str(payload.emoji.id)
        role_id = watching[message_id][reaction_id]
        role = guild.get_role(role_id)
        # on_raw_reaction_remove doesn't populate payload.member
        await guild.get_member(payload.user_id).remove_roles(role)
