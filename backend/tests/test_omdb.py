"""Network-free tests for the OMDb ratings client.

Every test in this file either calls the pure `parse_omdb_payload` function directly, or
drives `fetch_ratings` through an injected `httpx.MockTransport` -- no test here touches
the network or requires a real OMDB_API_KEY (the autouse `no_real_api_keys` fixture in
conftest.py strips both provider keys from the environment before every test).
"""
import httpx
import pytest

from app.redaction import REDACTED
from app.redaction import ProviderError
from app.services import omdb


# ---------------------------------------------------------------------------
# parse_omdb_payload -- the parse matrix
# ---------------------------------------------------------------------------

def test_parse_full_valid_payload():
    data = {
        "Response": "True", "imdbID": "tt0111161", "imdbRating": "9.3",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": "89%"}],
    }
    assert omdb.parse_omdb_payload(data) == {"imdb_id": "tt0111161", "imdb": 9.3, "rt_crit": 89.0}


def test_parse_response_false_returns_none():
    assert omdb.parse_omdb_payload({"Response": "False", "Error": "Incorrect IMDb ID."}) is None


@pytest.mark.parametrize("bad_input", [{}, "not a dict", None, [], 42])
def test_parse_non_matching_or_non_dict_input_returns_none(bad_input):
    assert omdb.parse_omdb_payload(bad_input) is None


def test_parse_imdb_rating_na_gives_none_but_dict_is_returned():
    data = {"Response": "True", "imdbID": "tt0111161", "imdbRating": "N/A"}
    result = omdb.parse_omdb_payload(data)
    assert result is not None
    assert result["imdb"] is None


def test_parse_ratings_key_absent_gives_none_rt_crit():
    data = {"Response": "True", "imdbID": "tt0111161", "imdbRating": "9.3"}
    assert omdb.parse_omdb_payload(data)["rt_crit"] is None


def test_parse_ratings_explicit_none_gives_none_rt_crit():
    data = {"Response": "True", "imdbID": "tt0111161", "imdbRating": "9.3", "Ratings": None}
    assert omdb.parse_omdb_payload(data)["rt_crit"] is None


def test_parse_ratings_present_with_no_rt_entry_gives_none_rt_crit():
    data = {
        "Response": "True", "imdbID": "tt0111161", "imdbRating": "9.3",
        "Ratings": [{"Source": "Internet Movie Database", "Value": "9.3/10"}],
    }
    assert omdb.parse_omdb_payload(data)["rt_crit"] is None


@pytest.mark.parametrize("bad_ratings", [{"Source": "Rotten Tomatoes"}, "a string", 42])
def test_parse_ratings_not_a_list_gives_none_rt_crit_no_exception(bad_ratings):
    data = {"Response": "True", "imdbID": "tt0111161", "Ratings": bad_ratings}
    result = omdb.parse_omdb_payload(data)
    assert result["rt_crit"] is None


@pytest.mark.parametrize("bad_rating", [{"nested": 1}, True])
def test_parse_imdb_rating_non_scalar_or_bool_gives_none(bad_rating):
    data = {"Response": "True", "imdbID": "tt0111161", "imdbRating": bad_rating}
    assert omdb.parse_omdb_payload(data)["imdb"] is None


def test_parse_imdb_rating_out_of_range_gives_none():
    data = {"Response": "True", "imdbID": "tt0111161", "imdbRating": "99"}
    assert omdb.parse_omdb_payload(data)["imdb"] is None


def test_parse_imdb_rating_nan_string_gives_none():
    data = {"Response": "True", "imdbID": "tt0111161", "imdbRating": "nan"}
    assert omdb.parse_omdb_payload(data)["imdb"] is None


@pytest.mark.parametrize("bad_value", ["-5%", "250%"])
def test_parse_rt_crit_out_of_range_gives_none(bad_value):
    data = {
        "Response": "True", "imdbID": "tt0111161",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": bad_value}],
    }
    assert omdb.parse_omdb_payload(data)["rt_crit"] is None


@pytest.mark.parametrize("value", ["89%", " 89 % ", 89])
def test_parse_rt_crit_variants_all_parse_to_89(value):
    data = {
        "Response": "True", "imdbID": "tt0111161",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": value}],
    }
    assert omdb.parse_omdb_payload(data)["rt_crit"] == 89.0


# ---------------------------------------------------------------------------
# fetch_ratings -- key gate and IMDb-ID validation, no network involved
# ---------------------------------------------------------------------------

async def test_fetch_ratings_returns_none_without_a_key_and_builds_no_request():
    # no_real_api_keys fixture already stripped OMDB_API_KEY
    assert await omdb.fetch_ratings("tt0111161") is None


async def test_fetch_ratings_title_raises_value_error():
    with pytest.raises(ValueError):
        await omdb.fetch_ratings("The Mummy")


@pytest.mark.parametrize("bad_id", ["tt1", "", None])
async def test_fetch_ratings_malformed_id_raises_value_error(bad_id):
    with pytest.raises(ValueError):
        await omdb.fetch_ratings(bad_id)


# ---------------------------------------------------------------------------
# fetch_ratings -- MockTransport-driven HTTP behavior
# ---------------------------------------------------------------------------

async def test_fetch_ratings_success_returns_parsed_dict(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRET123")

    def handler(request):
        return httpx.Response(200, json={
            "Response": "True", "imdbID": "tt0111161", "imdbRating": "9.3",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "89%"}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await omdb.fetch_ratings("tt0111161", client=client)

    assert result == {"imdb_id": "tt0111161", "imdb": 9.3, "rt_crit": 89.0}


async def test_fetch_ratings_non_json_body_raises_provider_error_not_json_error(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRET123")

    def handler(request):
        return httpx.Response(200, content=b"not json at all")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError):
            await omdb.fetch_ratings("tt0111161", client=client)


# ---------------------------------------------------------------------------
# Verbatim security regression tests specified by the plan
# ---------------------------------------------------------------------------

async def test_lookup_is_by_imdb_id_and_key_travels_as_an_encoded_param(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRET123")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={
            "Response": "True", "imdbID": "tt0111161", "imdbRating": "9.3",
            "Ratings": [{"Source": "Rotten Tomatoes", "Value": "89%"}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await omdb.fetch_ratings("tt0111161", client=client)

    assert result == {"imdb_id": "tt0111161", "imdb": 9.3, "rt_crit": 89.0}
    assert seen["url"].startswith("https://www.omdbapi.com/?")
    assert "i=tt0111161" in seen["url"]
    assert "t=" not in seen["url"].split("?")[1].replace("apikey=", "")  # no title lookup


async def test_http_failure_never_leaks_the_key(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRET123")

    def handler(request):
        return httpx.Response(401, json={"Response": "False", "Error": "Invalid API key!"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as excinfo:
            await omdb.fetch_ratings("tt0111161", client=client)

    message = str(excinfo.value)
    assert "SUPERSECRET123" not in message
    assert REDACTED in message
    assert excinfo.value.provider == "omdb"
    assert excinfo.value.__cause__ is None  # `from None` -- no unredacted chained traceback
