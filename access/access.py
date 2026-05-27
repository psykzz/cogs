import asyncio
import discord
from typing import Union

from redbot.core import commands, checks
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions


class Access(commands.Cog):
    """Simplify access and permissions to channels for roles or members"""

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @checks.mod_or_permissions(manage_roles=True)
    @commands.hybrid_group(name="access")
    async def access(self, ctx):
        """Manage channel access permissions for roles and members"""

    @access.command(name="give")
    async def access_give(
        self,
        ctx,
        target: Union[discord.Role, discord.Member],
        channel: discord.TextChannel = None
    ):
        """Give access to a channel for a role or member

        This grants view_channel, send_messages, and read_message_history permissions.
        The permissions are adjusted based on what the @everyone role has.

        Parameters
        ----------
        target : Union[discord.Role, discord.Member]
            The role or member to give access to
        channel : discord.TextChannel, optional
            The channel to grant access to (default: current channel)
        """
        await ctx.defer(ephemeral=True)

        # Default to current channel if not specified
        if channel is None:
            channel = ctx.channel

        # Get the @everyone role permissions for this channel
        everyone_role = ctx.guild.default_role
        everyone_perms = channel.overwrites_for(everyone_role)

        # Get current permissions for the target
        current_perms = channel.overwrites_for(target)

        # Build the plan of changes
        changes = []
        new_perms = discord.PermissionOverwrite()

        # Copy existing permissions
        for perm, value in current_perms:
            setattr(new_perms, perm, value)

        # Check each permission and plan changes based on @everyone
        # View Channel
        if everyone_perms.view_channel is False:
            if current_perms.view_channel is not True:
                new_perms.view_channel = True
                changes.append("✅ **View Channel**: Allow")
        else:
            if current_perms.view_channel is False:
                new_perms.view_channel = None
                changes.append("✅ **View Channel**: Reset to default (allowed by @everyone)")

        # Send Messages
        if everyone_perms.send_messages is False:
            if current_perms.send_messages is not True:
                new_perms.send_messages = True
                changes.append("✅ **Send Messages**: Allow")
        else:
            if current_perms.send_messages is False:
                new_perms.send_messages = None
                changes.append("✅ **Send Messages**: Reset to default (allowed by @everyone)")

        # Read Message History
        if everyone_perms.read_message_history is False:
            if current_perms.read_message_history is not True:
                new_perms.read_message_history = True
                changes.append("✅ **Read Message History**: Allow")
        else:
            if current_perms.read_message_history is False:
                new_perms.read_message_history = None
                changes.append("✅ **Read Message History**: Reset to default (allowed by @everyone)")

        # Check if there are any changes
        if not changes:
            await ctx.send(
                f"ℹ️ {target.mention} already has access to {channel.mention}.",
                ephemeral=True
            )
            return

        # Build confirmation message
        embed = discord.Embed(
            title="🔓 Grant Channel Access",
            description=f"Planning to give access to {target.mention} in {channel.mention}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Planned Changes",
            value="\n".join(changes),
            inline=False
        )
        embed.add_field(
            name="@everyone Permissions",
            value=(
                f"View Channel: {self._perm_status(everyone_perms.view_channel)}\n"
                f"Send Messages: {self._perm_status(everyone_perms.send_messages)}\n"
                f"Read Message History: {self._perm_status(everyone_perms.read_message_history)}"
            ),
            inline=False
        )
        embed.set_footer(text="React with ✅ to confirm or ❌ to cancel")

        msg = await ctx.send(embed=embed, ephemeral=True)

        # Add reactions and wait for confirmation
        emojis = ["✅", "❌"]
        start_adding_reactions(msg, emojis)
        pred = ReactionPredicate.with_emojis(emojis, msg, ctx.author)

        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60.0)
        except asyncio.TimeoutError:
            await msg.edit(content="⏱️ Request timed out.", embed=None)
            return

        if pred.result == 0:  # ✅ confirmed
            try:
                await channel.set_permissions(target, overwrite=new_perms)
                await msg.edit(
                    content=f"✅ Successfully granted access to {target.mention} in {channel.mention}!",
                    embed=None
                )
            except discord.Forbidden:
                await msg.edit(
                    content="❌ I don't have permission to modify channel permissions.",
                    embed=None
                )
            except discord.HTTPException as e:
                await msg.edit(
                    content=f"❌ An error occurred: {e}",
                    embed=None
                )
        else:  # ❌ cancelled
            await msg.edit(content="❌ Cancelled.", embed=None)

    @access.command(name="remove")
    async def access_remove(
        self,
        ctx,
        target: Union[discord.Role, discord.Member],
        channel: discord.TextChannel = None
    ):
        """Remove access to a channel for a role or member

        This denies view_channel, send_messages, and read_message_history permissions.
        The permissions are adjusted based on what the @everyone role has.

        Parameters
        ----------
        target : Union[discord.Role, discord.Member]
            The role or member to remove access from
        channel : discord.TextChannel, optional
            The channel to remove access from (default: current channel)
        """
        await ctx.defer(ephemeral=True)

        # Default to current channel if not specified
        if channel is None:
            channel = ctx.channel

        # Get the @everyone role permissions for this channel
        everyone_role = ctx.guild.default_role
        everyone_perms = channel.overwrites_for(everyone_role)

        # Get current permissions for the target
        current_perms = channel.overwrites_for(target)

        # Build the plan of changes
        changes = []
        new_perms = discord.PermissionOverwrite()

        # Copy existing permissions
        for perm, value in current_perms:
            setattr(new_perms, perm, value)

        # Check each permission and plan changes based on @everyone
        # View Channel
        if everyone_perms.view_channel is not False:
            if current_perms.view_channel is not False:
                new_perms.view_channel = False
                changes.append("❌ **View Channel**: Deny")
        else:
            if current_perms.view_channel is True:
                new_perms.view_channel = None
                changes.append("❌ **View Channel**: Reset to default (denied by @everyone)")

        # Send Messages
        if everyone_perms.send_messages is not False:
            if current_perms.send_messages is not False:
                new_perms.send_messages = False
                changes.append("❌ **Send Messages**: Deny")
        else:
            if current_perms.send_messages is True:
                new_perms.send_messages = None
                changes.append("❌ **Send Messages**: Reset to default (denied by @everyone)")

        # Read Message History
        if everyone_perms.read_message_history is not False:
            if current_perms.read_message_history is not False:
                new_perms.read_message_history = False
                changes.append("❌ **Read Message History**: Deny")
        else:
            if current_perms.read_message_history is True:
                new_perms.read_message_history = None
                changes.append("❌ **Read Message History**: Reset to default (denied by @everyone)")

        # Check if there are any changes
        if not changes:
            await ctx.send(
                f"ℹ️ {target.mention} already has no access to {channel.mention}.",
                ephemeral=True
            )
            return

        # Build confirmation message
        embed = discord.Embed(
            title="🔒 Remove Channel Access",
            description=f"Planning to remove access for {target.mention} in {channel.mention}",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Planned Changes",
            value="\n".join(changes),
            inline=False
        )
        embed.add_field(
            name="@everyone Permissions",
            value=(
                f"View Channel: {self._perm_status(everyone_perms.view_channel)}\n"
                f"Send Messages: {self._perm_status(everyone_perms.send_messages)}\n"
                f"Read Message History: {self._perm_status(everyone_perms.read_message_history)}"
            ),
            inline=False
        )
        embed.set_footer(text="React with ✅ to confirm or ❌ to cancel")

        msg = await ctx.send(embed=embed, ephemeral=True)

        # Add reactions and wait for confirmation
        emojis = ["✅", "❌"]
        start_adding_reactions(msg, emojis)
        pred = ReactionPredicate.with_emojis(emojis, msg, ctx.author)

        try:
            await ctx.bot.wait_for("reaction_add", check=pred, timeout=60.0)
        except asyncio.TimeoutError:
            await msg.edit(content="⏱️ Request timed out.", embed=None)
            return

        if pred.result == 0:  # ✅ confirmed
            try:
                await channel.set_permissions(target, overwrite=new_perms)
                await msg.edit(
                    content=f"✅ Successfully removed access for {target.mention} in {channel.mention}!",
                    embed=None
                )
            except discord.Forbidden:
                await msg.edit(
                    content="❌ I don't have permission to modify channel permissions.",
                    embed=None
                )
            except discord.HTTPException as e:
                await msg.edit(
                    content=f"❌ An error occurred: {e}",
                    embed=None
                )
        else:  # ❌ cancelled
            await msg.edit(content="❌ Cancelled.", embed=None)

    def _perm_status(self, perm_value):
        """Convert permission value to human-readable status"""
        if perm_value is True:
            return "✅ Allowed"
        elif perm_value is False:
            return "❌ Denied"
        else:
            return "➖ Not Set (Inherit)"
