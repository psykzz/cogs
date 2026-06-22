import logging

import discord

log = logging.getLogger("red.cog.wordgame")


class ScoreboardView(discord.ui.View):
    """Persistent view attached to the scoreboard message in a game thread."""

    def __init__(self, cog, thread_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.thread_id = thread_id

        end_button = discord.ui.Button(
            label="End Game",
            emoji="🔚",
            style=discord.ButtonStyle.danger,
            custom_id=f"wordgame:end:{thread_id}",
        )
        end_button.callback = self._end_game_callback
        self.add_item(end_button)

    async def _end_game_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ You need the **Manage Messages** permission to end a game.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        ended = await self.cog.end_game(self.thread_id, ended_by=interaction.user)
        if ended:
            await interaction.followup.send("✅ Game ended.", ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ No active game found in this thread.", ephemeral=True
            )


class BonusDMView(discord.ui.View):
    """View sent in bonus-guess DMs. Lets the player opt out of further DMs."""

    def __init__(self, cog, thread_id: int, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.thread_id = thread_id
        self.user_id = user_id

        ignore_button = discord.ui.Button(
            label="Stop DMs",
            emoji="🚫",
            style=discord.ButtonStyle.secondary,
            custom_id=f"wordgame:ignore:{thread_id}:{user_id}",
        )
        ignore_button.callback = self._ignore_callback
        self.add_item(ignore_button)

    async def _ignore_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        thread = self.cog.bot.get_channel(self.thread_id)
        if thread:
            async with self.cog.config.guild(thread.guild).active_games() as games:
                game = games.get(str(self.thread_id))
                if game:
                    player = game.get("players", {}).get(str(self.user_id))
                    if player:
                        player["ignore_dms"] = True

        # Disable the button and update the DM message
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(
                content=interaction.message.content
                + "\n\n*✅ You won't receive further DMs for this game.*",
                view=self,
            )
        except discord.HTTPException:
            pass
