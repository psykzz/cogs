# WordGame — Product Requirements Document

## Overview

`wordgame` is a multiplayer PvP word-guessing game (Wordle-style) for Discord, played entirely inside threads. Players compete for points by probing letters rather than racing to guess the final word — skilled players earn more by discovering correct letters than by solving early.

---

## Goals

- Give guild members a lightweight competitive game that can be started by anyone at any time
- Reward strategic letter-probing over lucky early solves
- Keep the game alive long enough for latecomers to join without punishing early finishers

---

## Game Flow

1. Any guild member runs `/wordgame start [length]`
2. The bot picks a random word of the requested length from a bundled dictionary
3. The bot posts an announcement in the channel and creates a thread from it
4. A live **scoreboard message** is posted as the first message in the thread
5. Players type words directly in the thread — no command prefix required
6. After each valid guess, the bot replies with per-letter feedback and updates the scoreboard
7. The game ends via inactivity timeout, admin force-close, or the End Game button

---

## Word Rules

| Property | Value |
|---|---|
| Minimum length | 3 letters |
| Maximum length | 8 letters |
| Default length | 5 letters |
| Answer pool | ~6k common English words (ENABLE × Google 10k common words) |
| Valid guess dictionary | ~80k words (full ENABLE public-domain list) |
| Guess validation | Must be an alpha string of the correct length and present in the valid-guess dictionary |

---

## Scoring

All scoring is **global** — once any player claims a `(letter, position)` pair, it cannot be scored by anyone else.

| Event | Points |
|---|---|
| Letter appears in the target word (any position) | +1 |
| Letter is in the correct position (first to claim it globally) | +1 additional |
| Guessing the full correct word | +2 bonus on top of per-letter scoring |

**Deduplication:** Duplicate letters within a single guess only score once.

**Strategy note:** It is generally better to probe unknown letters across multiple guesses than to guess the final word early, since a well-chosen probe word can yield more points than the flat +2 word bonus.

---

## Guess Limits & Bonus Guesses

- Each player starts with **3 guesses**
- After using all guesses, a player receives **+1 bonus guess every 5 minutes** from the time of their last guess
- The bonus timer is **per-player** — players who finish early get their bonus sooner
- When a bonus guess is granted, the player receives a **DM** notifying them to return
- Players can opt out of DMs by clicking the **🚫 Stop DMs** button in the DM — this persists for the duration of that game

---

## Game Lifecycle

| Trigger | Outcome |
|---|---|
| 10 minutes of no valid guesses from any player | Game auto-closes (inactivity timeout) |
| Admin runs `[p]wordgame end` in the thread | Game force-closed immediately |
| Admin clicks 🔚 End Game on the scoreboard | Game force-closed immediately |

The inactivity timer resets on every valid guess. The scoreboard displays a live Discord relative timestamp showing when the game will auto-close.

---

## Scoreboard (Live Message)

The first message in the thread is the scoreboard, edited in-place after every guess. It shows:

- Game ID and word length
- Status (🟢 Active / 🔴 Ended)
- Inactivity close time (`⏳ Auto-closes <t:...:R> if no guesses`)
- **Leaderboard** — players sorted by score, with personal bonus countdown for done players (`⏰ <t:...:R>`)
- **Guess history** — every player's guesses with `?!-` feedback and points earned per guess

### Feedback symbols

| Symbol | Meaning |
|---|---|
| `!` | Correct letter, correct position |
| `?` | Correct letter, wrong position |
| `-` | Letter not in the word |

---

## Commands

| Command | Type | Access | Description |
|---|---|---|---|
| `/wordgame start [length]` | Slash (hybrid) | Anyone | Start a new game in the current channel |
| `[p]wordgame end` | Prefix | Admin / Manage Messages | Force-end the game in the current thread |
| 🔚 End Game button | UI button | Admin / Manage Messages | Same as above, on the scoreboard message |
| 🚫 Stop DMs button | UI button (DM) | The player themselves | Opt out of bonus-guess DMs for this game |

---

## Persistence

Game state is stored in Red's `Config` per guild, keyed by thread ID. This means:

- Active games survive bot restarts
- Persistent views (`ScoreboardView`, `BonusDMView`) are re-registered on startup
- The inactivity watcher (`_close_games_loop`) restarts automatically if active games are found on startup

### Per-game state

| Field | Description |
|---|---|
| `word` | The target word (never exposed to players) |
| `length` | Word length |
| `status` | `active` or `ended` |
| `claimed_positions` | List of `[letter, position]` pairs globally claimed |
| `inactive_closes_at` | Unix timestamp for inactivity auto-close |
| `players` | Dict of user ID → player state |

### Per-player state

| Field | Description |
|---|---|
| `guesses` | List of submitted guess strings |
| `feedbacks` | Corresponding `?!-` feedback strings |
| `points_per_guess` | Points earned per guess |
| `score` | Total points |
| `done` | Whether the player has exhausted their current guesses |
| `max_guesses` | Current guess limit (starts at 3, incremented by bonus) |
| `bonus_guess_at` | Unix timestamp for the player's next bonus guess |
| `ignore_dms` | Whether the player has opted out of DMs for this game |

---

## Out of Scope (v1)

- Per-guild leaderboards / persistent stats across games
- Configurable guess limits or timeout durations
- Multi-word or phrase guesses
- Hard mode (required letter re-use)
- Custom word lists per guild
