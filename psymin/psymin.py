import discord
from redbot.core import commands


class Psymin(commands.Cog):
    """Bot owner administration commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="psymin", invoke_without_command=True)
    @commands.is_owner()
    async def psymin(self, ctx):
        """Bot owner administration commands"""
        await ctx.send_help(ctx.command)

    @psymin.command(name="permissions")
    @commands.is_owner()
    async def permissions(self, ctx):
        """List effective permissions granted by roles for each server.

        Shows the bot's permissions in all servers where it is present.
        Only available to bot owners.
        """
        guilds = self.bot.guilds

        if not guilds:
            await ctx.send("The bot is not in any servers.")
            return

        # Create embed for each guild
        for guild in guilds:
            # Get the bot's member object in this guild
            bot_member = guild.get_member(self.bot.user.id)

            if not bot_member:
                continue

            # Get effective permissions
            permissions = bot_member.guild_permissions

            # Create embed
            embed = discord.Embed(
                title=f"Permissions in {guild.name}",
                color=discord.Color.blue(),
                description=f"Bot permissions in **{guild.name}** (ID: {guild.id})"
            )

            # Add guild info
            embed.add_field(
                name="Guild Info",
                value=f"Members: {guild.member_count}\nOwner: {guild.owner.mention if guild.owner else 'Unknown'}",
                inline=False
            )

            # Get roles the bot has
            bot_roles = [role.name for role in bot_member.roles if role.name != "@everyone"]
            if bot_roles:
                embed.add_field(
                    name=f"Roles ({len(bot_roles)})",
                    value=", ".join(bot_roles),
                    inline=False
                )

            # List all permissions
            granted_perms = []
            denied_perms = []

            # Get all permission attributes
            for perm, value in permissions:
                perm_name = perm.replace('_', ' ').title()
                if value:
                    granted_perms.append(perm_name)
                else:
                    denied_perms.append(perm_name)

            # Add granted permissions
            if granted_perms:
                # Split into chunks if too long
                perm_chunks = self._chunk_list(granted_perms, 20)
                for i, chunk in enumerate(perm_chunks):
                    field_name = "Granted Permissions" if i == 0 else f"Granted Permissions (cont. {i+1})"
                    embed.add_field(
                        name=field_name,
                        value="✅ " + "\n✅ ".join(chunk),
                        inline=True
                    )

            # Add denied permissions (only first 10 to keep embed reasonable)
            if denied_perms:
                denied_preview = denied_perms[:10]
                remaining = len(denied_perms) - len(denied_preview)
                field_value = "❌ " + "\n❌ ".join(denied_preview)
                if remaining > 0:
                    field_value += f"\n*...and {remaining} more*"

                embed.add_field(
                    name="Denied Permissions",
                    value=field_value,
                    inline=True
                )

            # Set footer
            embed.set_footer(text=f"Bot ID: {self.bot.user.id}")

            # Send the embed
            await ctx.send(embed=embed)

    def _chunk_list(self, lst, chunk_size):
        """Split a list into chunks of specified size."""
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
