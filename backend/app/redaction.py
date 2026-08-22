"""Keeps provider secrets out of error strings, logs, and response bodies.

OMDb has no header auth, so its key must travel as `?apikey=`. httpx puts the full request
URL into its exception messages, so any unredacted provider error leaks the key.
"""
import os
import re

SECRET_ENV_VARS = ("OMDB_API_KEY", "TMDB_API_KEY", "MDBLIST_API_KEY")
REDACTED = "***REDACTED***"
_MIN_SECRET_LEN = 4
_QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:apikey|api_key|key)=)[^&\s\"'<>]+")


def redact_secrets(text: str) -> str:
    """Replace any provider secret in `text` with REDACTED.

    Both layers are needed: the substring pass catches a live key anywhere, including a
    header dump or JSON body, and the regex pass catches one that has since been rotated
    out of the environment.
    """
    out = str(text)
    for name in SECRET_ENV_VARS:
        value = os.environ.get(name)
        if value and len(value) >= _MIN_SECRET_LEN:
            out = out.replace(value, REDACTED)
    return _QUERY_SECRET_RE.sub(r"\1" + REDACTED, out)


class ProviderError(Exception):
    """An upstream failure, redacted at construction so a call site cannot forget.

    Raise with `from None` when re-raising an httpx error; chaining would put the
    unredacted original into the traceback.
    """

    def __init__(self, message: str, *, provider: str = "") -> None:
        self.provider = provider
        super().__init__(redact_secrets(str(message)))
