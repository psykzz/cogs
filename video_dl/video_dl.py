import asyncio
import logging
import os
import re
import tempfile
from pathlib import Path

import discord
from redbot.core import commands

log = logging.getLogger("red.cogs.video_dl")


class VideoDownloader(commands.Cog):
    """Download videos from DMs for bot owner only

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

    async def _is_owner(self, user):
        """Check if user is bot owner."""
        return await self.bot.is_owner(user)

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
        """Listen for DMs with video URLs from bot owner.

        Parameters
        ----------
        message : discord.Message
            The message that was sent
        """
        # Only process DMs
        if not isinstance(message.channel, discord.abc.PrivateChannel):
            return

        # Ignore bot's own messages
        if message.author.id == self.bot.user.id:
            return

        # Only respond to bot owner
        if not await self._is_owner(message.author):
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
                    except discord.HTTPException as e:
                        await message.reply(f"❌ Failed to upload file: {e}")
                else:
                    # Send error message
                    await message.reply(f"❌ {error_msg}")

            finally:
                # Clean up temporary directory
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    log.error(f"Failed to clean up temp directory {temp_dir}: {e}")
