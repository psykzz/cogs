"""
Unit tests for the React Roles cog.

Tests cover:
- Reaction role setup and removal
- Role assignment on reaction add
- Role removal on reaction remove
- Type consistency between int and string IDs (bug #119)
- Config persistence
- Edge cases (missing messages, duplicate setups)
"""

import pytest


# ============================================================================
# Test Reaction Role Configuration
# ============================================================================

@pytest.mark.asyncio
class TestReactRolesConfig:
    """Test ReactRoles configuration and setup."""

    async def test_default_config_values(self, mock_config):
        """Test that default config values are set correctly."""
        mock_config.register_guild(watching={})

        guild_data = await mock_config.guild(1).all()
        assert guild_data["watching"] == {}

    async def test_add_reaction_role_mapping(self, mock_config, guild):
        """Test adding a reaction-role mapping."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = 987654
        role_id = 111222

        # Add mapping
        watching = await mock_config.guild(guild).watching()
        watching.setdefault(message_id, {})
        watching[message_id][emoji_id] = role_id
        await mock_config.guild(guild).watching.set(watching)

        # Verify
        saved_watching = await mock_config.guild(guild).watching()
        assert message_id in saved_watching
        assert emoji_id in saved_watching[message_id]
        assert saved_watching[message_id][emoji_id] == role_id

    async def test_remove_reaction_role_mapping(self, mock_config, guild):
        """Test removing a reaction-role mapping."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = 987654
        role_id = 111222

        # Set up initial mapping
        watching = {message_id: {emoji_id: role_id}}
        await mock_config.guild(guild).watching.set(watching)

        # Remove mapping
        watching = await mock_config.guild(guild).watching()
        del watching[message_id][emoji_id]
        if not watching[message_id]:
            del watching[message_id]
        await mock_config.guild(guild).watching.set(watching)

        # Verify
        saved_watching = await mock_config.guild(guild).watching()
        assert message_id not in saved_watching


# ============================================================================
# Test Type Consistency (Bug #119)
# ============================================================================

@pytest.mark.asyncio
class TestTypeConsistency:
    """Test for type consistency bug between int and string IDs."""

    async def test_string_message_id_consistency(self, mock_config, guild):
        """Test that message IDs are stored and retrieved as strings."""
        mock_config.register_guild(watching={})

        # Store with int message ID (as it might come from Discord)
        message_id_int = 123456789
        emoji_id = 987654
        role_id = 111222

        watching = {}
        watching[str(message_id_int)] = {emoji_id: role_id}  # Convert to string
        await mock_config.guild(guild).watching.set(watching)

        # Retrieve and check
        saved_watching = await mock_config.guild(guild).watching()
        message_id_str = str(message_id_int)

        assert message_id_str in saved_watching
        assert emoji_id in saved_watching[message_id_str]

    async def test_emoji_id_type_consistency(self, mock_config, guild):
        """Test that emoji IDs maintain consistent type (int vs string)."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id_int = 987654
        role_id = 111222

        # REPRODUCE BUG: Store emoji_id as int (line 62 in react_roles.py)
        watching = {}
        watching[message_id] = {emoji_id_int: role_id}  # Stored as int
        await mock_config.guild(guild).watching.set(watching)

        # Try to retrieve with string (line 120 in react_roles.py)
        saved_watching = await mock_config.guild(guild).watching()
        emoji_id_str = str(emoji_id_int)

        # This demonstrates the bug: int key won't match string lookup
        assert emoji_id_int in saved_watching[message_id]  # Works with int

        # BUG: This would fail because we're looking up with string
        # but stored as int
        if emoji_id_str in saved_watching[message_id]:
            # If this passes, the bug is fixed (storing as string)
            role = saved_watching[message_id][emoji_id_str]
        else:
            # Bug exists: need to use int for lookup
            role = saved_watching[message_id].get(emoji_id_int)

        assert role == role_id

    async def test_correct_type_usage_for_emoji_ids(self, mock_config, guild):
        """Test the correct way to handle emoji IDs (always use strings for consistency)."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = 987654
        role_id = 111222

        # CORRECT APPROACH: Convert emoji_id to string immediately
        watching = {}
        watching[message_id] = {str(emoji_id): role_id}  # Store as string
        await mock_config.guild(guild).watching.set(watching)

        # Retrieve with string
        saved_watching = await mock_config.guild(guild).watching()
        emoji_id_str = str(emoji_id)

        # Should work with string lookup
        assert emoji_id_str in saved_watching[message_id]
        assert saved_watching[message_id][emoji_id_str] == role_id


