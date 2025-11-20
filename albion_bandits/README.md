# Albion Bandits

Track Albion Online bandit event role mentions and predict next occurrence times.

## Features

- Automatically detects role mentions with time indicators (e.g., "@bandits 15")
- Stores all bandit call records with timestamps and user information
- Deduplicates similar messages within a 10-minute window
- Predicts next bandit spawn based on 4-6 hour cooldown
- Paginated history view of all previous bandit calls

## Commands

### User Commands

- `!bandits next` - Show the last bandit time and predict when the next one will occur
- `!bandits list` - Display all previous bandit calls in a paginated menu
- `!bandits status` - Show current configuration and statistics

### Admin Commands

- `!bandits setrole <role>` - Set which role to monitor for bandit pings (requires Manage Guild permission)
- `!bandits reset` - Clear all recorded bandit call data (requires Manage Guild permission)

## Setup

1. Load the cog: `[p]load albion_bandits`
2. Set the role to monitor: `[p]bandits setrole @bandits`
3. Users can now mention the role with or without a time value:
   - "@bandits 15" (meaning bandits in 15 minutes)
   - "@bandits" (meaning bandits starting immediately)

## How It Works

When a user mentions the configured role, the cog:
1. Captures the mention and extracts the time value (if provided)
2. If no time is specified, assumes bandits start immediately (0 minutes)
3. Calculates when the bandits will start
4. Checks if this is a duplicate (within 10 minutes of a recent call)
5. If not a duplicate, stores the call with full details

The `next` command shows:
- When the last bandits occurred
- How long ago that was
- When the next bandits are expected (4-6 hour window)
- Whether we're currently in the spawn window

## Example Usage

```
User: @bandits 15
Bot: [Silently records the call]

User: @bandits
Bot: [Silently records the call - immediate start]

User: !bandits next
Bot: [Embed showing]:
     Last Bandit: 2024-01-20 14:30:00
     Time Since Last Bandit: 3 hours and 45 minutes
     Next Bandit Window Opens In: 15 minutes
     Expected Window: 18:30 - 20:30
     
User: !bandits list
Bot: [Paginated embed showing all previous calls]
```

## Notes

- Bandits typically spawn every 4-6 hours in Albion Online
- The deduplication window is set to 10 minutes to handle multiple people calling the same event
- Time values are optional; if omitted, assumes bandits start immediately
- When provided, time values are expected to be in minutes (0-120 range)
- All times are stored in the server's local timezone
