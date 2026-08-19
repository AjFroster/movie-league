import httpx

from app.redaction import REDACTED, ProviderError, redact_secrets


def test_httpx_error_string_would_leak_the_key_and_redaction_stops_it(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "SUPERSECRET123")

    def handler(request):
        return httpx.Response(401, json={"Response": "False", "Error": "Invalid API key!"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = client.get(
            "https://www.omdbapi.com/",
            params={"i": "tt0111161", "apikey": "SUPERSECRET123"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raw = str(exc)

    assert "SUPERSECRET123" in raw, "precondition: httpx really does embed the key"
    assert "SUPERSECRET123" not in redact_secrets(raw)
    assert REDACTED in redact_secrets(raw)
    assert "SUPERSECRET123" not in str(ProviderError(raw, provider="omdb"))


def test_redact_secrets_matches_apikey_query_param_with_no_env_var_set(monkeypatch):
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    out = redact_secrets("https://www.omdbapi.com/?i=tt1&apikey=leftover123&r=json")
    assert "leftover123" not in out
    assert REDACTED in out
    assert "i=tt1" in out
    assert "r=json" in out


def test_redact_secrets_matches_api_key_and_key_spellings_case_insensitively():
    assert redact_secrets("?API_KEY=abcd1234") == f"?API_KEY={REDACTED}"
    assert redact_secrets("&Key=abcd1234") == f"&Key={REDACTED}"
    assert redact_secrets("&KEY=abcd1234") == f"&KEY={REDACTED}"


def test_redact_secrets_leaves_ordinary_text_byte_identical(monkeypatch):
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    text = "Round 2: Super Girl scored 87 points, no secrets here."
    assert redact_secrets(text) == text


def test_redact_secrets_short_env_value_guard_does_not_over_redact(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "a")
    assert redact_secrets("banana") == "banana"


def test_redact_secrets_short_env_value_guard_handles_empty_string(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "")
    assert redact_secrets("banana") == "banana"


def test_provider_error_str_contains_no_secret(monkeypatch):
    monkeypatch.setenv("TMDB_API_KEY", "TMDBSECRET999")
    err = ProviderError("call failed: TMDBSECRET999 was rejected", provider="tmdb")
    assert "TMDBSECRET999" not in str(err)
    assert REDACTED in str(err)


def test_provider_error_exposes_provider_name():
    err = ProviderError("some failure", provider="omdb")
    assert err.provider == "omdb"
