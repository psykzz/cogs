import asyncio
import logging
import secrets
import string
import time

import discord
from discord.ext import tasks
from redbot.core import Config, checks, commands

from .game import (
    MAX_GUESSES,
    MAX_LENGTH,
    MIN_LENGTH,
    compute_feedback,
    compute_score,
    get_random_word,
    is_valid_guess,
)
from .views import BonusDMView, ScoreboardView

log = logging.getLogger("red.cog.wordgame")

INACTIVITY_TIMEOUT = 600  # 10 minutes without a guess → end game
BONUS_GUESS_INTERVAL = 300  # 5 minutes → grant +1 guess to all done players
IDENTIFIER = 7391028475916283


def _generate_game_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _build_scoreboard_text(game: dict, reveal_word: bool = False) -> str:
    """Build the full scoreboard embed description for a game."""
    word = game["word"]
    length = game["length"]
    game_id = game["game_id"]
    status = game["status"]
    players = game.get("players", {})

    status_icon = "🟢 Active" if status == "active" else "🔴 Ended"
    header = f"🎮 **Word Game** — {length} letters | Game `#{game_id}`\n"
    header += f"Status: {status_icon}"
    inactive_closes_at = game.get("inactive_closes_at")
    if inactive_closes_at and status == "active":
        header += f"\n⏳ Auto-closes <t:{int(inactive_closes_at)}:R> if no guesses"
    if reveal_word:
        header += f"\n🔑 The word was: **{word.upper()}**"
    header += "\n"

    # Leaderboard
    if players:
        sorted_players = sorted(
            players.items(), key=lambda kv: kv[1]["score"], reverse=True
        )
        leaderboard = "\n📊 **Leaderboard**\n"
        for rank, (uid, pdata) in enumerate(sorted_players, 1):
            if pdata.get("done"):
                bonus_at = pdata.get("bonus_guess_at")
                done_marker = f" ⏰ <t:{int(bonus_at)}:R>" if bonus_at else " ✅"
            else:
                done_marker = ""
            leaderboard += f"{rank}. <@{uid}> — **{pdata['score']} pts**{done_marker}\n"
    else:
        leaderboard = "\n📊 **Leaderboard**\n*No guesses yet — type a word in this thread!*\n"

    # Guess history
    guess_lines = "\n💬 **Guesses**\n"
    if players:
        for uid, pdata in sorted_players:
            guesses = pdata.get("guesses", [])
            feedbacks = pdata.get("feedbacks", [])
            points_per = pdata.get("points_per_guess", [])
            if not guesses:
                continue
            parts = []
            for g, fb, pts in zip(guesses, feedbacks, points_per):
                parts.append(f"`{g.upper()}` {fb} (+{pts}pts)")
            guess_lines += f"<@{uid}>: {' | '.join(parts)}\n"
    else:
        guess_lines += "*None yet*\n"

    return header + leaderboard + guess_lines


