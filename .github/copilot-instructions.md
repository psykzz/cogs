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

### Key Cogs
- **albion_auth/**: Albion Online authentication and daily verification system (requires: httpx>=0.14.1)
- **albion_regear/**: Albion Online regear cost calculator (requires: httpx>=0.14.1)
- **assign_roles/**: Role management system (no external deps)
- **empty_voices/**: Voice channel management (no external deps)
- **misc/**: Miscellaneous utilities (no external deps)
- **movie_vote/**: Movie voting system with IMDB integration (requires: cinemagoer==2022.12.27)
- **nw_server_status/**: New World server monitoring (requires: httpx>=0.14.1)
- **nw_timers/**: New World war timers (no external deps)
- **quotesdb/**: Quote storage system (no external deps)
- **react_roles/**: Role assignment via reactions (no external deps)
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

# For albion_regear and nw_server_status cogs (tgmc also needs httpx but doesn't specify in info.json)
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
- Runs on Python 3.13
- Uses flake8 for linting via py-actions/flake8@v2

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
