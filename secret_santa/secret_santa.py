import datetime
import logging
import random
from typing import List, Optional

import discord
from redbot.core import Config, checks, commands

log = logging.getLogger("red.cog.secret_santa")

IDENTIFIER = 8472916358274916


class SecretSanta(commands.Cog):
    """Manage Secret Santa events for your server."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER)

        default_guild = {
            "events": {},  # event_name -> event data
        }
        self.config.register_guild(**default_guild)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """Delete user data when requested."""
        all_guilds = await self.config.all_guilds()
        for guild_id, guild_data in all_guilds.items():
            events = guild_data.get("events", {})
            modified = False
            for event_name, event in events.items():
                participants = event.get("participants", {})
                user_id_str = str(user_id)
                if user_id_str in participants:
                    del events[event_name]["participants"][user_id_str]
                    modified = True
            if modified:
                await self.config.guild_from_id(guild_id).events.set(events)

    @commands.group(autohelp=False)
    @commands.guild_only()
    async def santa(self, ctx):
        """Secret Santa event management."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @santa.command(name="create")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_create(
        self,
        ctx,
        event_name: str,
        target_date: str,
        max_price: str,
        *participants: discord.Member
    ):
        """Create a new Secret Santa event.

        Parameters:
        - event_name: A unique name for this event
        - target_date: The target date (YYYY-MM-DD format)
        - max_price: Maximum gift price (e.g., "$25" or "25 USD")
        - participants: Mention all participants (at least 2 required)

        Example: [p]santa create xmas2024 2024-12-25 "$50" @user1 @user2 @user3
        """
        # Validate date format
        try:
            parsed_date = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            await ctx.send("Invalid date format. Please use YYYY-MM-DD (e.g., 2024-12-25)")
            return

        # Validate participants
        if len(participants) < 2:
            await ctx.send("You need at least 2 participants for a Secret Santa event.")
            return

        # Check for duplicate participants
        unique_participants = set(p.id for p in participants)
        if len(unique_participants) != len(participants):
            await ctx.send("Duplicate participants detected. Each person can only participate once.")
            return

        # Check if event already exists
        events = await self.config.guild(ctx.guild).events()
        if event_name in events:
            await ctx.send(
                f"An event named `{event_name}` already exists. "
                "Use a different name or delete the existing event."
            )
            return

        # Create participant data
        participant_data = {}
        for member in participants:
            participant_data[str(member.id)] = {
                "matched_to": None,
                "sent_gift": False,
                "received_gift": False,
            }

        # Create the event
        event = {
            "name": event_name,
            "target_date": target_date,
            "max_price": max_price,
            "participants": participant_data,
            "created_by": ctx.author.id,
            "created_at": datetime.datetime.now().isoformat(),
            "matched": False,
        }

        async with self.config.guild(ctx.guild).events() as events:
            events[event_name] = event

        participant_names = ", ".join(p.display_name for p in participants)
        embed = discord.Embed(
            title="🎅 Secret Santa Event Created!",
            description=f"Event **{event_name}** has been created.",
            color=discord.Color.red()
        )
        embed.add_field(name="Target Date", value=parsed_date.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Max Price", value=max_price, inline=True)
        embed.add_field(name="Participants", value=f"{len(participants)} people", inline=True)
        embed.add_field(name="Participant List", value=participant_names, inline=False)
        embed.set_footer(text="Use [p]santa match to assign pairs!")

        await ctx.send(embed=embed)

    @santa.command(name="import")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_import(
        self,
        ctx,
        event_name: str,
        target_date: str,
        max_price: str,
        *pairings: str
    ):
        """Import an existing Secret Santa event with forced pairings.

        Parameters:
        - event_name: A unique name for this event
        - target_date: The target date (YYYY-MM-DD format)
        - max_price: Maximum gift price (e.g., "$25" or "25 USD")
        - pairings: Pairs in format "giver_id:receiver_id" (use Discord user IDs)

        Example: [p]santa import xmas2024 2024-12-25 "$50" 123456789:987654321 111222333:444555666
        """
        # Validate date format
        try:
            parsed_date = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            await ctx.send("Invalid date format. Please use YYYY-MM-DD (e.g., 2024-12-25)")
            return

        if len(pairings) < 1:
            await ctx.send("You need at least 1 pairing to import.")
            return

        # Check if event already exists
        events = await self.config.guild(ctx.guild).events()
        if event_name in events:
            await ctx.send(
                f"An event named `{event_name}` already exists. "
                "Use a different name or delete the existing event."
            )
            return

        # Parse pairings
        participant_data = {}
        parsed_pairings = []
        all_givers = set()
        all_receivers = set()

        for pairing in pairings:
            if ":" not in pairing:
                await ctx.send(f"Invalid pairing format: `{pairing}`. Use format `giver_id:receiver_id`")
                return
            giver_str, receiver_str = pairing.split(":", 1)
            try:
                giver_id = int(giver_str.strip())
                receiver_id = int(receiver_str.strip())
            except ValueError:
                await ctx.send(f"Invalid user IDs in pairing: `{pairing}`. IDs must be numbers.")
                return

            if giver_id in all_givers:
                await ctx.send(f"User {giver_id} is listed as a giver more than once.")
                return
            if giver_id == receiver_id:
                await ctx.send(
                    f"User {giver_id} cannot give a gift to themselves. "
                    "Please fix the pairing."
                )
                return
            all_givers.add(giver_id)
            all_receivers.add(receiver_id)
            parsed_pairings.append((giver_id, receiver_id))

        # Validate that pairings form a complete exchange
        # Every participant should both give and receive
        if all_givers != all_receivers:
            missing_givers = all_receivers - all_givers
            missing_receivers = all_givers - all_receivers
            msg = "Incomplete pairings detected. "
            if missing_givers:
                msg += f"Users {missing_givers} receive but don't give. "
            if missing_receivers:
                msg += f"Users {missing_receivers} give but don't receive."
            await ctx.send(msg)
            return

        # Create participant data from pairings
        all_participants = all_givers | all_receivers
        for user_id in all_participants:
            participant_data[str(user_id)] = {
                "matched_to": None,
                "sent_gift": False,
                "received_gift": False,
            }

        # Apply pairings
        for giver_id, receiver_id in parsed_pairings:
            participant_data[str(giver_id)]["matched_to"] = receiver_id

        # Create the event
        event = {
            "name": event_name,
            "target_date": target_date,
            "max_price": max_price,
            "participants": participant_data,
            "created_by": ctx.author.id,
            "created_at": datetime.datetime.now().isoformat(),
            "matched": True,  # Already matched since we imported pairings
        }

        async with self.config.guild(ctx.guild).events() as events:
            events[event_name] = event

        embed = discord.Embed(
            title="🎅 Secret Santa Event Imported!",
            description=f"Event **{event_name}** has been imported with {len(parsed_pairings)} pairings.",
            color=discord.Color.green()
        )
        embed.add_field(name="Target Date", value=parsed_date.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Max Price", value=max_price, inline=True)
        embed.add_field(name="Participants", value=f"{len(all_participants)} people", inline=True)
        embed.set_footer(text="Participants can now use [p]santa message to contact their match!")

        await ctx.send(embed=embed)

    @santa.command(name="match")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_match(self, ctx, event_name: str):
        """Match all participants in a Secret Santa event.

        This will randomly assign each participant to give a gift to another participant.
        Each person gives to exactly one person and receives from exactly one person.

        Example: [p]santa match xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        event = events[event_name]

        if event["matched"]:
            await ctx.send(
                f"Event `{event_name}` has already been matched. "
                "Use `[p]santa rematch` to redo the matching."
            )
            return

        participants = list(event["participants"].keys())

        if len(participants) < 2:
            await ctx.send("Not enough participants to match.")
            return

        # Generate random pairings (each person gives to one person)
        pairings = self._generate_pairings([int(p) for p in participants])
        if not pairings:
            await ctx.send("Failed to generate valid pairings. Please try again.")
            return

        # Update participant data with pairings
        async with self.config.guild(ctx.guild).events() as events:
            for giver_id, receiver_id in pairings:
                events[event_name]["participants"][str(giver_id)]["matched_to"] = receiver_id
            events[event_name]["matched"] = True

        # Send DMs to participants
        success_count = 0
        fail_count = 0
        for giver_id, receiver_id in pairings:
            giver = self.bot.get_user(giver_id)
            receiver = self.bot.get_user(receiver_id)
            if giver and receiver:
                try:
                    embed = discord.Embed(
                        title="🎅 Secret Santa Match!",
                        description=f"You have been matched for **{event_name}** in **{ctx.guild.name}**!",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Your Giftee", value=receiver.display_name, inline=True)
                    embed.add_field(name="Max Price", value=event["max_price"], inline=True)
                    embed.add_field(name="Target Date", value=event["target_date"], inline=True)
                    embed.add_field(
                        name="Anonymous Messaging",
                        value=(
                            f"Use `[p]santa message {event_name} <your message>` "
                            "in the server to send an anonymous message to your giftee!"
                        ),
                        inline=False
                    )
                    embed.set_footer(text="Remember to keep it a secret! 🤫")
                    await giver.send(embed=embed)
                    success_count += 1
                except discord.Forbidden:
                    fail_count += 1

        embed = discord.Embed(
            title="🎅 Matching Complete!",
            description=f"All participants in **{event_name}** have been matched!",
            color=discord.Color.green()
        )
        embed.add_field(name="DMs Sent", value=str(success_count), inline=True)
        embed.add_field(name="DMs Failed", value=str(fail_count), inline=True)
        if fail_count > 0:
            embed.set_footer(text="Some users have DMs disabled. They can check their match with [p]santa whoami")

        await ctx.send(embed=embed)

    @santa.command(name="rematch")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_rematch(self, ctx, event_name: str):
        """Redo matching for a Secret Santa event.

        This will clear all existing pairings and create new random ones.

        Example: [p]santa rematch xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        # Reset matched status
        async with self.config.guild(ctx.guild).events() as events:
            for user_id in events[event_name]["participants"]:
                events[event_name]["participants"][user_id]["matched_to"] = None
            events[event_name]["matched"] = False

        await ctx.send(
            f"Pairings for `{event_name}` have been reset. "
            f"Use `[p]santa match {event_name}` to create new pairings."
        )

    def _generate_pairings(self, participants: List[int]) -> Optional[List[tuple]]:
        """Generate random pairings where no one is matched to themselves."""
        # Use derangement algorithm
        shuffled = participants.copy()
        max_attempts = 100

        for _ in range(max_attempts):
            random.shuffle(shuffled)
            # Check that no one is matched to themselves
            if all(participants[i] != shuffled[i] for i in range(len(participants))):
                return list(zip(participants, shuffled))

        return None

    @santa.command(name="message")
    async def santa_message(self, ctx, event_name: str, *, message: str):
        """Send an anonymous message to your Secret Santa giftee.

        Your identity will be kept secret - the bot will relay the message.

        Example: [p]santa message xmas2024 What's your favorite color?
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        event = events[event_name]

        if not event["matched"]:
            await ctx.send("This event hasn't been matched yet. Ask an admin to run the matching.")
            return

        user_id_str = str(ctx.author.id)
        if user_id_str not in event["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        matched_to = event["participants"][user_id_str]["matched_to"]
        if not matched_to:
            await ctx.send("You haven't been matched to anyone yet.")
            return

        recipient = self.bot.get_user(matched_to)
        if not recipient:
            await ctx.send("Could not find your giftee. They may have left the server.")
            return

        try:
            embed = discord.Embed(
                title="🎅 Anonymous Secret Santa Message!",
                description=message,
                color=discord.Color.red()
            )
            embed.add_field(name="Event", value=event_name, inline=True)
            embed.add_field(name="Server", value=ctx.guild.name, inline=True)
            embed.add_field(
                name="Reply",
                value=f"Use `[p]santa reply {event_name} <message>` in the server to reply anonymously!",
                inline=False
            )
            embed.set_footer(text="This is from your Secret Santa! 🎁")
            await recipient.send(embed=embed)

            # Delete the command message to preserve anonymity
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

            # Send confirmation via DM to the sender
            try:
                await ctx.author.send(
                    f"✅ Your message to your Secret Santa giftee in "
                    f"**{event_name}** was sent successfully!"
                )
            except discord.Forbidden:
                # If we can't DM them, send a temporary message in channel
                temp_msg = await ctx.send("✅ Message sent!")
                await temp_msg.delete(delay=5)

        except discord.Forbidden:
            await ctx.send("Could not send message to your giftee. They may have DMs disabled.")

    @santa.command(name="reply")
    async def santa_reply(self, ctx, event_name: str, *, message: str):
        """Send an anonymous reply to your Secret Santa (the person giving you a gift).

        This allows you to respond to questions from your Secret Santa.

        Example: [p]santa reply xmas2024 My favorite color is blue!
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        event = events[event_name]

        if not event["matched"]:
            await ctx.send("This event hasn't been matched yet.")
            return

        user_id_str = str(ctx.author.id)
        if user_id_str not in event["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        # Find who is giving a gift to this user
        santa_id = None
        for giver_id, data in event["participants"].items():
            if data["matched_to"] == ctx.author.id:
                santa_id = int(giver_id)
                break

        if not santa_id:
            await ctx.send("Could not find your Secret Santa. This might be a configuration error.")
            return

        santa = self.bot.get_user(santa_id)
        if not santa:
            await ctx.send("Could not find your Secret Santa. They may have left the server.")
            return

        try:
            embed = discord.Embed(
                title="🎁 Reply from Your Giftee!",
                description=message,
                color=discord.Color.green()
            )
            embed.add_field(name="Event", value=event_name, inline=True)
            embed.add_field(name="Server", value=ctx.guild.name, inline=True)
            embed.set_footer(text="This is from the person you're buying a gift for! 🎄")
            await santa.send(embed=embed)

            # Delete the command message to preserve anonymity
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass

            # Send confirmation via DM
            try:
                await ctx.author.send(f"✅ Your reply to your Secret Santa in **{event_name}** was sent successfully!")
            except discord.Forbidden:
                temp_msg = await ctx.send("✅ Reply sent!")
                await temp_msg.delete(delay=5)

        except discord.Forbidden:
            await ctx.send("Could not send reply to your Secret Santa. They may have DMs disabled.")

    @santa.command(name="sent")
    async def santa_sent(self, ctx, event_name: str):
        """Mark that you have sent your gift.

        Example: [p]santa sent xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        user_id_str = str(ctx.author.id)
        if user_id_str not in events[event_name]["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        async with self.config.guild(ctx.guild).events() as events:
            events[event_name]["participants"][user_id_str]["sent_gift"] = True

        await ctx.send("🎁 You've marked your gift as **sent**! Thank you!")

    @santa.command(name="received")
    async def santa_received(self, ctx, event_name: str):
        """Mark that you have received your gift.

        Example: [p]santa received xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        user_id_str = str(ctx.author.id)
        if user_id_str not in events[event_name]["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        async with self.config.guild(ctx.guild).events() as events:
            events[event_name]["participants"][user_id_str]["received_gift"] = True

        await ctx.send("🎄 You've marked your gift as **received**! Enjoy your present!")

    @santa.command(name="whoami")
    async def santa_whoami(self, ctx, event_name: str):
        """Check who you are matched to give a gift to (sent via DM).

        Example: [p]santa whoami xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        event = events[event_name]
        user_id_str = str(ctx.author.id)

        if user_id_str not in event["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        if not event["matched"]:
            await ctx.send("This event hasn't been matched yet.")
            return

        matched_to = event["participants"][user_id_str]["matched_to"]
        if not matched_to:
            await ctx.send("You haven't been matched to anyone yet.")
            return

        recipient = self.bot.get_user(matched_to)
        if not recipient:
            await ctx.send("Could not find your giftee. They may have left the server.")
            return

        try:
            embed = discord.Embed(
                title="🎅 Your Secret Santa Assignment",
                description=f"For event **{event_name}** in **{ctx.guild.name}**",
                color=discord.Color.red()
            )
            embed.add_field(name="Your Giftee", value=recipient.display_name, inline=True)
            embed.add_field(name="Max Price", value=event["max_price"], inline=True)
            embed.add_field(name="Target Date", value=event["target_date"], inline=True)
            embed.add_field(
                name="Gift Status",
                value="✅ Sent" if event["participants"][user_id_str]["sent_gift"] else "⏳ Not yet sent",
                inline=True
            )
            embed.set_footer(text="Keep it a secret! 🤫")
            await ctx.author.send(embed=embed)
            await ctx.send("📬 Check your DMs!")
        except discord.Forbidden:
            await ctx.send("I couldn't send you a DM. Please enable DMs from server members.")

    @santa.command(name="status")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_status(self, ctx, event_name: str):
        """Check the status of a Secret Santa event (admin only).

        Shows all participants and their gift status.

        Example: [p]santa status xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        event = events[event_name]

        embed = discord.Embed(
            title=f"🎅 Secret Santa Status: {event_name}",
            color=discord.Color.red()
        )
        embed.add_field(name="Target Date", value=event["target_date"], inline=True)
        embed.add_field(name="Max Price", value=event["max_price"], inline=True)
        embed.add_field(name="Matched", value="✅ Yes" if event["matched"] else "❌ No", inline=True)

        # Count statuses
        total = len(event["participants"])
        sent_count = sum(1 for p in event["participants"].values() if p.get("sent_gift"))
        received_count = sum(1 for p in event["participants"].values() if p.get("received_gift"))

        embed.add_field(name="Participants", value=str(total), inline=True)
        embed.add_field(name="Gifts Sent", value=f"{sent_count}/{total}", inline=True)
        embed.add_field(name="Gifts Received", value=f"{received_count}/{total}", inline=True)

        # Participant details
        participant_lines = []
        for user_id_str, data in event["participants"].items():
            user = self.bot.get_user(int(user_id_str))
            name = user.display_name if user else f"User {user_id_str}"
            sent = "✅" if data.get("sent_gift") else "⏳"
            received = "✅" if data.get("received_gift") else "⏳"
            participant_lines.append(f"{name}: Sent {sent} | Received {received}")

        if participant_lines:
            # Split into multiple fields if needed
            participant_text = "\n".join(participant_lines)
            if len(participant_text) <= 1024:
                embed.add_field(name="Participant Details", value=participant_text, inline=False)
            else:
                # Truncate if too long
                embed.add_field(name="Participant Details", value=participant_text[:1020] + "...", inline=False)

        await ctx.send(embed=embed)

    @santa.command(name="list")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_list(self, ctx):
        """List all Secret Santa events in this server.

        Example: [p]santa list
        """
        events = await self.config.guild(ctx.guild).events()

        if not events:
            await ctx.send("No Secret Santa events found in this server.")
            return

        embed = discord.Embed(
            title="🎅 Secret Santa Events",
            color=discord.Color.red()
        )

        for event_name, event in events.items():
            participant_count = len(event["participants"])
            matched_status = "✅ Matched" if event["matched"] else "⏳ Not matched"
            value = (
                f"Date: {event['target_date']}\n"
                f"Price: {event['max_price']}\n"
                f"Participants: {participant_count}\n"
                f"Status: {matched_status}"
            )
            embed.add_field(name=event_name, value=value, inline=True)

        await ctx.send(embed=embed)

    @santa.command(name="delete")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_delete(self, ctx, event_name: str):
        """Delete a Secret Santa event.

        Example: [p]santa delete xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        async with self.config.guild(ctx.guild).events() as events:
            del events[event_name]

        await ctx.send(f"🗑️ Event `{event_name}` has been deleted.")

    @santa.command(name="add")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_add(self, ctx, event_name: str, *members: discord.Member):
        """Add participants to an existing event (before matching).

        Example: [p]santa add xmas2024 @user1 @user2
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        if events[event_name]["matched"]:
            await ctx.send("Cannot add participants after matching. Use `[p]santa rematch` to reset matching first.")
            return

        if not members:
            await ctx.send("Please mention at least one member to add.")
            return

        added = []
        already_in = []

        async with self.config.guild(ctx.guild).events() as events:
            for member in members:
                user_id_str = str(member.id)
                if user_id_str in events[event_name]["participants"]:
                    already_in.append(member.display_name)
                else:
                    events[event_name]["participants"][user_id_str] = {
                        "matched_to": None,
                        "sent_gift": False,
                        "received_gift": False,
                    }
                    added.append(member.display_name)

        msg = ""
        if added:
            msg += f"✅ Added: {', '.join(added)}\n"
        if already_in:
            msg += f"ℹ️ Already in event: {', '.join(already_in)}"

        await ctx.send(msg or "No changes made.")

    @santa.command(name="remove")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_remove(self, ctx, event_name: str, *members: discord.Member):
        """Remove participants from an existing event (before matching).

        Example: [p]santa remove xmas2024 @user1 @user2
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        if events[event_name]["matched"]:
            await ctx.send("Cannot remove participants after matching. Use `[p]santa rematch` to reset matching first.")
            return

        if not members:
            await ctx.send("Please mention at least one member to remove.")
            return

        removed = []
        not_in = []

        async with self.config.guild(ctx.guild).events() as events:
            for member in members:
                user_id_str = str(member.id)
                if user_id_str in events[event_name]["participants"]:
                    del events[event_name]["participants"][user_id_str]
                    removed.append(member.display_name)
                else:
                    not_in.append(member.display_name)

        msg = ""
        if removed:
            msg += f"🗑️ Removed: {', '.join(removed)}\n"
        if not_in:
            msg += f"ℹ️ Not in event: {', '.join(not_in)}"

        await ctx.send(msg or "No changes made.")
