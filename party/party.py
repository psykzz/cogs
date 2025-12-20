import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import discord
from redbot.core import Config, checks, commands, modlog

log = logging.getLogger("red.cog.party")

IDENTIFIER = 2847102938475019

# Discord embed field character limit
EMBED_FIELD_MAX_LENGTH = 1024


class RoleSelectionModal(discord.ui.Modal):
    """Modal for selecting a role when signing up for a party (for freeform entry)."""

    def __init__(self, party_id: str, predefined_roles: list, cog):
        super().__init__(title="Enter Your Role")
        self.party_id = party_id
        self.predefined_roles = predefined_roles
        self.cog = cog

        # Create the role input field
        if predefined_roles:
            # Build placeholder with truncation to respect Discord's 100-char limit
            roles_text = ', '.join(predefined_roles)
            prefix = "Choose from: "
            suffix = ""
            max_roles_length = 100 - len(prefix) - len(suffix)

            if len(roles_text) <= max_roles_length:
                placeholder = f"{prefix}{roles_text}{suffix}"
            else:
                # Truncate at word boundary (last comma) to avoid splitting role names
                truncate_at = max_roles_length - 3
                if truncate_at > 0:
                    last_comma = roles_text.rfind(', ', 0, truncate_at)
                    if last_comma > 0:
                        truncated_roles = roles_text[:last_comma] + "..."
                    else:
                        # No comma found, truncate at character boundary
                        truncated_roles = roles_text[:truncate_at] + "..."
                else:
                    # Not enough space, just use ellipsis
                    truncated_roles = "..."
                placeholder = f"{prefix}{truncated_roles}{suffix}"

            label = "Your Role"
        else:
            placeholder = "Enter your role"
            label = "Your Role"

        self.role_input = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=100,
        )
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        role = self.role_input.value.strip()

        # Validate that the role is in the predefined list
        if self.predefined_roles and role not in self.predefined_roles:
            # Truncate role list in error message to avoid exceeding Discord's limit
            roles_list = ', '.join(self.predefined_roles)
            if len(roles_list) > 100:
                # Show first few roles with ellipsis
                roles_list = roles_list[:97] + "..."
            await interaction.followup.send(
                f"❌ Invalid role. Please choose from: {roles_list}",
                ephemeral=True
            )
            return

        # Add the user to the party with the selected role
        # Note: Modals don't have persistent UI components, so no view cleanup needed
        await self.cog.signup_user(interaction, self.party_id, role, disabled_view=None, deferred=True)


class EditPartyModal(discord.ui.Modal):
    """Modal for editing party title and description."""

    def __init__(self, party_id: str, party: dict, cog):
        super().__init__(title="Edit Party")
        self.party_id = party_id
        self.cog = cog

        # Title input
        self.title_input = discord.ui.TextInput(
            label="Party Title",
            placeholder="Enter the party title",
            default=party['name'],
            required=True,
            max_length=100,
        )
        self.add_item(self.title_input)

        # Description input
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Enter party description (optional)",
            default=party.get('description') or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        new_title = self.title_input.value.strip()
        new_description = self.description_input.value.strip() or None

        # Update the party data
        async with self.cog.config.guild(interaction.guild).parties() as parties:
            if self.party_id not in parties:
                await interaction.followup.send("❌ Party not found.", ephemeral=True)
                return

            old_title = parties[self.party_id]['name']
            old_description = parties[self.party_id].get('description')

            parties[self.party_id]['name'] = new_title
            parties[self.party_id]['description'] = new_description

        # Update the party message
        await self.cog.update_party_message(interaction.guild.id, self.party_id)

        # Create modlog entry
        reason = (
            f"Party '{old_title}' (ID: {self.party_id}) edited.\n"
            f"New title: {new_title}\n"
            f"Old description: {old_description or 'None'}\n"
            f"New description: {new_description or 'None'}"
        )
        await self.cog.create_party_modlog(
            interaction.guild,
            "party_edit",
            interaction.user,
            reason
        )

        await interaction.followup.send(
            "✅ Party updated successfully!",
            ephemeral=True
        )


