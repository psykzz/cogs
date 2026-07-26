import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import discord
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
        self.preferences = {}

    async def enabled(self):
        return True

    async def enabled_channels(self):
        return []

    async def timezone(self):
        return "UTC"

    def timestamp_replies(self):
        return ReplyMappings(self.reply_mappings)

    def user_preferences(self):
        return ReplyMappings(self.preferences)


class Config:
    def __init__(self, guild_config):
        self.guild_config = guild_config

    def guild(self, guild):
        return self.guild_config


class Author:
    bot = False
    id = 1


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
async def test_timestamp_reply_includes_private_controls(cog_and_message):
    cog, message, reply, _ = cog_and_message

    await cog.on_message(message)

    view = message.reply.await_args.kwargs["view"]
    assert type(view).__name__ == "TimestampControlsView"
    assert view.author_id == message.author.id


@pytest.mark.asyncio
async def test_never_reply_preference_prevents_future_replies(cog_and_message):
    cog, message, reply, guild_config = cog_and_message

    await cog._set_never_reply(message.guild, message.author.id)
    await cog.on_message(message)

    assert guild_config.preferences == {"1": {"never_reply": True}}
    reply.edit.assert_not_awaited()
    message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_removing_timestamp_reply_untracks_it(cog_and_message):
    cog, message, reply, guild_config = cog_and_message
    guild_config.reply_mappings[str(message.id)] = reply.id

    await cog._delete_timestamp_reply(message.guild, message.id, reply)

    assert guild_config.reply_mappings == {}
    reply.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_timestamp_removal_keeps_reply_tracked(cog_and_message):
    cog, message, reply, guild_config = cog_and_message
    guild_config.reply_mappings[str(message.id)] = reply.id
    reply.delete.side_effect = discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Forbidden"
    )

    deleted = await cog._delete_timestamp_reply(message.guild, message.id, reply)

    assert deleted is False
    assert guild_config.reply_mappings == {"100": 200}


def test_specific_timestamp_must_be_future_and_uses_guild_timezone(cog_and_message):
    cog, _, _, _ = cog_and_message

    timestamp = cog._parse_timestamp("2099-01-02 03:04", "Europe/London")

    assert timestamp == datetime(2099, 1, 2, 3, 4, tzinfo=ZoneInfo("Europe/London")).astimezone(
        timezone.utc
    )
    assert cog._parse_timestamp("not a date", "UTC") is None
    assert cog._parse_timestamp("2000-01-02 03:04", "UTC") is None