class WordGame(commands.Cog):
    """Multiplayer PvP word guessing game played in Discord threads."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER)

        default_guild = {
            "active_games": {},  # thread_id (str) -> game data
        }
        self.config.register_guild(**default_guild)

        # Per-thread locks prevent concurrent guesses from racing on claimed_positions
        self._guess_locks: dict = {}

        self.bot.loop.create_task(self._register_persistent_views())
        self._close_games_loop.start()

    def cog_unload(self):
        self._close_games_loop.cancel()

    def _get_thread_lock(self, thread_id: int):
        """Return (creating if necessary) a per-thread asyncio.Lock."""
        if thread_id not in self._guess_locks:
            self._guess_locks[thread_id] = asyncio.Lock()
        return self._guess_locks[thread_id]

    async def _register_persistent_views(self):
        """Re-register ScoreboardView for all active games after a restart."""
        await self.bot.wait_until_ready()
        has_active = False
        all_guilds = await self.config.all_guilds()
        for guild_data in all_guilds.values():
            for thread_id_str, game in guild_data.get("active_games", {}).items():
                if game.get("status") == "active":
                    thread_id = int(thread_id_str)
                    msg_id = game.get("scoreboard_message_id")
                    view = ScoreboardView(self, thread_id)
                    self.bot.add_view(view, message_id=msg_id)
                    has_active = True
        if has_active and not self._close_games_loop.is_running():
            self._close_games_loop.start()

    @tasks.loop(seconds=30)
    async def _close_games_loop(self):
        """End inactive games and grant per-player bonus guesses on schedule."""
        now = time.time()
        has_active = False
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            for thread_id_str, game in guild_data.get("active_games", {}).items():
                if game.get("status") != "active":
                    continue
                has_active = True
                thread_id = int(thread_id_str)

                closes_at = game.get("inactive_closes_at")
                if closes_at and now >= closes_at:
                    await self.end_game(thread_id)
                    has_active = False
                    continue

                for uid, player in game.get("players", {}).items():
                    bonus_at = player.get("bonus_guess_at")
                    if bonus_at and now >= bonus_at:
                        await self._grant_bonus_guess(thread_id, game, uid, player)

        if not has_active:
            self._close_games_loop.stop()

    @_close_games_loop.before_loop
    async def _before_close_games_loop(self):
        await self.bot.wait_until_ready()

    async def _grant_bonus_guess(
        self, thread_id: int, game: dict, user_id: str, player: dict
    ):
        """Grant +1 guess to a single player and DM them unless opted out."""
        thread = self.bot.get_channel(thread_id)
        if not thread:
            return

        player["max_guesses"] = player.get("max_guesses", MAX_GUESSES) + 1
        player["done"] = False
        player["bonus_guess_at"] = None

        async with self.config.guild(thread.guild).active_games() as games:
            games[str(thread_id)] = game

        await self._update_scoreboard(thread, game)

        if player.get("ignore_dms"):
            return

        user = self.bot.get_user(int(user_id))
        if not user:
            return
        try:
            view = BonusDMView(self, thread_id, int(user_id))
            self.bot.add_view(view)
            await user.send(
                f"⏰ **Bonus guess!** You have an extra guess waiting in "
                f"**Word Game** (Game `#{game['game_id']}`) — head back to "
                f"{thread.mention} and use it!",
                view=view,
            )
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------ #
    #  Commands                                                            #
    # ------------------------------------------------------------------ #

    @commands.hybrid_group(name="wordgame")
    async def wordgame(self, ctx: commands.Context):
        """Multiplayer PvP word guessing game."""

    @wordgame.command(name="start")
    @commands.guild_only()
    async def wordgame_start(self, ctx: commands.Context, length: int = 5):
        """Start a new word guessing game in this channel.

        Parameters
        ----------
        length : int
            Length of the word to guess (3–8, default 5).
        """
        await ctx.defer(ephemeral=True)

        if not MIN_LENGTH <= length <= MAX_LENGTH:
            await ctx.send(
                f"❌ Word length must be between {MIN_LENGTH} and {MAX_LENGTH}.",
                ephemeral=True,
            )
            return

        # Check no game is already running in this channel
        active_games = await self.config.guild(ctx.guild).active_games()
        for game in active_games.values():
            if (
                game.get("status") == "active"
                and game.get("channel_id") == ctx.channel.id
            ):
                await ctx.send(
                    "❌ There's already an active game in this channel.",
                    ephemeral=True,
                )
                return

        word = get_random_word(length)
        if not word:
            await ctx.send(
                f"❌ No words found for length {length}. Try a different length.",
                ephemeral=True,
            )
            return

        game_id = _generate_game_id()

        # Post the announcement message and create a thread from it
        announce_msg = await ctx.channel.send(
            f"🎮 A new **Word Game** has started! ({length} letters) — Game `#{game_id}`\n"
            f"Head into the thread below and start guessing!"
        )
        thread = await announce_msg.create_thread(
            name=f"Word Game #{game_id}",
            auto_archive_duration=1440,
        )

        # Post the live scoreboard as the first message in the thread
        game_data = {
            "game_id": game_id,
            "word": word,
            "length": length,
            "status": "active",
            "channel_id": ctx.channel.id,
            "thread_id": thread.id,
            "announce_message_id": announce_msg.id,
            "scoreboard_message_id": None,
            "claimed_positions": [],
            "claimed_letters": [],
            "inactive_closes_at": time.time() + INACTIVITY_TIMEOUT,
            "players": {},
        }

        scoreboard_text = _build_scoreboard_text(game_data)
        view = ScoreboardView(self, thread.id)
        scoreboard_msg = await thread.send(scoreboard_text, view=view)
        game_data["scoreboard_message_id"] = scoreboard_msg.id

        # Persist to Config
        async with self.config.guild(ctx.guild).active_games() as active_games:
            active_games[str(thread.id)] = game_data

        # Register the persistent view now that we have the message id
        self.bot.add_view(view, message_id=scoreboard_msg.id)

        # Ensure the inactivity watcher is running
        if not self._close_games_loop.is_running():
            self._close_games_loop.start()

        await ctx.send(
            f"✅ Game started! Head to {thread.mention} to play.", ephemeral=True
        )

    @wordgame.command(name="end")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_messages=True)
    async def wordgame_end(self, ctx: commands.Context):
        """Force-end the active game in the current thread (admin only)."""
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.send("❌ Run this command inside a game thread.", ephemeral=True)
            return

        ended = await self.end_game(ctx.channel.id, ended_by=ctx.author)
        if ended:
            await ctx.send("✅ Game ended.", ephemeral=True)
        else:
            await ctx.send("❌ No active game found in this thread.", ephemeral=True)

    # ------------------------------------------------------------------ #
    #  Game logic                                                          #
    # ------------------------------------------------------------------ #

    async def end_game(self, thread_id: int, ended_by=None) -> bool:
        """
        End the active game in thread_id. Posts final results, disables buttons.
        Returns True if a game was found and ended, False otherwise.
        """
        thread = self.bot.get_channel(thread_id)
        if thread is None:
            return False

        guild = thread.guild
        active_games = await self.config.guild(guild).active_games()
        game = active_games.get(str(thread_id))
        if not game or game.get("status") != "active":
            return False

        game["status"] = "ended"
        async with self.config.guild(guild).active_games() as games:
            if str(thread_id) in games:
                games[str(thread_id)]["status"] = "ended"

        await self._update_scoreboard(thread, game, reveal_word=True)

        players = game.get("players", {})
        if players:
            sorted_players = sorted(
                players.items(), key=lambda kv: kv[1]["score"], reverse=True
            )
            winner_id, winner_data = sorted_players[0]
            result_lines = "\n".join(
                f"{rank}. <@{uid}> — {pdata['score']} pts"
                for rank, (uid, pdata) in enumerate(sorted_players, 1)
            )
            suffix = f" (ended by {ended_by.mention})" if ended_by else ""
            await thread.send(
                f"🏁 **Game Over!**{suffix}\n"
                f"The word was **{game['word'].upper()}**\n\n"
                f"🏆 Winner: <@{winner_id}> with **{winner_data['score']} pts**\n\n"
                f"{result_lines}"
            )
        else:
            await thread.send(
                f"🏁 **Game Over!** No guesses were made.\n"
                f"The word was **{game['word'].upper()}**"
            )

        return True

    async def _update_scoreboard(
        self, thread: discord.Thread, game: dict, reveal_word: bool = False
    ):
        """Edit the pinned scoreboard message with current game state."""
        msg_id = game.get("scoreboard_message_id")
        if not msg_id:
            return
        try:
            msg = await thread.fetch_message(msg_id)
            text = _build_scoreboard_text(game, reveal_word=reveal_word)
            if game["status"] == "ended":
                # Disable the End Game button
                await msg.edit(content=text, view=None)
            else:
                await msg.edit(content=text)
        except discord.NotFound:
            log.warning("Scoreboard message not found for game %s", game.get("game_id"))
        except discord.HTTPException as e:
            log.error("Failed to update scoreboard: %s", e)

    async def _process_guess(self, message: discord.Message, guild):
        """Validate and score a guess, then update state and scoreboard."""
        guess = message.content.strip().lower()
        thread = message.channel
        user_id = str(message.author.id)

        # Re-read fresh state here — the caller holds a per-thread lock so this
        # read is guaranteed to reflect all previously committed guesses.
        active_games = await self.config.guild(guild).active_games()
        game = active_games.get(str(thread.id))
        if not game or game.get("status") != "active":
            return

        word = game["word"]

        # Guard: player already done
        players = game.setdefault("players", {})
        player = players.setdefault(
            user_id,
            {
                "guesses": [],
                "feedbacks": [],
                "points_per_guess": [],
                "score": 0,
                "done": False,
                "max_guesses": MAX_GUESSES,
                "bonus_guess_at": None,
                "ignore_dms": False,
            },
        )

        if player["done"]:
            await message.reply("❌ You've already used all your guesses!")
            return

        # Guard: wrong length (silent — handled by caller before reaching here)
        if len(guess) != game["length"]:
            return

        # Guard: not a valid word
        if not is_valid_guess(guess):
            try:
                await message.reply(f"❌ `{guess.upper()}` is not a recognised word.")
            except discord.HTTPException:
                pass
            return

        # Guard: word already guessed by someone (not an error, just ignore)
        all_guesses = [g for p in players.values() for g in p["guesses"]]
        if guess in all_guesses:
            return

        # Score the guess
        feedback = compute_feedback(guess, word)
        points, new_pos_claims, new_letter_claims = compute_score(
            guess, word, feedback, game["claimed_positions"], game.get("claimed_letters", [])
        )

        # Update state
        player["guesses"].append(guess)
        player["feedbacks"].append(feedback)
        player["points_per_guess"].append(points)
        player["score"] += points
        game["claimed_positions"].extend(new_pos_claims)
        game.setdefault("claimed_letters", []).extend(new_letter_claims)

        guesses_used = len(player["guesses"])
        word_found = guess == word
        if word_found or guesses_used >= player["max_guesses"]:
            player["done"] = True
            # Only offer a bonus guess if the player ran out without finding the word
            if not word_found:
                player["bonus_guess_at"] = time.time() + BONUS_GUESS_INTERVAL

        # Reset the inactivity timer on every valid guess
        game["inactive_closes_at"] = time.time() + INACTIVITY_TIMEOUT

        # Persist
        async with self.config.guild(guild).active_games() as games:
            games[str(thread.id)] = game

        # Reply with feedback
        guesses_left = player["max_guesses"] - guesses_used
        feedback_display = " ".join(f"`{c}`" for c in feedback)
        reply = (
            f"{feedback_display}\n"
            f"**+{points} pts** | "
            f"{'🎉 Correct!' if word_found else f'{guesses_left} guess(es) left'}"
        )
        try:
            await message.reply(reply)
        except discord.HTTPException:
            pass

        await self._update_scoreboard(thread, game)

    # ------------------------------------------------------------------ #
    #  Event listener                                                      #
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process messages in active game threads as guess attempts."""
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        # Must be in a thread
        if not isinstance(message.channel, discord.Thread):
            return

        thread_id = str(message.channel.id)

        # Read a snapshot to check quickly — _process_guess handles persistence
        active_games = await self.config.guild(message.guild).active_games()
        game = active_games.get(thread_id)

        if not game or game.get("status") != "active":
            return

        guess = message.content.strip().lower()

        # Only process pure alpha strings of the correct length
        if not guess.isalpha() or len(guess) != game["length"]:
            return

        async with self._get_thread_lock(int(thread_id)):
            await self._process_guess(message, message.guild)
