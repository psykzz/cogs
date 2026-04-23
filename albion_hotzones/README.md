# Albion Hot Zones

Track combat hot zones in Albion Online red and black zones by monitoring recent kill events.

## Features

- **Automatic Polling**: Polls the Albion Online gameinfo API every 2 minutes
- **Recent Activity Tracking**: Tracks kills within the last 14 minutes
- **Battle Zone Grouping**: Groups kills by Battle ID to identify hot zones
- **Red/Black Zone Focus**: Only tracks OPEN_WORLD kills (red and black zones)

## Commands

### `.hotzones`
Show the current hot zones with the most PvP activity.

**Example:**
```
.hotzones
```

Displays:
- Top 10 most active battle zones
- Kill count per zone
- Total fame per zone
- Number of players involved

### `.hotzones top [count]`
Show the top N hot zones (1-20).

**Example:**
```
.hotzones top 5
```

### `.hotzones stats`
Show statistics about the hot zone tracking system.

**Example:**
```
.hotzones stats
```

Displays:
- Number of active battle zones
- Total kills tracked
- Total fame across all zones
- Tracking configuration

## How It Works

1. **Polling**: The cog polls the Albion Online EU gameinfo API (`gameinfo-ams.albiononline.com`) every 2 minutes
2. **Filtering**: Only tracks kills in OPEN_WORLD (red/black zones), ignoring safe zones and arenas
3. **Grouping**: Groups kills by Battle ID - kills with the same Battle ID occurred in the same general area
4. **Tracking Window**: Maintains a sliding 14-minute window of recent kills
5. **Display**: Shows the most active zones sorted by kill count

## Technical Details

- **API Endpoint**: `https://gameinfo-ams.albiononline.com/api/gameinfo/events`
- **Region**: European server (EU)
- **Poll Interval**: 120 seconds (2 minutes)
- **Tracking Window**: 840 seconds (14 minutes)
- **Storage**: In-memory tracking (resets on bot restart)

## Privacy Note

This cog uses publicly available kill data from the Albion Online API. The API does not provide exact zone names for privacy reasons, so battles are identified by their Battle ID number.
