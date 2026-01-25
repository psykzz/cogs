# Red-bot Cogs Repository

This repository contains Red-bot cogs (Discord bot plugins) written in Python. Each cog is a self-contained module providing specific Discord bot functionality.

**ALWAYS reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Initial Setup and Validation
Run these commands to set up the development environment and validate the codebase:

```bash
# Install Red-DiscordBot (requires Python 3.11 or earlier, NOT 3.12+)
pip3 install Red-DiscordBot

# Install linting tools
pip3 install flake8

# Install common cog dependencies (install as needed based on info.json files)
pip3 install cinemagoer==2022.12.27 httpx discord.py python-a2s>=1.3.0 Pillow>=10.2.0

# Validate Python syntax for all cogs (immediate, ~1 second)
python3 -m py_compile */*.py

# Run linting to identify issues (immediate, <1 second)
flake8 . --statistics

# Test Red-DiscordBot imports (immediate, <1 second)
python3 -c "from redbot.core import commands; print('Red-DiscordBot imports working')"
```

### Validation Commands
Always run these validation steps before committing changes:

```bash
# Syntax validation for specific files (immediate)
python3 -m py_compile path/to/modified_file.py

# Check your changes don't introduce new F821 (undefined name) errors
flake8 path/to/modified_file.py --select=F821

# Full linting (immediate, <1 second)
flake8 . --count --statistics
```

## Repository Structure

### Cog Directories
Each cog follows this structure:
```
cog_name/
├── __init__.py          # Cog registration with async setup
├── main_file.py         # Main implementation
└── info.json           # Metadata and dependencies
```

### Cog Registration Pattern
All cogs use async setup functions in `__init__.py`:
```python
from .cog_name import CogClass

async def setup(bot):
    await bot.add_cog(CogClass(bot))
```

**IMPORTANT**: When creating new cogs or updating existing ones, always use the async setup pattern shown above. This is the modern Red-bot convention and ensures compatibility with the bot framework.

### Command Patterns

#### Hybrid Commands (Slash Commands)
**All commands should be hybrid commands** that work as both text commands and slash commands:

```python
from redbot.core import commands

@commands.hybrid_command(name="commandname")
async def my_command(self, ctx, arg: str):
    """Command description shown in slash command UI
    
    Parameters
    ----------
    arg : str
        Description of the argument
    """
    # Defer immediately for ephemeral response (preferred for most commands)
    await ctx.defer(ephemeral=True)
    
    # Use typing indicator for long operations
    async with ctx.typing():
        # Long operation here
        result = await self.do_something(arg)
    
    # Send response (ephemeral by default after defer)
    await ctx.send(f"Result: {result}", ephemeral=True)
```

**For command groups**, use `@commands.hybrid_group()`:
```python
@commands.hybrid_group(name="groupname")
async def my_group(self, ctx):
    """Group description"""
    if ctx.invoked_subcommand is None:
        await ctx.send_help(ctx.command)

@my_group.command(name="subcommand")
async def my_subcommand(self, ctx):
    """Subcommand description"""
    await ctx.defer(ephemeral=True)
    # Implementation
    await ctx.send("Done", ephemeral=True)
```

#### Response Patterns

**Ephemeral Responses (Preferred)**
Most commands should use ephemeral responses to reduce channel clutter:
```python
# Defer first to prevent timeout
await ctx.defer(ephemeral=True)
# Then send response
await ctx.send("Result", ephemeral=True)
```

**Public Responses**
Only use public responses for commands that benefit from visibility (leaderboards, announcements, etc.):
```python
await ctx.defer()  # No ephemeral flag
await ctx.send("Public announcement")
```

**Typing Indicators**
Use typing indicators for operations that take more than 1-2 seconds:
```python
async with ctx.typing():
    # Long database query
    # API call
    # Image processing
```

#### Modals for Complex Input
For commands with 3+ arguments or complex forms, use Discord modals:

