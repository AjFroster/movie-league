"""Downloading league data as a restorable archive.

Read-only by design. Restoring is `scripts/restore.py` rather than an endpoint: a restore
is rare, deliberate, and overwrites everything, and with no authentication in front of the
API yet, an endpoint that can replace every league would be the largest hole in the app.
Export is safe to expose because it only ever reads.
"""
import re
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .db import porting
from .db.session import session_scope

router = APIRouter(prefix="/api", tags=["export"])


def _slug(text: str) -> str:
    """League name -> a safe filename stem.

    Strict allowlist rather than escaping: this lands in a Content-Disposition header, and
    a league name is free text up to 120 characters. A name containing a quote or a CRLF
    would otherwise let a user inject response headers.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:60] or "league"


def _download(payload: dict, filename: str) -> JSONResponse:
    return JSONResponse(
        payload, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/export")
def get_archive():
    """Every league, in one restorable file. This is the backup."""
    with session_scope() as session:
        payload = porting.dump_archive(session)
    return _download(payload, f"movie-league-backup-{date.today().isoformat()}.json")


@router.get("/leagues/{league_id}/export")
def get_league_archive(league_id: int):
    """One league, same format, so a single season can be shared or archived alone."""
    with session_scope() as session:
        try:
            league = porting.dump_league(session, league_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        payload = porting.archive([league])
        name = league["name"]
    return _download(payload, f"{_slug(name)}-{date.today().isoformat()}.json")
