"""
Unit tests for the VideoDownloader cog.

Tests cover:
- URL pattern detection (YouTube, TikTok, Instagram)
- Owner-only DM filtering
- Message type filtering (DM vs Guild)
- Guild enable/disable logic
- Channel and user disable logic
- Platform detection logic
- URL extraction from messages
"""

import sys
from unittest.mock import MagicMock, AsyncMock, patch

import discord
import pytest

# Mock redbot before importing the cog
sys.modules['redbot'] = MagicMock()
sys.modules['redbot.core'] = MagicMock()
sys.modules['redbot.core.commands'] = MagicMock()


# Create a mock Cog class with listener decorator
class MockCog:
    @staticmethod
    def listener():
        def decorator(func):
            return func
        return decorator


sys.modules['redbot.core'].commands.Cog = MockCog
sys.modules['redbot.core'].commands.Cog.listener = MockCog.listener

from video_dl.video_dl import VideoDownloader  # noqa: E402


# ============================================================================
# Mock Discord Objects for DM Testing
# ============================================================================

class MockDMChannel(discord.abc.PrivateChannel):
    """Mock Discord DM channel."""

    def __init__(self):
        self.id = 12345
        self.type = discord.ChannelType.private
        self._state = MagicMock()
        self.me = MockUser(id=999, is_bot=True)

    def typing(self):
        """Mock typing context manager."""

        class TypingContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return TypingContext()


class MockGuildChannel:
    """Mock Discord Guild channel."""

    def __init__(self):
        self.id = 67890
        self.type = discord.ChannelType.text

    def typing(self):
        """Mock typing context manager."""

        class TypingContext:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        return TypingContext()


class MockUser:
    """Mock Discord User."""

    def __init__(self, id: int = 1, is_bot: bool = False):
        self.id = id
        self.name = f"User{id}"
        self.bot = is_bot


class MockGuild:
    """Mock Discord Guild."""

    def __init__(self, id: int = 54321, premium_tier: int = 0):
        self.id = id
        self.name = f"Guild{id}"
        self.premium_tier = premium_tier


class MockMessage:
    """Mock Discord Message."""

    def __init__(self, content: str, author: MockUser, channel, bot_id: int = 999,
                 guild=None):
        self.content = content
        self.author = author
        self.channel = channel
        self.bot = MockUser(id=bot_id, is_bot=True)
        self.guild = guild

    async def reply(self, content=None, file=None):
        """Mock reply method."""
        pass


