import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .auth import verify_startup_configuration
from .db.session import init_db
from .routes_export import router as export_router
from .routes_leagues import router as leagues_router

app = FastAPI(title="Fantasy Movie League API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(leagues_router)
app.include_router(export_router)


@app.on_event("startup")
def _startup():
    """Create tables on first run. Alembic owns schema changes; this is bootstrap only."""
    # Before anything else: refuse to serve at all if this looks like a deployment with no
    # identity provider behind it. A startup crash is recoverable; silently treating every
    # request on the internet as the same trusted local user is not.
    verify_startup_configuration()
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
