# Albion Ava

Track Roads of Avalon connections via Portaler API.

## Description

This cog integrates with the Portaler API to track and display Roads of Avalon connections in Albion Online. It features:

- **On-Demand Fetching**: Fetches connection data when you request it (via commands)
- **Connection Graphs**: Display connections from a configured home zone
- **Portaler Integration**: Uses Portaler API for accurate, real-time connection data
- **Multi-Guild Support**: Subscribe to multiple Portaler guilds to merge their connection data

## Setup

### 1. Install the cog

Load the cog using Red's standard installation:

```
[p]load albion_ava
```

### 2. Get your Portaler API credentials

1. Visit [Portaler.app](https://portaler.app)
2. Log in with your Discord account
3. Obtain your API bearer token (check Portaler documentation or browser dev tools)
4. Get the Portaler guild ID(s) you want to query from the Portaler website

### 3. Configure the cog

**Step 1: Set the global Portaler token** (bot owner only, must be done in a DM for security):

```
[p]setava token <token>
```

Example:
```
[p]setava token eyJhbGci...
```

The token will be used globally for all Portaler API requests across all servers.

**Step 2: Configure Portaler guild IDs** (must be done in each server):

```
[p]setava guilds <guild_id> [<guild_id> ...]
```

Example:
```
[p]setava guilds 123456789 987654321
```

This sets which Portaler guilds to query for this Discord server. You can specify multiple guild IDs to merge their connection data together. To clear all guild IDs:
```
[p]setava guilds
```

**Step 3: Set your home zone** (must be done in the server):

```
[p]setava home <zone>
```

Example:
```
[p]setava home Lymhurst
```

**Step 4: Set the maximum number of connections to display** (optional):

```
[p]setava connections <number>
```

Example:
```
[p]setava connections 15
```

The cog will prioritize showing connections to royal cities and portal rooms.

## Usage

### Display connections

To see current connections from your home zone in text format:

```
[p]ava
```

To see connections as a visual graph image:

```
[p]ava image
```

To manually add a connection (useful when Portaler data is unavailable):

```
[p]ava add <from> <to> [duration_hours]
```

Example:
```
[p]ava add Lymhurst Thetford 4
```

Both display commands will show:
- Target zones
- Portal sizes
- Time remaining

The data is fetched fresh from the Portaler API each time you run these commands, and manual connections are merged with API data.

## Requirements

- `httpx>=0.14.1` (for API requests)
- `Pillow>=10.2.0` (for image generation)
- Portaler API access (requires account on Portaler.app)

## Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `[p]setava token <token>` | Bot Owner (DM only) | Set global Portaler API bearer token for all servers |
| `[p]setava guilds <guild_id> ...` | Admin (Server only) | Set which Portaler guild IDs to query (complete list, not additive) |
| `[p]setava home <zone>` | Admin (Server only) | Set home zone to focus connections from |
| `[p]setava connections <number>` | Admin (Server only) | Set maximum number of connections to display (default: 10) |
| `[p]ava` | Everyone | Display connections from home zone (text format) |
| `[p]ava image` | Everyone | Display connections as a visual graph image |
| `[p]ava add <from> <to> [duration]` | Admin | Manually add a connection with optional duration in hours (default: 4) |

## About Roads of Avalon

The Roads of Avalon are a dynamic network of portals connecting different zones in Albion Online. These connections change regularly, making tools like this cog essential for guilds that navigate the Roads. For more information, see the [official Albion Online guide](https://albiononline.com/guides/article/the-roads-of-avalon+107).

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/psykzz/cogs).
