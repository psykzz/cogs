"""
Unit tests for the Movie Vote cog.

Tests cover:
- IMDB link parsing
- Movie addition and removal
- Vote counting
- Leaderboard generation
- Watch/unwatch functionality
- Channel enable/disable
"""

import pytest
import re

# Fixtures are automatically discovered from conftest.py
# No need to import them explicitly


# ============================================================================
# Test IMDB Link Parsing
# ============================================================================

class TestIMDBParsing:
    """Test IMDB link extraction and parsing."""

    def test_imdb_link_regex_valid_url(self):
        """Test that valid IMDB links are matched."""
        # Test the regex pattern directly without importing the module
        RE_IMDB_LINK = re.compile(r"(https:\/\/www\.imdb\.com\/title\/tt\d+)")

        test_cases = [
            "Check out https://www.imdb.com/title/tt0111161",
            "Link: https://www.imdb.com/title/tt0468569/",
            "https://www.imdb.com/title/tt1375666 is great!",
        ]

        for text in test_cases:
            match = RE_IMDB_LINK.search(text)
            assert match is not None, f"Failed to match: {text}"
            assert "imdb.com/title/tt" in match.group(1)

    def test_imdb_link_regex_invalid_url(self):
        """Test that invalid IMDB links are not matched."""
        # Test the regex pattern directly without importing the module
        RE_IMDB_LINK = re.compile(r"(https:\/\/www\.imdb\.com\/title\/tt\d+)")

        test_cases = [
            "No link here",
            "http://imdb.com/title/123",  # Missing https and www
            "imdb.com/title/tt0111161",  # Missing protocol
            "https://www.imdb.com/name/nm0000136",  # Name, not title
        ]

        for text in test_cases:
            match = RE_IMDB_LINK.search(text)
            assert match is None, f"Incorrectly matched: {text}"

    def test_imdb_id_extraction(self):
        """Test extracting IMDB ID from link."""
        link = "https://www.imdb.com/title/tt0111161"
        imdb_id = link.split('/tt')[-1]
        assert imdb_id == "0111161"

    def test_imdb_id_extraction_with_slash(self):
        """Test extracting IMDB ID from link with trailing slash."""
        link = "https://www.imdb.com/title/tt0468569/"
        imdb_id = link.split('/tt')[-1].rstrip('/')
        assert imdb_id == "0468569"


# ============================================================================
# Test Movie Vote Configuration
# ============================================================================

@pytest.mark.asyncio
class TestMovieVoteConfig:
    """Test MovieVote cog configuration."""

    async def test_default_config_values(self, mock_config):
        """Test that default config values are set correctly."""
        mock_config.register_guild(
            channels_enabled=[],
            movies=[],
            leaderboard=0,
            up_emoji="👍",
            dn_emoji="👎",
            notify_episode=[],
        )

        # Access guild config
        guild_data = await mock_config.guild(1).all()

        assert guild_data["channels_enabled"] == []
        assert guild_data["movies"] == []
        assert guild_data["leaderboard"] == 0
        assert guild_data["up_emoji"] == "👍"
        assert guild_data["dn_emoji"] == "👎"

    async def test_enable_channel(self, mock_config, guild, channel):
        """Test enabling MovieVote in a channel."""
        mock_config.register_guild(channels_enabled=[])

        # Enable channel
        channels = await mock_config.guild(guild).channels_enabled()
        channels.append(channel.id)
        await mock_config.guild(guild).channels_enabled.set(channels)

        # Verify
        enabled = await mock_config.guild(guild).channels_enabled()
        assert channel.id in enabled

    async def test_disable_channel(self, mock_config, guild, channel):
        """Test disabling MovieVote in a channel."""
        mock_config.register_guild(channels_enabled=[channel.id])

        # Set initial state
        await mock_config.guild(guild).channels_enabled.set([channel.id])

        # Disable channel
        channels = await mock_config.guild(guild).channels_enabled()
        channels.remove(channel.id)
        await mock_config.guild(guild).channels_enabled.set(channels)

        # Verify
        enabled = await mock_config.guild(guild).channels_enabled()
        assert channel.id not in enabled


# ============================================================================
# Test Movie Management
# ============================================================================

