"""Turning domain exceptions into HTTP responses."""
import builtins
from contextlib import contextmanager

from fastapi import HTTPException

from .redaction import redact_secrets


@contextmanager
def http_errors(**mapping: int):
    """Map exception types to status codes for the block.

        with http_errors(LookupError=404, ValueError=409):
            repo.make_pick(...)

    The codes stay at the call site because they are part of what a route promises, and
    they are not uniform: a ValueError is 409 when the draft's state rejects a request and
    422 when the input was never valid. A single global handler would have to flatten that.

    Redaction is not optional. httpx puts the full request URL in its messages and OMDb
    authenticates by query parameter, so an unredacted detail leaks the key. `from None`
    suppresses the chain for the same reason: the original exception is not redacted.

    HTTPException passes through untouched, so a permission check inside the block keeps
    its own status.

    Scope is domain exceptions -- the builtins the repo layer raises. Provider failures
    (ProviderError, httpx.HTTPError -> 502) stay as explicit handlers: they are an upstream
    outage rather than a rejected request, and folding them in here would hide that.

    Matching is by EXACT type, not by subclass. `except LookupError` also catches KeyError
    and IndexError, so an internal bug would have been reported to the caller as a 404 --
    a wrong answer that looks like a correct one. The app raises only the base types, so
    nothing legitimate is missed and real bugs surface as 500s.
    """
    types = tuple(getattr(builtins, name) for name in mapping)
    try:
        yield
    except HTTPException:
        raise
    except types as e:
        status = mapping.get(type(e).__name__)
        if status is None:
            raise
        raise HTTPException(status_code=status, detail=redact_secrets(str(e))) from None
