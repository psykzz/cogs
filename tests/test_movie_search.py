import importlib.util
import json
import sys
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def movie_search_module(monkeypatch):
    commands = SimpleNamespace(
        Cog=object,
        hybrid_command=lambda **kwargs: lambda function: function,
    )
    redbot = ModuleType("redbot")
    redbot_core = ModuleType("redbot.core")
    redbot.core = redbot_core
    redbot_core.commands = commands
    monkeypatch.setitem(sys.modules, "redbot", redbot)
    monkeypatch.setitem(sys.modules, "redbot.core", redbot_core)

    module_path = Path(__file__).parents[1] / "movie_search" / "movie_search.py"
    spec = importlib.util.spec_from_file_location("movie_search_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_imdb_search_returns_first_match_link(movie_search_module, monkeypatch):
    response = BytesIO(json.dumps({
        "d": [
            {"id": "nm0000206", "l": "Keanu Reeves"},
            {"id": "tt0133093", "l": "The Matrix", "y": 1999},
        ],
    }).encode())
    urlopen = Mock(return_value=response)
    monkeypatch.setattr(movie_search_module, "urlopen", urlopen)
    cog = movie_search_module.MovieSearch(bot=None)
    channel = SimpleNamespace(send=AsyncMock())
    ctx = SimpleNamespace(send=AsyncMock(), defer=AsyncMock(), channel=channel)

    await cog.imdb(ctx, title="  The Matrix  ")

    request = urlopen.call_args.args[0]
    assert request.full_url == (
        "https://v3.sg.media-imdb.com/suggestion/t/the%20matrix.json"
    )
    urlopen.assert_called_once_with(request, timeout=10)
    ctx.defer.assert_awaited_once_with(ephemeral=True)
    ctx.send.assert_not_awaited()
    channel.send.assert_awaited_once_with(
        "The Matrix (1999): https://www.imdb.com/title/tt0133093/",
    )


@pytest.mark.asyncio
async def test_imdb_search_reports_no_matches(movie_search_module, monkeypatch):
    response = BytesIO(json.dumps({"d": []}).encode())
    monkeypatch.setattr(movie_search_module, "urlopen", Mock(return_value=response))
    cog = movie_search_module.MovieSearch(bot=None)
    ctx = SimpleNamespace(send=AsyncMock(), defer=AsyncMock())

    await cog.imdb(ctx, title="Unknown title")

    ctx.defer.assert_awaited_once_with(ephemeral=True)
    ctx.send.assert_awaited_once_with(
        "No IMDb results found for 'Unknown title'.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_imdb_search_reports_lookup_failure(movie_search_module, monkeypatch):
    urlopen = Mock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(movie_search_module, "urlopen", urlopen)
    cog = movie_search_module.MovieSearch(bot=None)
    ctx = SimpleNamespace(send=AsyncMock(), defer=AsyncMock())

    await cog.imdb(ctx, title="The Matrix")

    ctx.defer.assert_awaited_once_with(ephemeral=True)
    ctx.send.assert_awaited_once_with(
        "IMDb search failed. Please try again later.",
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_imdb_search_rejects_blank_title(movie_search_module, monkeypatch):
    urlopen = Mock()
    monkeypatch.setattr(movie_search_module, "urlopen", urlopen)
    cog = movie_search_module.MovieSearch(bot=None)
    ctx = SimpleNamespace(send=AsyncMock(), defer=AsyncMock())

    await cog.imdb(ctx, title="   ")

    urlopen.assert_not_called()
    ctx.defer.assert_not_awaited()
    ctx.send.assert_awaited_once_with("Please provide a movie title.", ephemeral=True)
