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
