"""
Shared pytest fixtures and utilities for testing Red-DiscordBot cogs.

This module provides mock Discord objects and utilities for testing cogs
without requiring an actual Discord bot or Red-DiscordBot installation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from typing import Optional, Dict, Any
import asyncio


# ============================================================================
# Mock Discord Objects
# ============================================================================

class MockRole:
    """Mock Discord Role object."""

    def __init__(self, id: int = 1, name: str = "TestRole", position: int = 1):
        self.id = id
        self.name = name
        self.position = position
        self.mentionable = True
        self.permissions = MagicMock()

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, MockRole) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


class MockMember:
    """Mock Discord Member object."""

    def __init__(self, id: int = 1, name: str = "TestUser", roles: Optional[list] = None):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self._roles = roles or []
        self.guild = None
        self.bot = False

    @property
    def roles(self):
        return self._roles

    async def add_roles(self, *roles, reason: Optional[str] = None):
        """Mock adding roles to member."""
        for role in roles:
            if role not in self._roles:
                self._roles.append(role)

    async def remove_roles(self, *roles, reason: Optional[str] = None):
        """Mock removing roles from member."""
        for role in roles:
            if role in self._roles:
                self._roles.remove(role)

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, MockMember) and self.id == other.id

    def __hash__(self):
        return hash(self.id)


class MockGuild:
    """Mock Discord Guild object."""

    def __init__(self, id: int = 1, name: str = "TestGuild"):
        self.id = id
        self.name = name
        self.members = []
        self.roles = []
        self.channels = []
        self.me = MockMember(id=999, name="BotUser")

    def get_member(self, user_id: int) -> Optional[MockMember]:
        """Get member by ID."""
        for member in self.members:
            if member.id == user_id:
                return member
        return None

    def get_role(self, role_id: int) -> Optional[MockRole]:
        """Get role by ID."""
        for role in self.roles:
            if role.id == role_id:
                return role
        return None


class MockTextChannel:
    """Mock Discord TextChannel object."""

    def __init__(self, id: int = 1, name: str = "test-channel", guild: Optional[MockGuild] = None):
        self.id = id
        self.name = name
        self.guild = guild or MockGuild()
        self.mention = f"<#{id}>"
        self._messages = []

    async def send(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        """Mock sending a message."""
        message = MockMessage(
            id=len(self._messages) + 1,
            content=content,
            channel=self,
            author=self.guild.me
        )
        message.embeds = [embed] if embed else []
        self._messages.append(message)
        return message

    async def fetch_message(self, message_id: int):
        """Mock fetching a message."""
        for msg in self._messages:
            if msg.id == message_id:
                return msg
        raise ValueError(f"Message {message_id} not found")


class MockMessage:
    """Mock Discord Message object."""

    def __init__(self, id: int = 1, content: str = "", channel=None, author=None):
        self.id = id
        self.content = content
        self.channel = channel or MockTextChannel()
        self.author = author or MockMember()
        self.guild = channel.guild if channel else MockGuild()
        self.embeds = []
        self.reactions = []

    async def add_reaction(self, emoji):
        """Mock adding a reaction."""
        self.reactions.append(emoji)

    async def clear_reactions(self):
        """Mock clearing reactions."""
        self.reactions.clear()

    async def edit(self, **kwargs):
        """Mock editing a message."""
        if 'content' in kwargs:
            self.content = kwargs['content']
        if 'embed' in kwargs:
            self.embeds = [kwargs['embed']]

    async def delete(self):
        """Mock deleting a message."""
        if self in self.channel._messages:
            self.channel._messages.remove(self)


class MockContext:
    """Mock Discord Context object for commands."""

    def __init__(self, guild=None, author=None, channel=None, bot=None):
        self.guild = guild or MockGuild()
        self.author = author or MockMember()
        self.channel = channel or MockTextChannel(guild=self.guild)
        self.bot = bot or MockBot()
        self.message = MockMessage(channel=self.channel, author=self.author)
        self.interaction = None
        self._typing_context = None

    async def send(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        """Mock sending a message."""
        return await self.channel.send(content, embed=embed, view=view, ephemeral=ephemeral, **kwargs)

    async def defer(self, ephemeral=False):
        """Mock deferring a response."""
        pass

    def typing(self):
        """Mock typing indicator context manager."""
        if not self._typing_context:
            self._typing_context = MockTypingContext()
        return self._typing_context

    async def send_help(self, command=None):
        """Mock sending help."""
        pass


class MockTypingContext:
    """Mock typing context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockInteraction:
    """Mock Discord Interaction object."""

    def __init__(self, user=None, guild=None, channel=None):
        self.user = user or MockMember()
        self.guild = guild or MockGuild()
        self.channel = channel or MockTextChannel(guild=self.guild)
        self.response = MockInteractionResponse()
        self.followup = MockFollowup()
        self.message = None
        self.data = {}

    async def edit_original_response(self, **kwargs):
        """Mock editing the original response."""
        if self.message:
            await self.message.edit(**kwargs)


