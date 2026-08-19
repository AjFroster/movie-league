"""Keeps provider secrets out of error strings, logs, and HTTP response bodies.

Why this module exists: OMDb offers no header-based auth -- its key MUST travel as a
`?apikey=` query parameter. httpx puts the full request URL into HTTPStatusError and
RequestError messages, and app/main.py surfaces provider failures to HTTP clients via
`detail=str(e)`. Without redaction, an invalid-key 401 from OMDb would return the OMDb
API key in a 502 response body and print it into the uvicorn traceback. HANDOFF.md
records that an API-key-in-logs bug was already fixed once in this project.

ProviderError lives here rather than in a separate errors module on purpose: it is the
exception type whose message is redacted *at construction*, so a call site physically
cannot forget to redact. Keeping the guarantee and the mechanism in one file is what
makes that guarantee auditable.
"""
import os
import re

SECRET_ENV_VARS = ("OMDB_API_KEY", "TMDB_API_KEY")
REDACTED = "***REDACTED***"
_MIN_SECRET_LEN = 4

# Matches ?apikey=... / &api_key=... / &key=... regardless of whether the value is
# currently present in the environment (e.g. the key was rotated since the call).
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:apikey|api_key|key)=)[^&\s\"'<>]+")


def redact_secrets(text: str) -> str:
    """Return `text` with any provider secret replaced by REDACTED.

    Two independent layers, because either one alone has a hole:
      1. Substring-replace the live values of SECRET_ENV_VARS (catches a key that
         appears anywhere, including in a header dump or a JSON body).
      2. Regex-replace the value of any apikey/api_key/key query parameter (catches a
         key that is no longer in the environment).
    """
    out = str(text)
    for name in SECRET_ENV_VARS:
        value = os.environ.get(name)
        if value and len(value) >= _MIN_SECRET_LEN:
            out = out.replace(value, REDACTED)
    return _QUERY_SECRET_RE.sub(r"\1" + REDACTED, out)


class ProviderError(Exception):
    """An upstream provider failure whose message is redacted at construction time.

    Always raise this with `from None` when re-raising an httpx error, so the original
    (unredacted) exception is not chained into the printed traceback:

        except httpx.HTTPError as e:
            raise ProviderError(str(e), provider="omdb") from None
    """

    def __init__(self, message: str, *, provider: str = "") -> None:
        self.provider = provider
        super().__init__(redact_secrets(str(message)))
