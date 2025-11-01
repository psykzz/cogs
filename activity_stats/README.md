# Activity Stats Cog

Track Discord activity and keep statistics on the most played games across all members.

## Features

- **Automatic Tracking**: Automatically tracks what games members are playing using Discord presence updates
- **Server-wide Statistics**: View the most popular games across your entire server
- **Personal Statistics**: Check your own or other members' game playing history
- **Game Details**: Get detailed statistics for specific games including top players
- **Admin Controls**: Manage and clear statistics as needed

## Commands

All commands are grouped under the `!activity` command.

### User Commands

#### `!activity topgames [limit]`
Shows the most played games on the server.
- **limit**: Number of games to display (default: 10)
- **Example**: `!activity topgames 5` - Shows top 5 games

#### `!activity mygames [user]`
Shows game statistics for yourself or another user.
- **user**: Optional - The user to check (default: yourself)
- **Example**: `!activity mygames @JohnDoe` - Shows JohnDoe's game stats

#### `!activity gameinfo <game_name>`
Shows detailed statistics for a specific game.
- **game_name**: The name of the game to check
- **Example**: `!activity gameinfo Minecraft` - Shows stats for Minecraft

### Admin Commands

Requires "Manage Server" permission.

#### `!activity info`
Shows statistics about the tracking system (tracking status, total games tracked, users with stats, currently playing).

#### `!activity clear`
Clears all activity statistics for the server.

#### `!activity set enabled`
Enables activity tracking for this server. Tracking is enabled by default.

#### `!activity set disabled`
Disables activity tracking for this server. No new activity will be tracked until re-enabled.

## How It Works

The cog listens for Discord presence updates (when users start or stop playing games) and tracks:
- **Total playtime** for each game across all server members
- **Individual playtime** for each user's games
- **Active sessions** to calculate duration when games are stopped

Statistics are stored per-guild, so each server has its own independent tracking.

**Note:** Tracking is enabled by default for all servers. Server administrators can disable tracking at any time using `!activity set disabled`.

## Privacy Notes

- Only tracks games that are shown in Discord presence (requires users to have "Display current activity" enabled)
- Tracking is server-specific - stats are not shared between servers
- Server administrators can clear all statistics at any time
- Only tracks playtime duration, not detailed activity

## Installation

```
[p]load downloader
[p]repo add psykzz-cogs https://github.com/psykzz/cogs
[p]cog install psykzz-cogs activity_stats
[p]load activity_stats
```

## Example Usage

```
User: !activity topgames 5
Bot: 🎮 Top 5 Games on My Server
     1. Minecraft: 245h 30m
     2. League of Legends: 189h 15m
     3. Among Us: 156h 45m
     4. Valorant: 134h 20m
     5. World of Warcraft: 98h 10m

User: !activity mygames
Bot: 🎮 YourName's Games
     1. Minecraft: 45h 30m
     2. Among Us: 23h 15m
     3. Valorant: 12h 45m

User: !activity gameinfo Minecraft
Bot: 🎮 Minecraft
     Total playtime: 245h 30m
     Players: 12
     
     Top Players
     1. PlayerOne: 45h 30m
     2. PlayerTwo: 38h 15m
     3. PlayerThree: 29h 45m
     4. PlayerFour: 24h 20m
     5. PlayerFive: 19h 10m
```