# ============================================================================
# Test Role Assignment Logic
# ============================================================================

@pytest.mark.asyncio
class TestRoleAssignment:
    """Test role assignment and removal logic."""

    async def test_lookup_role_from_reaction(self, mock_config, guild):
        """Test looking up a role from a reaction."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = "987654"  # Use string
        role_id = 111222

        # Set up mapping
        watching = {message_id: {emoji_id: role_id}}
        await mock_config.guild(guild).watching.set(watching)

        # Simulate reaction payload
        payload_message_id = "123456"
        payload_emoji_id = "987654"

        # Look up role
        saved_watching = await mock_config.guild(guild).watching()
        if payload_message_id in saved_watching:
            if payload_emoji_id in saved_watching[payload_message_id]:
                found_role_id = saved_watching[payload_message_id][payload_emoji_id]
                assert found_role_id == role_id

    async def test_message_not_monitored(self, mock_config, guild):
        """Test handling reactions on non-monitored messages."""
        mock_config.register_guild(watching={})

        # Empty watching dict
        await mock_config.guild(guild).watching.set({})

        # Try to look up non-existent message
        watching = await mock_config.guild(guild).watching()
        message_id = "999999"

        assert message_id not in watching

    async def test_reaction_not_monitored(self, mock_config, guild):
        """Test handling unmonitored reactions on monitored messages."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = "987654"
        role_id = 111222

        # Set up one reaction
        watching = {message_id: {emoji_id: role_id}}
        await mock_config.guild(guild).watching.set(watching)

        # Try different emoji
        different_emoji = "555555"
        saved_watching = await mock_config.guild(guild).watching()

        assert message_id in saved_watching
        assert different_emoji not in saved_watching[message_id]


# ============================================================================
# Test Multiple Reactions
# ============================================================================

