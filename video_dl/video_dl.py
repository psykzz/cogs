import logging
import os
import re
import tempfile
from pathlib import Path

import discord
from redbot.core import commands, Config, checks

log = logging.getLogger("red.cogs.video_dl")


class VideoDownloader(commands.Cog):
    """Download videos from URLs in DMs and guilds

    Supports YouTube, TikTok, and Instagram videos/shorts/reels.
    """

    # Discord file size limits (in bytes)
    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB for non-Nitro users

    # URL patterns for supported platforms
    URL_PATTERNS = {
        'youtube': re.compile(
            r'(?:https?://)?(?:www\.|m\.)?'
            r'(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)'
            r'[\w-]+'
        ),
        'tiktok': re.compile(
            r'(?:https?://)?(?:www\.|vm\.)?tiktok\.com/[\w/@-]+'
        ),
        'instagram': re.compile(
            r'(?:https?://)?(?:www\.)?instagram\.com/(?:reel|p)/[\w-]+/?'
        ),
    }

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=7360073600, force_registration=True
        )
        # Default: guilds disabled, users enabled, channels enabled
        default_guild = {
            "enabled": False,
            "disabled_channels": [],
            "disabled_users": [],
        }
        self.config.register_guild(**default_guild)

    async def _is_owner(self, user):
        """Check if user is bot owner."""
        return await self.bot.is_owner(user)

    async def _can_download_in_guild(self, message: discord.Message):
        """Check if downloading is allowed in this guild/channel/user.

        Parameters
        ----------
        message : discord.Message
            The message to check permissions for

        Returns
        -------
        bool
            True if download is allowed, False otherwise
        """
        # Always allow in DMs for bot owner
        if isinstance(message.channel, discord.abc.PrivateChannel):
            return await self._is_owner(message.author)

        # Check guild is enabled
        guild_config = await self.config.guild(message.guild).all()
        if not guild_config["enabled"]:
            return False

        # Check channel is not disabled
        if message.channel.id in guild_config["disabled_channels"]:
            return False

        # Check user is not disabled
        if message.author.id in guild_config["disabled_users"]:
            return False

        return True

    def _detect_platform(self, url: str):
        """Detect which platform a URL belongs to.

        Parameters
        ----------
        url : str
            The URL to check

        Returns
        -------
        str or None
            Platform name ('youtube', 'tiktok', 'instagram') or None if not recognized
        """
        for platform, pattern in self.URL_PATTERNS.items():
            if pattern.search(url):
                return platform
        return None

    async def _download_video(self, url: str, platform: str, temp_dir: str):
        """Download video using yt-dlp.

        Parameters
        ----------
        url : str
            Video URL to download
        platform : str
            Platform name (youtube, tiktok, instagram)
        temp_dir : str
            Temporary directory to download to

        Returns
        -------
        tuple
            (success: bool, file_path: str or None, error_message: str or None)
        """
        try:
            import yt_dlp
        except ImportError:
            return False, None, "yt-dlp is not installed. Please install it with: pip install yt-dlp"

        # Configure yt-dlp options based on platform
        ydl_opts = {
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        if platform == 'youtube':
            # YouTube: best video up to 1080p + best audio
            ydl_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]'
            ydl_opts['format_sort'] = ['proto', 'ext:mp4:m4a', 'res', 'br']
        else:
            # TikTok & Instagram: best available with sorting
            ydl_opts['format_sort'] = ['proto', 'ext:mp4:m4a', 'res', 'br']

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                # Find the downloaded file
                if 'requested_downloads' in info and info['requested_downloads']:
                    file_path = info['requested_downloads'][0]['filepath']
                else:
                    # Fallback: look for the file in temp directory
                    files = list(Path(temp_dir).glob('*'))
                    if files:
                        file_path = str(files[0])
                    else:
                        return False, None, "Download succeeded but could not find the file"

                # Check file size
                file_size = os.path.getsize(file_path)
                if file_size > self.MAX_FILE_SIZE:
                    return False, None, f"Video is too large ({file_size / 1024 / 1024:.1f}MB). Discord limit is 25MB."

                return True, file_path, None

        except yt_dlp.utils.DownloadError as e:
            log.error(f"yt-dlp download error: {e}")
            return False, None, f"Download failed: {str(e)}"
        except Exception as e:
            log.exception(f"Unexpected error downloading video: {e}")
            return False, None, f"Unexpected error: {str(e)}"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages with video URLs.

        Parameters
        ----------
        message : discord.Message
            The message that was sent
        """
        # Ignore bot's own messages
        if message.author.id == self.bot.user.id:
            return

        # Check if downloading is allowed for this message
        if not await self._can_download_in_guild(message):
            return

        # Look for video URLs in the message
        urls = []
        for platform, pattern in self.URL_PATTERNS.items():
            matches = pattern.findall(message.content)
            for match in matches:
                urls.append((match, platform))

        if not urls:
            return

        # Process the first URL found
        url, platform = urls[0]

        # Send typing indicator
        async with message.channel.typing():
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix='video_dl_')

            try:
                # Download the video
                success, file_path, error_msg = await self._download_video(url, platform, temp_dir)

                if success and file_path:
                    # Send the file
                    try:
                        await message.reply(
                            content=f"Downloaded from {platform.title()}:",
                            file=discord.File(file_path)
                        )
                    except discord.HTTPException:
                        # Suppress errors for automatic downloads
                        pass
                # Suppress error messages for automatic downloads

            finally:
                # Clean up temporary directory
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    log.error(f"Failed to clean up temp directory {temp_dir}: {e}")

    @commands.hybrid_command(name="download")
    async def download_command(self, ctx, url: str):
        """Manually download a video from a URL.

        Parameters
        ----------
        url : str
            The URL of the video to download
        """
        await ctx.defer(ephemeral=True)

        # Detect platform
        platform = self._detect_platform(url)
        if not platform:
            await ctx.send("❌ URL not recognized. Supported platforms: YouTube, TikTok, Instagram", ephemeral=True)
            return

        # Send typing indicator
        async with ctx.typing():
            # Create temporary directory
            temp_dir = tempfile.mkdtemp(prefix='video_dl_')

            try:
                # Download the video
                success, file_path, error_msg = await self._download_video(url, platform, temp_dir)

                if success and file_path:
                    # Send the file
                    try:
                        await ctx.send(
                            content=f"Downloaded from {platform.title()}:",
                            file=discord.File(file_path),
                            ephemeral=True
                        )
                    except discord.HTTPException as e:
                        await ctx.send(f"❌ Failed to upload file: {e}", ephemeral=True)
                else:
                    # Send error message
                    await ctx.send(f"❌ {error_msg}", ephemeral=True)

            finally:
                # Clean up temporary directory
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    log.error(f"Failed to clean up temp directory {temp_dir}: {e}")

    @commands.guild_only()
    @commands.hybrid_group(name="videodl")
    async def videodl(self, ctx):
        """Configure video download settings."""
        pass

    @checks.is_owner()
    @videodl.command(name="enable")
    async def videodl_enable(self, ctx):
        """Enable automatic video downloads in this server (bot owner only)."""
        await ctx.defer(ephemeral=True)
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Automatic video downloads enabled for this server.", ephemeral=True)

    @checks.is_owner()
    @videodl.command(name="disable")
    async def videodl_disable(self, ctx):
        """Disable automatic video downloads in this server (bot owner only)."""
        await ctx.defer(ephemeral=True)
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("✅ Automatic video downloads disabled for this server.", ephemeral=True)

    @checks.admin_or_permissions(manage_guild=True)
    @videodl.command(name="channelenable")
    async def videodl_channel_enable(self, ctx, channel: discord.TextChannel = None):
        """Enable automatic video downloads in a specific channel.

        Parameters
        ----------
        channel : discord.TextChannel, optional
            The channel to enable (defaults to current channel)
        """
        await ctx.defer(ephemeral=True)
        channel = channel or ctx.channel

        disabled_channels = await self.config.guild(ctx.guild).disabled_channels()
        if channel.id in disabled_channels:
            disabled_channels.remove(channel.id)
            await self.config.guild(ctx.guild).disabled_channels.set(disabled_channels)
            await ctx.send(f"✅ Automatic video downloads enabled in {channel.mention}.", ephemeral=True)
        else:
            await ctx.send(f"ℹ️ Automatic video downloads are already enabled in {channel.mention}.", ephemeral=True)

    @checks.admin_or_permissions(manage_guild=True)
    @videodl.command(name="channeldisable")
    async def videodl_channel_disable(self, ctx, channel: discord.TextChannel = None):
        """Disable automatic video downloads in a specific channel.

        Parameters
        ----------
        channel : discord.TextChannel, optional
            The channel to disable (defaults to current channel)
        """
        await ctx.defer(ephemeral=True)
        channel = channel or ctx.channel

        disabled_channels = await self.config.guild(ctx.guild).disabled_channels()
        if channel.id not in disabled_channels:
            disabled_channels.append(channel.id)
            await self.config.guild(ctx.guild).disabled_channels.set(disabled_channels)
            await ctx.send(f"✅ Automatic video downloads disabled in {channel.mention}.", ephemeral=True)
        else:
            await ctx.send(f"ℹ️ Automatic video downloads are already disabled in {channel.mention}.", ephemeral=True)

    @checks.admin_or_permissions(manage_guild=True)
    @videodl.command(name="userenable")
    async def videodl_user_enable(self, ctx, user: discord.Member):
        """Enable automatic video downloads for a specific user.

        Parameters
        ----------
        user : discord.Member
            The user to enable
        """
        await ctx.defer(ephemeral=True)

        disabled_users = await self.config.guild(ctx.guild).disabled_users()
        if user.id in disabled_users:
            disabled_users.remove(user.id)
            await self.config.guild(ctx.guild).disabled_users.set(disabled_users)
            await ctx.send(f"✅ Automatic video downloads enabled for {user.mention}.", ephemeral=True)
        else:
            await ctx.send(f"ℹ️ Automatic video downloads are already enabled for {user.mention}.", ephemeral=True)

    @checks.admin_or_permissions(manage_guild=True)
    @videodl.command(name="userdisable")
    async def videodl_user_disable(self, ctx, user: discord.Member):
        """Disable automatic video downloads for a specific user.

        Parameters
        ----------
        user : discord.Member
            The user to disable
        """
        await ctx.defer(ephemeral=True)

        disabled_users = await self.config.guild(ctx.guild).disabled_users()
        if user.id not in disabled_users:
            disabled_users.append(user.id)
            await self.config.guild(ctx.guild).disabled_users.set(disabled_users)
            await ctx.send(f"✅ Automatic video downloads disabled for {user.mention}.", ephemeral=True)
        else:
            await ctx.send(f"ℹ️ Automatic video downloads are already disabled for {user.mention}.", ephemeral=True)

    @checks.admin_or_permissions(manage_guild=True)
    @videodl.command(name="status")
    async def videodl_status(self, ctx):
        """Show current video download configuration for this server."""
        await ctx.defer(ephemeral=True)

        guild_config = await self.config.guild(ctx.guild).all()
        enabled = guild_config["enabled"]
        disabled_channels = guild_config["disabled_channels"]
        disabled_users = guild_config["disabled_users"]

        status_msg = f"**Video Download Status for {ctx.guild.name}**\n\n"
        status_msg += f"Server-wide: {'✅ Enabled' if enabled else '❌ Disabled'}\n\n"

        if disabled_channels:
            channel_mentions = []
            for channel_id in disabled_channels:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    channel_mentions.append(channel.mention)
            if channel_mentions:
                status_msg += f"**Disabled Channels:** {', '.join(channel_mentions)}\n\n"

        if disabled_users:
            user_mentions = []
            for user_id in disabled_users:
                member = ctx.guild.get_member(user_id)
                if member:
                    user_mentions.append(member.mention)
            if user_mentions:
                status_msg += f"**Disabled Users:** {', '.join(user_mentions)}\n\n"

        await ctx.send(status_msg, ephemeral=True)
