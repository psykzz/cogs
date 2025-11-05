import asyncio
import logging

import httpx
from redbot.core import commands

log = logging.getLogger("red.cogs.albion_regear")


async def http_get(url, params=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    log.info(f"Making HTTP GET request to {url} with params: {params}")
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params, timeout=10.0)

            if r.status_code == 200:
                response_data = r.json()
                log.info(f"HTTP GET successful for {url} - Status: {r.status_code}")
                log.debug(f"Response data: {response_data}")
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


class AlbionRegear(commands.Cog):
    """Calculates regear costs for Albion Online deaths"""

    def __init__(self, bot):
        self.bot = bot

    async def search_player(self, name):
        """Search for a player by name"""
        log.info(f"Searching for player: {name}")
        url = "https://gameinfo-ams.albiononline.com/api/gameinfo/search"
        params = {"q": name}
        result = await http_get(url, params)

        if result and result.get("players"):
            player = result["players"][0]
            log.info(f"Player found: {player.get('Name')} (ID: {player.get('Id')})")
            return player

        log.warning(f"Player '{name}' not found in search results")
        return None

    async def get_latest_death(self, player_id):
        """Get the latest death event for a player"""
        log.info(f"Fetching latest death for player ID: {player_id}")
        url = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}/deaths"
        result = await http_get(url)

        if result and len(result) > 0:
            death = result[0]
            event_id = death.get("EventId")
            log.info(f"Latest death found - Event ID: {event_id}")
            victim_name = death.get('Victim', {}).get('Name')
            killer_name = death.get('Killer', {}).get('Name')
            log.info(f"Death event details: Victim={victim_name}, Killer={killer_name}")
            return death

        log.warning(f"No deaths found for player ID: {player_id}")
        return None

    async def get_item_prices(self, items_with_quality):
        """Get prices for multiple items with quality matching

        Args:
            items_with_quality: Dict mapping item_id to quality level

        Returns:
            Dict mapping item_id to sell_price_min for the specified quality
        """
        if not items_with_quality:
            log.warning("No items provided for price lookup")
            return {}

        # Build URL with item list in path and use Bridgewatch location
        # Don't filter by quality - get all qualities
        item_list = ",".join(items_with_quality.keys())
        log.info(f"Fetching prices for {len(items_with_quality)} items: {list(items_with_quality.keys())}")
        url = f"https://europe.albion-online-data.com/api/v2/stats/prices/{item_list}?locations=Bridgewatch"
        result = await http_get(url)

        if not result:
            log.error("Failed to fetch item prices - API returned no data")
            return {}

        # Create a map of (item_id, quality) -> sell_price_min
        price_data = {}
        for item_data in result:
            item_id = item_data.get("item_id")
            quality = item_data.get("quality", 0)
            sell_price_min = item_data.get("sell_price_min", 0)

            if sell_price_min and sell_price_min > 0:
                key = (item_id, quality)
                price_data[key] = sell_price_min
                log.debug(f"Price data: {item_id} Q{quality} = {sell_price_min} silver")

        # Match prices to requested items by quality
        price_map = {}
        for item_id, quality in items_with_quality.items():
            key = (item_id, quality)
            if key in price_data:
                price_map[item_id] = price_data[key]
                log.info(f"Price found for {item_id} Q{quality}: {price_data[key]} silver")
            else:
                log.warning(f"No price found for {item_id} Q{quality}")

        log.info(f"Successfully retrieved prices for {len(price_map)}/{len(items_with_quality)} items")
        return price_map

    async def calculate_regear_cost(self, death_event):
        """Calculate the cost to regear from a death event"""
        victim = death_event.get("Victim", {})
        equipment = victim.get("Equipment", {})

        log.info(f"Calculating regear cost for victim: {victim.get('Name')}")

        # Extract all equipment items (excluding inventory)
        # Equipment slots: MainHand, OffHand, Head, Armor, Shoes, Bag, Cape, Mount, Potion, Food
        equipment_slots = [
            "MainHand", "OffHand", "Head", "Armor", "Shoes",
            "Bag", "Cape", "Mount", "Potion", "Food"
        ]

        items_with_quality = {}  # Track items with their quality
        items_to_price = {}  # Track full item data

        # Log all items found in the death event
        log.info("Items found in death event:")
        for slot in equipment_slots:
            item = equipment.get(slot)
            if item and item.get("Type"):
                item_type = item["Type"]
                item_quality = item.get("Quality", 1)  # Default to quality 1 if not specified
                # Consumables (potions, food) have Quality=0, but API only has Q1 prices for them
                if item_quality == 0:
                    item_quality = 1
                item_count = item.get("Count", 1)
                log.info(f"  - {slot}: {item_type} Q{item_quality} (Count: {item_count})")
                items_with_quality[item_type] = item_quality
                items_to_price[item_type] = item
            else:
                log.debug(f"  - {slot}: Empty")

        if not items_with_quality:
            log.warning("No equipment items found in death event")
            return 0, [], []

        log.info(f"Total equipment items to price: {len(items_with_quality)}")

        # Get prices for all items with quality matching
        prices = await self.get_item_prices(items_with_quality)

        # Calculate total cost and track unpriced items
        total_cost = 0
        priced_items = []
        unpriced_items = []

        for item_type, item in items_to_price.items():
            quality = items_with_quality[item_type]
            price = prices.get(item_type, 0)

            if price > 0:
                total_cost += price
                priced_items.append({
                    "type": item_type,
                    "quality": quality,
                    "price": price
                })
                log.info(f"Item {item_type} Q{quality}: {price} silver added to total")
            else:
                unpriced_items.append({
                    "type": item_type,
                    "quality": quality
                })
                log.warning(f"Item {item_type} Q{quality}: No price available")

        msg = f"Regear cost calculation complete - Total: {total_cost} silver"
        msg += f" ({len(priced_items)}/{len(items_with_quality)} items priced)"
        log.info(msg)
        return total_cost, priced_items, unpriced_items

    @commands.command()
    async def regear(self, ctx, name: str):
        """Calculate regear cost for a player's latest death

        Usage: .regear <player_name>
        Example: .regear psykzz
        """
        log.info(f"Regear command invoked by {ctx.author} for player: {name}")
        async with ctx.typing():
            # Search for the player
            player = await self.search_player(name)
            if not player:
                log.warning(f"Regear command failed: Player '{name}' not found")
                await ctx.send(f"Player '{name}' not found.")
                return

            player_id = player.get("Id")
            player_name = player.get("Name", name)

            # Get latest death
            death = await self.get_latest_death(player_id)
            if not death:
                log.warning(f"Regear command failed: No deaths found for player '{player_name}'")
                await ctx.send(f"No deaths found for player '{player_name}'.")
                return

            event_id = death.get("EventId")
            killboard_url = f"https://albiononline.com/killboard/kill/{event_id}"

            # Calculate regear cost
            total_cost, priced_items, unpriced_items = await self.calculate_regear_cost(death)

            # Format the cost with commas for readability
            formatted_cost = f"{total_cost:,}"

            # Build item breakdown
            item_breakdown = ""
            if priced_items:
                lines = ["\n**Item Costs:**"]
                for item in priced_items:
                    item_name = item["type"]
                    item_quality = item["quality"]
                    item_price = f"{item['price']:,}"
                    lines.append(f"- {item_name} (Q{item_quality}): {item_price} silver")
                item_breakdown = "\n".join(lines) + "\n"

            # Build unpriced items section
            unpriced_breakdown = ""
            if unpriced_items:
                lines = ["\n**Items without prices:**"]
                for item in unpriced_items:
                    item_name = item["type"]
                    item_quality = item["quality"]
                    lines.append(f"- {item_name} (Q{item_quality})")
                unpriced_breakdown = "\n".join(lines) + "\n"

            log.info(f"Regear command successful: {player_name} - Total cost: {formatted_cost} silver")

            # Send response
            await ctx.send(
                f"**Regear cost for {player_name}:** {formatted_cost} silver\n"
                f"{item_breakdown}"
                f"{unpriced_breakdown}"
                f"Killboard: {killboard_url}"
            )
