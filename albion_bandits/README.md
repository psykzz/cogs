# Albion Bandits

Track Albion Online bandit event role mentions and predict next occurrence times. Supports real-time event tracking via NATS integration with Albion Data Project.

## Features

- Automatically detects role mentions with time indicators (e.g., "@bandits 15")
- Stores all bandit call records with timestamps and user information
- Deduplicates similar messages within a 10-minute window
- Predicts next bandit spawn based on 4-6 hour cooldown
- **Automatically estimates missed events** when calls come in after the expected 6-hour window
- Paginated history view of all previous bandit calls with estimated events marked
- **NATS Integration**: Real-time bandit event notifications from Albion Data Project

## Commands

### User Commands

- `!bandits next` - Show the last bandit time and predict when the next one will occur
- `!bandits list` - Display all previous bandit calls in a paginated menu
- `!bandits status` - Show current configuration and statistics (including NATS status)

### Admin Commands

- `!bandits setrole <role>` - Set which role to monitor for bandit pings (requires Manage Guild permission)
- `!bandits reset` - Clear all recorded bandit call data (requires Manage Guild permission)
- `!bandits nats_enable [channel]` - Enable NATS integration for real-time bandit events (requires Manage Guild permission)
- `!bandits nats_disable` - Disable NATS integration (requires Manage Guild permission)
- `!bandits nats_region <region>` - Set NATS region (americas, asia, or europe) (requires Manage Guild permission)
- `!bandits nats_channel <channel>` - Set the channel for NATS notifications (requires Manage Guild permission)

## Setup

### Basic Setup (Manual Role Mentions)

1. Load the cog: `[p]load albion_bandits`
2. Set the role to monitor: `[p]bandits setrole @bandits`
3. Users can now mention the role with or without a time value:
   - "@bandits 15" (meaning bandits in 15 minutes)
   - "@bandits" (meaning bandits starting immediately)

### NATS Integration Setup (Real-time Events)

1. Install the nats-py dependency: `pip install nats-py`
2. Load the cog: `[p]load albion_bandits`
3. Enable NATS integration: `[p]bandits nats_enable #bandit-alerts`
4. Set your game server region: `[p]bandits nats_region americas` (or `asia` or `europe`)
5. The bot will now automatically post notifications when bandit events are detected

**NATS Features:**
- Receives real-time bandit event data from Albion Data Project
- Posts advance notice (15 minutes before spawn)
- Posts active event notification when bandits spawn
- Automatically records events in bandit call history
- Supports all three game server regions (Americas, Asia, Europe)

## How It Works

### Manual Role Mentions

When a user mentions the configured role, the cog:
1. Captures the mention and extracts the time value (if provided)
2. If no time is specified, assumes bandits start immediately (0 minutes)
3. Calculates when the bandits will start
4. Checks if this is a duplicate (within 10 minutes of a recent call)
5. **If the gap from the last call is more than 6 hours, automatically creates estimated calls for missed events** (spaced 5 hours apart)
6. If not a duplicate, stores the call with full details

### NATS Integration

The cog connects to the Albion Data Project's NATS server and subscribes to bandit spawn events:
- **Advance Notice** (`AdvanceNotice: true`): Notification 15 minutes before event starts
- **Active Event** (`AdvanceNotice: false`): Notification when event is active

All NATS events are automatically recorded in the bandit call history alongside manual role mentions.

The `next` command shows:
- When the last bandits occurred
- How long ago that was
- When the next bandits are expected (4-6 hour window)
- Whether we're currently in the spawn window

## Example Usage

### Manual Tracking
```
User: @bandits 15
Bot: [Adds 👍 reaction]

User: @bandits
Bot: [Adds 👍 reaction - immediate start]

User: !bandits next
Bot: [Embed showing]:
     Last Bandit: 2024-01-20 14:30:00
     Time Since Last Bandit: 3 hours and 45 minutes
     Next Bandit Window Opens In: 15 minutes
     Expected Window: 18:30 - 20:30
     
User: !bandits list
Bot: [Paginated embed showing all previous calls]
```

### NATS Integration
```
[Bot automatically posts when event detected]:
🏴‍☠️ Bandit Event Incoming!
Bandits will spawn in approximately 15 minutes
Start Time: 2024-01-20 18:30:00
Source: Albion Data Project (NATS)

[15 minutes later, bot posts]:
🏴‍☠️ Bandit Event Active!
Bandits are spawning now!
Event End Time: 2024-01-20 19:00:00
Source: Albion Data Project (NATS)
```

## NATS Server Details

The cog connects to the Albion Data Project's public NATS servers:
- **Americas**: `nats://public:thenewalbiondata@nats.albion-online-data.com:4222`
- **Asia**: `nats://public:thenewalbiondata@nats.albion-online-data.com:24222`
- **Europe**: `nats://public:thenewalbiondata@nats.albion-online-data.com:34222`

## Notes

- Bandits typically spawn every 4-6 hours in Albion Online
- The deduplication window is set to 10 minutes to handle multiple people calling the same event
- Time values are optional; if omitted, assumes bandits start immediately
- When provided, time values are expected to be in minutes (0-120 range)
- All times are stored in the server's local timezone
- **Missed Event Handling**: When a call comes in after more than 6 hours since the last recorded event, the system automatically creates estimated calls at 5-hour intervals to fill the gap. These estimated calls are marked with a 📊 icon in the history list.
- **NATS Integration**: Requires the `nats-py` package to be installed. The cog will fall back to manual tracking if the package is not available.