def _make_guild_config_mock(enabled=False, disabled_channels=None, disabled_users=None):
    """Create a properly async-mocked Config for guild tests."""
    guild_config_data = {
        "enabled": enabled,
        "disabled_channels": disabled_channels or [],
        "disabled_users": disabled_users or [],
    }
    guild_scope = MagicMock()
    guild_scope.all = AsyncMock(return_value=guild_config_data)
    guild_scope.enabled = AsyncMock(return_value=guild_config_data["enabled"])
    guild_scope.disabled_channels = AsyncMock(
        return_value=guild_config_data["disabled_channels"]
    )
    guild_scope.disabled_users = AsyncMock(
        return_value=guild_config_data["disabled_users"]
    )
    config_mock = MagicMock()
    config_mock.guild = MagicMock(return_value=guild_scope)
    return config_mock


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_bot():
    """Create a mock bot."""
    bot = MagicMock()
    bot.user = MockUser(id=999, is_bot=True)
    bot.is_owner = AsyncMock(return_value=False)
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock guild."""
    return MockGuild()


@pytest.fixture
def cog(mock_bot):
    """Create a VideoDownloader cog instance with a mocked Config."""
    instance = VideoDownloader(mock_bot)
    # Replace config with a default (guild disabled) async-compatible mock
    instance.config = _make_guild_config_mock(enabled=False)
    return instance


# ============================================================================
# Test URL Pattern Detection
# ============================================================================

@pytest.mark.asyncio
class TestURLPatternDetection:
    """Test URL pattern detection for supported platforms."""

    async def test_detect_youtube_watch_url(self, cog):
        """Test detection of standard YouTube watch URLs."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        platform = cog._detect_platform(url)
        assert platform == "youtube"

    async def test_detect_youtube_short_url(self, cog):
        """Test detection of YouTube short URLs (youtu.be)."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        platform = cog._detect_platform(url)
        assert platform == "youtube"

    async def test_detect_youtube_shorts(self, cog):
        """Test detection of YouTube Shorts URLs."""
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        platform = cog._detect_platform(url)
        assert platform == "youtube"

    async def test_detect_youtube_mobile(self, cog):
        """Test detection of mobile YouTube URLs."""
        url = "https://m.youtube.com/watch?v=dQw4w9WgXcQ"
        platform = cog._detect_platform(url)
        assert platform == "youtube"

    async def test_detect_tiktok_url(self, cog):
        """Test detection of TikTok URLs."""
        url = "https://www.tiktok.com/@user/video/1234567890"
        platform = cog._detect_platform(url)
        assert platform == "tiktok"

    async def test_detect_tiktok_short_url(self, cog):
        """Test detection of TikTok short URLs (vm.tiktok.com)."""
        url = "https://vm.tiktok.com/ZMabcdefg/"
        platform = cog._detect_platform(url)
        assert platform == "tiktok"

    async def test_detect_instagram_reel(self, cog):
        """Test detection of Instagram Reel URLs."""
        url = "https://www.instagram.com/reel/ABC123def456/"
        platform = cog._detect_platform(url)
        assert platform == "instagram"

    async def test_detect_instagram_post(self, cog):
        """Test detection of Instagram post URLs."""
        url = "https://www.instagram.com/p/ABC123def456/"
        platform = cog._detect_platform(url)
        assert platform == "instagram"

    async def test_detect_no_platform_for_invalid_url(self, cog):
        """Test that invalid URLs return None."""
        url = "https://www.example.com/video"
        platform = cog._detect_platform(url)
        assert platform is None

    async def test_detect_no_platform_for_plain_text(self, cog):
        """Test that plain text returns None."""
        text = "Check out this video!"
        platform = cog._detect_platform(text)
        assert platform is None


# ============================================================================
# Test Message Filtering
# ============================================================================

@pytest.mark.asyncio
class TestMessageFiltering:
    """Test message filtering logic."""

    async def test_ignore_guild_messages_when_disabled(self, cog, mock_bot, mock_guild):
        """Test that guild messages are ignored when the guild has downloads disabled."""
        channel = MockGuildChannel()
        author = MockUser(id=1)
        message = MockMessage(
            "https://youtube.com/watch?v=test", author, channel, guild=mock_guild
        )

        # Guild is disabled by default in the fixture
        with patch.object(cog, '_download_video', new=AsyncMock()) as mock_download:
            await cog.on_message(message)
            mock_bot.is_owner.assert_not_called()
            mock_download.assert_not_called()

    async def test_process_guild_messages_when_enabled(self, cog, mock_bot, mock_guild):
        """Test that guild messages are processed when the guild has downloads enabled."""
        cog.config = _make_guild_config_mock(enabled=True)
        channel = MockGuildChannel()
        author = MockUser(id=1)
        message = MockMessage(
            "https://youtube.com/watch?v=test", author, channel, guild=mock_guild
        )

        with patch.object(cog, '_download_video', new=AsyncMock(
            return_value=(True, '/tmp/video.mp4', None)
        )):
            with patch('os.path.getsize', return_value=1024 * 1024):  # 1MB
                with patch('discord.File'):
                    with patch.object(message, 'reply', new=AsyncMock()):
                        await cog.on_message(message)
                        cog._download_video.assert_called_once()

    async def test_ignore_guild_message_in_disabled_channel(self, cog, mock_bot, mock_guild):
        """Test that messages in disabled channels are ignored even when guild is enabled."""
        channel = MockGuildChannel()  # channel.id == 67890
        cog.config = _make_guild_config_mock(enabled=True, disabled_channels=[67890])
        author = MockUser(id=1)
        message = MockMessage(
            "https://youtube.com/watch?v=test", author, channel, guild=mock_guild
        )

        with patch.object(cog, '_download_video', new=AsyncMock()) as mock_download:
            await cog.on_message(message)
            mock_download.assert_not_called()

    async def test_ignore_guild_message_from_disabled_user(self, cog, mock_bot, mock_guild):
        """Test that messages from disabled users are ignored even when guild is enabled."""
        channel = MockGuildChannel()
        cog.config = _make_guild_config_mock(enabled=True, disabled_users=[1])
        author = MockUser(id=1)  # user id 1 is in disabled_users
        message = MockMessage(
            "https://youtube.com/watch?v=test", author, channel, guild=mock_guild
        )

        with patch.object(cog, '_download_video', new=AsyncMock()) as mock_download:
            await cog.on_message(message)
            mock_download.assert_not_called()

    async def test_ignore_bot_own_messages(self, cog, mock_bot):
        """Test that bot's own messages are ignored."""
        channel = MockDMChannel()
        bot_user = MockUser(id=999, is_bot=True)  # Same ID as bot
        message = MockMessage("https://youtube.com/watch?v=test", bot_user, channel)

        # Should return early without processing
        await cog.on_message(message)
        # If it processes, is_owner would be called - verify it wasn't
        mock_bot.is_owner.assert_not_called()

    async def test_ignore_non_owner_dms(self, cog, mock_bot):
        """Test that DMs from non-owners are ignored."""
        channel = MockDMChannel()
        author = MockUser(id=1)
        message = MockMessage("https://youtube.com/watch?v=test", author, channel)

        # Mock is_owner to return False
        mock_bot.is_owner.return_value = False

        with patch.object(cog, '_download_video', new=AsyncMock()) as mock_download:
            await cog.on_message(message)
            # Should check is_owner but not download
            mock_bot.is_owner.assert_called_once_with(author)
            mock_download.assert_not_called()

    async def test_process_owner_dms_with_url(self, cog, mock_bot):
        """Test that DMs from owner with URLs are processed."""
        channel = MockDMChannel()
        author = MockUser(id=1)
        message = MockMessage("https://youtube.com/watch?v=test", author, channel)

        # Mock is_owner to return True
        mock_bot.is_owner.return_value = True

        with patch.object(cog, '_download_video', new=AsyncMock(return_value=(True, '/tmp/video.mp4', None))):
            with patch('os.path.getsize', return_value=1024 * 1024):  # 1MB
                with patch('discord.File'):
                    with patch.object(message, 'reply', new=AsyncMock()):
                        await cog.on_message(message)
                        # Should check is_owner
                        mock_bot.is_owner.assert_called_once_with(author)

    async def test_ignore_owner_dms_without_url(self, cog, mock_bot):
        """Test that DMs from owner without URLs are ignored."""
        channel = MockDMChannel()
        author = MockUser(id=1)
        message = MockMessage("Hello, just chatting!", author, channel)

        # Mock is_owner to return True
        mock_bot.is_owner.return_value = True

        with patch.object(cog, '_download_video', new=AsyncMock()) as mock_download:
            await cog.on_message(message)
            # Should check is_owner but not download (no URL)
            mock_bot.is_owner.assert_called_once_with(author)
            mock_download.assert_not_called()


