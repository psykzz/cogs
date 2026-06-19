import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import discord
from redbot.core import Config, checks, commands, modlog

from .helpers import (
    IDENTIFIER,
    EMBED_FIELD_MAX_LENGTH,
    _parse_roles_from_args,
    format_timestamp,
    parse_allow_multiple,
    parse_scheduled_time,
    validate_roles,
)
from .views import CreatePartyModal, EditPartyFullModal, PartyListView, PartyView

log = logging.getLogger("red.cog.party")


class Party(commands.Cog):
    """Create and manage party signups with role compositions."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER)

        default_global = {
            "templates": {},  # template_key -> template data (global templates, bot owner only)
        }
        self.config.register_global(**default_global)

        default_guild = {
            "parties": {},  # party_id -> party data
            "allow_multiple_per_role": True,  # Guild-wide default
            "templates": {},  # template_key -> template data (guild-specific templates)
        }
        self.config.register_guild(**default_guild)

        # Load persistent views for existing parties
        self.bot.loop.create_task(self._register_persistent_views())
        # Register custom modlog casetypes
        self.bot.loop.create_task(self._register_casetypes())

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
            for party_id, party in parties.items():
                view = PartyView(party_id, self)
                message_id = party.get("message_id")
                if message_id:
                    self.bot.add_view(view, message_id=message_id)
                    log.debug(f"Registered persistent view for party {party_id} (message {message_id})")
                else:
                    self.bot.add_view(view)
                    log.warning(f"Party {party_id} has no message_id, registering view without message binding")

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
            guild: Optional guild to get member display name/nickname from

        Returns:
            The user's display name (if in guild with nickname), username (if not in guild),
            or "Unknown User" as fallback if user cannot be found
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

            # Ensure signups dictionary exists (defensive check)
            if "signups" not in party:
                party["signups"] = {}

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
        # Show roles and signups
        signups = party.get("signups", {})
        total_signups = sum(len(users) for users in signups.values())

        embed = discord.Embed(
            title=f"🎉 {party['name']} ({total_signups} signed up)",
            description=party.get("description", "Join the party by selecting your role!"),
            color=discord.Color.blue()
        )

        # Get the compact setting (inline fields) - default to False (not compact)
        compact = party.get("compact", False)

        # Show scheduled time if set
        scheduled_time = party.get("scheduled_time")
        if scheduled_time:
            try:
                ts = int(float(scheduled_time))
                embed.add_field(
                    name="📅 Scheduled Time",
                    value=f"<t:{ts}:F>\n(<t:{ts}:R>)",
                    inline=compact
                )
            except (ValueError, OSError):
                pass

        roles = party.get("roles", [])

        # Add each role as a field
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

            embed.add_field(name=role, value=value, inline=compact)

        # Add roles that have signups but aren't in the predefined list (freeform roles)
        for role, users in signups.items():
            if role not in roles and users:
                user_mentions = self._get_user_mentions(users)
                if user_mentions:
                    value = ', '.join(user_mentions)
                    if len(value) > EMBED_FIELD_MAX_LENGTH:
                        value = value[:EMBED_FIELD_MAX_LENGTH-3] + "..."
                    embed.add_field(name=role, value=value, inline=compact)

        # If no roles defined and no signups, show a message
        if not roles and not any(users for users in signups.values()):
            embed.add_field(name="Signups", value="-", inline=compact)

        # Get owner name for footer
        owner_name = await self._get_user_display_name(party['author_id'], guild)

        # Set footer with party owner name and party ID
        embed.set_footer(text=f"Owner: {owner_name} | Party ID: {party['id']}")

        return embed

    @commands.hybrid_group()
    @commands.guild_only()
    async def party(self, ctx):
        """Party management commands."""

    @party.command(name="create")
    async def party_create(
        self,
        ctx,
        name: Optional[str] = None,
        roles: Optional[str] = None,
        compact: Optional[bool] = False
    ):
        """Create a new party with predefined roles.

        Call without arguments to use an interactive modal form.
        Call with arguments to use the traditional command format.

        Users can only select from the specified roles.
        At least one role must be specified when using arguments.
        Roles can be separated by spaces or commas.

        Parameters
        ----------
        name : Optional[str]
            The name of the party
        roles : Optional[str]
            Space or comma-separated list of roles (e.g., "Tank Healer DPS" or "Tank, Healer, DPS")
        compact : Optional[bool]
            Display party in compact mode (inline fields). Default is False (not compact).

        Examples:
        - [p]party create  (opens interactive modal)
        - [p]party create "Raid Night" "Tank Healer DPS"
        - [p]party create "Raid Night" "Tank, Healer, DPS"
        - [p]party create "Game Night" "Player1 Player2 Player3 Player4"
        - [p]party create "PvP Team" "Warrior, Mage, Archer"
        - [p]party create "Siege" "Siege Crossbow, Energy Shaper, GA"
        - [p]party create "Compact Party" "Tank Healer DPS" True
        """
        # If no arguments provided, show the modal
        if name is None:
            # Create and send the modal
            modal = CreatePartyModal(self)

            # For slash commands, show the modal directly
            if ctx.interaction:
                await ctx.interaction.response.send_modal(modal)
                return

            # For text commands, we need to send a button first
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

        # Handle roles being None (no roles provided)
        if not roles:
            await ctx.send("❌ Please provide at least one role for the party.")
            return

        roles_list = _parse_roles_from_args(roles)

        # Validate roles
        error = validate_roles(roles_list)
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
            "scheduled_time": None,
            "compact": compact,  # Use the compact parameter from command
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

        # Delete the original command message (not applicable for slash commands)
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
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
        """List all active parties in this server, newest first.

        Use the ◀ ▶ buttons to page, toggle sort order, or hide past parties.

        Example: [p]party list
        """
        parties = await self.config.guild(ctx.guild).parties()

        if not parties:
            await ctx.send("No active parties in this server.")
            return

        party_items = list(parties.items())  # insertion order = oldest first
        view = PartyListView(party_items, ctx.guild.id)

        items = view._filtered_sorted()
        total_pages = max(1, (len(items) + PartyListView.PARTIES_PER_PAGE - 1) // PartyListView.PARTIES_PER_PAGE)
        view._sync_buttons(total_pages)
        embed = view._build_embed(items, 0, total_pages)

        view.message = await ctx.send(embed=embed, view=view)

    @party.command(name="fix")
    @checks.admin_or_permissions(manage_guild=True)
    async def party_fix(self, ctx, party_id: str):
        """Re-render a party embed and re-register its buttons.

        Use this to fix parties whose buttons stopped working after a bot restart.

        Parameters
        ----------
        party_id : str
            The ID of the party to fix (shown in [p]party list).

        Example: [p]party fix abc123
        """
        await ctx.defer(ephemeral=True)

        party = await self.get_party(ctx.guild.id, party_id)
        if not party:
            await ctx.send("❌ Party not found.", ephemeral=True)
            return

        channel_id = party.get("channel_id")
        message_id = party.get("message_id")

        if not channel_id or not message_id:
            await ctx.send(
                "❌ Party has no associated message. It may need to be recreated.",
                ephemeral=True
            )
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send(
                f"❌ Cannot find channel <#{channel_id}>. It may have been deleted.",
                ephemeral=True
            )
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(
                "❌ Party message no longer exists. You may need to delete and recreate the party.",
                ephemeral=True
            )
            return
        except discord.Forbidden:
            await ctx.send("❌ Missing permissions to read that channel.", ephemeral=True)
            return

        # Build a fresh view and re-register it bound to this specific message
        view = PartyView(party_id, self)
        self.bot.add_view(view, message_id=message_id)

        # Edit the message with a fresh embed + re-attached view
        embed = await self.create_party_embed(party, ctx.guild)
        try:
            await message.edit(embed=embed, view=view)
        except discord.HTTPException as e:
            log.error(f"Failed to fix party message {message_id}: {e}")
            await ctx.send(f"❌ Failed to update the message: {e}", ephemeral=True)
            return

        log.info(f"Party {party_id} fixed by {ctx.author} ({ctx.author.id})")
        await ctx.send(
            f"✅ Party `{party_id}` ({party['name']}) has been re-rendered and its buttons re-registered.",
            ephemeral=True
        )

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

    @party.command(name="settime")
    async def party_settime(self, ctx, party_id: str, *, scheduled_time: str):
        """Set or clear the scheduled date and time for a party (UTC).

        Only the party creator or server admins can set the time.
        Use "clear" or "none" as the time to remove an existing scheduled time.

        Parameters
        ----------
        party_id : str
            The ID of the party to update
        scheduled_time : str
            Date and time in UTC, e.g. "2024-01-15 20:00". Use "clear" to remove.

        Examples:
        - [p]party settime abc123 2024-01-15 20:00
        - [p]party settime abc123 clear
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

        # Parse the scheduled time
        timestamp, error = parse_scheduled_time(scheduled_time)
        if error:
            await ctx.send(error)
            return

        old_time = party.get("scheduled_time")

        # Update the party
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id]["scheduled_time"] = timestamp

        # Update the message embed
        await self.update_party_message(ctx.guild.id, party_id)

        # Create modlog entry
        reason = (
            f"Party '{party['name']}' (ID: {party_id}) scheduled time updated.\n"
            f"Old: {format_timestamp(old_time)}\nNew: {format_timestamp(timestamp)}"
        )
        await self.create_party_modlog(
            ctx.guild,
            "party_edit",
            ctx.author,
            reason
        )

        if timestamp is None:
            await ctx.send(f"✅ Scheduled time cleared for party `{party_id}`.")
        else:
            ts = int(float(timestamp))
            await ctx.send(
                f"✅ Scheduled time set for party `{party_id}`: <t:{ts}:F> (<t:{ts}:R>)"
            )

    @party.command(name="compact")
    async def party_compact(self, ctx, party_id: str, compact: bool):
        """Set the compact display mode for a party.

        Compact mode displays party fields inline (side-by-side).
        Non-compact mode displays fields stacked vertically (default).

        Only the party creator or server admins can change this setting.

        Parameters
        ----------
        party_id : str
            The ID of the party to update
        compact : bool
            True for compact (inline) display, False for stacked display

        Examples:
        - [p]party compact abc123 True
        - [p]party compact abc123 False
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

        old_compact = party.get("compact", False)

        # Update compact setting
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id]["compact"] = compact

        # Update the message
        await self.update_party_message(ctx.guild.id, party_id)

        # Create modlog entry
        reason = (
            f"Party '{party['name']}' (ID: {party_id}) compact mode updated.\n"
            f"Old: {'Compact' if old_compact else 'Not compact'}\n"
            f"New: {'Compact' if compact else 'Not compact'}"
        )
        await self.create_party_modlog(
            ctx.guild,
            "party_edit",
            ctx.author,
            reason
        )

        mode_text = "compact (inline)" if compact else "non-compact (stacked)"
        await ctx.send(f"✅ Party `{party_id}` display mode set to **{mode_text}**.")

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

    @party.group(name="template")
    @commands.guild_only()
    async def party_template(self, ctx):
        """Manage party templates.

        Guild admins can create guild-specific templates.
        Bot owner can create global templates available across all guilds.
        """

    @party_template.command(name="create")
    @checks.admin_or_permissions(manage_guild=True)
    async def party_template_create(self, ctx, name: str, *, roles: str):
        """Create a guild-specific party template with predefined roles.

        Roles can be separated by commas (for multi-word roles) or spaces.

        Examples:
        - [p]party template create "Raid Comp" "Tank, Healer, DPS, DPS"
        - [p]party template create RaidComp Tank Healer DPS
        """
        roles_list = _parse_roles_from_args(roles)

        error = validate_roles(roles_list)
        if error:
            await ctx.send(error)
            return

        template_key = name.lower()
        template = {
            "name": name,
            "roles": roles_list,
            "created_by": ctx.author.id,
        }

        async with self.config.guild(ctx.guild).templates() as templates:
            templates[template_key] = template

        await ctx.send(
            f"✅ Guild template `{name}` created with {len(roles_list)} role(s): {', '.join(roles_list)}"
        )

    @party_template.command(name="global-create")
    @checks.is_owner()
    async def party_template_global_create(self, ctx, name: str, *, roles: str):
        """Create a global party template accessible across all guilds (bot owner only).

        Roles can be separated by commas (for multi-word roles) or spaces.

        Examples:
        - [p]party template global-create "Raid Comp" "Tank, Healer, DPS"
        - [p]party template global-create RaidComp Tank Healer DPS
        """
        roles_list = _parse_roles_from_args(roles)

        error = validate_roles(roles_list)
        if error:
            await ctx.send(error)
            return

        template_key = name.lower()
        template = {
            "name": name,
            "roles": roles_list,
            "created_by": ctx.author.id,
        }

        async with self.config.templates() as templates:
            templates[template_key] = template

        await ctx.send(
            f"✅ Global template `{name}` created with {len(roles_list)} role(s): {', '.join(roles_list)}"
        )

    @party_template.command(name="delete")
    @checks.admin_or_permissions(manage_guild=True)
    async def party_template_delete(self, ctx, *, name: str):
        """Delete a guild-specific party template.

        Only guild admins can delete guild templates.

        Example: [p]party template delete "Raid Comp"
        """
        template_key = name.lower()
        async with self.config.guild(ctx.guild).templates() as templates:
            if template_key not in templates:
                await ctx.send(f"❌ Guild template `{name}` not found.")
                return
            del templates[template_key]

        await ctx.send(f"✅ Guild template `{name}` deleted.")

    @party_template.command(name="global-delete")
    @checks.is_owner()
    async def party_template_global_delete(self, ctx, *, name: str):
        """Delete a global party template (bot owner only).

        Example: [p]party template global-delete "Raid Comp"
        """
        template_key = name.lower()
        async with self.config.templates() as templates:
            if template_key not in templates:
                await ctx.send(f"❌ Global template `{name}` not found.")
                return
            del templates[template_key]

        await ctx.send(f"✅ Global template `{name}` deleted.")

    @party_template.command(name="list")
    async def party_template_list(self, ctx):
        """List all available party templates (global and guild-specific).

        Example: [p]party template list
        """
        guild_templates = await self.config.guild(ctx.guild).templates()
        global_templates = await self.config.templates()

        if not guild_templates and not global_templates:
            await ctx.send("No party templates available.")
            return

        embed = discord.Embed(
            title="📋 Party Templates",
            color=discord.Color.blue()
        )

        # Global templates first (🌐), then guild-specific (🏠)
        entries = [
            (f"🌐 {t['name']} (Global)", t) for t in global_templates.values()
        ] + [
            (f"🏠 {t['name']}", t) for t in guild_templates.values()
        ]

        for label, template in entries:
            roles_text = ', '.join(template['roles'])
            if len(roles_text) > EMBED_FIELD_MAX_LENGTH:
                roles_text = roles_text[:EMBED_FIELD_MAX_LENGTH - 3] + "..."
            # Templates list display is not compact by default
            embed.add_field(name=label, value=roles_text, inline=False)

        await ctx.send(embed=embed)

    @party_template.command(name="use")
    async def party_template_use(self, ctx, template_name: str, *, title: str):
        """Create a party from a template with a custom title.

        The template's roles are pre-filled; you only need to provide a title.
        Guild templates take priority over global templates when names conflict.

        Parameters
        ----------
        template_name : str
            The name of the template to use
        title : str
            The title for the new party

        Examples:
        - [p]party template use "Raid Comp" "Friday Night Raid"
        - [p]party template use RaidComp "Saturday Dungeon Run"
        """
        template_key = template_name.lower()

        # Check guild templates first, then global (guild takes priority)
        guild_templates = await self.config.guild(ctx.guild).templates()
        global_templates = await self.config.templates()

        template = guild_templates.get(template_key) or global_templates.get(template_key)

        if not template:
            await ctx.send(
                f"❌ Template `{template_name}` not found. "
                f"Use `{ctx.clean_prefix}party template list` to see available templates."
            )
            return

        roles_list = template['roles']

        # Get guild settings
        allow_multiple = await self.config.guild(ctx.guild).allow_multiple_per_role()

        # Generate a unique party ID
        party_id = secrets.token_hex(4)

        # Create party data
        party = {
            "id": party_id,
            "name": title,
            "description": None,
            "author_id": ctx.author.id,
            "roles": roles_list,
            "signups": {},
            "allow_multiple_per_role": allow_multiple,
            "allow_freeform": False,
            "channel_id": None,
            "message_id": None,
            "scheduled_time": None,
            "compact": False,  # Default to not compact
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
            f"Party '{title}' (ID: {party_id}) created from template "
            f"'{template['name']}' with {len(roles_list)} role(s)."
        )

        await ctx.send(
            f"✅ Party created from template `{template['name']}`! ID: `{party_id}`",
            delete_after=10
        )

        # Delete the original command message (not applicable for slash commands)
        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
