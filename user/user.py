import base64
import discord
from redbot.core import commands


class User(commands.Cog):
    """Manage bot user settings"""

    def __init__(self, bot):
        self.bot = bot

    async def _edit_nickname(
        self,
        ctx: commands.Context,
        nickname: str | None
    ) -> None:
        """Helper to edit the bot's nickname in a guild with error handling.

        Args:
            ctx: The command context
            nickname: The new nickname, or None to reset
        """
        try:
            await ctx.guild.me.edit(nick=nickname)
            if nickname:
                await ctx.send(f"✅ Nickname changed to: {nickname}")
            else:
                await ctx.send("✅ Nickname reset to default.")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change my nickname.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to change nickname: {e}")

    async def _validate_image_attachment(
        self,
        ctx: commands.Context
    ) -> bytes | None:
        """Validate that the first message attachment is an image and return its bytes.

        Args:
            ctx: The command context

        Returns:
            Image bytes if valid, None otherwise (with error message sent)
        """
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach an image to use as the new avatar.")
            return None

        attachment = ctx.message.attachments[0]

        # Check if the attachment is an image
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            await ctx.send("❌ The attachment must be an image file.")
            return None

        try:
            image_data = await attachment.read()
            return image_data
        except Exception as e:
            await ctx.send(f"❌ Failed to read attachment: {e}")
            return None

    async def _update_guild_profile(
        self,
        guild_id: int,
        avatar_bytes: bytes | None = None,
        banner_bytes: bytes | None = None,
        nick: str | None = None,
        bio: str | None = None
    ) -> None:
        """Perform raw HTTP PATCH to update bot's per-guild profile.

        Args:
            guild_id: The guild ID to update profile for
            avatar_bytes: Optional avatar image bytes
            banner_bytes: Optional banner image bytes
            nick: Optional nickname
            bio: Optional bio

        Raises:
            discord.Forbidden: If lacking permissions
            discord.HTTPException: On other HTTP errors
        """
        payload = {}

        if avatar_bytes is not None:
            avatar_b64 = base64.b64encode(avatar_bytes).decode('ascii')
            payload['avatar'] = f'data:image/png;base64,{avatar_b64}'

        if banner_bytes is not None:
            banner_b64 = base64.b64encode(banner_bytes).decode('ascii')
            payload['banner'] = f'data:image/png;base64,{banner_b64}'

        if nick is not None:
            payload['nick'] = nick

        if bio is not None:
            payload['bio'] = bio

        route = discord.http.Route('PATCH', f'/guilds/{guild_id}/members/@me')
        await self.bot.http.request(route, json=payload)

    @commands.guild_only()
    @commands.group(name="user", invoke_without_command=True)
    async def _user(self, ctx):
        """Manage bot user settings"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @_user.command(name="nick")
    async def _nick(self, ctx, *, nickname: str = None):
        """Change the bot's nickname in this guild

        Use without a nickname to reset to default.
        """
        await self._edit_nickname(ctx, nickname)

    @commands.guild_only()
    @_user.command(name="avatar")
    async def _avatar(self, ctx):
        """Change the bot's avatar in this guild using an attached image

        Note: This changes the bot's avatar only in this server.
        """
        # Validate and get image bytes
        image_data = await self._validate_image_attachment(ctx)
        if image_data is None:
            return

        try:
            # Update the bot's per-guild profile with new avatar
            await self._update_guild_profile(ctx.guild.id, avatar_bytes=image_data)
            await ctx.send("✅ Avatar changed successfully in this server!")
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to change my avatar in this server.")
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to change avatar: {e}")
        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")
