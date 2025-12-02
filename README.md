# cogs ⚡

A collection of cogs (plugins) for [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot).

## Installation

> You need to ensure you have the downloader enabled first.

```
[p]load downloader
```

Then add this repository:

```
[p]repo add psykzz-cogs https://github.com/psykzz/cogs
```

Install a cog:

```
[p]cog install psykzz-cogs <cog_name>
```

Load the cog:

```
[p]load <cog_name>
```

> **Note:** Replace `[p]` with your bot's prefix (e.g., `.` or `!`).

---

## Available Cogs

### Activity Stats

Track Discord activity and game statistics for all members.

**Installation:**
```
[p]cog install psykzz-cogs activity_stats
[p]load activity_stats
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]activity topgames [limit]` | Show the most played games on this server |
| `[p]activity mygames [user]` | Show game statistics for yourself or another user |
| `[p]activity gameinfo <game_name>` | Show detailed statistics for a specific game |
| `[p]activity info` | Show statistics about the tracking system (Admin) |
| `[p]activity clear` | Clear all activity statistics (Admin) |
| `[p]activity set enabled` | Enable activity tracking (Admin) |
| `[p]activity set disabled` | Disable activity tracking (Admin) |

---

### Albion Auth

Authenticate and verify users with Albion Online player names.

**Requirements:** `httpx>=0.14.1`

**Installation:**
```
[p]cog install psykzz-cogs albion_auth
[p]load albion_auth
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]auth <player_name> [target_user]` | Authenticate with your Albion Online character name. Admins can specify a target user. |
| `[p]authset authrole [@role]` | Set the role to assign when someone authenticates (Admin) |
| `[p]authset dailycheck <true/false>` | Enable or disable daily name verification checks (Admin) |
| `[p]authset checkuser @user` | Manually check a specific user's name against Albion API (Admin) |

---

### Albion Bandits

Track Albion Online bandit event role mentions and timing predictions.

**Installation:**
```
[p]cog install psykzz-cogs albion_bandits
[p]load albion_bandits
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]bandits next` | Show the last bandit time and predict the next occurrence |
| `[p]bandits list` | List all previous bandit calls |
| `[p]bandits status` | Show current bandit tracking configuration |
| `[p]bandits setrole @role` | Set the role to monitor for bandit pings (Admin) |
| `[p]bandits reset` | Reset all bandit call data (Admin) |

**Usage:** Mention the configured role with an optional time in minutes (e.g., `@bandits 15` for bandits in 15 minutes).

---

### Albion Regear

Calculate regear costs for Albion Online deaths.

**Requirements:** `httpx>=0.14.1`

**Installation:**
```
[p]cog install psykzz-cogs albion_regear
[p]load albion_regear
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]regear <player_name>` | Calculate regear cost for a player's latest death |

---

### Assign Roles

Authorize one role to give another role to users.

**Installation:**
```
[p]cog install psykzz-cogs assign_roles
[p]load assign_roles
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]assign @role [@user]` | Assign or remove a role from a user (or yourself) |
| `[p]assign authorise @authorised_role @giveable_role` | Authorize a role to give another role (Admin) |
| `[p]assign deauthorise @authorised_role @giveable_role` | Deauthorize a role from giving another role (Admin) |
| `[p]assign list` | Show which roles can be given by other roles (Mod) |

---

### Empty Voices

Dynamic voice channel management - automatically creates and cleans up temporary voice channels.

**Installation:**
```
[p]cog install psykzz-cogs empty_voices
[p]load empty_voices
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]emptyvoices watch @category` | Set a category to watch for dynamic voice channels |
| `[p]emptyvoices stopwatch @category` | Stop watching a category |
| `[p]emptyvoices watching` | See what categories are being watched |
| `[p]emptyvoices list` | List current temporary channels |
| `[p]emptyvoices cleanup` | Manually clean up orphaned temporary channels |

---

### Game Embed

Monitor Steam game servers and display status embeds with quick-join buttons.

**Requirements:** `python-a2s>=1.3.0`

**Installation:**
```
[p]cog install psykzz-cogs game_embed
[p]load game_embed
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]gameserver add <ip> <port> [password]` | Add a Steam game server to monitor (Admin) |
| `[p]gameserver remove <ip> <port>` | Remove a server from monitoring (Admin) |
| `[p]gameserver list` | List all monitored servers |
| `[p]gameserver post <ip> <port>` | Post a status embed for a monitored server (Admin) |
| `[p]gameserver status <ip> <port>` | Get the current status of a specific server |
| `[p]gameserver refresh` | Manually refresh all server data (Admin) |

---

### Misc

Miscellaneous utility commands for your server.

