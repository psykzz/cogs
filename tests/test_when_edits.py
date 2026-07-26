import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_when_cog():
    try:
        from whentime.cog import WhenCog

        return WhenCog
    except ModuleNotFoundError:
        redbot = ModuleType("redbot")
        core = ModuleType("redbot.core")
        commands = ModuleType("redbot.core.commands")
        checks = ModuleType("redbot.core.checks")

        class Cog:
            @staticmethod
            def listener():
                return lambda func: func

        class Group:
            def command(self, **kwargs):
                return lambda func: func

            def group(self, **kwargs):
                return lambda func: Group()

        commands.Cog = Cog
        commands.hybrid_group = lambda **kwargs: lambda func: Group()
        commands.guild_only = lambda: lambda func: func
        checks.admin_or_permissions = lambda **kwargs: lambda func: func
        core.Config = MagicMock()
        core.checks = checks
        core.commands = commands
        sys.modules["redbot"] = redbot
        sys.modules["redbot.core"] = core
        sys.modules["redbot.core.commands"] = commands
        sys.modules["redbot.core.checks"] = checks
        from whentime.cog import WhenCog

        return WhenCog


WhenCog = _load_when_cog()


class ReplyMappings:
    def __init__(self, mappings):
        self.mappings = mappings

    async def __aenter__(self):
        return self.mappings

    async def __aexit__(self, *args):
        return None

    def __await__(self):
        async def get_mappings():
            return self.mappings

        return get_mappings().__await__()


class GuildConfig:
    def __init__(self):
        self.reply_mappings = {}

    async def enabled(self):
        return True

    async def enabled_channels(self):
        return []

    async def timezone(self):
        return "UTC"

    def timestamp_replies(self):
        return ReplyMappings(self.reply_mappings)


class Config:
    def __init__(self, guild_config):
        self.guild_config = guild_config

    def guild(self, guild):
        return self.guild_config


class Author:
    bot = False


class Channel:
    id = 1

    def __init__(self, reply):
        self.fetch_message = AsyncMock(return_value=reply)


class Message:
    def __init__(self, content, reply, channel):
        self.id = 100
        self.content = content
        self.author = Author()
        self.guild = MagicMock()
        self.channel = channel
        self.created_at = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        self.edited_at = None
        self.reply = AsyncMock(return_value=reply)


@pytest.fixture
def cog_and_message():
    reply = MagicMock()
    reply.id = 200
    reply.edit = AsyncMock()
    reply.delete = AsyncMock()
    guild_config = GuildConfig()
    channel = Channel(reply)
    message = Message("in an hour", reply, channel)
    cog = object.__new__(WhenCog)
    cog.config = Config(guild_config)
    return cog, message, reply, guild_config


@pytest.mark.asyncio
async def test_edit_updates_the_tracked_timestamp_reply(cog_and_message):
    cog, before, reply, guild_config = cog_and_message
    await cog.on_message(before)

    after = Message("in 2 hours", reply, before.channel)
    await cog.on_message_edit(before, after)

    assert guild_config.reply_mappings == {"100": 200}
    expected = int((before.created_at + timedelta(hours=2)).timestamp())
    reply.edit.assert_awaited_once_with(content=f"<t:{expected}:R>")


@pytest.mark.asyncio
async def test_edit_without_a_time_deletes_the_tracked_reply(cog_and_message):
    cog, before, reply, guild_config = cog_and_message
    await cog.on_message(before)

    after = Message("no time here", reply, before.channel)
    await cog.on_message_edit(before, after)

    assert guild_config.reply_mappings == {}
    reply.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_message_with_a_discord_timestamp_is_ignored(cog_and_message):
    cog, message, reply, guild_config = cog_and_message
    message.content = "in an hour <t:1784980800:R>"

    await cog.on_message(message)

    assert guild_config.reply_mappings == {}
    reply.edit.assert_not_awaited()
    reply.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_with_a_discord_timestamp_deletes_the_tracked_reply(cog_and_message):
    cog, before, reply, guild_config = cog_and_message
    await cog.on_message(before)
    after = Message("in 2 hours <t:1784980800:R>", reply, before.channel)

    await cog.on_message_edit(before, after)

    assert guild_config.reply_mappings == {}
    reply.delete.assert_awaited_once()
