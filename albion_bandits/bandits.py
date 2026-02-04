import asyncio
import datetime
import json
import logging
import math
import re

import discord
from dateutil.relativedelta import relativedelta
from discord.ext import tasks
from redbot.core import Config, commands, checks
from redbot.core.utils.menus import menu

try:
    from nats.aio.client import Client as NATS
    NATS_AVAILABLE = True
except ImportError:
    NATS_AVAILABLE = False

log = logging.getLogger("red.cogs.albion_bandits")

IDENTIFIER = 8472651938472651938  # Random identifier for this cog

# NATS server configuration
NATS_SERVERS = {
    "americas": "nats://public:thenewalbiondata@nats.albion-online-data.com:4222",
    "asia": "nats://public:thenewalbiondata@nats.albion-online-data.com:24222",
    "europe": "nats://public:thenewalbiondata@nats.albion-online-data.com:34222",
}
NATS_SUBJECT = "banditevent.ingest"

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
    "nats_enabled": False,  # Enable NATS integration
    "nats_region": "americas",  # Default NATS region
    "nats_channel_id": None,  # Channel to post NATS notifications
}


class AlbionBandits(commands.Cog):
    """Track Albion Online bandit event role mentions and timing"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )
        self.config.register_guild(**default_guild)
        self.nats_clients = {}  # {guild_id: NATS client}
        self.nats_subscriptions = {}  # {guild_id: subscription}
        # Track recently processed NATS events to prevent duplicates
        # Format: {guild_id: {(event_time_iso, advance_notice): event_time}}
        self._processed_events = {}
        self._processed_events_lock = asyncio.Lock()
        self._last_cleanup_time = datetime.datetime.utcnow()
        self._nats_connection_task.start()

    async def cog_unload(self):
        """Cancel the background task when cog unloads"""
        self._nats_connection_task.cancel()
        # Close all NATS connections asynchronously
        for guild_id, nc in list(self.nats_clients.items()):
            try:
                if nc.is_connected:
                    await nc.close()
                    log.info(f"Closed NATS connection for guild {guild_id}")
            except Exception as e:
                log.error(f"Error closing NATS connection for guild {guild_id}: {e}")

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

    @tasks.loop(minutes=5.0)
    async def _nats_connection_task(self):
        """Background task to manage NATS connections for guilds"""
        if not NATS_AVAILABLE:
            log.warning("NATS library not available. NATS integration disabled.")
            return

        try:
            # Check all guilds and ensure NATS connections
            all_guilds = await self.config.all_guilds()

            for guild_id, guild_data in all_guilds.items():
                if guild_data.get("nats_enabled", False):
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        await self._ensure_nats_connection(guild)
                else:
                    # Disconnect if NATS is disabled
                    if guild_id in self.nats_clients:
                        await self._disconnect_nats(guild_id)
        except Exception as e:
            log.exception(f"Error in NATS connection task: {e}")

    @_nats_connection_task.before_loop
    async def _before_nats_task(self):
        """Wait for bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()

    async def _ensure_nats_connection(self, guild: discord.Guild):
        """Ensure NATS connection is established for a guild"""
        guild_id = guild.id

        # Check if already connected
        if guild_id in self.nats_clients:
            nc = self.nats_clients[guild_id]
            if nc.is_connected:
                return
            else:
                # Connection lost, clean up
                await self._disconnect_nats(guild_id)

        try:
            # Get guild configuration
            guild_config = self.config.guild(guild)
            region = await guild_config.nats_region()
            nats_url = NATS_SERVERS.get(region, NATS_SERVERS["americas"])

            log.info(f"Connecting to NATS for guild {guild.name} ({guild_id}) on {region} region")

            # Create NATS client
            nc = NATS()
            await nc.connect(nats_url)

            # Subscribe to bandit spawn events
            async def message_handler(msg):
                """Handle NATS message without creating untracked tasks"""
                try:
                    await self._handle_nats_message(guild, msg)
                except Exception as e:
                    log.exception(f"Error in NATS message handler: {e}")

            sub = await nc.subscribe(NATS_SUBJECT, cb=message_handler)

            self.nats_clients[guild_id] = nc
            self.nats_subscriptions[guild_id] = sub

            log.info(f"Successfully connected to NATS for guild {guild.name} ({guild_id})")
        except Exception as e:
            log.error(f"Failed to connect to NATS for guild {guild.name} ({guild_id}): {e}")

    async def _disconnect_nats(self, guild_id: int):
        """Disconnect NATS client for a guild"""
        if guild_id in self.nats_clients:
            try:
                nc = self.nats_clients[guild_id]
                if nc.is_connected:
                    await nc.close()
                log.info(f"Disconnected NATS for guild {guild_id}")
            except Exception as e:
                log.error(f"Error disconnecting NATS for guild {guild_id}: {e}")
            finally:
                del self.nats_clients[guild_id]
                if guild_id in self.nats_subscriptions:
                    del self.nats_subscriptions[guild_id]

    def _cleanup_processed_events_internal(self):
        """Clean up old entries from the processed events cache (older than 1 hour from event time).

        Note: This method must be called while holding _processed_events_lock.
        """
        now = datetime.datetime.utcnow()
        for guild_id in list(self._processed_events.keys()):
            self._processed_events[guild_id] = {
                key: event_time for key, event_time in self._processed_events[guild_id].items()
                if (now - event_time).total_seconds() < 3600
            }
            # Remove empty guild entries
            if not self._processed_events[guild_id]:
                del self._processed_events[guild_id]
        self._last_cleanup_time = now

    async def _is_nats_event_duplicate(self, guild_id: int, event_time: datetime.datetime, advance_notice: bool) -> bool:
        """Check if a NATS event has already been processed recently.

        Returns True if this is a duplicate event that should be skipped.
        Thread-safe via asyncio lock.
        """
        async with self._processed_events_lock:
            # Periodically clean up old entries (every 10 minutes)
            now = datetime.datetime.utcnow()
            if (now - self._last_cleanup_time).total_seconds() > 600:
                self._cleanup_processed_events_internal()

            # Create cache entry for this guild if it doesn't exist
            if guild_id not in self._processed_events:
                self._processed_events[guild_id] = {}

            # Create a unique key for this event
            event_key = (event_time.isoformat(), advance_notice)

            # debug validation of event key
            log.info(f"event key - {event_key} == {event_time.isoformat()},  {advance_notice}, is_dup: {event_key in self._processed_events[guild_id]}")
            
            
            # Check if we've seen this exact event recently (within last hour)
            if event_key in self._processed_events[guild_id]:
                return True

            # Mark this event as processed (store event_time, not processing time)
            self._processed_events[guild_id][event_key] = event_time
            return False

    async def _handle_nats_message(self, guild: discord.Guild, msg):
        """Handle incoming NATS messages about bandit events"""
        try:
            data = json.loads(msg.data.decode())
            log.debug(f"Received NATS message for guild {guild.name}: {data}")

            # Parse the message
            event_time_ticks = data.get("EventTime")
            advance_notice = data.get("AdvanceNotice", False)

            if event_time_ticks is None:
                log.warning(f"NATS message missing EventTime: {data}")
                return

            # Convert .NET ticks to datetime
            # .NET ticks are 100-nanosecond intervals since 0001-01-01 00:00:00
            # Unix epoch in .NET ticks is 621355968000000000
            TICKS_UNIX_EPOCH = 621355968000000000
            TICKS_PER_SECOND = 10000000

            unix_timestamp = (event_time_ticks - TICKS_UNIX_EPOCH) / TICKS_PER_SECOND
            event_time = datetime.datetime.utcfromtimestamp(unix_timestamp)

            # Check for duplicate events before processing
            if await self._is_nats_event_duplicate(guild.id, event_time, advance_notice):
                log.info(
                    f"Skipping duplicate NATS bandit event - Guild: {guild.name}, "
                    f"AdvanceNotice: {advance_notice}, EventTime: {event_time}"
                )
                return

            log.info(
                f"NATS bandit event - Guild: {guild.name}, "
                f"AdvanceNotice: {advance_notice}, EventTime: {event_time}"
            )

            # Process the event
            if advance_notice:
                # 15 minutes before event starts
                await self._handle_advance_notice(guild, event_time)
            else:
                # Event is active, EventTime is when it ends
                await self._handle_active_event(guild, event_time)

        except Exception as e:
            log.exception(f"Error handling NATS message for guild {guild.name}: {e}")

    async def _handle_advance_notice(self, guild: discord.Guild, start_time: datetime.datetime):
        """Handle 15-minute advance notice for bandit event"""
        guild_config = self.config.guild(guild)
        channel_id = await guild_config.nats_channel_id()
        role_id = await guild_config.monitored_role_id()

        if not channel_id:
            log.debug(f"No notification channel configured for guild {guild.name}")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            log.warning(f"Notification channel {channel_id} not found in guild {guild.name}")
            return

        # Calculate minutes until start
        now = datetime.datetime.utcnow()
        minutes_until = int((start_time - now).total_seconds() / 60)

        # Create embed notification
        embed = discord.Embed(
            title="🏴‍☠️ Bandit Event Incoming!",
            description=f"Bandits will spawn in approximately **{minutes_until} minutes**",
            color=discord.Color.orange(),
            timestamp=start_time
        )
        embed.add_field(
            name="Start Time",
            value=start_time.strftime('%Y-%m-%d %H:%M:%S'),
            inline=False
        )
        embed.set_footer(text="Source: Albion Data Project (NATS)")

        # Mention the role if configured
        content = None
        if role_id:
            role = guild.get_role(role_id)
            if role:
                content = role.mention

        try:
            await channel.send(content=content, embed=embed)
            log.info(f"Sent advance notice to {channel.name} in {guild.name}")
        except discord.HTTPException as e:
            log.error(f"Failed to send advance notice to {channel.name}: {e}")

        # Record the bandit call
        await self._record_nats_bandit_call(guild, start_time, minutes_until)

    async def _handle_active_event(self, guild: discord.Guild, end_time: datetime.datetime):
        """Handle active bandit event (EventTime is when it ends)"""
        # Calculate when the event started (assume it just started)
        start_time = datetime.datetime.utcnow()

        guild_config = self.config.guild(guild)
        channel_id = await guild_config.nats_channel_id()

        if not channel_id:
            log.debug(f"No notification channel configured for guild {guild.name}")
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            log.warning(f"Notification channel {channel_id} not found in guild {guild.name}")
            return

        # Create embed notification
        embed = discord.Embed(
            title="🏴‍☠️ Bandit Event Active!",
            description="Bandits are spawning now!",
            color=discord.Color.red(),
            timestamp=end_time
        )
        embed.add_field(
            name="Event End Time",
            value=end_time.strftime('%Y-%m-%d %H:%M:%S'),
            inline=False
        )
        embed.set_footer(text="Source: Albion Data Project (NATS)")

        try:
            await channel.send(embed=embed)
            log.info(f"Sent active event notice to {channel.name} in {guild.name}")
        except discord.HTTPException as e:
            log.error(f"Failed to send active event notice to {channel.name}: {e}")

        # Record the bandit call
        await self._record_nats_bandit_call(guild, start_time, 0)

    async def _record_nats_bandit_call(self, guild: discord.Guild, bandit_time: datetime.datetime, minutes_until: int):
        """Record a bandit call from NATS"""
        guild_config = self.config.guild(guild)

        # Create call record
        call_record = {
            "user_id": 0,  # System generated
            "user_name": "NATS (Albion Data Project)",
            "channel_id": 0,
            "message_id": 0,
            "minutes_until": minutes_until,
            "call_time": datetime.datetime.utcnow().isoformat(),
            "bandit_time": bandit_time.isoformat(),
            "message_content": "Automated event from Albion Data Project",
            "is_estimated": False,
        }

        async with guild_config.bandit_calls() as calls_list:
            if calls_list:
                last_call = calls_list[-1]
                last_bandit_time = datetime.datetime.fromisoformat(last_call["bandit_time"])

                # Create estimated calls if there's a significant gap
                estimated_calls = await self._create_estimated_calls(
                    guild,
                    last_bandit_time,
                    bandit_time
                )

                if estimated_calls:
                    calls_list.extend(estimated_calls)
                    log.debug(f"Added {len(estimated_calls)} estimated call(s) from NATS")

            # Add the new call
            calls_list.append(call_record)

        log.info(f"Recorded NATS bandit call for guild {guild.name}")

    @commands.hybrid_group(invoke_without_command=True)
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
        nats_enabled = await guild_config.nats_enabled()
        nats_region = await guild_config.nats_region()
        nats_channel_id = await guild_config.nats_channel_id()

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

        # Add NATS status
        nats_status = "✅ Enabled" if nats_enabled else "❌ Disabled"
        if nats_enabled and not NATS_AVAILABLE:
            nats_status = "⚠️ Enabled but library not installed"
        embed.add_field(
            name="NATS Integration",
            value=nats_status,
            inline=True
        )

        if nats_enabled:
            embed.add_field(
                name="NATS Region",
                value=nats_region.capitalize(),
                inline=True
            )

            if nats_channel_id:
                channel = ctx.guild.get_channel(nats_channel_id)
                channel_name = channel.mention if channel else f"<Unknown: {nats_channel_id}>"
            else:
                channel_name = "Not configured"

            embed.add_field(
                name="NATS Notification Channel",
                value=channel_name,
                inline=True
            )

            # Show connection status
            is_connected = ctx.guild.id in self.nats_clients and self.nats_clients[ctx.guild.id].is_connected
            connection_status = "🟢 Connected" if is_connected else "🔴 Disconnected"
            embed.add_field(
                name="NATS Connection",
                value=connection_status,
                inline=True
            )

        await ctx.send(embed=embed)

    @bandits.command(name="nats_enable")
    @checks.admin_or_permissions(manage_guild=True)
    async def bandits_nats_enable(self, ctx, channel: discord.TextChannel = None):
        """Enable NATS integration for real-time bandit events

        Parameters
        ----------
        channel : discord.TextChannel, optional
            Channel to post NATS notifications. If not provided, uses current channel.
        """
        if not NATS_AVAILABLE:
            await ctx.send(
                "❌ NATS integration is not available. Please install the `nats-py` package.",
                ephemeral=True
            )
            return

        notification_channel = channel or ctx.channel

        guild_config = self.config.guild(ctx.guild)
        await guild_config.nats_enabled.set(True)
        await guild_config.nats_channel_id.set(notification_channel.id)

        # Trigger immediate connection attempt
        await self._ensure_nats_connection(ctx.guild)

        embed = discord.Embed(
            title="✅ NATS Integration Enabled",
            description="Real-time bandit event tracking is now active.",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Notification Channel",
            value=notification_channel.mention,
            inline=False
        )
        embed.add_field(
            name="Region",
            value=(await guild_config.nats_region()).capitalize(),
            inline=False
        )
        embed.set_footer(text="Use [p]bandits nats_region to change the game server region")

        await ctx.send(embed=embed)

    @bandits.command(name="nats_disable")
    @checks.admin_or_permissions(manage_guild=True)
    async def bandits_nats_disable(self, ctx):
        """Disable NATS integration"""
        guild_config = self.config.guild(ctx.guild)
        await guild_config.nats_enabled.set(False)

        # Disconnect NATS
        await self._disconnect_nats(ctx.guild.id)

        await ctx.send("✅ NATS integration has been disabled.")

    @bandits.command(name="nats_region")
    @checks.admin_or_permissions(manage_guild=True)
    async def bandits_nats_region(self, ctx, region: str):
        """Set the NATS region (americas, asia, or europe)

        Parameters
        ----------
        region : str
            Game server region: americas, asia, or europe
        """
        region_lower = region.lower()
        if region_lower not in NATS_SERVERS:
            await ctx.send(
                f"❌ Invalid region. Choose from: {', '.join(NATS_SERVERS.keys())}",
                ephemeral=True
            )
            return

        guild_config = self.config.guild(ctx.guild)
        old_region = await guild_config.nats_region()
        await guild_config.nats_region.set(region_lower)

        # If NATS is enabled and region changed, reconnect
        nats_enabled = await guild_config.nats_enabled()
        if nats_enabled and old_region != region_lower:
            await self._disconnect_nats(ctx.guild.id)
            await self._ensure_nats_connection(ctx.guild)

        await ctx.send(f"✅ NATS region set to **{region_lower.capitalize()}**")

    @bandits.command(name="nats_channel")
    @checks.admin_or_permissions(manage_guild=True)
    async def bandits_nats_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for NATS notifications

        Parameters
        ----------
        channel : discord.TextChannel
            Channel to post NATS notifications
        """
        guild_config = self.config.guild(ctx.guild)
        await guild_config.nats_channel_id.set(channel.id)
        await ctx.send(f"✅ NATS notifications will be posted in {channel.mention}")

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
