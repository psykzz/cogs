import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import discord

from .helpers import (
    format_timestamp,
    parse_roles_from_text,
    parse_scheduled_time,
    parse_settings_text,
    validate_roles,
)

log = logging.getLogger("red.cog.party")


class RoleSelectionModal(discord.ui.Modal):
    """Modal for selecting a role when signing up for a party (for freeform entry)."""

    def __init__(self, party_id: str, predefined_roles: list, cog):
        super().__init__(title="Enter Your Role")
        self.party_id = party_id
        self.predefined_roles = predefined_roles
        self.cog = cog

        if predefined_roles:
            prefix = "Choose from: "
            roles_text = ', '.join(predefined_roles)
            available = 100 - len(prefix)
            placeholder = prefix + (
                roles_text if len(roles_text) <= available else roles_text[:available - 3] + "..."
            )
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

        # Combined settings field (allow_multiple + compact)
        self.settings_input = discord.ui.TextInput(
            label="Settings (Optional)",
            placeholder="allow_multiple=yes\ncompact=no",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=100,
            default="allow_multiple=yes\ncompact=no",
        )
        self.add_item(self.settings_input)

        # Scheduled date & time
        self.scheduled_time_input = discord.ui.TextInput(
            label="Date & Time (Optional, UTC)",
            placeholder="YYYY-MM-DD HH:MM (e.g., 2024-01-15 20:00)",
            required=False,
            max_length=20,
        )
        self.add_item(self.scheduled_time_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        title = self.title_input.value.strip()
        description = self.description_input.value.strip() or None
        roles_text = self.roles_input.value.strip()
        settings_text = self.settings_input.value
        scheduled_time_text = self.scheduled_time_input.value.strip()

        # Validate title
        if not title:
            await interaction.followup.send(
                "❌ Party name cannot be empty.",
                ephemeral=True
            )
            return
        if len(title) > 256:
            await interaction.followup.send(
                "❌ Party name must be 256 characters or less.",
                ephemeral=True
            )
            return

        # Parse and validate settings (allow_multiple + compact)
        allow_multiple, compact, error = parse_settings_text(settings_text)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Parse roles from text
        unique_roles = parse_roles_from_text(roles_text)

        # Validate roles
        error = validate_roles(unique_roles)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Parse scheduled time
        scheduled_time, error = parse_scheduled_time(scheduled_time_text)
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
            "scheduled_time": scheduled_time,
            "compact": compact,  # Use compact from settings field
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

        # Combined settings field (allow_multiple + compact)
        allow_multiple_val = "yes" if party.get("allow_multiple_per_role", True) else "no"
        compact_val = "yes" if party.get("compact", False) else "no"
        settings_default = f"allow_multiple={allow_multiple_val}\ncompact={compact_val}"
        self.settings_input = discord.ui.TextInput(
            label="Settings (Optional)",
            placeholder="allow_multiple=yes\ncompact=no",
            default=settings_default,
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=100,
        )
        self.add_item(self.settings_input)

        # Scheduled date & time
        scheduled_ts = party.get("scheduled_time")
        scheduled_default = ""
        if scheduled_ts:
            try:
                dt = datetime.fromtimestamp(float(scheduled_ts), tz=timezone.utc)
                scheduled_default = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, OSError):
                scheduled_default = ""
        self.scheduled_time_input = discord.ui.TextInput(
            label="Date & Time (Optional, UTC)",
            placeholder="YYYY-MM-DD HH:MM or leave blank to clear",
            default=scheduled_default,
            required=False,
            max_length=20,
        )
        self.add_item(self.scheduled_time_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        # Defer immediately to prevent interaction timeout
        await interaction.response.defer(ephemeral=True)

        new_title = self.title_input.value.strip()
        new_description = self.description_input.value.strip() or None
        roles_text = self.roles_input.value.strip()
        settings_text = self.settings_input.value
        scheduled_time_text = self.scheduled_time_input.value.strip()

        # Read current values as defaults so omitted keys leave the party unchanged
        async with self.cog.config.guild(interaction.guild).parties() as _parties:
            _current = _parties.get(self.party_id, {})
            _default_allow_multiple = _current.get("allow_multiple_per_role", True)
            _default_compact = _current.get("compact", False)

        # Parse and validate settings (allow_multiple + compact)
        allow_multiple, compact, error = parse_settings_text(
            settings_text,
            default_allow_multiple=_default_allow_multiple,
            default_compact=_default_compact,
        )
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Parse roles from text
        unique_roles = parse_roles_from_text(roles_text)

        # Validate roles
        error = validate_roles(unique_roles)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return

        # Parse scheduled time
        scheduled_time, error = parse_scheduled_time(scheduled_time_text)
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
            old_compact = parties[self.party_id].get('compact', False)
            old_scheduled_time = parties[self.party_id].get('scheduled_time')

            parties[self.party_id]['name'] = new_title
            parties[self.party_id]['description'] = new_description
            parties[self.party_id]['roles'] = unique_roles
            parties[self.party_id]['allow_multiple_per_role'] = allow_multiple
            parties[self.party_id]['compact'] = compact
            parties[self.party_id]['scheduled_time'] = scheduled_time

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
        if old_compact != compact:
            changes.append(f"Compact: {old_compact} → {compact}")
        if old_scheduled_time != scheduled_time:
            changes.append(
                f"Scheduled Time: {format_timestamp(old_scheduled_time)} → {format_timestamp(scheduled_time)}"
            )

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
                    except ValueError:
                        log.warning(f"Invalid user ID format: {user_id_str}")
                        continue
                    except discord.NotFound:
                        log.debug(f"User {user_id_str} not found, may have left Discord")
                        continue


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
            if self.party_id not in parties:
                await interaction.followup.send("❌ Party not found.", ephemeral=True)
                return
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


class PartyListView(discord.ui.View):
    """Interactive paginated view for [p]party list with sort and filter controls."""

    PARTIES_PER_PAGE = 5

    def __init__(self, party_items: list, guild_id: int):
        super().__init__(timeout=120)
        self.all_party_items = party_items  # insertion order = oldest first
        self.guild_id = guild_id
        self.newest_first = True
        self.hide_past = False
        self.current_page = 0
        self.message: Optional[discord.Message] = None  # set after send

        # Set initial button states
        self._sync_buttons()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _filtered_sorted(self) -> list:
        items = list(self.all_party_items)

        if self.hide_past:
            now = datetime.now(timezone.utc).timestamp()
            items = [
                (pid, p) for pid, p in items
                if not p.get("scheduled_time") or float(p["scheduled_time"]) >= now
            ]

        if self.newest_first:
            items = list(reversed(items))

        return items

    def _build_embed(self, items: list, page: int, total_pages: int) -> discord.Embed:
        embed = discord.Embed(title="🎉 Active Parties", color=discord.Color.blue())

        start = page * self.PARTIES_PER_PAGE
        for party_id, party in items[start:start + self.PARTIES_PER_PAGE]:
            total_signups = sum(len(users) for users in party["signups"].values())
            role_count = len(party["roles"]) if party["roles"] else "Freeform"

            link_text = ""
            channel_id = party.get("channel_id")
            message_id = party.get("message_id")
            if channel_id and message_id:
                jump_url = (
                    f"https://discord.com/channels/"
                    f"{self.guild_id}/{channel_id}/{message_id}"
                )
                link_text = f"\n**[Jump to Party]({jump_url})**"

            time_text = ""
            scheduled_time = party.get("scheduled_time")
            if scheduled_time:
                try:
                    ts = int(float(scheduled_time))
                    time_text = f"\n**Time**: <t:{ts}:F> (<t:{ts}:R>)"
                except (ValueError, OSError):
                    pass

            value = (
                f"**ID**: `{party_id}`\n"
                f"**Roles**: {role_count}\n"
                f"**Signups**: {total_signups}\n"
                f"**Author**: <@{party['author_id']}>"
                f"{time_text}"
                f"{link_text}"
            )
            compact = party.get("compact", False)
            embed.add_field(name=party["name"], value=value, inline=compact)

        order_label = "⬆ Newest first" if self.newest_first else "⬇ Oldest first"
        filter_label = " · 🚫 Past hidden" if self.hide_past else ""
        embed.set_footer(
            text=f"Page {page + 1}/{total_pages} · {len(items)} parties · {order_label}{filter_label}"
        )
        return embed

    # ------------------------------------------------------------------
    # Button state sync
    # ------------------------------------------------------------------

    def _sync_buttons(self, total_pages: int = 1):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= total_pages - 1

        if self.newest_first:
            self.sort_button.label = "Oldest First"
            self.sort_button.emoji = discord.PartialEmoji(name="⬇")
            self.sort_button.style = discord.ButtonStyle.gray
        else:
            self.sort_button.label = "Newest First"
            self.sort_button.emoji = discord.PartialEmoji(name="⬆")
            self.sort_button.style = discord.ButtonStyle.blurple

        if self.hide_past:
            self.filter_past_button.label = "Show Past"
            self.filter_past_button.style = discord.ButtonStyle.red
        else:
            self.filter_past_button.label = "Hide Past"
            self.filter_past_button.style = discord.ButtonStyle.gray

    # ------------------------------------------------------------------
    # Shared refresh helper
    # ------------------------------------------------------------------

    async def _refresh(self, interaction: discord.Interaction):
        items = self._filtered_sorted()
        total_pages = max(1, (len(items) + self.PARTIES_PER_PAGE - 1) // self.PARTIES_PER_PAGE)
        self.current_page = min(self.current_page, total_pages - 1)

        if not items:
            embed = discord.Embed(
                title="🎉 Active Parties",
                description="No parties match the current filters.",
                color=discord.Color.blue(),
            )
            self._sync_buttons(1)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        self._sync_buttons(total_pages)
        embed = self._build_embed(items, self.current_page, total_pages)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    @discord.ui.button(label="◀", style=discord.ButtonStyle.blurple, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self._refresh(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.blurple, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self._refresh(interaction)

    @discord.ui.button(label="Close", emoji="🗑️", style=discord.ButtonStyle.red, row=0)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

    @discord.ui.button(label="Oldest First", emoji="⬇", style=discord.ButtonStyle.gray, row=1)
    async def sort_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.newest_first = not self.newest_first
        self.current_page = 0
        await self._refresh(interaction)

    @discord.ui.button(label="Hide Past", emoji="🚫", style=discord.ButtonStyle.gray, row=1)
    async def filter_past_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.hide_past = not self.hide_past
        self.current_page = 0
        await self._refresh(interaction)
