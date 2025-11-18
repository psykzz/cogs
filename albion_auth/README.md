# Albion Auth

Authenticate and verify Discord users with their Albion Online character names.

## Features

- **User Authentication**: Users can authenticate with their Albion Online character name
- **Automatic Nickname Change**: Discord nickname is automatically set to match the Albion character name
- **Role Assignment**: Optional role assignment upon successful authentication
- **Daily Verification**: Background task that automatically verifies users once per day
- **Mismatch Reporting**: Bot owner receives DM reports when user nicknames don't match their Albion names
- **Manual Checking**: Admins can manually check specific users

## Commands

### User Commands

#### `.auth <player_name>`
Authenticate with your Albion Online character name.

The bot will search for the player name in Albion Online and rename you to match. If an auth role is configured, it will also be assigned to you.

**Example:**
```
.auth MyCharacter
```

### Admin Commands

#### `.authset authrole [@role]`
Set the role to assign when someone authenticates. If no role is provided, clears the current auth role setting.

**Permissions Required:** Manage Server

**Examples:**
```
.authset authrole @Verified
.authset authrole
```

#### `.authset dailycheck <true/false>`
Enable or disable daily name verification checks for this server.

When enabled, the bot will automatically check verified users once per day to ensure their Discord nickname still matches their Albion Online name. The bot owner will receive a DM report of any mismatches found.

**Permissions Required:** Manage Server

**Examples:**
```
.authset dailycheck true
.authset dailycheck false
```

#### `.authset checkuser @user`
Manually check a specific user's name against the Albion API.

This will immediately verify if the user's Discord nickname matches their Albion Online character name.

**Permissions Required:** Manage Server

**Example:**
```
.authset checkuser @JohnDoe
```

## How Daily Verification Works

1. **Background Task**: A background task runs every hour
2. **24-Hour Interval**: Users are checked approximately once every 24 hours
3. **Staggered Checks**: Users are checked in batches to avoid rate limiting
4. **Mismatch Detection**: The bot compares the user's Discord nickname with their current Albion Online name
5. **Report Generation**: If mismatches are found, a detailed report is sent to the bot owner via DM

### Mismatch Scenarios

The bot will report mismatches in the following cases:
- Discord nickname doesn't match the current Albion Online character name
- Player is no longer found in the Albion Online API

### Report Format

The bot owner receives a DM report with:
- Timestamp of the check
- Total number of mismatches
- For each mismatch:
  - Guild name
  - User Discord tag and ID
  - Current Discord nickname
  - Stored Albion name
  - Current Albion API name (if found)
  - Issue description

## Configuration

### Enable/Disable Daily Checks

Daily checks are **enabled by default** for all servers. Admins can disable them per server:

```
.authset dailycheck false
```

### Setting an Auth Role

Configure a role to be automatically assigned when users authenticate:

```
.authset authrole @Verified
```

## Requirements

- `httpx>=0.14.1`

## Installation

1. Install the cog using Red's downloader:
   ```
   [p]repo add psykzz-cogs https://github.com/psykzz/cogs
   [p]cog install psykzz-cogs albion_auth
   ```

2. Load the cog:
   ```
   [p]load albion_auth
   ```

## Technical Details

### Data Storage

The cog stores the following data per guild using Red's Config system:
- `auth_role`: Role ID to assign upon authentication (optional)
- `verified_users`: Dictionary mapping user IDs to their verification data:
  - `name`: The Albion Online character name
  - `last_checked`: Timestamp of the last verification check
- `enable_daily_check`: Boolean flag to enable/disable daily verification

### API Usage

The cog uses the Albion Online official game info API:
- Endpoint: `https://gameinfo-ams.albiononline.com/api/gameinfo/search`
- Rate limiting protection: 2-second delay between user checks
- Retry logic: Up to 3 attempts per request with exponential backoff

### Background Task

The background task:
- Starts when the cog is loaded (`cog_load`)
- Runs every hour
- Checks users that haven't been verified in the last 24 hours
- Cancels gracefully when the cog is unloaded (`cog_unload`)

## Support

For issues or feature requests, please visit the [GitHub repository](https://github.com/psykzz/cogs).