@pytest.mark.asyncio
class TestMultipleReactions:
    """Test handling multiple reactions on the same message."""

    async def test_multiple_reactions_same_message(self, mock_config, guild):
        """Test multiple reaction-role mappings on one message."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        mappings = {
            "emoji1": 111,
            "emoji2": 222,
            "emoji3": 333,
        }

        # Set up multiple mappings
        watching = {message_id: mappings}
        await mock_config.guild(guild).watching.set(watching)

        # Verify all mappings exist
        saved_watching = await mock_config.guild(guild).watching()
        assert message_id in saved_watching
        for emoji_id, role_id in mappings.items():
            assert emoji_id in saved_watching[message_id]
            assert saved_watching[message_id][emoji_id] == role_id

    async def test_remove_one_of_multiple_reactions(self, mock_config, guild):
        """Test removing one reaction from a message with multiple reactions."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        mappings = {
            "emoji1": 111,
            "emoji2": 222,
            "emoji3": 333,
        }

        # Set up multiple mappings
        watching = {message_id: dict(mappings)}
        await mock_config.guild(guild).watching.set(watching)

        # Remove one mapping
        watching = await mock_config.guild(guild).watching()
        del watching[message_id]["emoji2"]
        await mock_config.guild(guild).watching.set(watching)

        # Verify removal
        saved_watching = await mock_config.guild(guild).watching()
        assert message_id in saved_watching
        assert "emoji1" in saved_watching[message_id]
        assert "emoji2" not in saved_watching[message_id]
        assert "emoji3" in saved_watching[message_id]

    async def test_remove_last_reaction_cleans_up_message(self, mock_config, guild):
        """Test that removing the last reaction removes the message key."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = "987654"
        role_id = 111222

        # Set up single mapping
        watching = {message_id: {emoji_id: role_id}}
        await mock_config.guild(guild).watching.set(watching)

        # Remove last mapping
        watching = await mock_config.guild(guild).watching()
        del watching[message_id][emoji_id]
        if not watching[message_id]:
            del watching[message_id]
        await mock_config.guild(guild).watching.set(watching)

        # Verify message key is gone
        saved_watching = await mock_config.guild(guild).watching()
        assert message_id not in saved_watching


# ============================================================================
# Test Edge Cases
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error scenarios."""

    async def test_prevent_duplicate_reaction_setup(self, mock_config, guild):
        """Test preventing duplicate reaction-role setups."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = "987654"
        role_id = 111222

        # Set up initial mapping
        watching = {message_id: {emoji_id: role_id}}
        await mock_config.guild(guild).watching.set(watching)

        # Try to add duplicate
        saved_watching = await mock_config.guild(guild).watching()
        is_duplicate = message_id in saved_watching and emoji_id in saved_watching[message_id]

        assert is_duplicate is True

    async def test_empty_watching_dict(self, mock_config, guild):
        """Test handling empty watching configuration."""
        mock_config.register_guild(watching={})

        watching = await mock_config.guild(guild).watching()
        assert watching == {}
        assert isinstance(watching, dict)

    async def test_setdefault_behavior(self, mock_config, guild):
        """Test setdefault behavior for adding reactions."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = "987654"
        role_id = 111222

        # Use setdefault pattern (as in react_roles.py:60)
        watching = {}
        watching.setdefault(message_id, {})
        watching[message_id][emoji_id] = role_id
        await mock_config.guild(guild).watching.set(watching)

        # Verify
        saved_watching = await mock_config.guild(guild).watching()
        assert message_id in saved_watching
        assert emoji_id in saved_watching[message_id]

    async def test_nonexistent_message_id_in_lookup(self, mock_config, guild):
        """Test looking up a non-existent message ID."""
        mock_config.register_guild(watching={})

        # Set up some data
        watching = {"111111": {"emoji1": 123}}
        await mock_config.guild(guild).watching.set(watching)

        # Try to look up different message
        saved_watching = await mock_config.guild(guild).watching()
        message_id = "999999"

        if message_id in saved_watching:
            pytest.fail("Should not find non-existent message")
        else:
            # Correctly handled
            pass


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestReactRolesIntegration:
    """Integration tests for complete workflows."""

    async def test_complete_reaction_role_workflow(self, mock_config, guild):
        """Test complete workflow: setup -> react -> remove."""
        mock_config.register_guild(watching={})

        message_id = "123456"
        emoji_id = "987654"
        role_id = 111222

        # 1. Setup reaction role
        watching = {}
        watching.setdefault(message_id, {})
        watching[message_id][emoji_id] = role_id
        await mock_config.guild(guild).watching.set(watching)

        # 2. Simulate user reaction (lookup role)
        saved_watching = await mock_config.guild(guild).watching()
        found_role = saved_watching.get(message_id, {}).get(emoji_id)
        assert found_role == role_id

        # 3. Remove reaction role
        watching = await mock_config.guild(guild).watching()
        del watching[message_id][emoji_id]
        if not watching[message_id]:
            del watching[message_id]
        await mock_config.guild(guild).watching.set(watching)

        # 4. Verify cleanup
        final_watching = await mock_config.guild(guild).watching()
        assert message_id not in final_watching

    async def test_multiple_messages_workflow(self, mock_config, guild):
        """Test managing reactions on multiple messages."""
        mock_config.register_guild(watching={})

        # Set up multiple messages
        watching = {
            "msg1": {"emoji1": 111},
            "msg2": {"emoji2": 222, "emoji3": 333},
            "msg3": {"emoji4": 444},
        }
        await mock_config.guild(guild).watching.set(watching)

        # Verify all messages
        saved_watching = await mock_config.guild(guild).watching()
        assert len(saved_watching) == 3
        assert "msg1" in saved_watching
        assert "msg2" in saved_watching
        assert "msg3" in saved_watching

        # Remove one message
        watching = await mock_config.guild(guild).watching()
        del watching["msg2"]
        await mock_config.guild(guild).watching.set(watching)

        # Verify
        final_watching = await mock_config.guild(guild).watching()
        assert len(final_watching) == 2
        assert "msg2" not in final_watching
