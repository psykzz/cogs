import datetime
import logging
import math
import re

import discord
from dateutil.relativedelta import relativedelta
from redbot.core import Config, commands, checks
from redbot.core.utils.menus import menu

log = logging.getLogger("red.cogs.albion_bandits")

IDENTIFIER = 8472651938472651938  # Random identifier for this cog

# Bandit timing constants (in hours)
MIN_BANDIT_COOLDOWN_HOURS = 4
MAX_BANDIT_COOLDOWN_HOURS = 6
ESTIMATED_BANDIT_INTERVAL_HOURS = 5  # Midpoint of 4-6 hour window
# Missed event threshold: start creating estimates after max cooldown window
MISSED_EVENT_THRESHOLD_HOURS = MAX_BANDIT_COOLDOWN_HOURS
# Minimum spacing between calls: use min cooldown as the threshold
MIN_TIME_BETWEEN_CALLS_HOURS = MIN_BANDIT_COOLDOWN_HOURS
GRACE_PERIOD_HOURS = 3  # Starting offset for first estimate

# Estimated call identifiers
ESTIMATED_CALL_USER_NAME = "System (Estimated)"
ESTIMATED_CALL_MESSAGE = "Auto-generated estimate for missed event"

default_guild = {
    "monitored_role_id": None,  # Role ID to monitor for pings
    "bandit_calls": [],  # List of bandit call records
}


