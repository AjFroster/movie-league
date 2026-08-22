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

    Codes stay at the call site because they are not uniform: a ValueError is 409 when the
    draft's state rejects a request and 422 when the input was never valid.

    Matching is by EXACT type. `except LookupError` also catches KeyError, so an internal
    bug would reach the caller as a 404 -- a wrong answer that looks correct.

    HTTPException passes through, so a permission check inside the block keeps its status.
    Provider failures stay as explicit handlers: an upstream outage is not a rejected
    request.
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
