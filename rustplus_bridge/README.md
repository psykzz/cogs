# RustPlus Bridge

A bidirectional chat bridge between Discord and Rust+ in-game team chat.

## Features

- **Bidirectional messaging**: Messages from Discord are sent to Rust team chat and vice versa
- **FCM Push Notifications**: Optional Firebase Cloud Messaging support for real-time updates (no polling needed)
- **Configurable polling**: Adjustable polling interval (1-60 seconds) when not using FCM
- **Automatic connection management**: Handles reconnections and connection failures gracefully
- **Memory-safe**: Properly tracks messages to avoid duplicates and implements cleanup on shutdown
- **Exponential backoff**: Automatically retries failed connections with increasing delays
- **Admin controls**: Full suite of commands to manage the bridge

## Requirements

- `rustplus>=6.0.0`
- User must be in a team on the Rust server
- Valid Rust+ player credentials (player_id and player_token)

## Getting Rust+ Credentials

To use this bridge, you need your player_id and player_token from the Rust+ companion app:

1. Download and install the Rust+ mobile app
2. Pair it with your in-game character
3. Use a network packet sniffer or Rust+ API tools to capture your credentials
4. Alternative: Use tools like [rustplus.js](https://github.com/liamcottle/rustplus.js) to extract credentials

**Note**: The player must be in a team on the server for team chat bridging to work.

### Getting FCM Credentials (Optional)

For real-time push notifications instead of polling, you can configure FCM (Firebase Cloud Messaging):

1. Use the Rust+ mobile app and pair it with your character
2. Extract FCM credentials using tools like [rustplus.js](https://github.com/liamcottle/rustplus.js)
3. The credentials include FCM tokens and keys needed for push notifications
4. Configure them with `[p]rustbridge fcm <json_credentials>`

**Benefits of FCM**:
- Instant notifications (no polling delay)
- Lower resource usage
- More efficient for active servers

**Without FCM**:
- The bridge works perfectly fine using polling mode (default)
- Configurable polling interval (1-60 seconds)
- Simpler setup (no additional credentials needed)

## Installation

```
[p]cog install psykzz-cogs rustplus_bridge
[p]load rustplus_bridge
```

## Setup

1. **Configure server credentials**:
   ```
   [p]rustbridge setup <server_ip> <server_port> <player_id> <player_token>
   ```
   Example: `[p]rustbridge setup 192.168.1.1 28082 12345678 87654321`

2. **Set bridge channel**:
   ```
   [p]rustbridge channel #rust-chat
   ```

3. **Enable the bridge**:
   ```
   [p]rustbridge enable
   ```

## Commands

All commands require administrator permissions or the "Administrator" permission.

### Basic Commands

| Command | Description |
|---------|-------------|
| `[p]rustbridge setup <ip> <port> <player_id> <token>` | Configure Rust+ server credentials |
| `[p]rustbridge channel #channel` | Set the Discord channel for the bridge |
| `[p]rustbridge enable` | Enable the bridge and start forwarding messages |
| `[p]rustbridge disable` | Disable the bridge and stop forwarding messages |
| `[p]rustbridge status` | Check the current bridge status and connection state |
| `[p]rustbridge reconnect` | Force a reconnection to the Rust server |
| `[p]rustbridge clear` | Clear all bridge configuration |

### FCM Commands (Optional - for Push Notifications)

| Command | Description |
|---------|-------------|
| `[p]rustbridge fcm [credentials]` | Configure FCM credentials (JSON format) or use "clear" to remove |
| `[p]rustbridge fcmenable` | Enable FCM push notifications (requires FCM credentials) |
| `[p]rustbridge fcmdisable` | Disable FCM and use polling mode instead |
| `[p]rustbridge pollinterval <seconds>` | Set polling interval (1-60 seconds, default: 2) |

## How It Works

### Discord → Rust
- Messages sent in the configured Discord channel are forwarded to Rust team chat
- Format: `{Discord Username}: {message}`
- Messages longer than 128 characters are truncated
- A ✅ reaction is added to successfully sent messages
- A ❌ reaction is added if sending fails

### Rust → Discord
- Team chat messages from Rust are sent to the configured Discord channel as embeds
- Embeds show the player name, message content, and Steam ID
- Messages are color-coded based on the Rust chat color
- Timestamp shows when the message was sent in-game

### Connection Management
- The bridge automatically connects when enabled
- **Two modes available**:
  - **Polling mode** (default): Checks for new messages at regular intervals (configurable, default 2 seconds)
  - **FCM mode** (optional): Uses Firebase Cloud Messaging for real-time push notifications (no polling overhead)
- Failed connections trigger automatic reconnection with exponential backoff
- Maximum retry delay is 60 seconds
- Connection state is monitored continuously
- Memory-safe message tracking prevents duplicates

## Troubleshooting

### Bridge won't connect
- Verify your credentials are correct with `[p]rustbridge status`
- Ensure you're in a team on the Rust server
- Check that the server IP and port are correct
- Try forcing a reconnection with `[p]rustbridge reconnect`

### Messages not appearing
- Verify the bridge is enabled: `[p]rustbridge status`
- Check that you have an active connection (shown in status)
- Ensure the bot has permissions to read/send messages in the bridge channel
- Make sure you're in a team on the Rust server

### Connection keeps dropping
- This can happen if the Rust server restarts or your team is disbanded
- The bridge will automatically attempt to reconnect
- Check the reconnect attempt count with `[p]rustbridge status`
- If reconnections keep failing, verify your credentials

## Technical Details

### Polling Mode (Default)
- Checks for new team chat messages at configurable intervals (default: 2 seconds)
- Adjustable from 1-60 seconds via `[p]rustbridge pollinterval`
- Messages are tracked by timestamp to prevent duplicates
- Message tracking set is cleaned when it exceeds 1000 entries (keeps most recent 500)
- Lower intervals provide faster updates but use more API calls

### FCM Mode (Optional - Recommended)
- Uses Firebase Cloud Messaging for real-time push notifications
- No polling overhead - messages arrive instantly
- Requires additional FCM credentials from the Rust+ mobile app
- More efficient for high-traffic servers
- Connection is kept alive with minimal resource usage

### Memory Management
- All connections are properly cleaned up on cog unload
- Message tracking uses a bounded set (cleanup threshold: 1000, target size: 500)
- FCM listeners run in daemon threads and stop on process exit
- Tasks are cancelled gracefully on shutdown

### Error Handling
- Connection errors trigger automatic reconnection
- API errors are logged and don't crash the bridge
- Broken connections are detected and replaced
- FCM failures automatically fall back to polling mode

## Security Notes

- Credentials are stored in the bot's configuration (encrypted by Red-bot)
- Only administrators can configure or manage the bridge
- Player tokens should be kept private and never shared

## Support

For issues or feature requests, please visit the [GitHub repository](https://github.com/psykzz/cogs).