class CreatePartyModal(discord.ui.Modal):
    """Modal for creating a new party without command arguments."""

    def __init__(self, cog):
        super().__init__(title="Create New Party")
        self.cog = cog

        # Title input
        self.title_input = discord.ui.TextInput(
            label="Party Title",
            placeholder="Enter the party title (e.g., Raid Night)",
            required=True,
            max_length=100,
        )
        self.add_item(self.title_input)

        # Description input
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Enter party description",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        self.add_item(self.description_input)

        # Roles input (one per line)
        self.roles_input = discord.ui.TextInput(
            label="Roles (one per line, max 25)",
            placeholder="Tank\nHealer\nDPS\nSupport",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.add_item(self.roles_input)

        # Allow multiple signups per role
        self.allow_multiple_input = discord.ui.TextInput(
            label="Allow Multiple Per Role? (yes/no)",
            placeholder="yes",
            required=False,
            max_length=3,
            default="yes",
        )
        self.add_item(self.allow_multiple_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        title = self.title_input.value.strip()
        description = self.description_input.value.strip() or None
        roles_text = self.roles_input.value.strip()
        allow_multiple_text = self.allow_multiple_input.value

        # Parse and validate allow_multiple setting
        allow_multiple, error = Party.parse_allow_multiple(allow_multiple_text)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Parse roles from text
        unique_roles = Party.parse_roles_from_text(roles_text)

        # Validate roles
        error = Party.validate_roles(unique_roles)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Generate a unique party ID
        party_id = secrets.token_hex(4)

        # Create party data
        party = {
            "id": party_id,
            "name": title,
            "description": description,
            "author_id": interaction.user.id,
            "roles": unique_roles,
            "signups": {},
            "allow_multiple_per_role": allow_multiple,
            "allow_freeform": False,
            "channel_id": None,
            "message_id": None,
        }

        # Initialize signups for each predefined role
        for role in unique_roles:
            party["signups"][role] = []

        # Save the party
        async with self.cog.config.guild(interaction.guild).parties() as parties:
            parties[party_id] = party

        # Create the party embed
        embed = await self.cog.create_party_embed(party, interaction.guild)

        # Create the view with buttons
        view = PartyView(party_id, self.cog)

        # Send the message to the channel where the interaction occurred
        channel = interaction.channel
        message = await channel.send(embed=embed, view=view)

        # Save the message ID and channel ID
        async with self.cog.config.guild(interaction.guild).parties() as parties:
            parties[party_id]["message_id"] = message.id
            parties[party_id]["channel_id"] = channel.id

        # Create modlog entry
        await self.cog.create_party_modlog(
            interaction.guild,
            "party_create",
            interaction.user,
            f"Party '{title}' (ID: {party_id}) created with {len(unique_roles)} role(s) via modal."
        )

        # Respond to the interaction
        await interaction.followup.send(
            f"✅ Party created! ID: `{party_id}`",
            ephemeral=True
        )


class EditPartyFullModal(discord.ui.Modal):
    """Modal for editing all party settings including roles."""

    def __init__(self, party_id: str, party: dict, cog):
        super().__init__(title="Edit Party")
        self.party_id = party_id
        self.cog = cog

        # Title input
        self.title_input = discord.ui.TextInput(
            label="Party Title",
            placeholder="Enter the party title",
            default=party['name'],
            required=True,
            max_length=100,
        )
        self.add_item(self.title_input)

        # Description input
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Enter party description",
            default=party.get('description') or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        self.add_item(self.description_input)

        # Roles input (one per line)
        roles_text = '\n'.join(party.get('roles', []))
        self.roles_input = discord.ui.TextInput(
            label="⚠️ Roles (one per line, max 25)",
            placeholder="Tank\nHealer\nDPS\n\n⚠️ Removing roles will clear those signups",
            default=roles_text,
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.add_item(self.roles_input)

        # Allow multiple signups per role
        allow_multiple_default = "yes" if party.get("allow_multiple_per_role", True) else "no"
        self.allow_multiple_input = discord.ui.TextInput(
            label="Allow Multiple Per Role? (yes/no)",
            placeholder="yes or no",
            default=allow_multiple_default,
            required=False,
            max_length=3,
        )
        self.add_item(self.allow_multiple_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        new_title = self.title_input.value.strip()
        new_description = self.description_input.value.strip() or None
        roles_text = self.roles_input.value.strip()
        allow_multiple_text = self.allow_multiple_input.value

        # Parse and validate allow_multiple setting
        allow_multiple, error = Party.parse_allow_multiple(allow_multiple_text)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Parse roles from text
        unique_roles = Party.parse_roles_from_text(roles_text)

        # Validate roles
        error = Party.validate_roles(unique_roles)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Update the party data
        async with self.cog.config.guild(interaction.guild).parties() as parties:
            if self.party_id not in parties:
                await interaction.followup.send("❌ Party not found.", ephemeral=True)
                return

            old_title = parties[self.party_id]['name']
            old_description = parties[self.party_id].get('description')
            old_roles = parties[self.party_id].get('roles', [])
            old_allow_multiple = parties[self.party_id].get('allow_multiple_per_role', True)

            parties[self.party_id]['name'] = new_title
            parties[self.party_id]['description'] = new_description
            parties[self.party_id]['roles'] = unique_roles
            parties[self.party_id]['allow_multiple_per_role'] = allow_multiple

            # Handle role changes: preserve signups for roles that still exist
            old_signups = parties[self.party_id].get('signups', {})
            new_signups = {}

            # Track users whose roles were removed (for DM notifications)
            removed_role_users = {}  # role -> list of user_ids

            # Keep signups for roles that are still in the list
            for role in unique_roles:
                if role in old_signups:
                    new_signups[role] = old_signups[role]
                else:
                    new_signups[role] = []

            # Identify removed roles and their users
            for role, users in old_signups.items():
                if role not in unique_roles and users:
                    # This role was removed, track the users
                    removed_role_users[role] = users.copy()

            parties[self.party_id]['signups'] = new_signups

            # Store party message info for DM link
            channel_id = parties[self.party_id].get('channel_id')
            message_id = parties[self.party_id].get('message_id')

        # Send success message to user immediately after data update
        try:
            await interaction.followup.send(
                "✅ Party updated successfully!",
                ephemeral=True
            )
        except discord.errors.NotFound:
            # Interaction expired, log but continue with remaining tasks
            log.warning(f"Interaction expired before sending confirmation for party {self.party_id}")

        # Update the party message (after responding to user)
        await self.cog.update_party_message(interaction.guild.id, self.party_id)

        # Create modlog entry
        changes = []
        if old_title != new_title:
            changes.append(f"Title: '{old_title}' → '{new_title}'")
        if old_description != new_description:
            changes.append(f"Description: '{old_description or 'None'}' → '{new_description or 'None'}'")
        if old_roles != unique_roles:
            changes.append(f"Roles: {old_roles} → {unique_roles}")
            if removed_role_users:
                total_notified = sum(len(users) for users in removed_role_users.values())
                changes.append(f"Removed roles affected {total_notified} user(s), DMs will be sent")
        if old_allow_multiple != allow_multiple:
            changes.append(f"Allow Multiple: {old_allow_multiple} → {allow_multiple}")

        reason = f"Party '{old_title}' (ID: {self.party_id}) edited.\n" + "\n".join(changes)

        await self.cog.create_party_modlog(
            interaction.guild,
            "party_edit",
            interaction.user,
            reason
        )

        # Send DMs to users whose roles were removed (after modlog entry)
        if removed_role_users:
            party_name = new_title
            # Build jump URL for the party message
            party_link = ""
            if channel_id and message_id:
                jump_url = (
                    f"https://discord.com/channels/"
                    f"{interaction.guild.id}/{channel_id}/{message_id}"
                )
                party_link = f"\n\n[View Party Message]({jump_url})"
            for role, user_ids in removed_role_users.items():
                for user_id_str in user_ids:
                    try:
                        user_id = int(user_id_str)
                        user = await self.cog.bot.fetch_user(user_id)
                        if user:
                            try:
                                await user.send(
                                    f"⚠️ Your role **{role}** has been removed from the party "
                                    f"**{party_name}** in **{interaction.guild.name}**.\n\n"
                                    f"Your signup has been cleared. Please sign up again if you'd like to participate."
                                    f"{party_link}"
                                )
                            except discord.Forbidden:
                                # User has DMs disabled, skip silently
                                pass
                            except discord.HTTPException:
                                # Other Discord API errors, skip silently
                                pass
                    except (ValueError, discord.NotFound):
                        # Invalid user ID or user not found, skip
                        pass


class RoleSelectView(discord.ui.View):
    """View with a select menu for choosing predefined roles."""

    def __init__(self, party_id: str, roles: list, cog):
        super().__init__(timeout=180)  # 3 minute timeout for ephemeral view
        self.party_id = party_id
        self.cog = cog

        # Create select menu with role options (max 25 options)
        options = [
            discord.SelectOption(label=role, value=role)
            for role in roles[:25]  # Discord limit
        ]

        self.role_select = discord.ui.Select(
            placeholder="Choose your role...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.role_select.callback = self.select_callback
        self.add_item(self.role_select)

    async def select_callback(self, interaction: discord.Interaction):
        """Handle role selection from dropdown."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        selected_role = self.role_select.values[0]

        # Disable all components in the view after selection
        for item in self.children:
            item.disabled = True

        # Sign up the user (this will handle the interaction response)
        await self.cog.signup_user(interaction, self.party_id, selected_role, disabled_view=self, deferred=True)


class PartyView(discord.ui.View):
    """Persistent view for party signup buttons."""

    def __init__(self, party_id: str, cog):
        super().__init__(timeout=None)
        self.party_id = party_id
        self.cog = cog

    @discord.ui.button(label="Sign Up", style=discord.ButtonStyle.green, custom_id="party_signup", emoji="✅")
    async def signup_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle signup button click."""
        # Get party data
        party = await self.cog.get_party(interaction.guild.id, self.party_id)
        if not party:
            # Defer for error case to prevent timeout
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send("❌ Party not found.", ephemeral=True)
            return

        # Check if user is already signed up
        user_id = str(interaction.user.id)
        current_role = None
        for role_name, users in party["signups"].items():
            if user_id in users:
                current_role = role_name
                break

        roles = party["roles"]

        # Validate that roles are defined
        if not roles:
            # Defer for error case to prevent timeout
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                "❌ This party has no roles defined. Please contact the party creator.",
                ephemeral=True
            )
            return

        if current_role:
            # User is already signed up
            message = (
                f"You're already signed up as **{current_role}**. "
                f"Select a new role to update or use the Leave button to leave the party."
            )
        else:
            message = "Select your role:"

        # Always use select menu (max 25 roles enforced at creation)
        # Note: Cannot defer here as we need to send a view with response.send_message
        view = RoleSelectView(self.party_id, roles, self.cog)
        await interaction.response.send_message(
            message,
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red, custom_id="party_leave", emoji="❌")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle leave button click."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        result = await self.cog.leave_party(interaction.guild.id, self.party_id, interaction.user.id)
        if result:
            await interaction.followup.send("✅ You've left the party.", ephemeral=True)
            await self.cog.update_party_message(interaction.guild.id, self.party_id)
        else:
            await interaction.followup.send("❌ You're not signed up for this party.", ephemeral=True)

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.gray, custom_id="party_edit", emoji="✏️", row=1)
    async def edit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle edit button click (admin/owner only)."""
        # Get party data
        party = await self.cog.get_party(interaction.guild.id, self.party_id)
        if not party:
            await interaction.response.send_message("❌ Party not found.", ephemeral=True)
            return

        # Check permissions
        is_author = party["author_id"] == interaction.user.id
        is_admin = interaction.user.guild_permissions.administrator

        if not (is_author or is_admin):
            await interaction.response.send_message(
                "❌ You don't have permission to edit this party.",
                ephemeral=True
            )
            return

        # Show the comprehensive edit modal with all settings
        modal = EditPartyFullModal(self.party_id, party, self.cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.gray, custom_id="party_delete", emoji="🗑️", row=1)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle delete button click (admin/owner only)."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        # Get party data
        party = await self.cog.get_party(interaction.guild.id, self.party_id)
        if not party:
            await interaction.followup.send("❌ Party not found.", ephemeral=True)
            return

        # Check permissions
        is_author = party["author_id"] == interaction.user.id
        is_admin = interaction.user.guild_permissions.administrator

        if not (is_author or is_admin):
            await interaction.followup.send(
                "❌ You don't have permission to delete this party.",
                ephemeral=True
            )
            return

        # Delete the party
        async with self.cog.config.guild(interaction.guild).parties() as parties:
            del parties[self.party_id]

        # Try to delete the message
        channel_id = party.get("channel_id")
        message_id = party.get("message_id")

        if channel_id and message_id:
            channel = self.cog.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

        # Create modlog entry
        await self.cog.create_party_modlog(
            interaction.guild,
            "party_delete",
            interaction.user,
            f"Party '{party['name']}' (ID: {self.party_id}) deleted."
        )

        await interaction.followup.send(
            f"✅ Party `{self.party_id}` ({party['name']}) deleted.",
            ephemeral=True
        )


class Party(commands.Cog):
    """Create and manage party signups with role compositions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER)

        default_guild = {
            "parties": {},  # party_id -> party data
            "allow_multiple_per_role": True,  # Guild-wide default
        }
        self.config.register_guild(**default_guild)

        # Load persistent views for existing parties
        self.bot.loop.create_task(self._register_persistent_views())
        # Register custom modlog casetypes
        self.bot.loop.create_task(self._register_casetypes())

    @staticmethod
    def parse_allow_multiple(allow_multiple_text: str) -> tuple[bool, Optional[str]]:
        """Parse and validate allow_multiple_per_role setting.

        Args:
            allow_multiple_text: User input for allow_multiple setting

        Returns:
            Tuple of (parsed_value, error_message). Error message is None if valid.
        """
        allow_multiple_text = allow_multiple_text.strip().lower()
        allow_multiple = allow_multiple_text in ["yes", "true", "y", "1", ""]

        # Validate the input
        if allow_multiple_text and allow_multiple_text not in ["yes", "no", "true", "false", "y", "n", "1", "0", ""]:
            return False, "❌ Invalid value for 'Allow Multiple Per Role'. Use 'yes' or 'no'."

        return allow_multiple, None

    @staticmethod
    def parse_roles_from_text(roles_text: str) -> list[str]:
        """Parse roles from multiline text, removing duplicates while preserving order.

        Args:
            roles_text: Multiline text with one role per line

        Returns:
            List of unique role names
        """
        # Parse roles (one per line)
        roles_list = [line.strip() for line in roles_text.split('\n') if line.strip()]

        # Remove duplicates while preserving order
        seen = set()
        unique_roles = []
        for role in roles_list:
            if role and role not in seen:
                seen.add(role)
                unique_roles.append(role)

        return unique_roles

    @staticmethod
    def validate_roles(roles: list[str]) -> Optional[str]:
        """Validate role list meets requirements.

        Args:
            roles: List of role names

        Returns:
            Error message if invalid, None if valid
        """
        if not roles:
            return "❌ You must specify at least one role for the party."

        if len(roles) > 25:
            return f"❌ You can specify a maximum of 25 roles per party. You provided {len(roles)} roles."

        return None

    async def _register_casetypes(self):
        """Register custom modlog case types for party events."""
        await self.bot.wait_until_ready()
        try:
            # Register party creation case type
            await modlog.register_casetype(
                name="party_create",
                default_setting=True,
                image="🎉",
                case_str="Party Created"
            )
            # Register party edit case type
            await modlog.register_casetype(
                name="party_edit",
                default_setting=True,
                image="✏️",
                case_str="Party Edited"
            )
            # Register party delete case type
            await modlog.register_casetype(
                name="party_delete",
                default_setting=True,
                image="🗑️",
                case_str="Party Deleted"
            )
        except RuntimeError:
            # Case types already registered
            pass

    async def create_party_modlog(self, guild: discord.Guild, action_type: str, moderator: discord.Member, reason: str):
        """Create a modlog entry for party actions."""
        try:
            await modlog.create_case(
                self.bot,
                guild,
                datetime.now(timezone.utc),
                action_type,
                moderator,  # The moderator is the user/target for party actions
                moderator,
                reason
            )
        except Exception as e:
            log.error(f"Failed to create modlog entry: {e}")

    async def _register_persistent_views(self):
        """Register persistent views for existing parties."""
        await self.bot.wait_until_ready()
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            parties = guild_data.get("parties", {})
            for party_id in parties:
                view = PartyView(party_id, self)
                self.bot.add_view(view)
                log.debug(f"Registered persistent view for party {party_id}")

    def _get_user_mentions(self, user_ids):
        """Convert user IDs to Discord mentions, filtering out invalid IDs.

        Validates that IDs are positive integers. Discord will gracefully handle
        invalid snowflakes by not making them clickable, so we only need to
        ensure they're positive integers to prevent obvious errors.

        Args:
            user_ids: List of user IDs (strings or integers)

        Returns:
            List of Discord mention strings
        """
        mentions = []
        for user_id in user_ids:
            # Handle both string and integer user IDs
            try:
                # Convert to int to validate it's a positive integer
                user_id_int = int(user_id)
                if user_id_int > 0:
                    mentions.append(f"<@{user_id_int}>")
            except (TypeError, ValueError):
                # Skip invalid user IDs silently
                continue
        return mentions

    async def _get_user_display_name(self, user_id: int, guild: discord.Guild = None) -> str:
        """Get the display name for a user.

        Args:
            user_id: The Discord user ID
            guild: Optional guild to get member display name from

        Returns:
            The user's display name, username, or "Unknown User" as fallback
        """
        if guild:
            # Try to get member from guild (includes display name/nickname)
            member = guild.get_member(user_id)
            if member:
                return member.display_name

        # Try to fetch user from bot cache/API
        try:
            user = self.bot.get_user(user_id)
            if not user:
                user = await self.bot.fetch_user(user_id)
            if user:
                return user.name
        except (discord.NotFound, discord.HTTPException):
            # User not found or API error, use fallback
            pass

        return "Unknown User"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Delete user data when requested."""
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            parties = guild_data.get("parties", {})
            modified = False
            for party_id, party in parties.items():
                user_id_str = str(user_id)
                for role_name, users in party.get("signups", {}).items():
                    if user_id_str in users:
                        parties[party_id]["signups"][role_name].remove(user_id_str)
                        modified = True
            if modified:
                await self.config.guild_from_id(guild_id).parties.set(parties)

    async def get_party(self, guild_id: int, party_id: str) -> Optional[dict]:
        """Get party data by ID."""
        parties = await self.config.guild_from_id(guild_id).parties()
        return parties.get(party_id)

    async def signup_user(
        self,
        interaction: discord.Interaction,
        party_id: str,
        role: str,
        disabled_view: Optional[discord.ui.View] = None,
        deferred: bool = False
    ):
        """Sign up a user for a party with a specific role.

        Args:
            interaction: The Discord interaction
            party_id: The party to sign up for
            role: The role to sign up as
            disabled_view: A pre-disabled view to include in the response message.
                          If provided, the original message will be edited instead of sending a new one.
                          If None, a new ephemeral message is sent.
            deferred: Whether the interaction has already been deferred. If True, uses followup/edit_original_response.
                     If False, uses response methods.
        """
        guild_id = interaction.guild.id
        user_id = str(interaction.user.id)

        async with self.config.guild_from_id(guild_id).parties() as parties:
            if party_id not in parties:
                if disabled_view:
                    # Edit the original message to show error and remove the select view
                    if deferred:
                        await interaction.edit_original_response(
                            content="❌ Party not found.",
                            view=None
                        )
                    else:
                        await interaction.response.edit_message(
                            content="❌ Party not found.",
                            view=None
                        )
                else:
                    if deferred:
                        await interaction.followup.send(
                            "❌ Party not found.",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            "❌ Party not found.",
                            ephemeral=True
                        )
                return

            party = parties[party_id]
            allow_multiple = party.get("allow_multiple_per_role", True)

            # Remove user from any existing role first
            for role_name, users in party["signups"].items():
                if user_id in users:
                    party["signups"][role_name].remove(user_id)

            # Check if role exists in signups, if not create it
            if role not in party["signups"]:
                party["signups"][role] = []

            # Check if multiple signups allowed
            if not allow_multiple and len(party["signups"][role]) > 0:
                if disabled_view:
                    # Edit the original message to show error and remove the select view
                    if deferred:
                        await interaction.edit_original_response(
                            content=f"❌ The role **{role}** is already full (multiple signups not allowed).",
                            view=None
                        )
                    else:
                        await interaction.response.edit_message(
                            content=f"❌ The role **{role}** is already full (multiple signups not allowed).",
                            view=None
                        )
                else:
                    if deferred:
                        await interaction.followup.send(
                            f"❌ The role **{role}** is already full (multiple signups not allowed).",
                            ephemeral=True
                        )
                    else:
                        await interaction.response.send_message(
                            f"❌ The role **{role}** is already full (multiple signups not allowed).",
                            ephemeral=True
                        )
                return

            # Add user to the role
            party["signups"][role].append(user_id)

        # Send success response
        if disabled_view:
            # Edit the original message to show success and remove the select view
            if deferred:
                await interaction.edit_original_response(
                    content=f"✅ You've signed up as **{role}**!",
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    content=f"✅ You've signed up as **{role}**!",
                    view=None
                )
        else:
            if deferred:
                await interaction.followup.send(
                    f"✅ You've signed up as **{role}**!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"✅ You've signed up as **{role}**!",
                    ephemeral=True
                )
        await self.update_party_message(guild_id, party_id)

    async def leave_party(self, guild_id: int, party_id: str, user_id: int) -> bool:
        """Remove a user from a party."""
        user_id_str = str(user_id)

        async with self.config.guild_from_id(guild_id).parties() as parties:
            if party_id not in parties:
                return False

            party = parties[party_id]
            removed = False

            for role_name, users in party["signups"].items():
                if user_id_str in users:
                    party["signups"][role_name].remove(user_id_str)
                    removed = True
                    break

            return removed

    async def update_party_message(self, guild_id: int, party_id: str):
        """Update the party message embed."""
        party = await self.get_party(guild_id, party_id)
        if not party:
            return

        # Get the channel and message
        channel_id = party.get("channel_id")
        message_id = party.get("message_id")

        if not channel_id or not message_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return

        # Build the updated embed (pass guild from channel if available)
        guild = getattr(channel, 'guild', None)
        embed = await self.create_party_embed(party, guild)

        # Update the message
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            log.error(f"Failed to update party message {message_id}")

    async def create_party_embed(self, party: dict, guild: discord.Guild = None) -> discord.Embed:
        """Create an embed for a party.

        Args:
            party: The party data dictionary
            guild: Optional guild object to resolve the owner's display name
        """
        embed = discord.Embed(
            title=f"🎉 {party['name']}",
            description=party.get("description", "Join the party by selecting your role!"),
            color=discord.Color.blue()
        )

        # Show roles and signups
        signups = party.get("signups", {})
        roles = party.get("roles", [])

        # Add each role as an inline field
        for role in roles:
            users = signups.get(role, [])
            user_mentions = self._get_user_mentions(users)
            if user_mentions:
                # Truncate field value if it exceeds Discord's limit
                value = ', '.join(user_mentions)
                if len(value) > EMBED_FIELD_MAX_LENGTH:
                    value = value[:EMBED_FIELD_MAX_LENGTH-3] + "..."
            else:
                value = "-"

            embed.add_field(name=role, value=value, inline=True)

        # Add roles that have signups but aren't in the predefined list (freeform roles)
        for role, users in signups.items():
            if role not in roles and users:
                user_mentions = self._get_user_mentions(users)
                if user_mentions:
                    value = ', '.join(user_mentions)
                    if len(value) > EMBED_FIELD_MAX_LENGTH:
                        value = value[:EMBED_FIELD_MAX_LENGTH-3] + "..."
                    embed.add_field(name=role, value=value, inline=True)

        # If no roles defined and no signups, show a message
        if not roles and not any(users for users in signups.values()):
            embed.add_field(name="Signups", value="-", inline=True)

        # Get owner name for footer
        owner_name = await self._get_user_display_name(party['author_id'], guild)

        # Set footer with party owner name and party ID
        embed.set_footer(text=f"Owner: {owner_name} | Party ID: {party['id']}")

        return embed

    @commands.group(autohelp=False)
    @commands.guild_only()
    async def party(self, ctx):
        """Party management commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @party.command(name="create")
    async def party_create(
        self,
        ctx,
        name: Optional[str] = None,
        *roles: str
    ):
        """Create a new party with predefined roles.

        Call without arguments to use an interactive modal form.
        Call with arguments to use the traditional command format.

        Users can only select from the specified roles.
        At least one role must be specified when using arguments.
        Roles can be separated by spaces or commas.

        Examples:
        - [p]party create  (opens interactive modal)
        - [p]party create "Raid Night" Tank Healer DPS
        - [p]party create "Raid Night" "Tank, Healer, DPS"
        - [p]party create "Game Night" Player1 Player2 Player3 Player4
        - [p]party create "PvP Team" Warrior, Mage, Archer
        - [p]party create "Siege" Siege Crossbow, Energy Shaper, GA
        """
        # If no arguments provided, show the modal
        if name is None:
            # Create and send the modal
            modal = CreatePartyModal(self)

            # We need to create an interaction to send the modal
            # Since we're in a text command context, we need to send a message first
            # that the user can interact with to trigger the modal
            view = discord.ui.View(timeout=300)  # 5 minute timeout

            async def modal_button_callback(interaction: discord.Interaction):
                await interaction.response.send_modal(modal)

            button = discord.ui.Button(
                label="Open Party Creation Form",
                style=discord.ButtonStyle.primary,
                emoji="📝"
            )
            button.callback = modal_button_callback
            view.add_item(button)

            await ctx.send(
                "Click the button below to open the party creation form:",
                view=view,
                delete_after=300  # Delete after 5 minutes
            )

            # Delete the command message
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

            return

        # Parse roles: join all arguments first, then split appropriately
        # This ensures multi-word roles like "Siege Crossbow" stay together
        # when separated by commas
        joined_roles = ' '.join(roles)

        # If commas are present, split by comma (allows multi-word roles)
        # Otherwise, split by whitespace (for backward compatibility)
        if ',' in joined_roles:
            # Split on comma and strip whitespace from each part
            parsed_roles = [r.strip() for r in joined_roles.split(',') if r.strip()]
        else:
            # Split on whitespace
            parsed_roles = [r.strip() for r in joined_roles.split() if r.strip()]

        # Remove any empty strings and duplicates while preserving order
        seen = set()
        roles_list = []
        for role in parsed_roles:
            if role and role not in seen:
                seen.add(role)
                roles_list.append(role)

        # Validate roles
        error = self.validate_roles(roles_list)
        if error:
            await ctx.send(error)
            return

        # Generate a unique party ID
        party_id = secrets.token_hex(4)

        # Get guild settings
        allow_multiple = await self.config.guild(ctx.guild).allow_multiple_per_role()

        # Create party data
        party = {
            "id": party_id,
            "name": name,
            "description": None,
            "author_id": ctx.author.id,
            "roles": roles_list,
            "signups": {},
            "allow_multiple_per_role": allow_multiple,
            "allow_freeform": False,  # Only allow predefined roles
            "channel_id": None,
            "message_id": None,
        }

        # Initialize signups for each predefined role
        for role in roles_list:
            party["signups"][role] = []

        # Save the party
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id] = party

        # Create the party embed
        embed = await self.create_party_embed(party, ctx.guild)

        # Create the view with buttons
        view = PartyView(party_id, self)

        # Send the message
        message = await ctx.send(embed=embed, view=view)

        # Save the message ID and channel ID
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id]["message_id"] = message.id
            parties[party_id]["channel_id"] = ctx.channel.id

        # Create modlog entry
        await self.create_party_modlog(
            ctx.guild,
            "party_create",
            ctx.author,
            f"Party '{name}' (ID: {party_id}) created with {len(roles_list)} role(s)."
        )

        await ctx.send(f"✅ Party created! ID: `{party_id}`", delete_after=10)

        # Delete the original command message
        try:
            await ctx.message.delete()
        except discord.NotFound:
            # Message already deleted
            pass
        except discord.Forbidden:
            # Bot doesn't have permission to delete messages
            pass

    @party.command(name="delete")
    async def party_delete(self, ctx, *, party_identifier: str):
        """Delete a party by ID or title.

        Only the party creator or server admins can delete a party.

        Examples:
        - [p]party delete abc123
        - [p]party delete Raid Night
        """
        parties = await self.config.guild(ctx.guild).parties()

        # First, try to find by exact party_id
        if party_identifier in parties:
            party_id = party_identifier
            party = parties[party_id]
        else:
            # Try to find by title (case-insensitive)
            matching_parties = []
            for pid, p in parties.items():
                if p["name"].lower() == party_identifier.lower():
                    matching_parties.append((pid, p))

            if not matching_parties:
                await ctx.send("❌ Party not found.")
                return
            elif len(matching_parties) > 1:
                # Multiple parties with the same title
                party_list = "\n".join([f"- `{pid}`: {p['name']}" for pid, p in matching_parties])
                await ctx.send(
                    f"❌ Multiple parties found with that title:\n{party_list}\n\n"
                    f"Please use the party ID to delete a specific one."
                )
                return
            else:
                # Exactly one match
                party_id, party = matching_parties[0]

        # Check permissions
        is_author = party["author_id"] == ctx.author.id
        is_admin = ctx.author.guild_permissions.administrator

        if not (is_author or is_admin):
            await ctx.send("❌ You don't have permission to delete this party.")
            return

        # Delete the party
        async with self.config.guild(ctx.guild).parties() as parties:
            del parties[party_id]

        # Try to delete the message
        channel_id = party.get("channel_id")
        message_id = party.get("message_id")

        if channel_id and message_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    await ctx.send("⚠️ Party deleted, but I couldn't delete the message (missing permissions).")
                    return

        # Create modlog entry
        await self.create_party_modlog(
            ctx.guild,
            "party_delete",
            ctx.author,
            f"Party '{party['name']}' (ID: {party_id}) deleted."
        )

        await ctx.send(f"✅ Party `{party_id}` ({party['name']}) deleted.")

    @party.command(name="list")
    async def party_list(self, ctx):
        """List all active parties in this server.

        Example: [p]party list
        """
        parties = await self.config.guild(ctx.guild).parties()

        if not parties:
            await ctx.send("No active parties in this server.")
            return

        embed = discord.Embed(
            title="🎉 Active Parties",
            color=discord.Color.blue()
        )

        for party_id, party in parties.items():
            total_signups = sum(len(users) for users in party["signups"].values())
            role_count = len(party["roles"]) if party["roles"] else "Freeform"

            # Build the link to the party message if available
            link_text = ""
            channel_id = party.get("channel_id")
            message_id = party.get("message_id")
            if channel_id and message_id:
                jump_url = (
                    f"https://discord.com/channels/"
                    f"{ctx.guild.id}/{channel_id}/{message_id}"
                )
                link_text = f"\n**[Jump to Party]({jump_url})**"

            value = (
                f"**ID**: `{party_id}`\n"
                f"**Roles**: {role_count}\n"
                f"**Signups**: {total_signups}\n"
                f"**Author**: <@{party['author_id']}>"
                f"{link_text}"
            )
            embed.add_field(name=party["name"], value=value, inline=True)

        await ctx.send(embed=embed)

    @party.command(name="config")
    @checks.admin_or_permissions(manage_guild=True)
    async def party_config(self, ctx, setting: str, value: str):
        """Configure party settings for this server.

        Settings:
        - allow_multiple_per_role: yes/no - Allow multiple users to signup for the same role

        Example: [p]party config allow_multiple_per_role yes
        """
        setting = setting.lower()

        if setting == "allow_multiple_per_role":
            if value.lower() in ["yes", "true", "1", "on"]:
                await self.config.guild(ctx.guild).allow_multiple_per_role.set(True)
                await ctx.send("✅ Multiple signups per role are now **allowed**.")
            elif value.lower() in ["no", "false", "0", "off"]:
                await self.config.guild(ctx.guild).allow_multiple_per_role.set(False)
                await ctx.send("✅ Multiple signups per role are now **disabled**.")
            else:
                await ctx.send("❌ Invalid value. Use yes/no.")
        else:
            await ctx.send(f"❌ Unknown setting: `{setting}`")

    @party.command(name="description")
    async def party_description(self, ctx, party_id: str, *, description: str):
        """Set the description for a party.

        Only the party creator or server admins can set the description.

        Example: [p]party description abc123 Join us for a fun raid tonight!
        """
        parties = await self.config.guild(ctx.guild).parties()

        if party_id not in parties:
            await ctx.send("❌ Party not found.")
            return

        party = parties[party_id]

        # Check permissions
        is_author = party["author_id"] == ctx.author.id
        is_admin = ctx.author.guild_permissions.administrator

        if not (is_author or is_admin):
            await ctx.send("❌ You don't have permission to modify this party.")
            return

        # Update description
        old_description = party.get("description")
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id]["description"] = description

        # Update the message
        await self.update_party_message(ctx.guild.id, party_id)

        # Create modlog entry
        reason = (
            f"Party '{party['name']}' (ID: {party_id}) description updated.\n"
            f"Old: {old_description or 'None'}\nNew: {description}"
        )
        await self.create_party_modlog(
            ctx.guild,
            "party_edit",
            ctx.author,
            reason
        )

        await ctx.send(f"✅ Description updated for party `{party_id}`.")

    @party.command(name="rename-option")
    async def party_rename_option(self, ctx, party_id: str, old_option: str, *, new_option: str):
        """Rename an option/role in a party.

        Only the party creator or server admins can rename options.

        Example: [p]party rename-option abc123 "Old Role" "New Role"
        """
        parties = await self.config.guild(ctx.guild).parties()

        if party_id not in parties:
            await ctx.send("❌ Party not found.")
            return

        party = parties[party_id]

        # Check permissions
        is_author = party["author_id"] == ctx.author.id
        is_admin = ctx.author.guild_permissions.administrator

        if not (is_author or is_admin):
            await ctx.send("❌ You don't have permission to modify this party.")
            return

        # Update the party
        async with self.config.guild(ctx.guild).parties() as parties:
            # Re-validate party exists (in case it was deleted concurrently)
            if party_id not in parties:
                await ctx.send("❌ Party not found.")
                return

            # Validate roles key exists
            if "roles" not in parties[party_id]:
                await ctx.send("❌ Party has no roles defined.")
                return

            # Validate signups key exists
            if "signups" not in parties[party_id]:
                parties[party_id]["signups"] = {}

            # Check if old option exists in roles
            if old_option not in parties[party_id]["roles"]:
                await ctx.send(f"❌ Role `{old_option}` not found in party.")
                return

            # Check if new option already exists
            if new_option in parties[party_id]["roles"]:
                await ctx.send(f"❌ Role `{new_option}` already exists in party.")
                return

            # Update the roles list
            role_index = parties[party_id]["roles"].index(old_option)
            parties[party_id]["roles"][role_index] = new_option

            # Migrate signups from old role name to new role name
            if old_option in parties[party_id]["signups"]:
                parties[party_id]["signups"][new_option] = parties[party_id]["signups"][old_option]
                del parties[party_id]["signups"][old_option]

        # Update the message
        await self.update_party_message(ctx.guild.id, party_id)

        # Create modlog entry
        reason = (
            f"Party '{party['name']}' (ID: {party_id}) role renamed.\n"
            f"Old role: {old_option}\n"
            f"New role: {new_option}"
        )
        await self.create_party_modlog(
            ctx.guild,
            "party_edit",
            ctx.author,
            reason
        )

        await ctx.send(f"✅ Renamed role `{old_option}` to `{new_option}` in party `{party_id}`.")