**Installation:**
```
[p]cog install psykzz-cogs misc
[p]load misc
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]laws` | State a random law (Asimov's Laws of Robotics) |

---

### Movie Vote

Manage a channel for collecting votes for what movies to watch next.

**Requirements:** `cinemagoer==2022.12.27`

**Installation:**
```
[p]cog install psykzz-cogs movie_vote
[p]load movie_vote
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]movie` | Show current MovieVote settings |
| `[p]movie on` | Turn on MovieVote in the current channel (Admin) |
| `[p]movie off` | Turn off MovieVote in the current channel (Admin) |
| `[p]movie upemoji <emoji>` | Set the upvote emoji (Admin) |
| `[p]movie downemoji <emoji>` | Set the downvote emoji (Admin) |
| `[p]movie watch <imdb_link>` | Mark a movie as watched (Admin) |
| `[p]movie rewatch <imdb_link>` | Mark a movie as unwatched (Admin) |
| `[p]movie next` | Get the next movie to watch |
| `[p]movie leaderboard [watched_only]` | Get the movie leaderboard |
| `[p]movie pinboard` | Create a pinned leaderboard that auto-updates (Admin) |
| `[p]movie check <imdb_link>` | Check if vidsrc has the next episode (Admin) |
| `[p]movie updatedb` | Update all movies with fresh IMDB data (Admin) |

**Usage:** Post IMDB links in enabled channels to add movies to the voting list.

---

### NW Server Status (New World)

Monitor New World server status and display queue information.

**Requirements:** `httpx>=0.14.1`

**Installation:**
```
[p]cog install psykzz-cogs nw_server_status
[p]load nw_server_status
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]queue [server]` | Get current queue information for a server |
| `[p]queueset [server]` | Set the default server for this Discord server (Admin) |
| `[p]monitor <voice_channel>` | Set a voice channel to display server status (Admin) |
| `[p]forcemonitor` | Force an update of the monitor channel (Admin) |

---

### NW Timers (New World War Timers)

Manage war timers for New World.

**Installation:**
```
[p]cog install psykzz-cogs nw_timers
[p]load nw_timers
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]war next [zone]` | Get the next upcoming war (optionally for a specific zone) |
| `[p]war add <zone> <relative_time>` | Add a war timer for a zone (Mod) |
| `[p]war remove <zone>` | Remove a war timer for a zone (Mod) |

**Example:** `[p]war add Everfall 24h3m` - Adds a war timer for Everfall in 24 hours and 3 minutes.

---

### QuotesDB

Store and retrieve user-generated quotes with triggers.

**Installation:**
```
[p]cog install psykzz-cogs quotesdb
[p]load quotesdb
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]. <trigger> <quote>` | Add a new quote with a trigger |
| `[p].. <trigger>` | Show a random quote for the given trigger |
| `[p]qdel <quote_id>` | Delete a quote (creator or admin only) |
| `[p]qid <quote_id>` | Show details about a specific quote |

---

### React Roles

Assign roles to users based on their reactions to messages.

**Installation:**
```
[p]cog install psykzz-cogs react_roles
[p]load react_roles
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]add_react #channel <message_id> <emoji> @role` | Setup a reaction role for a specific message (Manage Roles) |
| `[p]remove_react #channel <message_id> <emoji>` | Remove a reaction role from a message (Manage Roles) |

---

### Secret Santa

Manage Secret Santa events with participant matching, anonymous messaging, and gift tracking.

**Installation:**
```
[p]cog install psykzz-cogs secret_santa
[p]load secret_santa
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]santa create <event_name> <date> <max_price> @participants...` | Create a new Secret Santa event (Admin) |
| `[p]santa import <event_name> <date> <max_price> <pairings...>` | Import an existing event with forced pairings (Admin) |
| `[p]santa match <event_name>` | Match all participants randomly (Admin) |
| `[p]santa rematch <event_name>` | Redo matching for an event (Admin) |
| `[p]santa status <event_name>` | Check the status of an event (Admin) |
| `[p]santa list` | List all Secret Santa events (Admin) |
| `[p]santa delete <event_name>` | Delete an event (Admin) |
| `[p]santa remind <event_name>` | Send reminder DMs to all participants (Admin) |
| `[p]santa add <event_name> @users...` | Add participants to an event (Admin) |
| `[p]santa remove <event_name> @users...` | Remove participants from an event (Admin) |
| `[p]santa message <event_name> <message>` | Send anonymous message to your giftee |
| `[p]santa reply <event_name> <message>` | Send anonymous reply to your Secret Santa |
| `[p]santa sent <event_name>` | Mark that you have sent your gift |
| `[p]santa received <event_name>` | Mark that you have received your gift |
| `[p]santa whoami <event_name>` | Check who you are matched to (sent via DM) |

**DM Commands (for anonymity):**

| Command | Description |
|---------|-------------|
| `[p]santadm message <event_id> <message>` | Send anonymous message to your giftee via DM |
| `[p]santadm reply <event_id> <message>` | Reply to your Secret Santa via DM |
| `[p]santadm wishlist <event_id> <wishlist>` | Set your wishlist via DM |
| `[p]santadm info <event_id>` | Get your event info via DM |
| `[p]santadm sent <event_id>` | Mark gift as sent via DM |
| `[p]santadm received <event_id>` | Mark gift as received via DM |

---

### TGMC

Interface for the TGMC (TerraGov Marine Corps) game API.

**Installation:**
```
[p]cog install psykzz-cogs tgmc
[p]load tgmc
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]winrates all [delta]` | Get the current overall winrates |
| `[p]winrates distress [delta]` | Get winrates on Distress Signal |
| `[p]winrates crash [delta]` | Get winrates on Crash |
| `[p]winrates bughunt [delta]` | Get winrates on Bug Hunt |
| `[p]winrates huntparty [delta]` | Get winrates on Hunt Party |
| `[p]winrates nuclearwar [delta]` | Get winrates on Nuclear War |
| `[p]winrates campaign [delta]` | Get winrates on Campaign |
| `[p]winrates combatpatrol [delta]` | Get winrates on Combat Patrol |
| `[p]winrates sensorcapture [delta]` | Get winrates on Sensor Capture |

> `delta` is the number of days to look back (default: 14).

---

### User

Manage bot user settings (nickname and avatar).

**Installation:**
```
[p]cog install psykzz-cogs user
[p]load user
```

**Commands:**

| Command | Description |
|---------|-------------|
| `[p]user nick [nickname]` | Change the bot's nickname in this guild (reset if no nickname provided) |
| `[p]user avatar` | Change the bot's avatar using an attached image |

---

## Support

For issues or feature requests, please visit the [GitHub repository](https://github.com/psykzz/cogs).
