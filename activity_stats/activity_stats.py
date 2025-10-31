import time
from typing import Optional

import discord
from redbot.core import Config, commands

IDENTIFIER = 1730414669000000000


class ActivityStats(commands.Cog):
    """Track Discord activity and game statistics for all members."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=IDENTIFIER, force_registration=True
        )

        default_guild = {
            "game_stats": {},  # {game_name: total_seconds}
            "user_game_stats": {},  # {user_id: {game_name: total_seconds}}
            "last_activity": {},  # {user_id: {game_name: timestamp}}
        }
        self.config.register_guild(**default_guild)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Track when users start or stop playing games."""
        if not after.guild:
            return

        guild_config = self.config.guild(after.guild)

        # Get the current timestamp
        now = time.time()

        # Check if user was playing a game before
        before_game = self._get_game_name(before)
        after_game = self._get_game_name(after)

        # If the game changed, update stats
        if before_game != after_game:
            # Handle stopping the previous game
            if before_game:
                await self._stop_tracking_game(guild_config, after.id, before_game, now)

            # Handle starting a new game
            if after_game:
                await self._start_tracking_game(guild_config, after.id, after_game, now)

    def _get_game_name(self, member: discord.Member) -> Optional[str]:
        """Extract the game name from a member's activities."""
        for activity in member.activities:
            if isinstance(activity, discord.Game):
                return activity.name
            elif isinstance(activity, discord.Activity) and activity.type == discord.ActivityType.playing:
                return activity.name
        return None

    async def _start_tracking_game(self, guild_config, user_id: int, game_name: str, timestamp: float):
        """Start tracking a game session for a user."""
        async with guild_config.last_activity() as last_activity:
            user_id_str = str(user_id)
            if user_id_str not in last_activity:
                last_activity[user_id_str] = {}
            last_activity[user_id_str][game_name] = timestamp

    async def _stop_tracking_game(self, guild_config, user_id: int, game_name: str, timestamp: float):
        """Stop tracking a game session and update statistics."""
        last_activity = await guild_config.last_activity()
        user_id_str = str(user_id)

        if user_id_str in last_activity and game_name in last_activity[user_id_str]:
            start_time = last_activity[user_id_str][game_name]
            duration = timestamp - start_time

            if duration > 0:
                # Update global game stats
                async with guild_config.game_stats() as game_stats:
                    if game_name not in game_stats:
                        game_stats[game_name] = 0
                    game_stats[game_name] += duration

                # Update user game stats
                async with guild_config.user_game_stats() as user_game_stats:
                    if user_id_str not in user_game_stats:
                        user_game_stats[user_id_str] = {}
                    if game_name not in user_game_stats[user_id_str]:
                        user_game_stats[user_id_str][game_name] = 0
                    user_game_stats[user_id_str][game_name] += duration

            # Remove from last_activity
            async with guild_config.last_activity() as last_activity_update:
                if user_id_str in last_activity_update and game_name in last_activity_update[user_id_str]:
                    del last_activity_update[user_id_str][game_name]
                    # Clean up empty user entries
                    if not last_activity_update[user_id_str]:
                        del last_activity_update[user_id_str]

    @commands.guild_only()
    @commands.command(name="topgames")
    async def top_games(self, ctx, limit: int = 10):
        """Show the most played games on this server.

        Args:
            limit: Number of games to display (default: 10)
        """
        guild_config = self.config.guild(ctx.guild)
        game_stats = await guild_config.game_stats()

        if not game_stats:
            await ctx.send("No game activity has been tracked yet!")
            return

        # Sort games by total playtime
        sorted_games = sorted(game_stats.items(), key=lambda x: x[1], reverse=True)
        sorted_games = sorted_games[:limit]

        embed = discord.Embed(
            title=f"🎮 Top {len(sorted_games)} Games on {ctx.guild.name}",
            color=discord.Color.blue(),
        )

        for i, (game_name, total_seconds) in enumerate(sorted_games, 1):
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            embed.add_field(
                name=f"{i}. {game_name}",
                value=f"{hours}h {minutes}m",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(name="mygames")
    async def my_games(self, ctx, user: Optional[discord.Member] = None):
        """Show game statistics for yourself or another user.

        Args:
            user: The user to check (default: yourself)
        """
        target_user = user or ctx.author
        guild_config = self.config.guild(ctx.guild)
        user_game_stats = await guild_config.user_game_stats()

        user_id_str = str(target_user.id)
        if user_id_str not in user_game_stats or not user_game_stats[user_id_str]:
            await ctx.send(f"{target_user.display_name} hasn't played any games yet!")
            return

        user_stats = user_game_stats[user_id_str]
        sorted_games = sorted(user_stats.items(), key=lambda x: x[1], reverse=True)

        embed = discord.Embed(
            title=f"🎮 {target_user.display_name}'s Games",
            color=discord.Color.green(),
        )

        for i, (game_name, total_seconds) in enumerate(sorted_games[:10], 1):
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            embed.add_field(
                name=f"{i}. {game_name}",
                value=f"{hours}h {minutes}m",
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(name="gameinfo")
    async def game_info(self, ctx, *, game_name: str):
        """Show detailed statistics for a specific game.

        Args:
            game_name: The name of the game to check
        """
        guild_config = self.config.guild(ctx.guild)
        game_stats = await guild_config.game_stats()
        user_game_stats = await guild_config.user_game_stats()

        # Find the game (case-insensitive)
        matching_game = None
        for game in game_stats:
            if game.lower() == game_name.lower():
                matching_game = game
                break

        if not matching_game:
            await ctx.send(f"No statistics found for game: {game_name}")
            return

        total_seconds = game_stats[matching_game]
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)

        # Count players
        player_count = 0
        top_players = []
        for user_id_str, games in user_game_stats.items():
            if matching_game in games:
                player_count += 1
                user_seconds = games[matching_game]
                top_players.append((user_id_str, user_seconds))

        top_players.sort(key=lambda x: x[1], reverse=True)
        top_players = top_players[:5]

        embed = discord.Embed(
            title=f"🎮 {matching_game}",
            description=f"Total playtime: **{hours}h {minutes}m**\nPlayers: **{player_count}**",
            color=discord.Color.purple(),
        )

        if top_players:
            top_players_text = ""
            for i, (user_id_str, user_seconds) in enumerate(top_players, 1):
                member = ctx.guild.get_member(int(user_id_str))
                display_name = member.display_name if member else f"User {user_id_str}"
                user_hours = int(user_seconds // 3600)
                user_minutes = int((user_seconds % 3600) // 60)
                top_players_text += f"{i}. {display_name}: {user_hours}h {user_minutes}m\n"

            embed.add_field(
                name="Top Players",
                value=top_players_text,
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.group(name="activitystats")
    @commands.has_permissions(manage_guild=True)
    async def activity_stats_admin(self, ctx):
        """Admin commands for activity statistics."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @activity_stats_admin.command(name="clear")
    async def clear_stats(self, ctx):
        """Clear all activity statistics for this server."""
        guild_config = self.config.guild(ctx.guild)
        await guild_config.game_stats.set({})
        await guild_config.user_game_stats.set({})
        await guild_config.last_activity.set({})
        await ctx.send("✅ All activity statistics have been cleared!")

    @activity_stats_admin.command(name="info")
    async def stats_info(self, ctx):
        """Show statistics about the tracking system."""
        guild_config = self.config.guild(ctx.guild)
        game_stats = await guild_config.game_stats()
        user_game_stats = await guild_config.user_game_stats()
        last_activity = await guild_config.last_activity()

        total_games = len(game_stats)
        total_users = len(user_game_stats)
        active_users = len(last_activity)

        embed = discord.Embed(
            title="📊 Activity Stats Info",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Games Tracked", value=str(total_games), inline=True)
        embed.add_field(name="Users with Stats", value=str(total_users), inline=True)
        embed.add_field(name="Currently Playing", value=str(active_users), inline=True)

        await ctx.send(embed=embed)
