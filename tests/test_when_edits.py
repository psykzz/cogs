import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import discord
import pytest


def _load_when_cog():
    try:
        from whentime.cog import SetTimestampModal, TimestampActionsView, WhenCog

        return SetTimestampModal, TimestampActionsView, WhenCog
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
        from whentime.cog import SetTimestampModal, TimestampActionsView, WhenCog

        return SetTimestampModal, TimestampActionsView, WhenCog


SetTimestampModal, TimestampActionsView, WhenCog = _load_when_cog()


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
        self.timestamp_overrides = {}
        self.preferences = {}

    async def enabled(self):
        return True

    async def enabled_channels(self):
        return []

    async def timezone(self):
        return "UTC"

    def timestamp_replies(self):
        return ReplyMappings(self.reply_mappings)

    def manual_timestamps(self):
        return ReplyMappings(self.timestamp_overrides)

    def user_preferences(self):
        return ReplyMappings(self.preferences)


class Config:
    def __init__(self, guild_config):
        self.guild_configs = {1: guild_config}

    def guild(self, guild):
        return self.guild_configs.setdefault(guild.id, GuildConfig())

    async def all_guilds(self):
        return self.guild_configs

    def guild_from_id(self, guild_id):
        return self.guild_configs[guild_id]


class Bot:
    def __init__(self):
        self.cogs = {}
        self.views = []

    def add_view(self, view):
        self.views.append(view)

    def get_cog(self, name):
        return self.cogs.get(name)


class Author:
    def __init__(self, author_id=1):
        self.bot = False
        self.id = author_id


class Guild:
    def __init__(self, guild_id=1):
        self.id = guild_id


class Channel:
    id = 1

    def __init__(self, reply):
        self.fetch_message = AsyncMock(return_value=reply)


class Message:
    def __init__(self, content, reply, channel):
        self.id = 100
        self.content = content
        self.author = Author()
        self.guild = Guild()
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
    bot = Bot()
    cog = object.__new__(WhenCog)
    cog.bot = bot
    cog.config = Config(guild_config)
    bot.cogs["WhenCog"] = cog
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
async def test_timestamp_reply_has_persistent_controls(cog_and_message):
    cog, message, _, _ = cog_and_message

    await cog.cog_load()
    await cog.on_message(message)

    view = message.reply.await_args.kwargs["view"]
    assert len(cog.bot.views) == 1
    assert cog.bot.views[0].is_persistent()
    assert view.is_persistent()
    assert view.children[0].custom_id == "whentime:manage_timestamp"


