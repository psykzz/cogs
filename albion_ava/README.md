# Albion Ava

Track Roads of Avalon connections via Portaler API.

## Description

This cog integrates with the Portaler API to track and display Roads of Avalon connections in Albion Online. It features:

- **Background Updates**: Automatically fetches connection data every 5 minutes
- **Connection Graphs**: Display connections from a configured home zone
- **Portaler Integration**: Uses Portaler API for accurate, real-time connection data

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

**Note:** The cog automatically uses your Discord server ID as the Portaler guild ID.

### 3. Configure the cog

Set your Portaler token:

```
[p]setava token <token>
```

Example:
```
[p]setava token your_bearer_token_here
```

Set your home zone (the zone you want to see connections from):

```
[p]setava home <zone>
```

Example:
```
[p]setava home Lymhurst
```

## Usage

### Display connections

To see current connections from your home zone:

```
[p]ava
```

This will display a graph showing all active connections from your configured home zone, including:
- Target zones
- Portal sizes
- Time remaining

## Background Updates

The cog automatically checks the Portaler API every 5 minutes to keep connection data up to date. This happens in the background without any user intervention.

## Requirements

- `httpx>=0.14.1` (automatically installed with cog dependencies)
- Portaler API access (requires account on Portaler.app)

## Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `[p]setava token <token>` | Admin | Set Portaler API bearer token (uses Discord server ID automatically) |
| `[p]setava home <zone>` | Admin | Set home zone to focus connections from |
| `[p]ava` | Everyone | Display connections from home zone |

## About Roads of Avalon

The Roads of Avalon are a dynamic network of portals connecting different zones in Albion Online. These connections change regularly, making tools like this cog essential for guilds that navigate the Roads. For more information, see the [official Albion Online guide](https://albiononline.com/guides/article/the-roads-of-avalon+107).

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/psykzz/cogs).
