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

Set your Portaler token (must be done in a DM for security):

```
[p]setava token <token> <guild_id>
```

Example:
```
[p]setava token eyJhbGci... 123456789012345678
```

To get your guild ID:
1. Enable Developer Mode in Discord (User Settings > Advanced > Developer Mode)
2. Right-click your server icon and select "Copy Server ID"

Set your home zone (must be done in the server):

```
[p]setava home <zone>
```

Example:
```
[p]setava home Lymhurst
```

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

Both commands will display:
- Target zones
- Portal sizes
- Time remaining

## Background Updates

The cog automatically checks the Portaler API every 5 minutes to keep connection data up to date. This happens in the background without any user intervention.

## Requirements

- `httpx>=0.14.1` (for API requests)
- `Pillow>=10.2.0` (for image generation)
- Portaler API access (requires account on Portaler.app)

## Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `[p]setava token <token> <guild_id>` | Admin (DM only) | Set Portaler API bearer token for a specific server |
| `[p]setava home <zone>` | Admin (Server only) | Set home zone to focus connections from |
| `[p]ava` | Everyone | Display connections from home zone (text format) |
| `[p]ava image` | Everyone | Display connections as a visual graph image |

## About Roads of Avalon

The Roads of Avalon are a dynamic network of portals connecting different zones in Albion Online. These connections change regularly, making tools like this cog essential for guilds that navigate the Roads. For more information, see the [official Albion Online guide](https://albiononline.com/guides/article/the-roads-of-avalon+107).

## Support

For issues or questions, please open an issue on the [GitHub repository](https://github.com/psykzz/cogs).
