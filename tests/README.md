# Test Suite Documentation

This directory contains unit and integration tests for the Red-DiscordBot cogs repository.

## Overview

The test suite validates cog functionality without requiring a running Discord bot or Red-DiscordBot instance. Tests use mock Discord objects and simulate bot behavior for testing purposes.

## Test Infrastructure

### Configuration Files

- **`pytest.ini`**: Pytest configuration including test discovery, coverage settings, and markers
- **`.coveragerc`**: Coverage reporting configuration
- **`conftest.py`**: Shared pytest fixtures and mock utilities
- **`requirements-test.txt`**: Testing dependencies

### Mock Objects

The `conftest.py` file provides comprehensive mock objects for testing:

- **Mock Discord Objects**:
  - `MockBot`: Simulates a Discord bot instance
  - `MockGuild`: Simulates a Discord server/guild
  - `MockMember`: Simulates a Discord user/member
  - `MockRole`: Simulates a Discord role
  - `MockTextChannel`: Simulates a Discord text channel
  - `MockMessage`: Simulates a Discord message
  - `MockContext`: Simulates command context (for text commands)
  - `MockInteraction`: Simulates slash command interactions

- **Mock Red-DiscordBot Objects**:
  - `MockConfig`: Simulates Red-DiscordBot's Config API for data persistence
  - `MockConfigGroup`: Handles guild/user/channel-level config
  - `MockConfigAttribute`: Manages individual config attributes

### Pytest Fixtures

Available fixtures (automatically imported in all test files):

```python
@pytest.fixture
def bot():
    """Provides a mock Discord bot."""

@pytest.fixture
def guild():
    """Provides a mock Discord guild."""

@pytest.fixture
def member(guild):
    """Provides a mock Discord member."""

@pytest.fixture
def channel(guild):
    """Provides a mock Discord text channel."""

@pytest.fixture
def ctx(bot, guild, member, channel):
    """Provides a mock Discord command context."""

@pytest.fixture
def interaction(member, guild, channel):
    """Provides a mock Discord interaction."""

@pytest.fixture
def mock_config():
    """Provides a mock Red-DiscordBot Config object."""
```

## Running Tests

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test File

```bash
pytest tests/test_movie_vote.py -v
```

### Run Specific Test Class

```bash
pytest tests/test_movie_vote.py::TestIMDBParsing -v
```

### Run Specific Test

```bash
pytest tests/test_movie_vote.py::TestIMDBParsing::test_imdb_link_regex_valid_url -v
```

### Run Tests with Coverage

```bash
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html
```

View HTML coverage report:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run Tests Matching a Pattern

```bash
pytest tests/ -k "test_emoji" -v
```

## Test Organization

Tests are organized by cog with clear test class groupings:

### Example: `test_movie_vote.py`

- **TestIMDBParsing**: IMDB link regex and ID extraction
- **TestMovieVoteConfig**: Configuration and channel management
- **TestMovieManagement**: Adding, removing, marking movies
- **TestVoteCounting**: Vote calculation and score updates
- **TestLeaderboard**: Sorting and filtering leaderboards
- **TestEmojiHandling**: Custom emoji configuration
- **TestEdgeCases**: Edge cases and error scenarios
- **TestMovieVoteIntegration**: Complete workflow tests

### Example: `test_react_roles.py`

- **TestReactRolesConfig**: Configuration setup
- **TestTypeConsistency**: Type handling (int vs string) - addresses bug #119
- **TestRoleAssignment**: Role lookup and assignment logic
- **TestMultipleReactions**: Managing multiple reactions per message
- **TestEdgeCases**: Error scenarios
- **TestReactRolesIntegration**: Complete workflows

## Test Markers

Tests can be marked for categorization:

```python
@pytest.mark.unit
async def test_simple_function():
    """Unit test for an isolated function."""

@pytest.mark.integration
async def test_complex_workflow():
    """Integration test for a complete workflow."""

@pytest.mark.slow
async def test_expensive_operation():
    """Test that takes longer to run."""
```

Run tests by marker:
```bash
pytest tests/ -m unit -v  # Run only unit tests
pytest tests/ -m "not slow" -v  # Skip slow tests
```

## Writing New Tests

### Test File Structure

```python
"""
Brief description of what this test file covers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Fixtures are auto-imported from conftest.py


@pytest.mark.asyncio
class TestFeatureName:
    """Test description."""

    async def test_specific_behavior(self, mock_config, guild):
        """Test that specific behavior works correctly."""
        # Arrange
        mock_config.register_guild(some_setting=[])

        # Act
        result = await some_operation()

        # Assert
        assert result == expected_value
```

### Best Practices

1. **Use descriptive test names**: `test_prevent_duplicate_movies` is better than `test_duplicates`
2. **Follow AAA pattern**: Arrange, Act, Assert
3. **Test one thing per test**: Each test should validate a single behavior
4. **Use fixtures**: Reuse common setup via fixtures
5. **Test edge cases**: Include tests for empty data, None values, errors
6. **Test happy paths**: Ensure normal workflows work correctly
7. **Document with docstrings**: Explain what each test validates

### Example Test

```python
@pytest.mark.asyncio
async def test_add_movie_to_list(self, mock_config, guild):
    """Test adding a movie to the list."""
    # Arrange - Set up the test conditions
    mock_config.register_guild(movies=[])
    movie = {
        "link": "https://www.imdb.com/title/tt0111161",
        "imdb_id": "0111161",
        "score": 0,
        "watched": False,
    }

    # Act - Perform the operation being tested
    movies = await mock_config.guild(guild).movies()
    movies.append(movie)
    await mock_config.guild(guild).movies.set(movies)

    # Assert - Verify the expected outcome
    saved_movies = await mock_config.guild(guild).movies()
    assert len(saved_movies) == 1
    assert saved_movies[0]["imdb_id"] == "0111161"
```

## Coverage Goals

- **Critical cogs**: Aim for >70% coverage
- **Bug regression tests**: Every bug fix should have a corresponding test
- **Edge cases**: Test boundary conditions and error scenarios

## CI Integration

Tests run automatically in GitHub Actions on every push:

1. **Lint Job**: Runs flake8 to check code quality
2. **Test Job**: Validates Red-DiscordBot imports and cog syntax
3. **Pytest Job**: Runs the full pytest test suite with coverage reporting

See `.github/workflows/lint.yml` for the CI configuration.

## Troubleshooting

### Test Discovery Issues

If tests aren't being discovered:
- Ensure test files are named `test_*.py`
- Ensure test functions are named `test_*`
- Ensure test files are in the `tests/` directory
- Check `pytest.ini` for custom discovery settings

### Import Errors

If you get import errors:
- Install test dependencies: `pip install -r requirements-test.txt`
- Ensure you're running from the repository root
- Check that `conftest.py` is in the `tests/` directory

### Async Test Errors

If async tests fail with "coroutine was never awaited":
- Add `@pytest.mark.asyncio` decorator to async test functions
- Ensure `pytest-asyncio` is installed
- Check that async functions use `async def` and `await`

## Adding Tests for New Cogs

When adding a new cog, create a corresponding test file:

1. Create `tests/test_<cog_name>.py`
2. Import necessary fixtures (they auto-import from conftest.py)
3. Organize tests into logical classes
4. Cover:
   - Configuration and defaults
   - Command logic
   - Data persistence
   - Edge cases
   - Integration workflows

## Future Improvements

- Add more cog-specific tests (party, secret_santa, hat, etc.)
- Increase coverage for critical cogs
- Add performance/load tests for concurrent operations
- Add integration tests with actual Discord.py objects (if feasible)
- Add mutation testing to validate test quality
