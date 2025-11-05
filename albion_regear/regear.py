import asyncio

import httpx
from redbot.core import commands


async def http_get(url, params=None):
    """Make HTTP GET request with retries"""
    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params, timeout=10.0)

            if r.status_code == 200:
                return r.json()
            else:
                attempt += 1
                await asyncio.sleep(2)
        except (httpx.ConnectTimeout, httpx.RequestError):
            attempt += 1
            await asyncio.sleep(2)
    return None


class AlbionRegear(commands.Cog):
    """Calculates regear costs for Albion Online deaths"""

    def __init__(self, bot):
        self.bot = bot

    async def search_player(self, name):
        """Search for a player by name"""
        url = "https://gameinfo-ams.albiononline.com/api/gameinfo/search"
        params = {"q": name}
        result = await http_get(url, params)

        if result and result.get("players"):
            return result["players"][0]
        return None

    async def get_latest_death(self, player_id):
        """Get the latest death event for a player"""
        url = f"https://gameinfo-ams.albiononline.com/api/gameinfo/players/{player_id}/deaths"
        result = await http_get(url)

        if result and len(result) > 0:
            return result[0]
        return None

    async def get_item_prices(self, item_ids):
        """Get prices for multiple items"""
        if not item_ids:
            return {}

        # Build URL with item list in path and use Bridgewatch location
        item_list = ",".join(item_ids)
        url = f"https://europe.albion-online-data.com/api/v2/stats/prices/{item_list}"
        params = {"locations": "Bridgewatch", "qualities": "1"}
        result = await http_get(url, params)

        if not result:
            return {}

        # Create a map of item_id -> buy_price_max
        price_map = {}
        for item_data in result:
            item_id = item_data.get("item_id")
            buy_price_max = item_data.get("buy_price_max", 0)
            # Avoid extreme values by checking if buy_price_max is reasonable
            if buy_price_max and buy_price_max > 0:
                # Use existing price or take the max across cities
                if item_id not in price_map or buy_price_max > price_map[item_id]:
                    price_map[item_id] = buy_price_max

        return price_map

    async def calculate_regear_cost(self, death_event):
        """Calculate the cost to regear from a death event"""
        victim = death_event.get("Victim", {})
        equipment = victim.get("Equipment", {})

        # Extract all equipment items (excluding inventory)
        # Equipment slots: MainHand, OffHand, Head, Armor, Shoes, Bag, Cape, Mount, Potion, Food
        equipment_slots = [
            "MainHand", "OffHand", "Head", "Armor", "Shoes",
            "Bag", "Cape", "Mount", "Potion", "Food"
        ]

        item_ids = []
        items_to_price = {}  # Track which items we're pricing

        for slot in equipment_slots:
            item = equipment.get(slot)
            if item and item.get("Type"):
                item_type = item["Type"]
                item_ids.append(item_type)
                items_to_price[item_type] = item

        if not item_ids:
            return 0, []

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

        return total_cost, priced_items

    @commands.command()
    async def regear(self, ctx, name: str):
        """Calculate regear cost for a player's latest death

        Usage: .regear <player_name>
        Example: .regear psykzz
        """
        async with ctx.typing():
            # Search for the player
            player = await self.search_player(name)
            if not player:
                await ctx.send(f"Player '{name}' not found.")
                return

            player_id = player.get("Id")
            player_name = player.get("Name", name)

            # Get latest death
            death = await self.get_latest_death(player_id)
            if not death:
                await ctx.send(f"No deaths found for player '{player_name}'.")
                return

            event_id = death.get("EventId")
            killboard_url = f"https://albiononline.com/killboard/kill/{event_id}"

            # Calculate regear cost
            total_cost, priced_items = await self.calculate_regear_cost(death)

            # Format the cost with commas for readability
            formatted_cost = f"{total_cost:,}"

            # Send response
            await ctx.send(
                f"**Regear cost for {player_name}:** {formatted_cost} silver\n"
                f"Killboard: {killboard_url}"
            )