```python
class MyModal(discord.ui.Modal):
    """Modal for complex input"""
    
    def __init__(self, cog):
        super().__init__(title="Form Title")
        self.cog = cog
        
        self.field1 = discord.ui.TextInput(
            label="Field 1",
            placeholder="Enter value",
            required=True,
            max_length=100,
        )
        self.add_item(self.field1)
        
        # Add more fields (max 5)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Defer immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        # Process input
        value = self.field1.value.strip()
        await self.cog.process_data(value)
        
        # Send response
        await interaction.followup.send("✅ Done!", ephemeral=True)

# In command, show modal:
@commands.hybrid_command()
async def mycommand(self, ctx):
    """Open form to input data"""
    modal = MyModal(self)
    await ctx.interaction.response.send_modal(modal)
```

**Modal Best Practices:**
- Use for 3+ arguments or multi-line input
- Always defer immediately in `on_submit()`
- Use ephemeral responses
- Validate input and show clear error messages
- Max 5 fields per modal (Discord limit)

#### Error Handling
Always handle errors gracefully with informative messages:
```python
@commands.hybrid_command()
async def mycommand(self, ctx):
    await ctx.defer(ephemeral=True)
    
    try:
        result = await self.risky_operation()
        await ctx.send(f"✅ Success: {result}", ephemeral=True)
    except ValueError as e:
        await ctx.send(f"❌ Invalid input: {e}", ephemeral=True)
    except Exception as e:
        log.exception("Unexpected error in mycommand")
        await ctx.send("❌ An error occurred. Please try again.", ephemeral=True)
```

