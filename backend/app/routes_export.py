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

from .auth import CurrentUser
from .db import porting, repo
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
def get_archive(user: str = CurrentUser):
    """Your leagues, in one restorable file. This is the backup.

    Scoped to the caller. Before accounts existed this route dumped every league in the
    database to anyone who asked -- owner ids, player names and all -- because the Stage 2
    audit only inspected mutating routes and a GET that reads everything did not look like
    one. A backup is *your* data; the whole database is not yours to download.
    """
    with session_scope() as session:
        # scope="mine": a backup is the data you own, not every public league you can read.
        mine = [lg["id"] for lg in repo.list_leagues(session, user_id=user, scope="mine")]
        payload = porting.archive([porting.dump_league(session, i) for i in mine])
    return _download(payload, f"movie-league-backup-{date.today().isoformat()}.json")


@router.get("/leagues/{league_id}/export")
def get_league_archive(league_id: int, user: str = CurrentUser):
    """One league, same format, so a single season can be shared or archived alone.

    Members only, even for a public league. Public grants reading the standings; an archive
    additionally carries every account id that has claimed a slot, which is not the same
    thing and should not ride along with a shared link.
    """
    with session_scope() as session:
        try:
            member = repo.is_member(session, league_id, user)
        except LookupError:
            member = False
        # One answer for "does not exist" and "not yours", deliberately: distinguishing
        # them would let anyone enumerate which league ids are real.
        if not member:
            raise HTTPException(status_code=404, detail="No such league.")
        league = porting.dump_league(session, league_id)
        payload = porting.archive([league])
        name = league["name"]
    return _download(payload, f"{_slug(name)}-{date.today().isoformat()}.json")