# ============================================================================
# Test URL Extraction from Messages
# ============================================================================

@pytest.mark.asyncio
class TestURLExtraction:
    """Test URL extraction from various message formats."""

    async def test_extract_url_from_simple_message(self, cog):
        """Test extracting URL from a simple message."""
        content = "https://youtube.com/watch?v=test"
        platform = cog._detect_platform(content)
        assert platform == "youtube"

    async def test_extract_url_from_message_with_text(self, cog):
        """Test extracting URL from message with surrounding text."""
        content = "Check this out: https://youtube.com/watch?v=test Amazing video!"
        # The regex should find the URL even with surrounding text
        matches = cog.URL_PATTERNS['youtube'].findall(content)
        assert len(matches) > 0

    async def test_extract_multiple_urls(self, cog):
        """Test that first URL is processed when multiple are present."""
        content = "https://youtube.com/watch?v=test1 https://tiktok.com/@user/video/123"
        # Should detect both platforms
        youtube_matches = cog.URL_PATTERNS['youtube'].findall(content)
        tiktok_matches = cog.URL_PATTERNS['tiktok'].findall(content)
        assert len(youtube_matches) > 0
        assert len(tiktok_matches) > 0


# ============================================================================
# Test Owner Check
# ============================================================================

@pytest.mark.asyncio
class TestOwnerCheck:
    """Test owner verification."""

    async def test_owner_check_returns_true_for_owner(self, cog, mock_bot):
        """Test that owner check returns True for bot owner."""
        user = MockUser(id=1)
        mock_bot.is_owner.return_value = True

        result = await cog._is_owner(user)
        assert result is True
        mock_bot.is_owner.assert_called_once_with(user)

    async def test_owner_check_returns_false_for_non_owner(self, cog, mock_bot):
        """Test that owner check returns False for non-owner."""
        user = MockUser(id=2)
        mock_bot.is_owner.return_value = False

        result = await cog._is_owner(user)
        assert result is False
        mock_bot.is_owner.assert_called_once_with(user)
