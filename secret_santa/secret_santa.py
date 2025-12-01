import datetime
import logging
import random
import secrets
import string
from typing import List, Optional, Tuple

import discord
from redbot.core import Config, checks, commands

log = logging.getLogger("red.cog.secret_santa")

IDENTIFIER = 8472916358274916

# Constants for event ID generation
EVENT_ID_LENGTH = 8
MAX_EVENT_ID_RETRIES = 100

# Discord embed field character limit
EMBED_FIELD_MAX_LENGTH = 1024


def generate_event_id() -> str:
    """Generate a random alphanumeric event ID."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(EVENT_ID_LENGTH))


class SecretSanta(commands.Cog):
    """Manage Secret Santa events for your server."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=IDENTIFIER)

        default_guild = {
            "events": {},  # event_name -> event data
        }
        default_global = {
            "event_lookup": {},  # event_id -> {"guild_id": int, "event_name": str}
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

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

    async def _lookup_event_by_id(
        self, event_id: str
    ) -> Optional[Tuple[int, str, dict]]:
        """Look up an event by its unique event ID.

        Returns (guild_id, event_name, event_data) or None if not found.
        """
        event_lookup = await self.config.event_lookup()
        if event_id not in event_lookup:
            return None

        lookup_data = event_lookup[event_id]
        guild_id = lookup_data["guild_id"]
        event_name = lookup_data["event_name"]

        events = await self.config.guild_from_id(guild_id).events()
        if event_name not in events:
            return None

        return (guild_id, event_name, events[event_name])

    async def _generate_unique_event_id(self) -> str:
        """Generate a unique event ID that doesn't conflict with existing ones."""
        event_lookup = await self.config.event_lookup()
        for _ in range(MAX_EVENT_ID_RETRIES):
            event_id = generate_event_id()
            if event_id not in event_lookup:
                return event_id
        # Fallback: use a longer ID
        return generate_event_id() + generate_event_id()

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

        # Generate unique event ID for DM-based messaging
        event_id = await self._generate_unique_event_id()

        # Create participant data
        participant_data = {}
        for member in participants:
            participant_data[str(member.id)] = {
                "matched_to": None,
                "sent_gift": False,
                "received_gift": False,
                "wishlist": None,
            }

        # Create the event
        event = {
            "name": event_name,
            "event_id": event_id,
            "target_date": target_date,
            "max_price": max_price,
            "participants": participant_data,
            "created_by": ctx.author.id,
            "created_at": datetime.datetime.now().isoformat(),
            "matched": False,
        }

        async with self.config.guild(ctx.guild).events() as events:
            events[event_name] = event

        # Register the event ID in the global lookup
        async with self.config.event_lookup() as lookup:
            lookup[event_id] = {
                "guild_id": ctx.guild.id,
                "event_name": event_name,
            }

        # Send DMs to participants asking for their wishlist
        dm_success = 0
        dm_failed = 0
        for member in participants:
            try:
                embed = discord.Embed(
                    title="🎅 You've Been Added to a Secret Santa Event!",
                    description=(
                        f"You've been added to **{event_name}** in **{ctx.guild.name}**!"
                    ),
                    color=discord.Color.red()
                )
                embed.add_field(name="Target Date", value=parsed_date.strftime("%B %d, %Y"), inline=True)
                embed.add_field(name="Max Price", value=max_price, inline=True)
                embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
                embed.add_field(
                    name="📝 Set Your Wishlist",
                    value=(
                        f"Please set your wishlist so your Secret Santa knows what you'd like!\n"
                        f"DM me: `[p]santadm wishlist {event_id} <your wishlist>`\n\n"
                        f"Example: `[p]santadm wishlist {event_id} "
                        f"I'd love a book, some chocolates, or a cozy sweater!`"
                    ),
                    inline=False
                )
                embed.set_footer(text="Your wishlist will be shared with your Secret Santa after matching!")
                await member.send(embed=embed)
                dm_success += 1
            except discord.Forbidden:
                dm_failed += 1

        participant_names = ", ".join(p.display_name for p in participants)
        embed = discord.Embed(
            title="🎅 Secret Santa Event Created!",
            description=f"Event **{event_name}** has been created.",
            color=discord.Color.red()
        )
        embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
        embed.add_field(name="Target Date", value=parsed_date.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Max Price", value=max_price, inline=True)
        embed.add_field(name="Participants", value=f"{len(participants)} people", inline=True)
        embed.add_field(name="DMs Sent", value=f"{dm_success} ✅ / {dm_failed} ❌", inline=True)
        embed.add_field(name="Participant List", value=participant_names, inline=False)
        embed.set_footer(text="Participants have been asked for wishlists. Use [p]santa match to assign pairs!")

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
                "wishlist": None,
            }

        # Apply pairings
        for giver_id, receiver_id in parsed_pairings:
            participant_data[str(giver_id)]["matched_to"] = receiver_id

        # Generate unique event ID for DM-based messaging
        event_id = await self._generate_unique_event_id()

        # Create the event
        event = {
            "name": event_name,
            "event_id": event_id,
            "target_date": target_date,
            "max_price": max_price,
            "participants": participant_data,
            "created_by": ctx.author.id,
            "created_at": datetime.datetime.now().isoformat(),
            "matched": True,  # Already matched since we imported pairings
        }

        async with self.config.guild(ctx.guild).events() as events:
            events[event_name] = event

        # Register the event ID in the global lookup
        async with self.config.event_lookup() as lookup:
            lookup[event_id] = {
                "guild_id": ctx.guild.id,
                "event_name": event_name,
            }

        # Send DMs to participants with their match info and ask for wishlist
        dm_success = 0
        dm_failed = 0
        for giver_id, receiver_id in parsed_pairings:
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
                    embed.add_field(name="Max Price", value=max_price, inline=True)
                    embed.add_field(name="Target Date", value=parsed_date.strftime("%B %d, %Y"), inline=True)
                    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
                    embed.add_field(
                        name="📝 Set Your Wishlist",
                        value=(
                            f"Set your wishlist so your Santa knows what you'd like!\n"
                            f"DM me: `[p]santadm wishlist {event_id} <your wishlist>`"
                        ),
                        inline=False
                    )
                    embed.add_field(
                        name="Anonymous Messaging",
                        value=(
                            f"Send anonymous messages to your giftee via DM:\n"
                            f"`[p]santadm message {event_id} <your message>`\n\n"
                            f"Reply to your Santa via DM:\n"
                            f"`[p]santadm reply {event_id} <your message>`"
                        ),
                        inline=False
                    )
                    embed.set_footer(text="Remember to keep it a secret! 🤫")
                    await giver.send(embed=embed)
                    dm_success += 1
                except discord.Forbidden:
                    dm_failed += 1

        embed = discord.Embed(
            title="🎅 Secret Santa Event Imported!",
            description=f"Event **{event_name}** has been imported with {len(parsed_pairings)} pairings.",
            color=discord.Color.green()
        )
        embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
        embed.add_field(name="Target Date", value=parsed_date.strftime("%B %d, %Y"), inline=True)
        embed.add_field(name="Max Price", value=max_price, inline=True)
        embed.add_field(name="Participants", value=f"{len(all_participants)} people", inline=True)
        embed.add_field(name="DMs Sent", value=f"{dm_success} ✅ / {dm_failed} ❌", inline=True)
        embed.set_footer(text="Participants can use [p]santadm commands in DMs to message their match!")

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
        event_id = event.get("event_id")

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

        # Reload event data to get wishlists
        events = await self.config.guild(ctx.guild).events()
        event = events[event_name]

        # Send DMs to participants
        success_count = 0
        fail_count = 0
        for giver_id, receiver_id in pairings:
            giver = self.bot.get_user(giver_id)
            receiver = self.bot.get_user(receiver_id)
            if giver and receiver:
                try:
                    # Get the receiver's wishlist
                    receiver_wishlist = event["participants"].get(str(receiver_id), {}).get("wishlist")

                    embed = discord.Embed(
                        title="🎅 Secret Santa Match!",
                        description=f"You have been matched for **{event_name}** in **{ctx.guild.name}**!",
                        color=discord.Color.red()
                    )
                    embed.add_field(name="Your Giftee", value=receiver.display_name, inline=True)
                    embed.add_field(name="Max Price", value=event["max_price"], inline=True)
                    embed.add_field(name="Target Date", value=event["target_date"], inline=True)
                    if event_id:
                        embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)

                    # Include the giftee's wishlist if available
                    if receiver_wishlist:
                        embed.add_field(
                            name="🎁 Your Giftee's Wishlist",
                            value=receiver_wishlist[:EMBED_FIELD_MAX_LENGTH],
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="🎁 Your Giftee's Wishlist",
                            value="No wishlist set yet. You can ask them via anonymous message!",
                            inline=False
                        )

                    if event_id:
                        embed.add_field(
                            name="Anonymous Messaging (via DM)",
                            value=(
                                f"Send anonymous messages to your giftee:\n"
                                f"`[p]santadm message {event_id} <your message>`\n\n"
                                f"Reply to your Santa:\n"
                                f"`[p]santadm reply {event_id} <your message>`"
                            ),
                            inline=False
                        )
                    else:
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
        if event_id:
            embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
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
            if len(participant_text) <= EMBED_FIELD_MAX_LENGTH:
                embed.add_field(name="Participant Details", value=participant_text, inline=False)
            else:
                # Truncate if too long
                truncate_at = EMBED_FIELD_MAX_LENGTH - 4
                embed.add_field(
                    name="Participant Details",
                    value=participant_text[:truncate_at] + "...",
                    inline=False
                )

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

        # Get the event_id before deletion to clean up the lookup
        event_id = events[event_name].get("event_id")

        async with self.config.guild(ctx.guild).events() as events:
            del events[event_name]

        # Clean up the global event lookup
        if event_id:
            async with self.config.event_lookup() as lookup:
                if event_id in lookup:
                    del lookup[event_id]

        await ctx.send(f"🗑️ Event `{event_name}` has been deleted.")

    @santa.command(name="remind")
    @checks.admin_or_permissions(manage_guild=True)
    async def santa_remind(self, ctx, event_name: str):
        """Send reminder DMs to all participants in a Secret Santa event.

        Reminds participants to:
        - Update their wishlist
        - Mark their gift as sent (if not already)
        - Mark their gift as received (if not already)
        - Use anonymous DM messaging

        Example: [p]santa remind xmas2024
        """
        events = await self.config.guild(ctx.guild).events()

        if event_name not in events:
            await ctx.send(f"Event `{event_name}` not found.")
            return

        event = events[event_name]
        event_id = event.get("event_id")
        target_date = event.get("target_date", "Not specified")
        max_price = event.get("max_price", "Not specified")

        dm_success = 0
        dm_failed = 0

        for user_id_str, participant_data in event["participants"].items():
            user = self.bot.get_user(int(user_id_str))
            if not user:
                dm_failed += 1
                continue

            try:
                embed = discord.Embed(
                    title="🎅 Secret Santa Reminder!",
                    description=f"A friendly reminder about **{event_name}** in **{ctx.guild.name}**!",
                    color=discord.Color.red()
                )
                embed.add_field(name="Target Date", value=target_date, inline=True)
                embed.add_field(name="Max Price", value=max_price, inline=True)
                if event_id:
                    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)

                # Wishlist reminder
                if participant_data.get("wishlist"):
                    embed.add_field(
                        name="📝 Your Wishlist",
                        value=(
                            f"You have a wishlist set! You can update it anytime.\n"
                            f"DM me: `[p]santadm wishlist {event_id} <your wishlist>`"
                            if event_id else "You have a wishlist set!"
                        ),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📝 Set Your Wishlist",
                        value=(
                            f"You haven't set a wishlist yet! Help your Santa out.\n"
                            f"DM me: `[p]santadm wishlist {event_id} <your wishlist>`"
                            if event_id else "You haven't set a wishlist yet!"
                        ),
                        inline=False
                    )

                # Gift sent reminder (only if matched)
                if event["matched"]:
                    if participant_data.get("sent_gift"):
                        embed.add_field(
                            name="🎁 Gift Sent",
                            value="✅ You've marked your gift as sent!",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="🎁 Gift Sent",
                            value=(
                                f"⏳ Don't forget to mark your gift as sent!\n"
                                f"Use: `[p]santa sent {event_name}` in the server"
                            ),
                            inline=True
                        )

                    # Gift received reminder
                    if participant_data.get("received_gift"):
                        embed.add_field(
                            name="🎄 Gift Received",
                            value="✅ You've marked your gift as received!",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="🎄 Gift Received",
                            value=(
                                f"⏳ Remember to mark when you receive your gift!\n"
                                f"Use: `[p]santa received {event_name}` in the server"
                            ),
                            inline=True
                        )

                # Anonymous messaging reminder (only if matched and event_id exists)
                if event["matched"] and event_id:
                    embed.add_field(
                        name="💬 Anonymous Messaging",
                        value=(
                            f"You can send anonymous messages via DM!\n\n"
                            f"**Message your giftee:**\n"
                            f"`[p]santadm message {event_id} <your message>`\n\n"
                            f"**Reply to your Santa:**\n"
                            f"`[p]santadm reply {event_id} <your message>`"
                        ),
                        inline=False
                    )

                embed.set_footer(text="Happy gifting! 🎁")
                await user.send(embed=embed)
                dm_success += 1
            except discord.Forbidden:
                dm_failed += 1

        embed = discord.Embed(
            title="🎅 Reminders Sent!",
            description=f"Reminder DMs have been sent for **{event_name}**.",
            color=discord.Color.green()
        )
        embed.add_field(name="DMs Sent", value=f"{dm_success} ✅", inline=True)
        embed.add_field(name="DMs Failed", value=f"{dm_failed} ❌", inline=True)
        if dm_failed > 0:
            embed.set_footer(text="Some users have DMs disabled or couldn't be found.")

        await ctx.send(embed=embed)

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

        event = events[event_name]
        event_id = event.get("event_id")
        max_price = event.get("max_price", "Not specified")
        target_date = event.get("target_date", "Not specified")

        added = []
        already_in = []
        added_members = []

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
                        "wishlist": None,
                    }
                    added.append(member.display_name)
                    added_members.append(member)

        # Send DMs to newly added members asking for their wishlist
        dm_success = 0
        dm_failed = 0
        for member in added_members:
            try:
                embed = discord.Embed(
                    title="🎅 You've Been Added to a Secret Santa Event!",
                    description=(
                        f"You've been added to **{event_name}** in **{ctx.guild.name}**!"
                    ),
                    color=discord.Color.red()
                )
                embed.add_field(name="Target Date", value=target_date, inline=True)
                embed.add_field(name="Max Price", value=max_price, inline=True)
                if event_id:
                    embed.add_field(name="Event ID", value=f"`{event_id}`", inline=True)
                    embed.add_field(
                        name="📝 Set Your Wishlist",
                        value=(
                            f"Please set your wishlist so your Secret Santa knows what you'd like!\n"
                            f"DM me: `[p]santadm wishlist {event_id} <your wishlist>`\n\n"
                            f"Example: `[p]santadm wishlist {event_id} "
                            f"I'd love a book, some chocolates, or a cozy sweater!`"
                        ),
                        inline=False
                    )
                embed.set_footer(text="Your wishlist will be shared with your Secret Santa after matching!")
                await member.send(embed=embed)
                dm_success += 1
            except discord.Forbidden:
                dm_failed += 1

        msg = ""
        if added:
            msg += f"✅ Added: {', '.join(added)}\n"
            msg += f"📬 DMs sent: {dm_success} ✅ / {dm_failed} ❌\n"
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

    # DM-only commands using event_id for anonymity
    @commands.group(autohelp=False)
    @commands.dm_only()
    async def santadm(self, ctx):
        """Secret Santa DM commands for anonymous messaging.

        These commands can only be used in DMs with the bot to preserve anonymity.
        Use the Event ID provided when you joined the event.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @santadm.command(name="message")
    async def santadm_message(self, ctx, event_id: str, *, message: str):
        """Send an anonymous message to your Secret Santa giftee (DM only).

        Your identity is kept secret - the bot relays the message.
        Use the Event ID provided when you joined the event.

        Example: [p]santadm message ABC12345 What's your favorite color?
        """
        result = await self._lookup_event_by_id(event_id.upper())

        if not result:
            await ctx.send(
                f"Event with ID `{event_id}` not found. "
                "Please check the Event ID from your Secret Santa notification."
            )
            return

        guild_id, event_name, event = result

        if not event["matched"]:
            await ctx.send("This event hasn't been matched yet. Please wait for the matching to complete.")
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

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Server"

        try:
            embed = discord.Embed(
                title="🎅 Anonymous Secret Santa Message!",
                description=message,
                color=discord.Color.red()
            )
            embed.add_field(name="Event", value=event_name, inline=True)
            embed.add_field(name="Server", value=guild_name, inline=True)
            embed.add_field(name="Event ID", value=f"`{event_id.upper()}`", inline=True)
            embed.add_field(
                name="Reply",
                value=f"Reply anonymously via DM: `[p]santadm reply {event_id.upper()} <message>`",
                inline=False
            )
            embed.set_footer(text="This is from your Secret Santa! 🎁")
            await recipient.send(embed=embed)

            await ctx.send("✅ Your message to your Secret Santa giftee was sent successfully!")

        except discord.Forbidden:
            await ctx.send("Could not send message to your giftee. They may have DMs disabled.")

    @santadm.command(name="reply")
    async def santadm_reply(self, ctx, event_id: str, *, message: str):
        """Send an anonymous reply to your Secret Santa (DM only).

        This allows you to respond to questions from your Secret Santa.
        Use the Event ID provided when you joined the event.

        Example: [p]santadm reply ABC12345 My favorite color is blue!
        """
        result = await self._lookup_event_by_id(event_id.upper())

        if not result:
            await ctx.send(
                f"Event with ID `{event_id}` not found. "
                "Please check the Event ID from your Secret Santa notification."
            )
            return

        guild_id, event_name, event = result

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

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Server"

        try:
            embed = discord.Embed(
                title="🎁 Reply from Your Giftee!",
                description=message,
                color=discord.Color.green()
            )
            embed.add_field(name="Event", value=event_name, inline=True)
            embed.add_field(name="Server", value=guild_name, inline=True)
            embed.add_field(name="Event ID", value=f"`{event_id.upper()}`", inline=True)
            embed.set_footer(text="This is from the person you're buying a gift for! 🎄")
            await santa.send(embed=embed)

            await ctx.send("✅ Your reply to your Secret Santa was sent successfully!")

        except discord.Forbidden:
            await ctx.send("Could not send reply to your Secret Santa. They may have DMs disabled.")

    @santadm.command(name="wishlist")
    async def santadm_wishlist(self, ctx, event_id: str, *, wishlist: str):
        """Set your wishlist for a Secret Santa event (DM only).

        Your wishlist will be shared with your Secret Santa when matching occurs.
        If matching already happened, your Santa will be notified of the update.

        Example: [p]santadm wishlist ABC12345 I'd love a book, some chocolates, or a cozy sweater!
        """
        result = await self._lookup_event_by_id(event_id.upper())

        if not result:
            await ctx.send(
                f"Event with ID `{event_id}` not found. "
                "Please check the Event ID from your Secret Santa notification."
            )
            return

        guild_id, event_name, event = result

        user_id_str = str(ctx.author.id)
        if user_id_str not in event["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        # Update the wishlist
        async with self.config.guild_from_id(guild_id).events() as events:
            events[event_name]["participants"][user_id_str]["wishlist"] = wishlist

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Server"

        await ctx.send(
            f"✅ Your wishlist for **{event_name}** in **{guild_name}** has been saved!\n\n"
            f"**Your wishlist:**\n{wishlist}"
        )

        # If the event is already matched, notify the Santa of the wishlist update
        if event["matched"]:
            # Find who is giving a gift to this user
            santa_id = None
            for giver_id, data in event["participants"].items():
                if data["matched_to"] == ctx.author.id:
                    santa_id = int(giver_id)
                    break

            if santa_id:
                santa = self.bot.get_user(santa_id)
                if santa:
                    try:
                        embed = discord.Embed(
                            title="📝 Your Giftee Updated Their Wishlist!",
                            description="Your giftee has updated their wishlist.",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Event", value=event_name, inline=True)
                        embed.add_field(name="Server", value=guild_name, inline=True)
                        embed.add_field(
                            name="🎁 Updated Wishlist",
                            value=wishlist[:EMBED_FIELD_MAX_LENGTH],
                            inline=False
                        )
                        embed.set_footer(text="Use this information to pick the perfect gift! 🎄")
                        await santa.send(embed=embed)
                    except discord.Forbidden:
                        log.debug(
                            "Failed to DM Santa %s about wishlist update for event %s",
                            santa_id, event_name
                        )

    @santadm.command(name="info")
    async def santadm_info(self, ctx, event_id: str):
        """Get information about your Secret Santa event (DM only).

        Shows your assignment, wishlist, and event details.

        Example: [p]santadm info ABC12345
        """
        result = await self._lookup_event_by_id(event_id.upper())

        if not result:
            await ctx.send(
                f"Event with ID `{event_id}` not found. "
                "Please check the Event ID from your Secret Santa notification."
            )
            return

        guild_id, event_name, event = result

        user_id_str = str(ctx.author.id)
        if user_id_str not in event["participants"]:
            await ctx.send("You are not a participant in this event.")
            return

        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else "Unknown Server"

        participant_data = event["participants"][user_id_str]

        embed = discord.Embed(
            title="🎅 Your Secret Santa Info",
            description=f"Event **{event_name}** in **{guild_name}**",
            color=discord.Color.red()
        )
        embed.add_field(name="Event ID", value=f"`{event_id.upper()}`", inline=True)
        embed.add_field(name="Target Date", value=event.get("target_date", "Not set"), inline=True)
        embed.add_field(name="Max Price", value=event.get("max_price", "Not set"), inline=True)

        if event["matched"]:
            matched_to = participant_data.get("matched_to")
            if matched_to:
                recipient = self.bot.get_user(matched_to)
                giftee_name = recipient.display_name if recipient else f"User {matched_to}"
                embed.add_field(name="Your Giftee", value=giftee_name, inline=True)

                # Get the recipient's wishlist
                recipient_data = event["participants"].get(str(matched_to), {})
                recipient_wishlist = recipient_data.get("wishlist")
                if recipient_wishlist:
                    embed.add_field(
                        name="🎁 Your Giftee's Wishlist",
                        value=recipient_wishlist[:EMBED_FIELD_MAX_LENGTH],
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="🎁 Your Giftee's Wishlist",
                        value="No wishlist set yet.",
                        inline=False
                    )
        else:
            embed.add_field(name="Status", value="⏳ Not matched yet", inline=True)

        # Show user's own wishlist
        my_wishlist = participant_data.get("wishlist")
        if my_wishlist:
            embed.add_field(
                name="📝 Your Wishlist",
                value=my_wishlist[:EMBED_FIELD_MAX_LENGTH],
                inline=False
            )
        else:
            embed.add_field(
                name="📝 Your Wishlist",
                value=f"Not set. Use `[p]santadm wishlist {event_id.upper()} <your wishlist>` to set it!",
                inline=False
            )

        embed.add_field(
            name="Gift Status",
            value="✅ Sent" if participant_data.get("sent_gift") else "⏳ Not yet sent",
            inline=True
        )
        embed.add_field(
            name="Received",
            value="✅ Yes" if participant_data.get("received_gift") else "⏳ Not yet",
            inline=True
        )

        embed.set_footer(text="Keep it a secret! 🤫")
        await ctx.send(embed=embed)
