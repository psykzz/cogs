# Party Cog

A Discord bot cog for creating and managing party signups with role-based compositions.

## Features

- **Create Parties**: Set up parties with predefined or freeform roles
- **Interactive Signups**: Users sign up via Discord buttons and modals
- **Role Management**: Support for both predefined and custom roles
- **Update Signups**: Users can change their role selection at any time
- **Leave Party**: Users can leave parties with a single button click
- **Configuration**: Guild-wide settings for multiple signups per role
- **Permissions**: Only party creators or server admins can manage parties
- **Party Management**: List, delete, and add descriptions to parties

## Commands

### User Commands

#### `[p]party create <name> [roles...]`
Create a new party with optional predefined roles.

**Examples:**
```
[p]party create "Raid Night" Tank Healer DPS
[p]party create "Game Night"
[p]party create "PvP Team" Warrior Mage Archer
```

If no roles are specified, users can enter any role they want (freeform mode).
If roles are specified, users must choose from the list or can enter custom roles depending on server configuration.

#### `[p]party list`
List all active parties in the server.

Shows party name, ID, number of roles, total signups, and author.

### Management Commands

#### `[p]party delete <party_id_or_title>`
Delete a party by ID or title (requires author or admin permissions).

You can delete a party by its ID or by its title. If multiple parties have the same title, you'll be asked to use the party ID instead.

**Examples:**
```
[p]party delete abc123
[p]party delete Raid Night
```

#### `[p]party description <party_id> <description>`
Set the description for a party (requires author or admin permissions).

**Example:**
```
[p]party description abc123 Join us for a fun raid tonight!
```

#### `[p]party rename-option <party_id> <old_option> <new_option>`
Rename an option/role in a party (requires author or admin permissions).

This command updates the role name in the party's role list and migrates all signups from the old role name to the new role name.

**Examples:**
```
[p]party rename-option abc123 Tank "Main Tank"
[p]party rename-option abc123 "Off Tank" "Secondary Tank"
```

### Admin Commands

#### `[p]party config <setting> <value>`
Configure party settings for the server (requires admin or manage_guild permissions).

**Settings:**
- `allow_multiple_per_role`: yes/no - Allow multiple users to signup for the same role

**Example:**
```
[p]party config allow_multiple_per_role yes
```

## Usage Flow

1. **Create a Party**: Use `[p]party create` to create a new party
2. **Users Sign Up**: Click the "Sign Up" button on the party message
3. **Select Role**: 
   - If party has predefined roles only: Choose from a dropdown menu
   - If party allows freeform roles: Enter your role in a text input modal
4. **Update Role**: Click "Sign Up" again to change your role
5. **Leave Party**: Click the "Leave" button to remove yourself

## Discord UI Components

The cog uses modern Discord UI components:

- **Buttons**: Sign Up and Leave buttons on party messages
- **Select Menus**: Dropdown for choosing from predefined roles (when freeform is disabled)
- **Modals**: Text input form for freeform role entry
- **Embeds**: Rich party information display with signups

## Configuration

### Guild Settings

- **allow_multiple_per_role**: Controls whether multiple users can sign up for the same role
  - Default: `True` (multiple signups allowed)
  - Can be changed per server by admins

### Party Settings

- **allow_freeform**: Always `True` - users can enter custom roles
- **roles**: List of predefined roles for the party
- **signups**: Dictionary mapping roles to list of user IDs

## Data Storage

The cog uses Red-bot's Config system to store:

- Party data (name, description, roles, signups, author, etc.)
- Guild-wide settings
- Message IDs for party embeds

## Permissions

The cog requires these Discord permissions:
- `send_messages`: To send party messages
- `embed_links`: To display rich embeds
- `manage_messages`: To delete party messages when parties are deleted

## Persistent Views

The cog implements persistent views that survive bot restarts:
- Views are re-registered on bot startup
- Buttons continue to work on old messages after restarts
- Party IDs are used to maintain state

## Implementation Details

### User Caching
The cog implements smart user caching to optimize performance:
1. Check instance cache first
2. Try `bot.get_user()` (from bot cache)
3. Fallback to `bot.fetch_user()` (API call)
4. Store result in instance cache

### Smart Truncation
If party signups exceed Discord's embed field limit (1024 characters):
- Content is truncated at line boundaries (not mid-line)
- Shows how many additional roles are hidden
- Prevents cutting off text mid-word

### Async Architecture
All Discord operations are async:
- User lookups
- Embed generation
- Message updates
- Config operations

## Dependencies

This cog has no external dependencies beyond Red-bot core and discord.py.

## Author

Created by psykzz for the Red-bot Discord bot framework.
