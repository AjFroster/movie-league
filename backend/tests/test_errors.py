"""The exception-to-status mapping used by every route."""
import pytest
from fastapi import HTTPException

from app.errors import http_errors


def status_of(exc, **mapping):
    with pytest.raises(HTTPException) as caught:
        with http_errors(**mapping):
            raise exc
    return caught.value


def test_maps_an_exception_to_its_status():
    assert status_of(LookupError("gone"), LookupError=404).status_code == 404


def test_the_same_type_can_map_differently_in_different_routes():
    """A ValueError is 409 when state rejects a request, 422 when input was never valid."""
    assert status_of(ValueError("taken"), ValueError=409).status_code == 409
    assert status_of(ValueError("bad"), ValueError=422).status_code == 422


def test_an_unmapped_exception_propagates_unchanged():
    with pytest.raises(RuntimeError):
        with http_errors(LookupError=404):
            raise RuntimeError("not mapped")


def test_a_keyerror_is_not_treated_as_a_lookup_failure():
    """KeyError subclasses LookupError, so `except LookupError` would report an internal
    bug to the caller as a 404 -- a wrong answer that looks like a correct one."""
    with pytest.raises(KeyError):
        with http_errors(LookupError=404):
            raise KeyError("a bug, not a missing league")


def test_an_httpexception_passes_through_with_its_own_status():
    """A permission check inside the block must keep its 403, not become a 404."""
    with pytest.raises(HTTPException) as caught:
        with http_errors(LookupError=404):
            raise HTTPException(status_code=403, detail="not yours")
    assert caught.value.status_code == 403


def test_a_subclass_does_not_map_to_its_base():
    """Exact matching, deliberately. Add the subclass to the mapping if you want it."""
    class MissingLeague(LookupError):
        pass
    with pytest.raises(MissingLeague):
        with http_errors(LookupError=404):
            raise MissingLeague("gone")


def test_the_detail_is_redacted():
    """The whole reason this is one helper: httpx messages carry the key."""
    leaky = ValueError("failed: https://www.omdbapi.com/?i=tt1&apikey=SUPERSECRET123")
    detail = status_of(leaky, ValueError=502).detail
    assert "SUPERSECRET123" not in detail


def test_nothing_is_raised_when_the_block_succeeds():
    with http_errors(LookupError=404):
        result = 1 + 1
    assert result == 2
