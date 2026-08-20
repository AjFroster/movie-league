"""Tests for the MDBList ratings client.

Every request is stubbed -- no network, no real key (conftest's autouse fixture strips
MDBLIST_API_KEY before each test). The key-leak tests matter as much as the parsing ones:
MDBList authenticates by query parameter, so its key rides in the URL exactly as OMDb's
does, and httpx puts the full URL into its error text.
"""
import httpx
import pytest

from app.redaction import ProviderError
from app.services import mdblist


def _payload(**overrides):
    ratings = [
        {"source": "imdb", "value": 8.5, "score": 85, "votes": 418361},
        {"source": "metacritic", "value": 88, "score": 88},
        {"source": "tomatoes", "value": 94, "score": 94},
        {"source": "popcorn", "value": 97, "score": 97},
        {"source": "letterboxd", "value": 4.4, "score": 88},
        {"source": "trakt", "value": 88},
    ]
    base = {"title": "The Odyssey", "year": 2026, "ratings": ratings}
    base.update(overrides)
    return base


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------

def test_parses_all_four_league_inputs():
    """popcorn is RT's audience score -- the mapping is the whole reason this module exists."""
    assert mdblist.parse_mdblist_payload(_payload()) == {
        "imdb": 8.5, "rt_crit": 94.0, "rt_aud": 97.0, "letterboxd": 4.4,
    }


def test_ignores_sources_the_league_does_not_score():
    parsed = mdblist.parse_mdblist_payload(_payload())
    assert set(parsed) == {"imdb", "rt_crit", "rt_aud", "letterboxd"}


def test_partial_ratings_return_only_what_is_present():
    payload = _payload(ratings=[{"source": "imdb", "value": 7.1}])
    assert mdblist.parse_mdblist_payload(payload) == {"imdb": 7.1}


@pytest.mark.parametrize("payload", [
    {}, {"ratings": []}, {"ratings": None}, "not a dict", None,
    {"ratings": [{"source": "imdb", "value": None}]},
    {"ratings": [{"source": "unknown-source", "value": 5}]},
])
def test_no_usable_rating_returns_none(payload):
    """None lets the caller cache a negative result instead of a row of nulls."""
    assert mdblist.parse_mdblist_payload(payload) is None


@pytest.mark.parametrize("source,value", [
    ("imdb", 11), ("imdb", -1), ("letterboxd", 6), ("tomatoes", 101), ("popcorn", -5),
    ("imdb", True), ("imdb", "8.5"), ("imdb", float("nan")),
])
def test_out_of_range_and_wrong_typed_values_are_dropped(source, value):
    """A value outside its scale is a schema surprise, not data worth storing."""
    assert mdblist.parse_mdblist_payload({"ratings": [{"source": source, "value": value}]}) is None


def test_malformed_rating_entries_do_not_break_the_parse():
    payload = {"ratings": ["junk", None, 42, {"source": "imdb", "value": 6.0}]}
    assert mdblist.parse_mdblist_payload(payload) == {"imdb": 6.0}


# ---------------------------------------------------------------------------
# fetch_ratings
# ---------------------------------------------------------------------------

async def test_fetch_returns_none_without_a_key(monkeypatch):
    """No key must be distinguishable from no record -- the caller caches them differently."""
    monkeypatch.delenv("MDBLIST_API_KEY", raising=False)

    def handler(request):
        raise AssertionError("must not call the API without a key")

    async with _client(handler) as client:
        assert await mdblist.fetch_ratings("tt0111161", client=client) is None


async def test_fetch_happy_path(monkeypatch):
    monkeypatch.setenv("MDBLIST_API_KEY", "SENTINELKEY")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_payload())

    async with _client(handler) as client:
        result = await mdblist.fetch_ratings("tt33764258", client=client)

    assert result["rt_aud"] == 97.0 and result["letterboxd"] == 4.4
    assert "/imdb/movie/tt33764258" in seen["url"]


async def test_404_is_no_record_not_an_error(monkeypatch):
    monkeypatch.setenv("MDBLIST_API_KEY", "SENTINELKEY")
    async with _client(lambda r: httpx.Response(404, json={})) as client:
        assert await mdblist.fetch_ratings("tt0111161", client=client) is None


@pytest.mark.parametrize("imdb_id", ["", "nope", "tt", "1234567", None, 12345])
async def test_malformed_imdb_id_raises_before_any_request(imdb_id):
    def handler(request):
        raise AssertionError("must not issue a request for a malformed id")

    async with _client(handler) as client:
        with pytest.raises(ValueError):
            await mdblist.fetch_ratings(imdb_id, client=client)


# ---------------------------------------------------------------------------
# key leakage -- MDBList authenticates by query parameter
# ---------------------------------------------------------------------------

async def test_http_error_never_exposes_the_key(monkeypatch):
    monkeypatch.setenv("MDBLIST_API_KEY", "SUPERSECRET999")
    async with _client(lambda r: httpx.Response(401, json={"error": "bad key"})) as client:
        with pytest.raises(ProviderError) as excinfo:
            await mdblist.fetch_ratings("tt0111161", client=client)

    assert "SUPERSECRET999" not in str(excinfo.value)
    # `from None` matters: the original exception carries the unredacted URL, and a
    # traceback would print it even though the message itself is clean.
    assert excinfo.value.__cause__ is None


async def test_transport_error_never_exposes_the_key(monkeypatch):
    monkeypatch.setenv("MDBLIST_API_KEY", "SUPERSECRET999")

    def handler(request):
        raise httpx.ConnectError("connection failed", request=request)

    async with _client(handler) as client:
        with pytest.raises(ProviderError) as excinfo:
            await mdblist.fetch_ratings("tt0111161", client=client)

    assert "SUPERSECRET999" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None


async def test_non_json_body_never_exposes_the_key(monkeypatch):
    """An HTML error page can echo the query string back verbatim."""
    monkeypatch.setenv("MDBLIST_API_KEY", "SUPERSECRET999")
    body = "<html>bad request: ?apikey=SUPERSECRET999</html>"
    async with _client(lambda r: httpx.Response(200, text=body)) as client:
        with pytest.raises(ProviderError) as excinfo:
            await mdblist.fetch_ratings("tt0111161", client=client)

    assert "SUPERSECRET999" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