class MockInteractionResponse:
    """Mock Discord InteractionResponse object."""

    def __init__(self):
        self._deferred = False
        self._sent = False

    async def defer(self, ephemeral=False, thinking=False):
        """Mock deferring a response."""
        self._deferred = True

    async def send_message(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        """Mock sending a response."""
        self._sent = True

    async def send_modal(self, modal):
        """Mock sending a modal."""
        self._sent = True


class MockFollowup:
    """Mock Discord InteractionFollowup object."""

    async def send(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        """Mock sending a followup message."""
        return MockMessage(content=content)


class MockBot:
    """Mock Discord Bot object."""

    def __init__(self):
        self.user = MockMember(id=999, name="BotUser")
        self.guilds = []
        self._cogs = {}
        self.loop = asyncio.get_event_loop()

    def get_guild(self, guild_id: int):
        """Get guild by ID."""
        for guild in self.guilds:
            if guild.id == guild_id:
                return guild
        return None

    def get_cog(self, name: str):
        """Get cog by name."""
        return self._cogs.get(name)

    async def add_cog(self, cog):
        """Add a cog to the bot."""
        self._cogs[cog.__class__.__name__] = cog

    def wait_until_ready(self):
        """Mock waiting until bot is ready."""
        async def _wait():
            pass
        return _wait()


# ============================================================================
# Mock Red-DiscordBot Config
# ============================================================================

class MockConfig:
    """
    Mock Red-DiscordBot Config object for testing.

    Provides a simple in-memory storage system that mimics the Config API
    without requiring actual Red-DiscordBot installation.
    """

    def __init__(self, cog_name: str):
        self.cog_name = cog_name
        self._data = {
            'guild': {},
            'member': {},
            'user': {},
            'channel': {},
            'role': {},
            'global': {}
        }
        self._defaults = {
            'guild': {},
            'member': {},
            'user': {},
            'channel': {},
            'role': {},
            'global': {}
        }

    def register_guild(self, **defaults):
        """Register guild-level config defaults."""
        self._defaults['guild'].update(defaults)

    def register_member(self, **defaults):
        """Register member-level config defaults."""
        self._defaults['member'].update(defaults)

    def register_user(self, **defaults):
        """Register user-level config defaults."""
        self._defaults['user'].update(defaults)

    def register_channel(self, **defaults):
        """Register channel-level config defaults."""
        self._defaults['channel'].update(defaults)

    def register_role(self, **defaults):
        """Register role-level config defaults."""
        self._defaults['role'].update(defaults)

    def register_global(self, **defaults):
        """Register global config defaults."""
        self._defaults['global'].update(defaults)

    def guild(self, guild):
        """Get guild-level config accessor."""
        guild_id = guild.id if hasattr(guild, 'id') else guild
        return MockConfigGroup(self._data['guild'], self._defaults['guild'], guild_id)

    def member(self, member):
        """Get member-level config accessor."""
        member_id = member.id if hasattr(member, 'id') else member
        guild_id = member.guild.id if hasattr(member, 'guild') else 0
        key = (guild_id, member_id)
        return MockConfigGroup(self._data['member'], self._defaults['member'], key)

    def user(self, user):
        """Get user-level config accessor."""
        user_id = user.id if hasattr(user, 'id') else user
        return MockConfigGroup(self._data['user'], self._defaults['user'], user_id)

    def channel(self, channel):
        """Get channel-level config accessor."""
        channel_id = channel.id if hasattr(channel, 'id') else channel
        return MockConfigGroup(self._data['channel'], self._defaults['channel'], channel_id)

    def role(self, role):
        """Get role-level config accessor."""
        role_id = role.id if hasattr(role, 'id') else role
        return MockConfigGroup(self._data['role'], self._defaults['role'], role_id)

    async def clear_all_guilds(self):
        """Clear all guild data."""
        self._data['guild'].clear()

    async def clear_all_members(self):
        """Clear all member data."""
        self._data['member'].clear()

    async def clear_all_users(self):
        """Clear all user data."""
        self._data['user'].clear()


class MockConfigGroup:
    """Mock config group for a specific scope and identifier."""

    def __init__(self, data: dict, defaults: dict, identifier):
        self._data = data
        self._defaults = defaults
        self._id = identifier

        # Ensure this identifier exists in data
        if identifier not in self._data:
            self._data[identifier] = {}

    async def all(self) -> dict:
        """Get all config data for this identifier."""
        # Merge defaults with actual data
        result = dict(self._defaults)
        result.update(self._data[self._id])
        return result

    async def set(self, value: dict):
        """Set all config data for this identifier."""
        self._data[self._id] = value

    async def clear(self):
        """Clear all config data for this identifier."""
        self._data[self._id] = {}

    def __call__(self):
        """Allow calling the group to get a sub-accessor."""
        return self

    def __getattr__(self, item: str):
        """Get a specific config attribute."""
        return MockConfigAttribute(self._data, self._defaults, self._id, item)


class MockConfigAttribute:
    """Mock config attribute accessor."""

    def __init__(self, data: dict, defaults: dict, identifier, attribute: str):
        self._data = data
        self._defaults = defaults
        self._id = identifier
        self._attr = attribute

    async def __call__(self) -> Any:
        """Get the value of this attribute."""
        if self._id not in self._data:
            self._data[self._id] = {}

        if self._attr in self._data[self._id]:
            return self._data[self._id][self._attr]

        return self._defaults.get(self._attr)

    async def set(self, value: Any):
        """Set the value of this attribute."""
        if self._id not in self._data:
            self._data[self._id] = {}
        self._data[self._id][self._attr] = value

    async def clear(self):
        """Clear the value of this attribute."""
        if self._id in self._data and self._attr in self._data[self._id]:
            del self._data[self._id][self._attr]


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest.fixture
def bot():
    """Fixture providing a mock Discord bot."""
    return MockBot()


@pytest.fixture
def guild():
    """Fixture providing a mock Discord guild."""
    return MockGuild(id=123, name="TestGuild")


@pytest.fixture
def member(guild):
    """Fixture providing a mock Discord member."""
    member = MockMember(id=456, name="TestUser")
    member.guild = guild
    guild.members.append(member)
    return member


@pytest.fixture
def channel(guild):
    """Fixture providing a mock Discord text channel."""
    return MockTextChannel(id=789, name="test-channel", guild=guild)


@pytest.fixture
def ctx(bot, guild, member, channel):
    """Fixture providing a mock Discord command context."""
    return MockContext(guild=guild, author=member, channel=channel, bot=bot)


@pytest.fixture
def interaction(member, guild, channel):
    """Fixture providing a mock Discord interaction."""
    return MockInteraction(user=member, guild=guild, channel=channel)


@pytest.fixture
def mock_config():
    """Fixture providing a mock Red-DiscordBot Config object."""
    return MockConfig("TestCog")


@pytest.fixture
async def setup_config(mock_config, guild):
    """
    Fixture to set up common config structure for testing.

    Provides a pre-configured config with typical guild defaults.
    """
    mock_config.register_guild(
        enabled=True,
        data={},
    )
    return mock_config


# ============================================================================
# Helper Functions
# ============================================================================

def create_mock_member(user_id: int, username: str, guild=None) -> MockMember:
    """Helper function to create a mock member."""
    member = MockMember(id=user_id, name=username)
    if guild:
        member.guild = guild
        guild.members.append(member)
    return member


def create_mock_role(role_id: int, name: str, guild=None) -> MockRole:
    """Helper function to create a mock role."""
    role = MockRole(id=role_id, name=name)
    if guild:
        guild.roles.append(role)
    return role


async def wait_for_tasks():
    """Wait for all pending asyncio tasks to complete."""
    await asyncio.sleep(0)