### Key Cogs
- **access/**: Simplify channel access and permissions for roles or members by managing channel-specific permission overrides with confirmation dialogs (no external deps)
- **activity_stats/**: Discord activity and game statistics tracking (no external deps)
- **albion_auth/**: Albion Online authentication and daily verification system (requires: httpx>=0.14.1)
- **albion_ava/**: Roads of Avalon connection tracker via Portaler API with on-demand data fetching and connection graphs (requires: httpx>=0.14.1, Pillow>=10.2.0)
- **albion_bandits/**: Albion Online bandit event tracking with timing predictions (no external deps)
- **albion_hotzones/**: Albion Online hot zones tracker for red/black zone PvP combat (requires: httpx>=0.14.1)
- **albion_regear/**: Albion Online regear cost calculator (requires: httpx>=0.14.1)
- **assign_roles/**: Role management system (no external deps)
- **empty_voices/**: Voice channel management (no external deps)
- **game_embed/**: Steam game server monitoring with status embeds and quick-join buttons (requires: python-a2s>=1.3.0)
- **hat/**: Add festive Christmas hats to user avatars with customizable scale, rotation, and position (requires: Pillow>=10.2.0)
- **ideas/**: Suggest ideas by creating GitHub issues in the repository (requires: httpx>=0.14.1)
- **misc/**: Miscellaneous utilities (no external deps)
- **movie_vote/**: Movie voting system with IMDB integration (requires: cinemagoer==2022.12.27)
- **nw_server_status/**: New World server monitoring (requires: httpx>=0.14.1)
- **nw_timers/**: New World war timers (no external deps)
- **party/**: Party signup system with role-based composition management using Discord buttons and modals (no external deps)
- **psymin/**: Bot owner administration commands for viewing permissions across all servers (no external deps)
- **quotesdb/**: Quote storage system (no external deps)
- **react_roles/**: Role assignment via reactions (no external deps)
- **secret_santa/**: Secret Santa event management with participant matching, anonymous messaging, and gift tracking (no external deps)
- **tgmc/**: API interface for TGMC game (requires: httpx, but not specified in info.json)
- **user/**: Bot user management with nickname and avatar commands (no external deps)

## Dependencies and Installation

### Per-Cog Dependencies
Check each cog's `info.json` file for specific requirements:

```bash
# View cog dependencies
cat cog_name/info.json | grep -A5 "requirements"

# Install specific cog dependencies
pip3 install dependency_name==version
```

### Common Dependencies
```bash
# For movie_vote cog
pip3 install cinemagoer==2022.12.27

# For albion_auth, albion_ava, albion_regear, ideas, and nw_server_status cogs (tgmc also needs httpx but doesn't specify in info.json)
pip3 install httpx>=0.14.1

# For game_embed cog (Steam server monitoring)
pip3 install python-a2s>=1.3.0

# For hat cog (avatar image manipulation)
pip3 install Pillow>=10.2.0

# For Discord functionality (if testing imports)
pip3 install discord.py
```

## Testing and Validation

### Code Validation
Since this is a Red-bot cog repository, there is **no traditional build process**. Validation focuses on:

1. **Python syntax validation** (immediate)
2. **Import testing** (immediate, requires Red-DiscordBot to be installed)
3. **Linting compliance** (immediate, <1 second)

### Manual Testing Scenarios
When making changes to cogs, validate functionality by:

1. **For movie_vote changes**: Test IMDB link parsing and movie data retrieval
   ```bash
   # Test regex and basic functionality
   python3 -c "
   import re
   RE_IMDB_LINK = re.compile(r'(https:\/\/www\.imdb\.com\/title\/tt\d+)')
   test_link = 'https://www.imdb.com/title/tt1234567'
   match = RE_IMDB_LINK.search(test_link)
   print(f'IMDB regex test: {match.group(1) if match else \"Failed\"}')"
   ```

2. **For timer cogs**: Test datetime parsing and timer calculations  
   ```bash
   # Test timer logic without redbot dependencies
   python3 -c "
   import datetime
   from dateutil.relativedelta import relativedelta
   now = datetime.datetime.now()
   future = now + datetime.timedelta(hours=2, minutes=30)
   delta = future - now
   print(f'Timer calculation test: {delta}')"
   ```

3. **For API cogs**: Test HTTP request patterns (without actual requests)
   ```bash
   # Test HTTP client setup patterns
   python3 -c "
   import httpx
   import asyncio
   print('HTTP client import successful')
   print('httpx version:', httpx.__version__)"
   ```

4. **For role cogs**: Test permission validation and role assignment logic
   ```bash
   # Test Discord object patterns  
   python3 -c "
   import discord
   print('Discord.py import successful')
   print('discord.py version:', discord.__version__)"
   ```

5. **For game_embed changes**: Test A2S protocol and server query patterns
   ```bash
   # Test python-a2s module import and basic functionality
   python3 -c "
   import a2s
   print('python-a2s import successful')
   print('Available functions:', [f for f in dir(a2s) if not f.startswith('_')])"
   ```

6. **For hat changes**: Test Pillow image manipulation
   ```bash
   # Test Pillow module import and basic functionality
   python3 -c "
   from PIL import Image
   import io
   print('Pillow import successful')
   # Test basic image creation
   img = Image.new('RGBA', (100, 100), (255, 0, 0, 128))
   output = io.BytesIO()
   img.save(output, format='PNG')
   print('Image creation test: OK')"
   ```

### Red-bot Framework Testing
**IMPORTANT**: Red-DiscordBot requires Python 3.11 or earlier (not 3.12+). When testing with redbot.core:

**What you CAN do:**
- Install Red-DiscordBot with Python 3.11: `pip install Red-DiscordBot`
- Import redbot modules: `from redbot.core import commands, Config, checks`
- Test cog imports and basic initialization
- Validate that cogs can be loaded by the framework

**What you CANNOT do:**
- Run actual Red-bot instances (requires full Discord bot setup)
- Test Discord interactions without a running bot
- Test cog loading/unloading without a bot instance

**Testing Strategy:**
1. Install Red-DiscordBot (Python 3.11 only)
2. Test imports: `python -c "from redbot.core import commands"`
3. Validate syntax: `python -m py_compile */*.py`
4. Run linting: `flake8 . --statistics`

## CI/CD Pipeline

### GitHub Actions
The repository uses `.github/workflows/lint.yml` which:
- Runs on Python 3.11 (required for Red-DiscordBot compatibility)
- Uses flake8 for linting via py-actions/flake8@v2
- Installs Red-DiscordBot and tests cog imports
- Validates that all cogs compile successfully

### Pre-commit Validation
Always run before committing:
```bash
# Syntax check modified files
python3 -m py_compile modified_file.py

