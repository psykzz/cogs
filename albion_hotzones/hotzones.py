import asyncio
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Dict, List, Tuple

import discord
import httpx
from redbot.core import commands, Config

log = logging.getLogger("red.cogs.albion_hotzones")


async def http_get(url, params=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        log.debug(f"Making HTTP GET request to {url} (attempt {attempt + 1}/{max_attempts})")
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params, timeout=15.0)

            if r.status_code == 200:
                response_data = r.json()
                log.debug(f"HTTP GET successful for {url} - Status: {r.status_code}")
                return response_data
            else:
                attempt += 1
                log.warning(f"HTTP GET failed for {url} - Status: {r.status_code}, Attempt {attempt}/{max_attempts}")
                await asyncio.sleep(2)
        except (httpx.ConnectTimeout, httpx.RequestError) as e:
            attempt += 1
            log.warning(f"HTTP GET error for {url}: {type(e).__name__}: {str(e)}, Attempt {attempt}/{max_attempts}")
            await asyncio.sleep(2)

    log.error(f"HTTP GET failed after {max_attempts} attempts for {url}")
    return None


class AlbionHotZones(commands.Cog):
    """Track combat hot zones in Albion Online"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=73602, force_registration=True)
        self.config.register_global(
            poll_interval=120,  # Poll every 2 minutes
            kill_timeframe=840,  # Track kills within 14 minutes (840 seconds)
        )
        # Store recent kills in memory: {battle_id: [kill_events]}
        self.recent_kills: Dict[int, List[Dict]] = defaultdict(list)
        self._poll_task = None
        self._last_event_id = None

    async def cog_load(self):
        """Start the background polling task when cog loads"""
        self._poll_task = self.bot.loop.create_task(self._poll_loop())
        log.info("Started hot zones polling task")

    async def cog_unload(self):
        """Cancel the background polling task when cog unloads"""
        if self._poll_task:
            self._poll_task.cancel()
            log.info("Cancelled hot zones polling task")

    async def _poll_loop(self):
        """Background task to poll the Albion gameinfo API"""
        await self.bot.wait_until_ready()
        log.info("Hot zones poll loop started")

        while True:
            try:
                poll_interval = await self.config.poll_interval()
                await asyncio.sleep(poll_interval)
                await self._fetch_recent_kills()
                await self._cleanup_old_kills()
            except asyncio.CancelledError:
                log.info("Hot zones poll loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in hot zones poll loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying on error

    async def _fetch_recent_kills(self):
        """Fetch recent kill events from the Albion gameinfo API"""
        url = "https://gameinfo-ams.albiononline.com/api/gameinfo/events"
        # Fetch a reasonable batch of recent events to scan for new kills
        params = {"limit": 51}

        log.debug("Fetching recent kills from Albion API")
        result = await http_get(url, params)

        if not result:
            log.warning("Failed to fetch kill events")
            return

        if not isinstance(result, list):
            log.warning(f"Unexpected API response format: {type(result)}")
            return

        new_kills = 0

        for event in result:
            event_id = event.get("EventId")

            # Skip if we've already processed this event
            # Note: Assumes event IDs are generally increasing; uses >= to be defensive
            if self._last_event_id and event_id and event_id <= self._last_event_id:
                continue

            # Only track OPEN_WORLD kills (red/black zones)
            kill_area = event.get("KillArea")
            if kill_area != "OPEN_WORLD":
                continue

            # Parse timestamp
            timestamp_str = event.get("TimeStamp")
            if not timestamp_str:
                continue

            try:
                event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                log.warning(f"Invalid timestamp format: {timestamp_str}")
                continue

            # Get battle ID to group kills by zone
            battle_id = event.get("BattleId")
            if not battle_id:
                continue

            # Store the kill event
            kill_data = {
                "event_id": event_id,
                "timestamp": event_time,
                "battle_id": battle_id,
                "kill_fame": event.get("TotalVictimKillFame", 0),
                "participants": event.get("numberOfParticipants", 0),
            }

            self.recent_kills[battle_id].append(kill_data)
            new_kills += 1

        # Update last seen event ID
        if result:
            latest_event_id = max(event.get("EventId", 0) for event in result)
            if not self._last_event_id or latest_event_id > self._last_event_id:
                self._last_event_id = latest_event_id

        if new_kills > 0:
            log.info(f"Added {new_kills} new kills across {len(self.recent_kills)} battle zones")

    async def _cleanup_old_kills(self):
        """Remove kills older than the configured timeframe"""
        kill_timeframe = await self.config.kill_timeframe()
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=kill_timeframe)

        battles_to_remove = []
        for battle_id, kills in self.recent_kills.items():
            # Filter out old kills
            self.recent_kills[battle_id] = [
                k for k in kills if k["timestamp"] > cutoff_time
            ]
            # Mark empty battles for removal
            if not self.recent_kills[battle_id]:
                battles_to_remove.append(battle_id)

        # Remove empty battle entries
        for battle_id in battles_to_remove:
            del self.recent_kills[battle_id]

        if battles_to_remove:
            log.debug(f"Cleaned up {len(battles_to_remove)} inactive battle zones")

    def _get_hot_zones(self) -> List[Tuple[int, int, int, int]]:
        """
        Get hot zones sorted by kill count

        Returns:
            List of tuples: (battle_id, kill_count, total_fame, participant_count)
        """
        hot_zones = []

        for battle_id, kills in self.recent_kills.items():
            if not kills:
                continue

            kill_count = len(kills)
            total_fame = sum(k["kill_fame"] for k in kills)
            total_participants = sum(k["participants"] for k in kills)

            hot_zones.append((battle_id, kill_count, total_fame, total_participants))

        # Sort by kill count (descending)
        hot_zones.sort(key=lambda x: x[1], reverse=True)

        return hot_zones

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def hotzones(self, ctx):
        """Show current hot zones for PvP combat in Albion Online"""
        await self._show_hotzones(ctx)

    async def _show_hotzones(self, ctx):
        """Display the current hot zones"""
        hot_zones = self._get_hot_zones()

        if not hot_zones:
            embed = discord.Embed(
                title="🔥 Albion Online Hot Zones",
                description="No recent combat activity detected in the last 14 minutes.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        embed = discord.Embed(
            title="🔥 Albion Online Hot Zones",
            description="Most active PvP zones based on recent kills (last 14 minutes)",
            color=discord.Color.red()
        )

        # Show top 10 hot zones
        for idx, (battle_id, kill_count, total_fame, participants) in enumerate(hot_zones[:10], 1):
            # Format fame with thousands separator
            fame_str = f"{total_fame:,}"

            field_value = (
                f"**Kills:** {kill_count}\n"
                f"**Total Fame:** {fame_str}\n"
                f"**Players Involved:** {participants}"
            )

            embed.add_field(
                name=f"{idx}. Battle Zone #{battle_id}",
                value=field_value,
                inline=False
            )

        # Add footer with stats
        total_zones = len(hot_zones)
        total_kills = sum(z[1] for z in hot_zones)

        embed.set_footer(
            text=f"Total active zones: {total_zones} | Total kills tracked: {total_kills}"
        )

        await ctx.send(embed=embed)

    @hotzones.command(name="stats")
    async def hotzones_stats(self, ctx):
        """Show statistics about hot zone tracking"""
        hot_zones = self._get_hot_zones()

        embed = discord.Embed(
            title="📊 Hot Zones Tracking Statistics",
            color=discord.Color.green()
        )

        total_zones = len(hot_zones)
        total_kills = sum(z[1] for z in hot_zones)
        total_fame = sum(z[2] for z in hot_zones)

        embed.add_field(
            name="Active Battle Zones",
            value=str(total_zones),
            inline=True
        )

        embed.add_field(
            name="Total Kills Tracked",
            value=str(total_kills),
            inline=True
        )

        embed.add_field(
            name="Total Fame",
            value=f"{total_fame:,}",
            inline=True
        )

        poll_interval = await self.config.poll_interval()
        kill_timeframe = await self.config.kill_timeframe()

        embed.add_field(
            name="Poll Interval",
            value=f"{poll_interval} seconds",
            inline=True
        )

        embed.add_field(
            name="Tracking Window",
            value=f"{kill_timeframe // 60} minutes",
            inline=True
        )

        embed.add_field(
            name="Last Event ID",
            value=str(self._last_event_id) if self._last_event_id else "None",
            inline=True
        )

        await ctx.send(embed=embed)

    @hotzones.command(name="top")
    async def hotzones_top(self, ctx, count: int = 5):
        """Show the top N hot zones

        Usage: .hotzones top [count]
        Example: .hotzones top 3
        """
        if count < 1 or count > 20:
            await ctx.send("❌ Count must be between 1 and 20.")
            return

        hot_zones = self._get_hot_zones()

        if not hot_zones:
            await ctx.send("No recent combat activity detected.")
            return

        # Limit to requested count
        hot_zones = hot_zones[:count]

        embed = discord.Embed(
            title=f"🔥 Top {len(hot_zones)} Hot Zones",
            description="Most active PvP zones in the last 14 minutes",
            color=discord.Color.orange()
        )

        for idx, (battle_id, kill_count, total_fame, participants) in enumerate(hot_zones, 1):
            fame_str = f"{total_fame:,}"

            field_value = (
                f"**Kills:** {kill_count} | "
                f"**Fame:** {fame_str} | "
                f"**Players:** {participants}"
            )

            embed.add_field(
                name=f"{idx}. Battle Zone #{battle_id}",
                value=field_value,
                inline=False
            )

        await ctx.send(embed=embed)