class AlbionBandits(commands.Cog):
    """Track Albion Online bandit event role mentions and timing"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(**default_guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for role mentions with time indicators"""
        # Ignore bot messages
        if message.author.bot:
            log.debug(f"Ignoring message from bot: {message.author} ({message.author.id})")
            return

        # Only process guild messages
        if not message.guild:
            log.debug("Ignoring non-guild message (DM or other)")
            return

        # Ignore bot commands
        if message.content.startswith(tuple(await self.bot.get_valid_prefixes())):
            log.debug(f"Ignoring bot command in guild {message.guild.name} ({message.guild.id})")
            return

        # Get the monitored role ID for this guild
        guild_config = self.config.guild(message.guild)
        role_id = await guild_config.monitored_role_id()

        if not role_id:
            log.debug(
                f"No monitored role configured for guild {message.guild.name} ({message.guild.id})"
            )
            return

        # Check if the message mentions the monitored role
        role = message.guild.get_role(role_id)
        if not role or role not in message.role_mentions:
            log.debug(
                f"Message in guild {message.guild.name} ({message.guild.id}) does not mention "
                f"monitored role (role_id: {role_id})"
            )
            return

        log.debug(
            f"Detected role mention in guild {message.guild.name} ({message.guild.id}), "
            f"channel #{message.channel.name} ({message.channel.id}), "
            f"by user {message.author} ({message.author.id})"
        )

        # Try to extract a time value (number of minutes) from the message
        # Pattern: @role followed by a number (e.g., "@bandits 15")
        # If no time is specified, assume bandits start immediately (0 minutes)
        # Use clean content to avoid matching on snowflake ids
        time_match = re.search(r'\b(\d+)\b', message.clean_content)
        if time_match:
            minutes = int(time_match.group(1))
            # Reasonable range for bandit timing (0-120 minutes)
            if minutes < 0 or minutes > 120:
                log.debug(
                    f"Time value {minutes} out of valid range (0-120), ignoring message"
                )
                return
            log.debug(f"Extracted time value: {minutes} minutes (within valid range)")
        else:
            # No time specified, assume immediate start
            minutes = 0
            log.debug("No time value specified, assuming immediate start (0 minutes)")

        # Calculate the bandit start time
        bandit_time = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
        log.debug(
            f"Calculated bandit start time: {bandit_time.strftime('%Y-%m-%d %H:%M:%S')} "
            f"({minutes} minutes from now)"
        )

        # Check for duplicate within recent timeframe
        if await self._is_duplicate(message.guild, bandit_time):
            log.debug(
                "Duplicate bandit call detected (within 10 minutes of existing call), "
                "ignoring message"
            )
            return

        # Check if we need to add estimated calls for missed events and store the new call
        call_record = {
            "user_id": message.author.id,
            "user_name": str(message.author),
            "channel_id": message.channel.id,
            "message_id": message.id,
            "minutes_until": minutes,
            "call_time": datetime.datetime.now().isoformat(),
            "bandit_time": bandit_time.isoformat(),
            "message_content": message.content[:200],  # Truncate long messages
            "is_estimated": False,  # Actual call, not estimated
        }

        async with guild_config.bandit_calls() as calls_list:
            if calls_list:
                last_call = calls_list[-1]
                last_bandit_time = datetime.datetime.fromisoformat(last_call["bandit_time"])

                # Create estimated calls if there's a significant gap
                estimated_calls = await self._create_estimated_calls(
                    message.guild,
                    last_bandit_time,
                    bandit_time
                )

                if estimated_calls:
                    calls_list.extend(estimated_calls)
                    log.debug(f"Added {len(estimated_calls)} estimated call(s)")

            # Add the new call
            calls_list.append(call_record)

        log.debug(
            f"Successfully recorded bandit call: {minutes} minutes until bandits "
            f"at {bandit_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # Add thumbs up reaction to confirm the message was recorded
        try:
            await message.add_reaction("👍")
            log.debug("Successfully added 👍 reaction to confirm message was recorded")
        except discord.HTTPException as e:
            log.warning(f"Failed to add reaction to message: {e}")

    async def _is_duplicate(self, guild: discord.Guild, new_bandit_time: datetime.datetime) -> bool:
        """Check if a similar bandit call exists within 10 minutes"""
        guild_config = self.config.guild(guild)
        calls = await guild_config.bandit_calls()

        # Check the last few calls
        for call in calls[-5:]:  # Only check last 5 calls for efficiency
            existing_time = datetime.datetime.fromisoformat(call["bandit_time"])
            time_diff = abs((new_bandit_time - existing_time).total_seconds() / 60)

            # If within 10 minutes, consider it a duplicate
            if time_diff < 10:
                return True

        return False

    async def _create_estimated_calls(
        self,
        guild: discord.Guild,
        last_bandit_time: datetime.datetime,
        new_bandit_time: datetime.datetime
    ) -> list:
        """Create estimated calls for missed bandit events between last and new call.

        Args:
            guild: The Discord guild
            last_bandit_time: The timestamp of the last recorded bandit event
            new_bandit_time: The timestamp of the new bandit call

        Returns:
            List of estimated call records
        """
        estimated_calls = []

        # Calculate hours between last and new call
        hours_gap = (new_bandit_time - last_bandit_time).total_seconds() / 3600

        # If gap is past the expected window, add estimates
        if hours_gap > MISSED_EVENT_THRESHOLD_HOURS:
            # Estimate number of missed events (using regular interval)
            # Use floor to ensure we only create estimates for complete intervals
            estimated_count = max(0, math.floor((hours_gap - GRACE_PERIOD_HOURS) / ESTIMATED_BANDIT_INTERVAL_HOURS))

            log.debug(
                f"Gap of {hours_gap:.1f} hours detected. "
                f"Creating {estimated_count} estimated call(s)"
            )

            # Create estimated calls with regular spacing
            for i in range(estimated_count):
                estimated_time = last_bandit_time + datetime.timedelta(
                    hours=ESTIMATED_BANDIT_INTERVAL_HOURS * (i + 1)
                )

                # Don't create an estimate if it's too close to the new call
                time_to_new = abs((new_bandit_time - estimated_time).total_seconds() / 3600)
                if time_to_new < MIN_TIME_BETWEEN_CALLS_HOURS:
                    log.debug(
                        f"Skipping estimated call at {estimated_time} "
                        f"(too close to new call)"
                    )
                    break

                estimated_call = self._create_estimated_call_record(estimated_time)
                estimated_calls.append(estimated_call)
                log.debug(
                    f"Created estimated call for {estimated_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )

        return estimated_calls

    def _create_estimated_call_record(self, estimated_time: datetime.datetime) -> dict:
        """Create a standardized estimated call record.

        Args:
            estimated_time: The estimated timestamp for the bandit event

        Returns:
            Dictionary containing the estimated call record
        """
        return {
            "user_id": 0,  # System generated
            "user_name": ESTIMATED_CALL_USER_NAME,
            "channel_id": 0,
            "message_id": 0,
            "minutes_until": 0,
            "call_time": estimated_time.isoformat(),
            "bandit_time": estimated_time.isoformat(),
            "message_content": ESTIMATED_CALL_MESSAGE,
            "is_estimated": True,  # Flag to mark this as an estimate
        }

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def bandits(self, ctx):
        """Manage bandit tracking"""
        await ctx.send_help()

    @bandits.command(name="next")
    async def bandits_next(self, ctx):
        """Show the last bandit time and predict the next occurrence"""
        guild_config = self.config.guild(ctx.guild)
        calls = await guild_config.bandit_calls()

        if not calls:
            await ctx.send("No bandit calls have been recorded yet.")
            return

        # Get the last bandit call
        last_call = calls[-1]
        last_bandit_time = datetime.datetime.fromisoformat(last_call["bandit_time"])

        # Calculate time since last bandit
        now = datetime.datetime.now()
        time_since = relativedelta(now, last_bandit_time)

        # Calculate next possible bandit times (using cooldown constants)
        earliest_next = last_bandit_time + datetime.timedelta(hours=MIN_BANDIT_COOLDOWN_HOURS)
        latest_next = last_bandit_time + datetime.timedelta(hours=MAX_BANDIT_COOLDOWN_HOURS)

        embed = discord.Embed(
            title="🏴‍☠️ Albion Bandits Timing",
            color=discord.Color.red()
        )

        # Format last bandit time
        embed.add_field(
            name="Last Bandit",
            value=f"{last_bandit_time.strftime('%Y-%m-%d %H:%M:%S')}",
            inline=False
        )

        # Show time since
        time_since_str = self._humanize_delta(time_since)
        embed.add_field(
            name="Time Since Last Bandit",
            value=time_since_str,
            inline=False
        )

        # Show next predicted window
        if now < earliest_next:
            # Next window hasn't started yet
            time_until_earliest = relativedelta(earliest_next, now)
            embed.add_field(
                name="Next Bandit Window Opens In",
                value=self._humanize_delta(time_until_earliest),
                inline=False
            )
            embed.add_field(
                name="Expected Window",
                value=f"{earliest_next.strftime('%H:%M')} - {latest_next.strftime('%H:%M')}",
                inline=False
            )
        elif now <= latest_next:
            # We're in the window
            time_until_latest = relativedelta(latest_next, now)
            embed.add_field(
                name="🔥 Bandit Window Active!",
                value=f"Window closes in {self._humanize_delta(time_until_latest)}",
                inline=False
            )
        else:
            # Past the window
            embed.add_field(
                name="Status",
                value="⚠️ Past expected window - next bandits should spawn soon!",
                inline=False
            )

        embed.set_footer(text=f"Called by {last_call['user_name']}")

        await ctx.send(embed=embed)

    @bandits.command(name="list")
    async def bandits_list(self, ctx):
        """List all previous bandit calls"""
        guild_config = self.config.guild(ctx.guild)
        calls = await guild_config.bandit_calls()

        if not calls:
            await ctx.send("No bandit calls have been recorded yet.")
            return

        # Create pages for the menu (10 calls per page)
        pages = []
        calls_per_page = 10

        for i in range(0, len(calls), calls_per_page):
            page_calls = calls[i:i + calls_per_page]
            embed = discord.Embed(
                title="🏴‍☠️ Bandit Call History",
                color=discord.Color.blue()
            )

            for call in page_calls:
                call_time = datetime.datetime.fromisoformat(call["call_time"])
                bandit_time = datetime.datetime.fromisoformat(call["bandit_time"])
                is_estimated = call.get("is_estimated", False)

                # Add indicator for estimated calls
                prefix = "📊 " if is_estimated else ""
                field_name = f"{prefix}{call_time.strftime('%Y-%m-%d %H:%M:%S')}"

                field_value = (
                    f"**Called by:** {call['user_name']}\n"
                    f"**Time until start:** {call['minutes_until']} minutes\n"
                    f"**Bandit time:** {bandit_time.strftime('%H:%M:%S')}"
                )

                embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=False
                )

            page_num = len(pages) + 1
            total_pages = (len(calls) + calls_per_page - 1) // calls_per_page
            embed.set_footer(
                text=f"Page {page_num}/{total_pages} | Total calls: {len(calls)}"
            )
            pages.append(embed)

        await menu(ctx, pages)

    @bandits.command(name="setrole")
    @checks.admin_or_permissions(manage_guild=True)
    async def bandits_setrole(self, ctx, role: discord.Role):
        """Set the role to monitor for bandit pings"""
        guild_config = self.config.guild(ctx.guild)
        await guild_config.monitored_role_id.set(role.id)
        await ctx.send(f"Now monitoring {role.mention} for bandit pings.")

    @bandits.command(name="reset")
    @checks.admin_or_permissions(manage_guild=True)
    async def bandits_reset(self, ctx):
        """Reset all bandit call data"""
        guild_config = self.config.guild(ctx.guild)
        await guild_config.bandit_calls.set([])
        await ctx.send("All bandit call data has been reset.")

    @bandits.command(name="status")
    async def bandits_status(self, ctx):
        """Show current bandit tracking configuration"""
        guild_config = self.config.guild(ctx.guild)
        role_id = await guild_config.monitored_role_id()
        calls = await guild_config.bandit_calls()

        embed = discord.Embed(
            title="⚙️ Bandit Tracking Status",
            color=discord.Color.green()
        )

        if role_id:
            role = ctx.guild.get_role(role_id)
            role_name = role.mention if role else f"<Unknown Role: {role_id}>"
        else:
            role_name = "Not configured"

        embed.add_field(
            name="Monitored Role",
            value=role_name,
            inline=False
        )

        embed.add_field(
            name="Total Calls Recorded",
            value=str(len(calls)),
            inline=False
        )

        if calls:
            last_call = calls[-1]
            last_time = datetime.datetime.fromisoformat(last_call["bandit_time"])
            embed.add_field(
                name="Last Bandit",
                value=last_time.strftime('%Y-%m-%d %H:%M:%S'),
                inline=False
            )

        await ctx.send(embed=embed)

    def _humanize_delta(self, delta: relativedelta, precision: str = "seconds", max_units: int = 3) -> str:
        """Convert a relativedelta to a human-readable string"""
        units = (
            ("years", delta.years),
            ("months", delta.months),
            ("days", delta.days),
            ("hours", delta.hours),
            ("minutes", delta.minutes),
            ("seconds", delta.seconds),
        )

        time_strings = []
        unit_count = 0

        for unit, value in units:
            if value:
                if value == 1:
                    time_strings.append(f"{value} {unit[:-1]}")
                else:
                    time_strings.append(f"{value} {unit}")
                unit_count += 1

            if unit == precision or unit_count >= max_units:
                break

        if not time_strings:
            return f"less than a {precision[:-1]}"

        if len(time_strings) > 1:
            time_strings[-1] = f"{time_strings[-2]} and {time_strings[-1]}"
            del time_strings[-2]

        return ", ".join(time_strings)
