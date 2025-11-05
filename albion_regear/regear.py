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

    async def get_item_prices(self, item_ids):
        """Get prices for multiple items"""
        if not item_ids:
            log.warning("No item IDs provided for price lookup")
            return {}

        # Build URL with item list in path and use Bridgewatch location
        item_list = ",".join(item_ids)
        log.info(f"Fetching prices for {len(item_ids)} items: {item_ids}")
        url = f"https://europe.albion-online-data.com/api/v2/stats/prices/{item_list}"
        params = {"locations": "Bridgewatch", "qualities": "1"}
        result = await http_get(url, params)

        if not result:
            log.error("Failed to fetch item prices - API returned no data")
            return {}

        # Create a map of item_id -> sell_price_min
        price_map = {}
        for item_data in result:
            item_id = item_data.get("item_id")
            sell_price_min = item_data.get("sell_price_min", 0)
            # Avoid extreme values by checking if sell_price_min is reasonable
            if sell_price_min and sell_price_min > 0:
                # Use existing price or take the max across cities
                if item_id not in price_map or sell_price_min > price_map[item_id]:
                    price_map[item_id] = sell_price_min
                    log.info(f"Price found for {item_id}: {sell_price_min} silver")
            else:
                msg = f"No valid price found for item: {item_id}"
                msg += f" (sell_price_min={sell_price_min})"
                log.warning(msg)

        # Log items that didn't get prices
        for item_id in item_ids:
            if item_id not in price_map:
                log.warning(f"Item {item_id} has no price data available")

        log.info(f"Successfully retrieved prices for {len(price_map)}/{len(item_ids)} items")
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

        item_ids = []
        items_to_price = {}  # Track which items we're pricing

        # Log all items found in the death event
        log.info("Items found in death event:")
        for slot in equipment_slots:
            item = equipment.get(slot)
            if item and item.get("Type"):
                item_type = item["Type"]
                item_count = item.get("Count", 1)
                log.info(f"  - {slot}: {item_type} (Count: {item_count})")
                item_ids.append(item_type)
                items_to_price[item_type] = item
            else:
                log.debug(f"  - {slot}: Empty")

        if not item_ids:
            log.warning("No equipment items found in death event")
            return 0, []

        log.info(f"Total equipment items to price: {len(item_ids)}")

        # Get prices for all items
        prices = await self.get_item_prices(item_ids)

        # Calculate total cost
        total_cost = 0
        priced_items = []

        for item_type, item in items_to_price.items():
            price = prices.get(item_type, 0)
            total_cost += price
            if price > 0:
                priced_items.append({"type": item_type, "price": price})
                log.info(f"Item {item_type}: {price} silver added to total")
            else:
                log.warning(f"Item {item_type}: No price available (price is 0)")

        msg = f"Regear cost calculation complete - Total: {total_cost} silver"
        msg += f" ({len(priced_items)}/{len(item_ids)} items priced)"
        log.info(msg)
        return total_cost, priced_items

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
            total_cost, priced_items = await self.calculate_regear_cost(death)

            # Format the cost with commas for readability
            formatted_cost = f"{total_cost:,}"

            # Build item breakdown
            item_breakdown = ""
            if priced_items:
                lines = ["\n**Item Costs:**"]
                for item in priced_items:
                    item_name = item["type"]
                    item_price = f"{item['price']:,}"
                    lines.append(f"- {item_name}: {item_price} silver")
                item_breakdown = "\n".join(lines) + "\n"

            log.info(f"Regear command successful: {player_name} - Total cost: {formatted_cost} silver")

            # Send response
            await ctx.send(
                f"**Regear cost for {player_name}:** {formatted_cost} silver\n"
                f"{item_breakdown}"
                f"Killboard: {killboard_url}"
            )