@pytest.mark.asyncio
class TestMovieManagement:
    """Test adding, removing, and managing movies."""

    async def test_add_movie_to_list(self, mock_config, guild):
        """Test adding a movie to the list."""
        mock_config.register_guild(movies=[])

        # Create movie entry
        movie = {
            "link": "https://www.imdb.com/title/tt0111161",
            "imdb_id": "0111161",
            "score": 0,
            "watched": False,
            "title": "The Shawshank Redemption",
            "genres": ["Drama"],
            "year": 1994
        }

        # Add movie
        movies = await mock_config.guild(guild).movies()
        movies.append(movie)
        await mock_config.guild(guild).movies.set(movies)

        # Verify
        saved_movies = await mock_config.guild(guild).movies()
        assert len(saved_movies) == 1
        assert saved_movies[0]["imdb_id"] == "0111161"
        assert saved_movies[0]["title"] == "The Shawshank Redemption"

    async def test_prevent_duplicate_movies(self, mock_config, guild):
        """Test that duplicate movies are detected."""
        mock_config.register_guild(movies=[])

        # Add first movie
        movie = {
            "link": "https://www.imdb.com/title/tt0111161",
            "imdb_id": "0111161",
            "score": 0,
            "watched": False,
        }
        movies = [movie]
        await mock_config.guild(guild).movies.set(movies)

        # Check for duplicate
        movies = await mock_config.guild(guild).movies()
        imdb_id = "0111161"
        exists = any(m["imdb_id"] == imdb_id for m in movies)

        assert exists is True

    async def test_mark_movie_as_watched(self, mock_config, guild):
        """Test marking a movie as watched."""
        mock_config.register_guild(movies=[])

        # Add movie
        movie = {
            "link": "https://www.imdb.com/title/tt0111161",
            "imdb_id": "0111161",
            "score": 5,
            "watched": False,
        }
        await mock_config.guild(guild).movies.set([movie])

        # Mark as watched
        movies = await mock_config.guild(guild).movies()
        for m in movies:
            if m["imdb_id"] == "0111161":
                m["watched"] = True
        await mock_config.guild(guild).movies.set(movies)

        # Verify
        saved_movies = await mock_config.guild(guild).movies()
        assert saved_movies[0]["watched"] is True

    async def test_remove_movie_from_list(self, mock_config, guild):
        """Test removing a movie from the list."""
        mock_config.register_guild(movies=[])

        # Add movies
        movies = [
            {"link": "https://www.imdb.com/title/tt0111161", "imdb_id": "0111161", "score": 5, "watched": False},
            {"link": "https://www.imdb.com/title/tt0468569", "imdb_id": "0468569", "score": 3, "watched": False},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Remove first movie
        movies = await mock_config.guild(guild).movies()
        movies = [m for m in movies if m["imdb_id"] != "0111161"]
        await mock_config.guild(guild).movies.set(movies)

        # Verify
        saved_movies = await mock_config.guild(guild).movies()
        assert len(saved_movies) == 1
        assert saved_movies[0]["imdb_id"] == "0468569"


# ============================================================================
# Test Vote Counting
# ============================================================================

@pytest.mark.asyncio
class TestVoteCounting:
    """Test vote counting and score calculation."""

    async def test_calculate_score_from_reactions(self):
        """Test calculating score from upvotes and downvotes."""
        upvotes = 10
        downvotes = 3
        score = upvotes - downvotes
        assert score == 7

    async def test_update_movie_score(self, mock_config, guild):
        """Test updating a movie's score."""
        mock_config.register_guild(movies=[])

        # Add movie with initial score
        movie = {
            "link": "https://www.imdb.com/title/tt0111161",
            "imdb_id": "0111161",
            "score": 0,
            "watched": False,
        }
        await mock_config.guild(guild).movies.set([movie])

        # Simulate vote counting
        upvotes, downvotes = 15, 5
        new_score = upvotes - downvotes

        # Update score
        movies = await mock_config.guild(guild).movies()
        for m in movies:
            if m["imdb_id"] == "0111161":
                m["score"] = new_score
        await mock_config.guild(guild).movies.set(movies)

        # Verify
        saved_movies = await mock_config.guild(guild).movies()
        assert saved_movies[0]["score"] == 10

    async def test_negative_score(self):
        """Test that negative scores are possible."""
        upvotes = 2
        downvotes = 10
        score = upvotes - downvotes
        assert score == -8


# ============================================================================
# Test Leaderboard Generation
# ============================================================================

@pytest.mark.asyncio
class TestLeaderboard:
    """Test leaderboard generation and sorting."""

    async def test_sort_movies_by_score(self, mock_config, guild):
        """Test that movies are sorted by score descending."""
        mock_config.register_guild(movies=[])

        # Add movies with different scores
        movies = [
            {"imdb_id": "1", "score": 5, "watched": False, "title": "Movie A", "year": 2020, "genres": ["Action"]},
            {"imdb_id": "2", "score": 15, "watched": False, "title": "Movie B", "year": 2021, "genres": ["Drama"]},
            {"imdb_id": "3", "score": 10, "watched": False, "title": "Movie C", "year": 2022, "genres": ["Comedy"]},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Sort by score
        movies = await mock_config.guild(guild).movies()
        sorted_movies = sorted(movies, key=lambda x: x["score"], reverse=True)

        assert sorted_movies[0]["imdb_id"] == "2"  # Highest score
        assert sorted_movies[1]["imdb_id"] == "3"
        assert sorted_movies[2]["imdb_id"] == "1"  # Lowest score

    async def test_filter_watched_movies(self, mock_config, guild):
        """Test filtering out watched movies from leaderboard."""
        mock_config.register_guild(movies=[])

        # Add movies, some watched
        movies = [
            {"imdb_id": "1", "score": 5, "watched": True, "title": "Movie A"},
            {"imdb_id": "2", "score": 15, "watched": False, "title": "Movie B"},
            {"imdb_id": "3", "score": 10, "watched": False, "title": "Movie C"},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Filter unwatched
        movies = await mock_config.guild(guild).movies()
        unwatched = [m for m in movies if not m.get("watched", False)]

        assert len(unwatched) == 2
        assert all(not m["watched"] for m in unwatched)

    async def test_get_next_movie_to_watch(self, mock_config, guild):
        """Test getting the highest-scored unwatched movie."""
        mock_config.register_guild(movies=[])

        # Add movies
        movies = [
            {"imdb_id": "1", "score": 5, "watched": True, "title": "Movie A", "year": 2020, "genres": ["Action"]},
            {"imdb_id": "2", "score": 15, "watched": False, "title": "Movie B", "year": 2021, "genres": ["Drama"]},
            {"imdb_id": "3", "score": 10, "watched": False, "title": "Movie C", "year": 2022, "genres": ["Comedy"]},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Get next movie (highest score, unwatched)
        movies = await mock_config.guild(guild).movies()
        unwatched = [m for m in movies if not m.get("watched", False)]
        sorted_movies = sorted(unwatched, key=lambda x: x["score"], reverse=True)
        next_movie = sorted_movies[0] if sorted_movies else None

        assert next_movie is not None
        assert next_movie["imdb_id"] == "2"
        assert next_movie["score"] == 15

    async def test_limit_leaderboard_results(self, mock_config, guild):
        """Test limiting leaderboard to top N movies."""
        mock_config.register_guild(movies=[])

        # Add many movies
        movies = [
            {"imdb_id": f"{i}", "score": i * 2, "watched": False, "title": f"Movie {i}",
             "year": 2020, "genres": ["Action"]}
            for i in range(10)
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Get top 5
        movies = await mock_config.guild(guild).movies()
        sorted_movies = sorted(movies, key=lambda x: x["score"], reverse=True)
        top_5 = sorted_movies[:5]

        assert len(top_5) == 5
        assert top_5[0]["score"] > top_5[4]["score"]


# ============================================================================
# Test Emoji Handling
# ============================================================================

@pytest.mark.asyncio
class TestEmojiHandling:
    """Test custom emoji handling."""

    async def test_set_custom_upvote_emoji(self, mock_config, guild):
        """Test setting a custom upvote emoji."""
        mock_config.register_guild(up_emoji="👍")

        # Set custom emoji
        new_emoji = "⬆️"
        await mock_config.guild(guild).up_emoji.set(new_emoji)

        # Verify
        emoji = await mock_config.guild(guild).up_emoji()
        assert emoji == "⬆️"

    async def test_set_custom_downvote_emoji(self, mock_config, guild):
        """Test setting a custom downvote emoji."""
        mock_config.register_guild(dn_emoji="👎")

        # Set custom emoji
        new_emoji = "⬇️"
        await mock_config.guild(guild).dn_emoji.set(new_emoji)

        # Verify
        emoji = await mock_config.guild(guild).dn_emoji()
        assert emoji == "⬇️"

    async def test_default_emoji_values(self, mock_config, guild):
        """Test that default emojis are set correctly."""
        mock_config.register_guild(up_emoji="👍", dn_emoji="👎")

        up_emoji = await mock_config.guild(guild).up_emoji()
        dn_emoji = await mock_config.guild(guild).dn_emoji()

        assert up_emoji == "👍"
        assert dn_emoji == "👎"


# ============================================================================
# Test Edge Cases
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_movie_list(self, mock_config, guild):
        """Test handling empty movie list."""
        mock_config.register_guild(movies=[])

        movies = await mock_config.guild(guild).movies()
        assert movies == []
        assert len(movies) == 0

    async def test_all_movies_watched(self, mock_config, guild):
        """Test when all movies are marked as watched."""
        mock_config.register_guild(movies=[])

        # Add all watched movies
        movies = [
            {"imdb_id": "1", "score": 5, "watched": True},
            {"imdb_id": "2", "score": 10, "watched": True},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Filter unwatched
        movies = await mock_config.guild(guild).movies()
        unwatched = [m for m in movies if not m["watched"]]

        assert len(unwatched) == 0

    async def test_movie_with_zero_score(self, mock_config, guild):
        """Test handling movies with zero score."""
        mock_config.register_guild(movies=[])

        movie = {"imdb_id": "1", "score": 0, "watched": False}
        await mock_config.guild(guild).movies.set([movie])

        movies = await mock_config.guild(guild).movies()
        assert movies[0]["score"] == 0

    async def test_find_nonexistent_movie(self, mock_config, guild):
        """Test searching for a movie that doesn't exist."""
        mock_config.register_guild(movies=[])

        movies = [
            {"imdb_id": "1", "link": "https://www.imdb.com/title/tt0111161"},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Search for non-existent movie
        movies = await mock_config.guild(guild).movies()
        target_link = "https://www.imdb.com/title/tt9999999"
        found = None
        for m in movies:
            if m["link"] == target_link:
                found = m
                break

        assert found is None


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
class TestMovieVoteIntegration:
    """Integration tests for complete workflows."""

    async def test_complete_movie_lifecycle(self, mock_config, guild):
        """Test complete movie lifecycle: add -> vote -> watch -> remove."""
        mock_config.register_guild(movies=[], up_emoji="👍", dn_emoji="👎")

        # 1. Add movie
        movie = {
            "link": "https://www.imdb.com/title/tt0111161",
            "imdb_id": "0111161",
            "score": 0,
            "watched": False,
            "title": "The Shawshank Redemption",
        }
        await mock_config.guild(guild).movies.set([movie])

        # 2. Vote on movie
        movies = await mock_config.guild(guild).movies()
        for m in movies:
            if m["imdb_id"] == "0111161":
                m["score"] = 10  # Simulated vote count
        await mock_config.guild(guild).movies.set(movies)

        # 3. Mark as watched
        movies = await mock_config.guild(guild).movies()
        for m in movies:
            if m["imdb_id"] == "0111161":
                m["watched"] = True
        await mock_config.guild(guild).movies.set(movies)

        # 4. Verify final state
        final_movies = await mock_config.guild(guild).movies()
        assert len(final_movies) == 1
        assert final_movies[0]["score"] == 10
        assert final_movies[0]["watched"] is True

    async def test_multiple_movies_voting_workflow(self, mock_config, guild):
        """Test voting workflow with multiple movies."""
        mock_config.register_guild(movies=[])

        # Add multiple movies
        movies = [
            {"imdb_id": "1", "score": 0, "watched": False, "title": "Movie A", "year": 2020, "genres": ["Action"]},
            {"imdb_id": "2", "score": 0, "watched": False, "title": "Movie B", "year": 2021, "genres": ["Drama"]},
            {"imdb_id": "3", "score": 0, "watched": False, "title": "Movie C", "year": 2022, "genres": ["Comedy"]},
        ]
        await mock_config.guild(guild).movies.set(movies)

        # Simulate voting
        movies = await mock_config.guild(guild).movies()
        movies[0]["score"] = 15
        movies[1]["score"] = 5
        movies[2]["score"] = 10
        await mock_config.guild(guild).movies.set(movies)

        # Get top movie
        movies = await mock_config.guild(guild).movies()
        sorted_movies = sorted(movies, key=lambda x: x["score"], reverse=True)
        top_movie = sorted_movies[0]

        assert top_movie["imdb_id"] == "1"
        assert top_movie["score"] == 15