# Check for new critical errors
flake8 modified_file.py --select=E9,F63,F7,F82

# Ensure no new undefined variables
flake8 modified_file.py --select=F821
```

## Common Development Tasks

### Adding New Cog Features
1. Modify the main Python file
2. Update info.json if adding dependencies
3. Run syntax validation: `python3 -m py_compile cog_name/main_file.py`
4. Test dependency imports if applicable
5. Run targeted linting: `flake8 cog_name/ --select=F821,E9`

### Modifying Existing Cogs
1. **Never** remove working code unless absolutely necessary
2. Focus on minimal changes to achieve the goal
3. Preserve existing patterns and style
4. Validate syntax immediately after changes
5. Check for new undefined variable errors

### Debugging Issues
1. Use `python3 -m py_compile` for syntax errors
2. Use `flake8 --select=F821` for undefined variables
3. Check info.json for missing dependencies
4. Review import statements for typos

### Using Discord Tasks for Background Operations
**IMPORTANT**: When implementing background tasks in cogs, always use native Discord tasks (`discord.ext.tasks`) instead of manual asyncio loops. This provides better error handling, automatic restart on failure, and cleaner lifecycle management.

#### Discord Tasks Pattern
Discord tasks are the recommended way to implement periodic background operations. They provide:
- Automatic error handling and recovery
- Built-in waiting for bot ready state
- Clean start/stop lifecycle management
- Automatic reconnection handling

#### Implementation Pattern
```python
from discord.ext import tasks

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Start the task when the cog is initialized
        self.my_background_task.start()
    
    def cog_unload(self):
        """Cancel the background task when cog unloads"""
        self.my_background_task.cancel()
    
    @tasks.loop(hours=1.0)  # or minutes=X, seconds=X
    async def my_background_task(self):
        """Background task that runs periodically"""
        try:
            # Your task logic here
            await self.do_something()
        except Exception as e:
            log.error(f"Error in background task: {e}", exc_info=True)
    
    @my_background_task.before_loop
    async def before_my_task(self):
        """Wait for bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()
```

#### Key Differences from Manual Loops

**❌ DO NOT use manual asyncio loops:**
```python
# OLD PATTERN - DO NOT USE
async def cog_load(self):
    self._task = self.bot.loop.create_task(self._my_loop())

async def _my_loop(self):
    await self.bot.wait_until_ready()
    while True:
        try:
            await asyncio.sleep(3600)
            await self.do_something()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Error: {e}")
            await asyncio.sleep(3600)
```

**✅ DO use Discord tasks:**
```python
# NEW PATTERN - USE THIS
def __init__(self, bot):
    self.bot = bot
    self.my_task.start()

@tasks.loop(hours=1.0)
async def my_task(self):
    await self.do_something()

@my_task.before_loop
async def before_my_task(self):
    await self.bot.wait_until_ready()
```

#### Examples in Repository
See these cogs for reference implementations:
- **nw_server_status/server_status.py**: Uses `@tasks.loop(minutes=5.0)` for server status updates
- **game_embed/game_embed.py**: Uses `@tasks.loop(seconds=15.0)` for game server monitoring
- **albion_auth/auth.py**: Uses `@tasks.loop(hours=1.0)` for daily verification checks

#### Task Loop Configuration
- Use `hours=X` for hourly intervals (e.g., `@tasks.loop(hours=1.0)`)
- Use `minutes=X` for minute intervals (e.g., `@tasks.loop(minutes=5.0)`)
- Use `seconds=X` for second intervals (e.g., `@tasks.loop(seconds=15.0)`)
- Tasks automatically restart on failure unless cancelled
- Always implement `@task_name.before_loop` to wait for bot ready

#### Benefits
1. **Automatic Error Recovery**: Tasks restart automatically after exceptions (no need for manual try/except in loop)
2. **Cleaner Code**: No need for `while True` loops or manual sleep management
3. **Better Lifecycle**: Tasks are properly managed by Discord.py framework
4. **Reconnection Handling**: Tasks automatically handle Discord reconnections
5. **Consistency**: Follows Discord.py best practices and matches Red-bot ecosystem patterns

## Maintaining Documentation

### Documentation Update Requirements
**CRITICAL**: The `.github/copilot-instructions.md` file MUST be updated whenever changes are made to the repository structure or cog functionality. This ensures AI assistants have accurate context for future work.

### When to Update Copilot Instructions
Update `.github/copilot-instructions.md` in the following scenarios:

1. **Adding a New Cog**:
   - Add the cog to the "Key Cogs" section (alphabetically ordered)
   - Include a brief description and list any external dependencies
   - Update "Common Dependencies" section if new dependencies are introduced
   - Add any cog-specific testing scenarios to "Manual Testing Scenarios"

2. **Modifying Cog Dependencies**:
   - Update the dependency information in "Key Cogs" section
   - Update "Common Dependencies" section with new version requirements
   - Update the initial setup commands if needed

3. **Removing a Cog**:
   - Remove the cog from "Key Cogs" section
   - Remove cog-specific dependencies from "Common Dependencies" if no longer used
   - Remove any cog-specific testing scenarios

4. **Changing Cog Functionality**:
   - Update the description in "Key Cogs" section if the purpose changes significantly
   - Update testing scenarios if the testing approach needs to change

5. **Repository Structure Changes**:
   - Update "Repository Structure" section
   - Update "File Locations" section
   - Update any affected commands or paths

6. **CI/CD Pipeline Changes**:
   - Update "GitHub Actions" section with new workflow details
   - Update validation commands if the pipeline requirements change

### Documentation Format Guidelines
- Keep descriptions concise (one line per cog)
- List dependencies in parentheses: `(requires: package>=version)` or `(no external deps)`
- Maintain alphabetical ordering in the "Key Cogs" section
- Use consistent terminology across all sections
- Include version numbers for dependencies when specified in info.json

### Validation After Documentation Updates
After updating copilot instructions, verify:
```bash
# Ensure the markdown is valid (no broken formatting)
head -50 .github/copilot-instructions.md

# Verify all cogs are documented (excludes .github directory)
ls -d */ | grep -v '.github/' | sed 's|/||' | sort > /tmp/cogs_actual.txt
grep -E "^\- \*\*[^/]+/\*\*:" .github/copilot-instructions.md | awk -F'**' '{print $2}' | sed 's|/.*||' | sort > /tmp/cogs_documented.txt
diff /tmp/cogs_actual.txt /tmp/cogs_documented.txt
```

Remember: Accurate documentation prevents confusion and reduces errors in future AI-assisted development work.

## Development Environment Limitations

### What Works
- Python syntax validation
- Dependency installation via pip
- Flake8 linting
- File editing and basic testing
- Red-DiscordBot installation (with Python 3.11)
- Cog import testing
- Red-DiscordBot module imports

### What Does NOT Work
- Running actual Red-bot instances (requires Discord bot setup)
- Testing Discord interactions without a bot
- Full cog loading/unloading testing (requires bot instance)
- Red-bot command execution testing

### Time Expectations
- Python syntax validation: Immediate (<1 second)
- Red-DiscordBot installation: 60-120 seconds (first time)
- Dependency installation: 30-60 seconds per package  
- Full repository linting: Immediate (<1 second)
- Individual file linting: Immediate
- Cog import testing: Immediate (<1 second)

## File Locations

### Repository Root
```
/home/runner/work/cogs/cogs/
├── .github/workflows/lint.yml    # CI configuration
├── .gitignore                    # Standard Python gitignore
├── README.md                     # Basic installation instructions
├── LICENSE                       # MIT license
└── [cog_directories]/            # Individual cog implementations
```

### Critical Files to Check
- `info.json` files for dependency requirements
- `__init__.py` files for cog registration patterns
- Main Python files for core functionality
- `.github/workflows/lint.yml` for CI requirements

Remember: This is a cog repository, not an application. Focus on plugin functionality, dependency management, and code quality rather than traditional build/test/deploy cycles.

## Discord.py Command Argument Parsing

### Understanding Command Arguments
When working with Discord commands, it's crucial to understand how discord.py parses command arguments. This knowledge is essential when designing commands with `*args` or handling multi-word arguments.

### Parsing Behavior
Discord.py uses a quote-aware parser (implemented in `discord/ext/commands/view.py` via `StringView.get_quoted_word()`):

1. **Whitespace Splitting**: Arguments are split by whitespace (spaces, tabs, newlines) by default
2. **Quote Protection**: Content within quotes is treated as a single argument
3. **Escape Sequences**: Backslash can escape quotes within quoted strings

### Example Parsing
```python
# Command: [p]party create Siege Tank Healer DPS
# Results in:
#   name = "Siege"
#   *roles = ("Tank", "Healer", "DPS")

# Command: [p]party create Siege "Off Tank" "Main Healer" DPS
# Results in:
#   name = "Siege"
#   *roles = ("Off Tank", "Main Healer", "DPS")

# Command: [p]party create Siege Tank, Healer, Off Tank, Main DPS
# Results in: (note: multi-word roles get split!)
#   name = "Siege"
#   *roles = ("Tank,", "Healer,", "Off", "Tank,", "Main", "DPS")
```

### Common Pitfalls
1. **Multi-word with Commas**: When users type comma-separated lists with multi-word items, the items get split by whitespace first, then you see commas attached to words
2. **Quote Awareness**: Your parsing logic must account for whether the user quoted arguments or not
3. **Backward Compatibility**: Changes to argument parsing must maintain compatibility with existing usage patterns

### Validation Strategy
When modifying command argument parsing:

1. **Review Source Code**: Check both:
   - [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot) for Red-bot specific behavior
   - [discord.py](https://github.com/Rapptz/discord.py) for underlying argument parsing (specifically `discord/ext/commands/view.py`)

2. **Test Multiple Formats**: Validate that your parsing handles:
   - Space-separated arguments: `arg1 arg2 arg3`
   - Quoted arguments: `"arg 1" "arg 2" arg3`
   - Comma-separated arguments: `arg1, arg2, arg3`
   - Mixed formats: `arg1, "arg 2", arg3`

3. **Document Expected Usage**: Clearly document in the command's docstring how users should format multi-word arguments

### Best Practices for Commands with `*args`
When designing commands that accept multiple arguments:

```python
@command()
async def mycommand(self, ctx, name: str, *items: str):
    """Command that accepts multiple items.
    
    For multi-word items, use one of these formats:
    - Comma-separated: [p]mycommand "Name" Item1, Multi Word Item, Item3
    - Quoted: [p]mycommand "Name" Item1 "Multi Word Item" Item3
    """
    # Join all args first, then split based on detected format
    joined = ' '.join(items)
    
    if ',' in joined:
        # Comma-separated: split by comma (preserves multi-word items)
        parsed_items = [i.strip() for i in joined.split(',') if i.strip()]
    else:
        # Space-separated: split by whitespace (assumes single-word items)
        parsed_items = [i.strip() for i in joined.split() if i.strip()]
```

### References
- Discord.py StringView: `discord/ext/commands/view.py`
- Red-bot Command Examples: `redbot/cogs/*/` in Red-DiscordBot repository
- Quote Handling: Discord.py supports many quote types (", ', «», etc.) defined in `_quotes` dictionary
