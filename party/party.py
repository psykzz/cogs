import logging
import secrets
from typing import Optional

import discord
from redbot.core import Config, checks, commands

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
        role = self.role_input.value.strip()

        # Validate that the role is in the predefined list
        if self.predefined_roles and role not in self.predefined_roles:
            # Truncate role list in error message to avoid exceeding Discord's limit
            roles_list = ', '.join(self.predefined_roles)
            if len(roles_list) > 100:
                # Show first few roles with ellipsis
                roles_list = roles_list[:97] + "..."
            await interaction.response.send_message(
                f"❌ Invalid role. Please choose from: {roles_list}",
                ephemeral=True
            )
            return

        # Add the user to the party with the selected role
        # Note: Modals don't have persistent UI components, so no view cleanup needed
        await self.cog.signup_user(interaction, self.party_id, role, disabled_view=None)


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
        selected_role = self.role_select.values[0]

        # Disable all components in the view after selection
        for item in self.children:
            item.disabled = True

        # Sign up the user (this will handle the interaction response)
        await self.cog.signup_user(interaction, self.party_id, selected_role, disabled_view=self)


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
            await interaction.response.send_message("❌ Party not found.", ephemeral=True)
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
            await interaction.response.send_message(
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
        view = RoleSelectView(self.party_id, roles, self.cog)
        await interaction.response.send_message(
            message,
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red, custom_id="party_leave", emoji="❌")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle leave button click."""
        result = await self.cog.leave_party(interaction.guild.id, self.party_id, interaction.user.id)
        if result:
            await interaction.response.send_message("✅ You've left the party.", ephemeral=True)
            await self.cog.update_party_message(interaction.guild.id, self.party_id)
        else:
            await interaction.response.send_message("❌ You're not signed up for this party.", ephemeral=True)


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
        disabled_view: Optional[discord.ui.View] = None
    ):
        """Sign up a user for a party with a specific role.

        Args:
            interaction: The Discord interaction
            party_id: The party to sign up for
            role: The role to sign up as
            disabled_view: A pre-disabled view to include in the response message.
                          If provided, the original message will be edited instead of sending a new one.
                          If None, a new ephemeral message is sent.
        """
        guild_id = interaction.guild.id
        user_id = str(interaction.user.id)

        async with self.config.guild_from_id(guild_id).parties() as parties:
            if party_id not in parties:
                if disabled_view:
                    # Edit the original message to show error and remove the select view
                    await interaction.response.edit_message(
                        content="❌ Party not found.",
                        view=None
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
                    await interaction.response.edit_message(
                        content=f"❌ The role **{role}** is already full (multiple signups not allowed).",
                        view=None
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
            await interaction.response.edit_message(
                content=f"✅ You've signed up as **{role}**!",
                view=None
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

        # Build the updated embed
        embed = await self.create_party_embed(party)

        # Update the message
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            log.error(f"Failed to update party message {message_id}")

    async def create_party_embed(self, party: dict) -> discord.Embed:
        """Create an embed for a party."""
        embed = discord.Embed(
            title=f"🎉 {party['name']}",
            description=party.get("description", "Join the party by selecting your role!"),
            color=discord.Color.blue()
        )

        # Show roles and signups
        signups = party.get("signups", {})
        roles = party.get("roles", [])

        # Build signup list
        signup_lines = []
        for role in roles:
            users = signups.get(role, [])
            user_mentions = self._get_user_mentions(users)
            if user_mentions:
                signup_lines.append(f"**{role}**: {', '.join(user_mentions)}")
            else:
                signup_lines.append(f"**{role}**: _No signups yet_")

        # Add roles that have signups but aren't in the predefined list (freeform roles)
        for role, users in signups.items():
            if role not in roles and users:
                user_mentions = self._get_user_mentions(users)
                if user_mentions:
                    signup_lines.append(f"**{role}**: {', '.join(user_mentions)}")

        if signup_lines:
            # Smart truncation: respect line boundaries
            current_length = 0
            included_lines = []
            for line in signup_lines:
                line_length = len(line) + 1  # +1 for newline
                if current_length + line_length < EMBED_FIELD_MAX_LENGTH:
                    included_lines.append(line)
                    current_length += line_length
                else:
                    # Can't fit this line, stop here
                    break

            if included_lines:
                signup_text = "\n".join(included_lines)
                if len(included_lines) < len(signup_lines):
                    # Add indicator that there are more signups
                    remaining = len(signup_lines) - len(included_lines)
                    signup_text += f"\n_... and {remaining} more role(s)_"
                embed.add_field(name="Signups", value=signup_text, inline=False)
            else:
                # Even one line is too long, truncate it
                embed.add_field(
                    name="Signups",
                    value=signup_lines[0][:EMBED_FIELD_MAX_LENGTH-3] + "...",
                    inline=False
                )
        else:
            embed.add_field(name="Signups", value="_No signups yet_", inline=False)

        # Add configuration info
        allow_multiple = party.get("allow_multiple_per_role", True)
        config_lines = []
        if allow_multiple:
            config_lines.append("✅ Multiple signups per role allowed")
        else:
            config_lines.append("❌ Only one signup per role")
        config_lines.append("📋 Only predefined roles allowed")

        embed.add_field(name="Configuration", value="\n".join(config_lines), inline=False)

        embed.set_footer(text=f"Party ID: {party['id']}")

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
        name: str,
        *roles: str
    ):
        """Create a new party with predefined roles.

        Users can only select from the specified roles.
        At least one role must be specified.
        Roles can be separated by spaces or commas.

        Examples:
        - [p]party create "Raid Night" Tank Healer DPS
        - [p]party create "Raid Night" "Tank, Healer, DPS"
        - [p]party create "Game Night" Player1 Player2 Player3 Player4
        - [p]party create "PvP Team" Warrior, Mage, Archer
        """
        # Parse roles: handle both comma-separated and whitespace-separated
        parsed_roles = []
        for role_arg in roles:
            # If the role contains commas, split on comma
            if ',' in role_arg:
                # Split on comma and strip whitespace from each part
                parsed_roles.extend([r.strip() for r in role_arg.split(',') if r.strip()])
            else:
                # No comma, treat as single role
                parsed_roles.append(role_arg.strip())

        # Remove any empty strings and duplicates while preserving order
        seen = set()
        roles_list = []
        for role in parsed_roles:
            if role and role not in seen:
                seen.add(role)
                roles_list.append(role)

        # Validate that at least one role is specified
        if not roles_list:
            await ctx.send("❌ You must specify at least one role for the party.")
            return

        # Validate maximum 25 roles (Discord select menu limit)
        if len(roles_list) > 25:
            await ctx.send("❌ You can specify a maximum of 25 roles per party.")
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
        embed = await self.create_party_embed(party)

        # Create the view with buttons
        view = PartyView(party_id, self)

        # Send the message
        message = await ctx.send(embed=embed, view=view)

        # Save the message ID and channel ID
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id]["message_id"] = message.id
            parties[party_id]["channel_id"] = ctx.channel.id

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

            value = (
                f"**ID**: `{party_id}`\n"
                f"**Roles**: {role_count}\n"
                f"**Signups**: {total_signups}\n"
                f"**Author**: <@{party['author_id']}>"
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
        async with self.config.guild(ctx.guild).parties() as parties:
            parties[party_id]["description"] = description

        # Update the message
        await self.update_party_message(ctx.guild.id, party_id)

        await ctx.send(f"✅ Description updated for party `{party_id}`.")