@pytest.mark.asyncio
async def test_manage_button_opens_ephemeral_actions_for_the_original_author(
    cog_and_message,
):
    cog, message, reply, _ = cog_and_message
    reply.reference = SimpleNamespace(message_id=message.id)
    reply.channel = message.channel
    message.channel.fetch_message = AsyncMock(return_value=message)
    await cog.on_message(message)
    view = message.reply.await_args.kwargs["view"]

    interaction = MagicMock()
    interaction.message = reply
    interaction.user = message.author
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    await view.children[0].callback(interaction)

    interaction.response.defer.assert_awaited_once_with(
        ephemeral=True, thinking=True
    )
    action_view = interaction.followup.send.await_args.kwargs["view"]
    assert isinstance(action_view, TimestampActionsView)
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_manage_button_rejects_non_authors_privately(cog_and_message):
    cog, message, reply, _ = cog_and_message
    reply.reference = SimpleNamespace(message_id=message.id)
    reply.channel = message.channel
    message.channel.fetch_message = AsyncMock(return_value=message)
    await cog.on_message(message)
    view = message.reply.await_args.kwargs["view"]

    interaction = MagicMock()
    interaction.message = reply
    interaction.user = Author(2)
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    await view.children[0].callback(interaction)

    interaction.followup.send.assert_awaited_once_with(
        "Only the original poster can manage this timestamp.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_never_reply_action_stores_guild_preference(cog_and_message):
    cog, message, reply, guild_config = cog_and_message
    actions_view = TimestampActionsView(
        cog, message.guild, message.id, reply, message.author.id
    )
    button = next(item for item in actions_view.children if item.label == "Never reply")

    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    await button.callback(interaction)

    assert guild_config.preferences == {"1": {"never_reply": True}}
    interaction.response.defer.assert_awaited_once_with(
        ephemeral=True, thinking=True
    )
    interaction.followup.send.assert_awaited_once_with(
        "When will no longer reply to your messages in this server.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_never_reply_preference_prevents_future_replies(cog_and_message):
    cog, message, _, guild_config = cog_and_message

    await cog._set_never_reply(message.guild, message.author.id)
    await cog.on_message(message)

    assert guild_config.preferences == {"1": {"never_reply": True}}
    message.reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_never_reply_preference_is_guild_scoped_and_deleted(cog_and_message):
    cog, message, _, guild_config = cog_and_message
    other_guild = Guild(2)

    await cog._set_never_reply(message.guild, message.author.id)
    assert guild_config.preferences == {"1": {"never_reply": True}}
    assert await cog._should_reply_to_user(other_guild, message.author.id)

    other_guild_config = cog.config.guild(other_guild)
    await cog._set_never_reply(other_guild, message.author.id)
    await cog.red_delete_data_for_user(
        requester="discord_deleted_user", user_id=message.author.id
    )

    assert guild_config.preferences == {}
    assert other_guild_config.preferences == {}


@pytest.mark.asyncio
async def test_removing_timestamp_reply_untracks_it(cog_and_message):
    cog, message, reply, guild_config = cog_and_message
    guild_config.reply_mappings[str(message.id)] = reply.id
    guild_config.timestamp_overrides[str(message.id)] = 123

    await cog._delete_timestamp_reply(message.guild, message.id, reply)

    assert guild_config.reply_mappings == {}
    assert guild_config.timestamp_overrides == {}
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


@pytest.mark.asyncio
async def test_manual_timestamp_is_preserved_when_source_message_is_edited(
    cog_and_message,
):
    cog, before, reply, guild_config = cog_and_message
    await cog.on_message(before)
    await cog._set_manual_timestamp(
        before.guild,
        before.id,
        int(datetime(2099, 1, 2, 3, 4, tzinfo=timezone.utc).timestamp()),
    )

    after = Message("no time here", reply, before.channel)
    after.guild = before.guild
    after.author = before.author
    after.id = before.id
    await cog.on_message_edit(before, after)

    assert guild_config.reply_mappings == {"100": 200}
    assert "100" in guild_config.timestamp_overrides
    reply.edit.assert_not_awaited()
    reply.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_setting_timestamp_updates_reply_and_stores_override(cog_and_message):
    cog, message, reply, guild_config = cog_and_message
    await cog.on_message(message)
    actions_view = TimestampActionsView(
        cog, message.guild, message.id, reply, message.author.id
    )
    modal = SetTimestampModal(actions_view, "UTC")
    modal.value._value = "2099-01-02 03:04"

    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    await modal.on_submit(interaction)

    expected = int(datetime(2099, 1, 2, 3, 4, tzinfo=timezone.utc).timestamp())
    reply.edit.assert_awaited_once_with(content=f"<t:{expected}:R>")
    assert guild_config.timestamp_overrides == {"100": expected}
    interaction.followup.send.assert_awaited_once_with(
        "Timestamp reply updated.", ephemeral=True
    )


def test_timestamp_modal_label_supports_long_timezones(cog_and_message):
    cog, message, reply, _ = cog_and_message
    timezone_name = "America/Argentina/ComodRivadavia"
    actions_view = TimestampActionsView(
        cog, message.guild, message.id, reply, message.author.id
    )

    modal = SetTimestampModal(actions_view, timezone_name)

    assert len(modal.value._underlying.label) <= 45
    assert timezone_name in modal.value._underlying.placeholder


def test_specific_timestamp_must_be_future_and_uses_guild_timezone(cog_and_message):
    cog, _, _, _ = cog_and_message

    timestamp = cog._parse_timestamp("2099-01-02 03:04", "Europe/London")

    assert timestamp == datetime(
        2099, 1, 2, 3, 4, tzinfo=ZoneInfo("Europe/London")
    ).astimezone(timezone.utc)
    assert cog._parse_timestamp("not a date", "UTC") is None
    assert cog._parse_timestamp("2000-01-02 03:04", "UTC") is None
    assert cog._parse_timestamp("2027-03-28 01:30", "Europe/London") is None
