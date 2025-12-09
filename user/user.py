import base64
import discord
from redbot.core import commands


# Valid image types for avatar/banner uploads
VALID_IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif")

# Maximum size for avatar uploads (8 MiB)
MAX_AVATAR_SIZE = 8 * 1024 * 1024


class User(commands.Cog):
    """Manage bot user settings"""

    def __init__(self, bot):
        self.bot = bot

    def _format_profile_http_error(
        self,
        e: discord.HTTPException,
        field: str | None = None
    ) -> str:
        """Format HTTP error messages for profile updates.

        Args:
            e: The HTTPException that occurred
            field: Optional field name (e.g., 'avatar', 'nickname')

        Returns:
            Formatted error message string
        """
        error_text = str(e)
        # Strip common prefixes for cleaner messages
        if error_text.startswith("Invalid Form Body"):
            error_text = error_text.replace("Invalid Form Body\n", "")

        if field:
            return f"❌ Failed to update {field}: {error_text}"
        return f"❌ Failed to update profile: {error_text}"

    def _detect_image_format(self, image_bytes: bytes) -> str:
        """Detect image format from bytes.

        Args:
            image_bytes: The image data

        Returns:
            MIME type string (e.g., 'image/png', 'image/jpeg')
        """
        # Check magic bytes for common image formats
        if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        elif image_bytes.startswith(b'\xFF\xD8\xFF'):
            return 'image/jpeg'
        elif image_bytes.startswith(b'GIF87a') or image_bytes.startswith(b'GIF89a'):
            return 'image/gif'
        elif image_bytes.startswith(b'RIFF') and image_bytes[8:12] == b'WEBP':
            return 'image/webp'
        else:
            # Default to PNG if unknown
            return 'image/png'

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
            await ctx.send(self._format_profile_http_error(e, "nickname"))

    async def _validate_image_attachment(
        self,
        ctx: commands.Context,
        *,
        max_size: int = MAX_AVATAR_SIZE
    ) -> bytes | None:
        """Validate that the first message attachment is an image and return its bytes.

        Args:
            ctx: The command context
            max_size: Maximum allowed file size in bytes (default: 8 MiB)

        Returns:
            Image bytes if valid, None otherwise (with error message sent)
        """
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach an image to use as the new avatar.")
            return None

        attachment = ctx.message.attachments[0]

        # Validate file size
        if attachment.size is not None and attachment.size > max_size:
            size_mb = max_size / (1024 * 1024)
            await ctx.send(f"❌ The provided attachment is too large. Max size is {size_mb:.0f}MB.")
            return None

        # Validate content type
        if not attachment.content_type:
            await ctx.send("❌ Unable to determine attachment type. Please ensure the file is an image.")
            return None

        if attachment.content_type not in VALID_IMAGE_TYPES:
            await ctx.send(
                f"❌ Invalid attachment type `{attachment.content_type}`; "
                "must be PNG, JPEG, or GIF."
            )
            return None

        try:
            image_data = await attachment.read()
            return image_data
        except discord.HTTPException as e:
            await ctx.send(f"❌ Failed to read attachment: {e}")
            return None
        except discord.NotFound:
            await ctx.send("❌ Attachment not found.")
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
            avatar_bytes: Optional avatar image bytes, or empty bytes to reset
            banner_bytes: Optional banner image bytes, or empty bytes to reset
            nick: Optional nickname
            bio: Optional bio

        Raises:
            discord.Forbidden: If lacking permissions
            discord.HTTPException: On other HTTP errors
        """
        payload = {}

        if avatar_bytes is not None:
            # Empty bytes signals a reset (use None in payload)
            if avatar_bytes == b'':
                payload['avatar'] = None
            else:
                avatar_format = self._detect_image_format(avatar_bytes)
                avatar_b64 = base64.b64encode(avatar_bytes).decode('ascii')
                payload['avatar'] = f'data:{avatar_format};base64,{avatar_b64}'

        if banner_bytes is not None:
            # Empty bytes signals a reset (use None in payload)
            if banner_bytes == b'':
                payload['banner'] = None
            else:
                banner_format = self._detect_image_format(banner_bytes)
                banner_b64 = base64.b64encode(banner_bytes).decode('ascii')
                payload['banner'] = f'data:{banner_format};base64,{banner_b64}'

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
    async def _avatar(self, ctx, action: str = None):
        """Change the bot's avatar in this guild using an attached image

        Use 'reset' to remove the per-guild avatar and use the global avatar.
        Note: This changes the bot's avatar only in this server.
        """
        # Handle reset action
        if action and action.lower() == "reset":
            try:
                # Send None to reset avatar to global default
                await self._update_guild_profile(ctx.guild.id, avatar_bytes=b'')
                await ctx.send("✅ Avatar reset to global default in this server!")
                return
            except discord.Forbidden:
                await ctx.send("❌ I don't have permission to change my avatar in this server.")
                return
            except discord.HTTPException as e:
                await ctx.send(self._format_profile_http_error(e, "avatar"))
                return
            except Exception as e:
                await ctx.send(f"❌ An error occurred: {e}")
                return

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
            await ctx.send(self._format_profile_http_error(e, "avatar"))
        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")
