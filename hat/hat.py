import asyncio
import io
import logging
from typing import Optional

import discord
from PIL import Image
from redbot.core import Config, checks, commands
from redbot.core.data_manager import bundled_data_path, cog_data_path

log = logging.getLogger("red.cog.hat")

IDENTIFIER = 8472916358274917

# Default hat settings
DEFAULT_SCALE = 0.5
DEFAULT_ROTATION = 0
DEFAULT_X_OFFSET = 0.5  # Center horizontally (0.0 = left, 1.0 = right)
DEFAULT_Y_OFFSET = 0.0  # Top of image (0.0 = top, 1.0 = bottom)

# Limits
MIN_SCALE = 0.1
MAX_SCALE = 2.0
MIN_ROTATION = -180
MAX_ROTATION = 180


class Hat(commands.Cog):
    """Add festive Christmas hats to your avatar!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER)

        default_global = {
            "hats": {},  # hat_name -> {"filename": str, "default": bool}
            "default_hat": None,
        }
        default_user = {
            "selected_hat": None,
            "scale": DEFAULT_SCALE,
            "rotation": DEFAULT_ROTATION,
            "x_offset": DEFAULT_X_OFFSET,
            "y_offset": DEFAULT_Y_OFFSET,
            "saved_settings": {},  # hat_name -> {"scale", "rotation", "x_offset", "y_offset"}
        }
        self.config.register_global(**default_global)
        self.config.register_user(**default_user)

        # Track recent command messages for cleanup
        self._recent_commands = {}

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Delete user data when requested."""
        await self.config.user_from_id(user_id).clear()

    def _get_data_path(self):
        """Get the cog data path for storing hat images."""
        return cog_data_path(self)

    def _get_bundled_path(self):
        """Get the bundled data path for default hats."""
        return bundled_data_path(self)

    async def _get_hat_path(self, hat_name: str) -> Optional[str]:
        """Get the full path to a hat image file."""
        hats = await self.config.hats()
        if hat_name not in hats:
            return None

        hat_data = hats[hat_name]
        filename = hat_data.get("filename")
        if not filename:
            return None

        # Check cog data path first (user uploaded hats)
        data_path = self._get_data_path()
        hat_path = data_path / filename
        if hat_path.exists():
            return str(hat_path)

        # Check bundled data path (default hats)
        bundled_path = self._get_bundled_path()
        hat_path = bundled_path / filename
        if hat_path.exists():
            return str(hat_path)

        return None

    async def _cleanup_previous_commands(self, ctx, user_id: int):
        """Delete previous command messages from this user in this channel."""
        key = (ctx.channel.id, user_id)
        if key in self._recent_commands:
            try:
                old_messages = self._recent_commands[key]
                for msg in old_messages:
                    try:
                        await msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass
            except Exception:
                pass
        self._recent_commands[key] = []

    async def _track_message(self, ctx, message: discord.Message):
        """Track a message for later cleanup."""
        key = (ctx.channel.id, ctx.author.id)
        if key not in self._recent_commands:
            self._recent_commands[key] = []
        self._recent_commands[key].append(message)

        # Also track the command message itself
        try:
            self._recent_commands[key].append(ctx.message)
        except Exception:
            pass

    async def _apply_hat_to_avatar(
        self,
        avatar_bytes: bytes,
        hat_path: str,
        scale: float,
        rotation: float,
        x_offset: float,
        y_offset: float,
    ) -> bytes:
        """Apply a hat overlay to an avatar image."""

        def process_image():
            # Open the avatar and convert to RGBA
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar_width, avatar_height = avatar.size

            # Open the hat and convert to RGBA
            hat = Image.open(hat_path).convert("RGBA")

            # Scale the hat relative to avatar width
            hat_width = int(avatar_width * scale)
            hat_height = int(hat.height * (hat_width / hat.width))
            hat = hat.resize((hat_width, hat_height), Image.Resampling.LANCZOS)

            # Rotate the hat
            if rotation != 0:
                hat = hat.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

            # Calculate position
            # x_offset: 0.0 = left edge, 0.5 = center, 1.0 = right edge
            # y_offset: 0.0 = top edge, 0.5 = center, 1.0 = bottom edge
            x = int((avatar_width - hat.width) * x_offset)
            y = int((avatar_height - hat.height) * y_offset)

            # Create a new image with the avatar and hat
            result = Image.new("RGBA", (avatar_width, avatar_height), (0, 0, 0, 0))
            result.paste(avatar, (0, 0))
            result.paste(hat, (x, y), hat)

            # Convert to PNG bytes
            output = io.BytesIO()
            result.save(output, format="PNG")
            output.seek(0)
            return output.getvalue()

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, process_image)

    async def _get_avatar_bytes(self, user: discord.User) -> Optional[bytes]:
        """Get avatar bytes for a user."""
        avatar = user.display_avatar
        try:
            return await avatar.read()
        except Exception:
            return None

    @commands.group(name="hat", invoke_without_command=True)
    async def _hat(self, ctx):
        """Add a festive Christmas hat to your avatar!

        Use `.hat preview` to see how it looks, and `.hat apply` to save.
        """
        await ctx.send_help(ctx.command)

    @_hat.command(name="list")
    async def _hat_list(self, ctx):
        """List all available hats."""
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        hats = await self.config.hats()
        default_hat = await self.config.default_hat()

        if not hats:
            msg = await ctx.send("❌ No hats available. Ask an admin to upload some!")
            await self._track_message(ctx, msg)
            return

        embed = discord.Embed(
            title="🎅 Available Hats",
            description="Use `.hat select <name>` to choose a hat!",
            color=discord.Color.red(),
        )

        hat_list = []
        for name, data in hats.items():
            is_default = "⭐ " if name == default_hat else ""
            hat_list.append(f"{is_default}**{name}**")

        embed.add_field(name="Hats", value="\n".join(hat_list) or "None", inline=False)
        embed.set_footer(text="⭐ = Default hat")

        msg = await ctx.send(embed=embed)
        await self._track_message(ctx, msg)

    @_hat.command(name="select")
    async def _hat_select(self, ctx, hat_name: str):
        """Select a hat to use.

        Example: `.hat select santa`
        """
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        hats = await self.config.hats()
        hat_name_lower = hat_name.lower()

        # Find hat (case insensitive)
        found_hat = None
        for name in hats:
            if name.lower() == hat_name_lower:
                found_hat = name
                break

        if not found_hat:
            available = ", ".join(hats.keys()) if hats else "None available"
            msg = await ctx.send(f"❌ Hat `{hat_name}` not found. Available hats: {available}")
            await self._track_message(ctx, msg)
            return

        # Load saved settings for this hat if they exist
        saved_settings = await self.config.user(ctx.author).saved_settings()
        if found_hat in saved_settings:
            settings = saved_settings[found_hat]
            await self.config.user(ctx.author).scale.set(settings.get("scale", DEFAULT_SCALE))
            await self.config.user(ctx.author).rotation.set(settings.get("rotation", DEFAULT_ROTATION))
            await self.config.user(ctx.author).x_offset.set(settings.get("x_offset", DEFAULT_X_OFFSET))
            await self.config.user(ctx.author).y_offset.set(settings.get("y_offset", DEFAULT_Y_OFFSET))

        await self.config.user(ctx.author).selected_hat.set(found_hat)
        msg = await ctx.send(f"🎩 Selected hat: **{found_hat}**. Use `.hat preview` to see it!")
        await self._track_message(ctx, msg)

    @_hat.command(name="scale")
    async def _hat_scale(self, ctx, scale: float):
        """Adjust the hat size (0.1 to 2.0).

        Example: `.hat scale 0.7`
        """
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        if scale < MIN_SCALE or scale > MAX_SCALE:
            msg = await ctx.send(f"❌ Scale must be between {MIN_SCALE} and {MAX_SCALE}.")
            await self._track_message(ctx, msg)
            return

        await self.config.user(ctx.author).scale.set(scale)
        msg = await ctx.send(f"📏 Hat scale set to **{scale}**. Use `.hat preview` to see the result!")
        await self._track_message(ctx, msg)

    @_hat.command(name="rotate")
    async def _hat_rotate(self, ctx, degrees: float):
        """Adjust the hat rotation (-180 to 180 degrees).

        Example: `.hat rotate 15`
        """
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        if degrees < MIN_ROTATION or degrees > MAX_ROTATION:
            msg = await ctx.send(f"❌ Rotation must be between {MIN_ROTATION} and {MAX_ROTATION} degrees.")
            await self._track_message(ctx, msg)
            return

        await self.config.user(ctx.author).rotation.set(degrees)
        msg = await ctx.send(f"🔄 Hat rotation set to **{degrees}°**. Use `.hat preview` to see the result!")
        await self._track_message(ctx, msg)

    @_hat.command(name="position")
    async def _hat_position(self, ctx, x: float, y: float):
        """Adjust the hat position (0.0 to 1.0 for both x and y).

        x: 0.0 = left, 0.5 = center, 1.0 = right
        y: 0.0 = top, 0.5 = center, 1.0 = bottom

        Example: `.hat position 0.5 0.1`
        """
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        if x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
            msg = await ctx.send("❌ Position values must be between 0.0 and 1.0.")
            await self._track_message(ctx, msg)
            return

        await self.config.user(ctx.author).x_offset.set(x)
        await self.config.user(ctx.author).y_offset.set(y)
        msg = await ctx.send(f"📍 Hat position set to **({x}, {y})**. Use `.hat preview` to see the result!")
        await self._track_message(ctx, msg)

    @_hat.command(name="reset")
    async def _hat_reset(self, ctx):
        """Reset hat settings to defaults."""
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        await self.config.user(ctx.author).scale.set(DEFAULT_SCALE)
        await self.config.user(ctx.author).rotation.set(DEFAULT_ROTATION)
        await self.config.user(ctx.author).x_offset.set(DEFAULT_X_OFFSET)
        await self.config.user(ctx.author).y_offset.set(DEFAULT_Y_OFFSET)

        msg = await ctx.send("🔄 Hat settings reset to defaults!")
        await self._track_message(ctx, msg)

    @_hat.command(name="save")
    async def _hat_save(self, ctx):
        """Save current hat settings for future use."""
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        user_data = await self.config.user(ctx.author).all()
        selected_hat = user_data["selected_hat"]

        if not selected_hat:
            msg = await ctx.send("❌ No hat selected. Use `.hat select <name>` first!")
            await self._track_message(ctx, msg)
            return

        settings = {
            "scale": user_data["scale"],
            "rotation": user_data["rotation"],
            "x_offset": user_data["x_offset"],
            "y_offset": user_data["y_offset"],
        }

        async with self.config.user(ctx.author).saved_settings() as saved:
            saved[selected_hat] = settings

        msg = await ctx.send(f"💾 Settings saved for hat **{selected_hat}**!")
        await self._track_message(ctx, msg)

    @_hat.command(name="load")
    async def _hat_load(self, ctx, hat_name: Optional[str] = None):
        """Load previously saved hat settings.

        If no hat name is given, loads settings for the currently selected hat.

        Example: `.hat load santa`
        """
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        user_data = await self.config.user(ctx.author).all()

        if hat_name is None:
            hat_name = user_data["selected_hat"]

        if not hat_name:
            msg = await ctx.send("❌ No hat specified or selected. Use `.hat select <name>` first!")
            await self._track_message(ctx, msg)
            return

        saved_settings = user_data["saved_settings"]
        if hat_name not in saved_settings:
            msg = await ctx.send(f"❌ No saved settings for hat **{hat_name}**. Use `.hat save` first!")
            await self._track_message(ctx, msg)
            return

        settings = saved_settings[hat_name]
        await self.config.user(ctx.author).scale.set(settings.get("scale", DEFAULT_SCALE))
        await self.config.user(ctx.author).rotation.set(settings.get("rotation", DEFAULT_ROTATION))
        await self.config.user(ctx.author).x_offset.set(settings.get("x_offset", DEFAULT_X_OFFSET))
        await self.config.user(ctx.author).y_offset.set(settings.get("y_offset", DEFAULT_Y_OFFSET))
        await self.config.user(ctx.author).selected_hat.set(hat_name)

        msg = await ctx.send(f"📂 Loaded saved settings for hat **{hat_name}**!")
        await self._track_message(ctx, msg)

    @_hat.command(name="preview")
    async def _hat_preview(self, ctx):
        """Preview your avatar with the selected hat."""
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        user_data = await self.config.user(ctx.author).all()
        selected_hat = user_data["selected_hat"]

        # If no hat selected, try to use default
        if not selected_hat:
            selected_hat = await self.config.default_hat()

        if not selected_hat:
            msg = await ctx.send("❌ No hat selected! Use `.hat list` to see available hats, then `.hat select <name>`.")
            await self._track_message(ctx, msg)
            return

        hat_path = await self._get_hat_path(selected_hat)
        if not hat_path:
            msg = await ctx.send(f"❌ Hat `{selected_hat}` not found. It may have been removed.")
            await self._track_message(ctx, msg)
            return

        # Get avatar
        avatar_bytes = await self._get_avatar_bytes(ctx.author)
        if not avatar_bytes:
            msg = await ctx.send("❌ Could not fetch your avatar.")
            await self._track_message(ctx, msg)
            return

        # Apply hat
        try:
            result = await self._apply_hat_to_avatar(
                avatar_bytes,
                hat_path,
                user_data["scale"],
                user_data["rotation"],
                user_data["x_offset"],
                user_data["y_offset"],
            )
        except Exception as e:
            log.exception("Error applying hat to avatar")
            msg = await ctx.send(f"❌ Error applying hat: {e}")
            await self._track_message(ctx, msg)
            return

        # Create embed with preview
        embed = discord.Embed(
            title="🎅 Hat Preview",
            description="Use `.hat apply` to save this as your avatar!",
            color=discord.Color.red(),
        )
        embed.add_field(name="Hat", value=selected_hat, inline=True)
        embed.add_field(name="Scale", value=f"{user_data['scale']}", inline=True)
        embed.add_field(name="Rotation", value=f"{user_data['rotation']}°", inline=True)
        embed.add_field(name="Position", value=f"({user_data['x_offset']}, {user_data['y_offset']})", inline=True)
        embed.set_footer(text="Adjust with .hat scale, .hat rotate, .hat position")

        file = discord.File(io.BytesIO(result), filename="hat_preview.png")
        embed.set_image(url="attachment://hat_preview.png")

        msg = await ctx.send(embed=embed, file=file)
        await self._track_message(ctx, msg)

    @_hat.command(name="apply")
    async def _hat_apply(self, ctx):
        """Apply the hat to your avatar and get the final image.

        This generates the final hatted avatar that you can download and use.
        """
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        user_data = await self.config.user(ctx.author).all()
        selected_hat = user_data["selected_hat"]

        # If no hat selected, try to use default
        if not selected_hat:
            selected_hat = await self.config.default_hat()

        if not selected_hat:
            msg = await ctx.send("❌ No hat selected! Use `.hat list` to see available hats, then `.hat select <name>`.")
            await self._track_message(ctx, msg)
            return

        hat_path = await self._get_hat_path(selected_hat)
        if not hat_path:
            msg = await ctx.send(f"❌ Hat `{selected_hat}` not found. It may have been removed.")
            await self._track_message(ctx, msg)
            return

        # Get avatar
        avatar_bytes = await self._get_avatar_bytes(ctx.author)
        if not avatar_bytes:
            msg = await ctx.send("❌ Could not fetch your avatar.")
            await self._track_message(ctx, msg)
            return

        # Apply hat
        try:
            result = await self._apply_hat_to_avatar(
                avatar_bytes,
                hat_path,
                user_data["scale"],
                user_data["rotation"],
                user_data["x_offset"],
                user_data["y_offset"],
            )
        except Exception as e:
            log.exception("Error applying hat to avatar")
            msg = await ctx.send(f"❌ Error applying hat: {e}")
            await self._track_message(ctx, msg)
            return

        # Save current settings for this hat
        settings = {
            "scale": user_data["scale"],
            "rotation": user_data["rotation"],
            "x_offset": user_data["x_offset"],
            "y_offset": user_data["y_offset"],
        }
        async with self.config.user(ctx.author).saved_settings() as saved:
            saved[selected_hat] = settings

        # Send final image
        embed = discord.Embed(
            title="🎄 Your Festive Avatar!",
            description="Right-click the image to save it, then set it as your Discord avatar!",
            color=discord.Color.green(),
        )
        embed.set_footer(text="Happy Holidays! 🎅")

        file = discord.File(io.BytesIO(result), filename="festive_avatar.png")
        embed.set_image(url="attachment://festive_avatar.png")

        msg = await ctx.send(embed=embed, file=file)
        await self._track_message(ctx, msg)

    @_hat.command(name="settings")
    async def _hat_settings(self, ctx):
        """Show your current hat settings."""
        await self._cleanup_previous_commands(ctx, ctx.author.id)

        user_data = await self.config.user(ctx.author).all()

        embed = discord.Embed(
            title="⚙️ Your Hat Settings",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Selected Hat", value=user_data["selected_hat"] or "None", inline=True)
        embed.add_field(name="Scale", value=f"{user_data['scale']}", inline=True)
        embed.add_field(name="Rotation", value=f"{user_data['rotation']}°", inline=True)
        embed.add_field(name="Position X", value=f"{user_data['x_offset']}", inline=True)
        embed.add_field(name="Position Y", value=f"{user_data['y_offset']}", inline=True)

        saved_hats = list(user_data["saved_settings"].keys())
        embed.add_field(
            name="Saved Settings",
            value=", ".join(saved_hats) if saved_hats else "None",
            inline=False,
        )

        msg = await ctx.send(embed=embed)
        await self._track_message(ctx, msg)

    # Admin commands
    @commands.group(name="sethat", invoke_without_command=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def _sethat(self, ctx):
        """Admin commands for managing hats."""
        await ctx.send_help(ctx.command)

    @_sethat.command(name="upload")
    @checks.admin_or_permissions(manage_guild=True)
    async def _sethat_upload(self, ctx, hat_name: str):
        """Upload a new hat image.

        Attach a PNG image with transparency to your message.

        Example: `.sethat upload santa` (with image attached)
        """
        if not ctx.message.attachments:
            await ctx.send("❌ Please attach a PNG image to use as the hat.")
            return

        attachment = ctx.message.attachments[0]

        # Validate file type
        if not attachment.filename.lower().endswith(".png"):
            await ctx.send("❌ Hat images must be PNG files with transparency.")
            return

        # Validate name
        hat_name_clean = hat_name.lower().strip()
        if not hat_name_clean.isalnum():
            await ctx.send("❌ Hat name must be alphanumeric (letters and numbers only).")
            return

        # Check if hat already exists
        hats = await self.config.hats()
        if hat_name_clean in hats:
            await ctx.send(f"❌ A hat named `{hat_name_clean}` already exists. Use `.sethat remove` first.")
            return

        # Download and save the image
        try:
            image_data = await attachment.read()

            # Validate it's a valid image
            img = Image.open(io.BytesIO(image_data))
            if img.format != "PNG":
                await ctx.send("❌ Hat images must be PNG files.")
                return

            # Save to cog data path
            data_path = self._get_data_path()
            data_path.mkdir(parents=True, exist_ok=True)

            filename = f"{hat_name_clean}.png"
            file_path = data_path / filename

            with open(file_path, "wb") as f:
                f.write(image_data)

            # Register the hat
            async with self.config.hats() as hats_config:
                hats_config[hat_name_clean] = {
                    "filename": filename,
                    "uploaded_by": ctx.author.id,
                }

            # If this is the first hat, make it default
            default_hat = await self.config.default_hat()
            if not default_hat:
                await self.config.default_hat.set(hat_name_clean)

            await ctx.send(f"✅ Hat `{hat_name_clean}` uploaded successfully!")

        except Exception as e:
            log.exception("Error uploading hat")
            await ctx.send(f"❌ Error uploading hat: {e}")

    @_sethat.command(name="remove")
    @checks.admin_or_permissions(manage_guild=True)
    async def _sethat_remove(self, ctx, hat_name: str):
        """Remove a hat.

        Example: `.sethat remove santa`
        """
        hats = await self.config.hats()
        hat_name_lower = hat_name.lower()

        # Find hat (case insensitive)
        found_hat = None
        for name in hats:
            if name.lower() == hat_name_lower:
                found_hat = name
                break

        if not found_hat:
            await ctx.send(f"❌ Hat `{hat_name}` not found.")
            return

        # Remove file if it exists in cog data path
        hat_data = hats[found_hat]
        filename = hat_data.get("filename")
        if filename:
            data_path = self._get_data_path()
            file_path = data_path / filename
            if file_path.exists():
                file_path.unlink()

        # Remove from config
        async with self.config.hats() as hats_config:
            del hats_config[found_hat]

        # If this was the default hat, clear default
        default_hat = await self.config.default_hat()
        if default_hat == found_hat:
            await self.config.default_hat.set(None)

        await ctx.send(f"🗑️ Hat `{found_hat}` removed.")

    @_sethat.command(name="list")
    @checks.admin_or_permissions(manage_guild=True)
    async def _sethat_list(self, ctx):
        """List all hats with admin info."""
        hats = await self.config.hats()
        default_hat = await self.config.default_hat()

        if not hats:
            await ctx.send("❌ No hats configured. Use `.sethat upload <name>` to add one!")
            return

        embed = discord.Embed(
            title="🎩 Hat Management",
            description="All available hats with admin details",
            color=discord.Color.gold(),
        )

        for name, data in hats.items():
            is_default = "⭐ DEFAULT" if name == default_hat else ""
            uploaded_by = data.get("uploaded_by", "Unknown")
            user = self.bot.get_user(uploaded_by) if uploaded_by != "Unknown" else None
            uploader_name = user.name if user else f"User {uploaded_by}"

            embed.add_field(
                name=f"{name} {is_default}",
                value=f"File: `{data.get('filename', 'N/A')}`\nUploaded by: {uploader_name}",
                inline=True,
            )

        await ctx.send(embed=embed)

    @_sethat.command(name="default")
    @checks.admin_or_permissions(manage_guild=True)
    async def _sethat_default(self, ctx, hat_name: str):
        """Set the default hat for users who haven't selected one.

        Example: `.sethat default santa`
        """
        hats = await self.config.hats()
        hat_name_lower = hat_name.lower()

        # Find hat (case insensitive)
        found_hat = None
        for name in hats:
            if name.lower() == hat_name_lower:
                found_hat = name
                break

        if not found_hat:
            available = ", ".join(hats.keys()) if hats else "None available"
            await ctx.send(f"❌ Hat `{hat_name}` not found. Available hats: {available}")
            return

        await self.config.default_hat.set(found_hat)
        await ctx.send(f"⭐ Default hat set to **{found_hat}**!")
