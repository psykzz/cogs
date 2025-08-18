# Red-bot Cogs Repository

This repository contains Red-bot cogs (Discord bot plugins) written in Python. Each cog is a self-contained module providing specific Discord bot functionality.

**ALWAYS reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Initial Setup and Validation
Run these commands to set up the development environment and validate the codebase:

```bash
# Install linting tools
pip3 install flake8

# Install common cog dependencies (install as needed based on info.json files)
pip3 install cinemagoer==2022.12.27 httpx discord.py

# Validate Python syntax for all cogs (immediate, ~1 second)
python3 -m py_compile */*.py

# Run linting to identify issues (immediate, <1 second)
flake8 . --statistics
```

### Expected Linting Issues
The codebase currently has **228 flake8 violations** including:
- 132 line length violations (E501)
- 30 excessive blank lines (E303) 
- 24 whitespace issues (W293)
- 14 unused f-string placeholders (F541)
- 9 unused imports (F401)
- 3 undefined variables (F821) in movie_vote/movie_vote.py and nw_server_status/server_status.py

**Do NOT attempt to fix existing linting issues** unless directly related to your changes. The CI build expects these issues.

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
├── __init__.py          # Cog registration
├── main_file.py         # Main implementation
└── info.json           # Metadata and dependencies
```

### Key Cogs
- **movie_vote/**: Movie voting system with IMDB integration (requires: cinemagoer==2022.12.27)
- **tgmc/**: API interface for TGMC game (requires: httpx)
- **nw_timers/**: New World war timers (no external deps)
- **nw_server_status/**: New World server monitoring (requires: httpx>=0.14.1)
- **react_roles/**: Role assignment via reactions (no external deps)
- **assign_roles/**: Role management system (no external deps)
- **misc/**: Miscellaneous utilities (no external deps)
- **quotesdb/**: Quote storage system (no external deps)
- **empty_voices/**: Voice channel management (no external deps)

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

# For server status and API cogs  
pip3 install httpx>=0.14.1

# For Discord functionality (if testing imports)
pip3 install discord.py
```

## Testing and Validation

### Code Validation
Since this is a Red-bot cog repository, there is **no traditional build process**. Validation focuses on:

1. **Python syntax validation** (immediate)
2. **Import testing** (immediate, may fail due to missing redbot.core)
3. **Linting compliance** (15 seconds)

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

### Red-bot Framework
**IMPORTANT**: The redbot.core framework is NOT installable in this environment due to Python version compatibility. You cannot:
- Import redbot modules directly
- Run actual Red-bot instances
- Test cog loading/unloading

Focus on syntax validation and logic testing instead.

## CI/CD Pipeline

### GitHub Actions
The repository uses `.github/workflows/lint.yml` which:
- Runs on Python 3.9
- Uses flake8 for linting via py-actions/flake8@v1
- **Expects current linting violations** - do not attempt to fix unrelated issues

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

## Development Environment Limitations

### What Works
- Python syntax validation
- Dependency installation via pip
- Flake8 linting
- File editing and basic testing

### What Does NOT Work
- Red-bot framework installation (Python version incompatibility)
- Actual cog loading/testing
- Discord bot functionality testing
- Red-bot command testing

### Time Expectations
- Python syntax validation: Immediate (<1 second)
- Dependency installation: 30-60 seconds per package  
- Full repository linting: Immediate (<1 second)
- Individual file linting: Immediate

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