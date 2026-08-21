"""Relational schema for leagues, drafts, rosters, and watches.

Written against SQLAlchemy rather than raw sqlite3 so the engine is a deployment choice
rather than an architectural one: `sqlite:///league.db` locally, `postgresql://...` on a
host, with the same models and queries. Plain SQLite cannot back multiple app instances --
each would get its own file -- so the ORM is what keeps that door open.

Two constraints here do work that application code previously had to get right by hand, and
previously got wrong:

  UNIQUE(league_id, tmdb_id)          one film cannot be drafted twice, enforced by the
                                      database even if two picks arrive simultaneously
  PRIMARY KEY(entry_id, player_id)    a watch is a row, so concurrent toggles by different
                                      players cannot overwrite each other

The old JSON store lost 3 of 4 simultaneous watch toggles because every write rewrote the
whole file from a stale read. Both problems are transactional, not schema-shaped, but the
constraints make the invariants explicit rather than implicit.
"""
from datetime import datetime, timezone

from sqlalchemy import (JSON, CheckConstraint, DateTime, Float, ForeignKey, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(DeclarativeBase):
    pass


# League lifecycle. A league is in exactly one of these at any time.
STATUS_SETUP = "setup"          # players named, draft not started
STATUS_DRAFTING = "drafting"    # order randomized, picks under way
STATUS_COMPLETE = "complete"    # every slot filled
STATUSES = (STATUS_SETUP, STATUS_DRAFTING, STATUS_COMPLETE)


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    year: Mapped[int] = mapped_column(Integer)
    rounds: Mapped[int] = mapped_column(Integer, default=6)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_SETUP)
    # The randomized snake order, as a list of player names. Stored rather than derived
    # because it is the one part of a draft that must not change once picking starts.
    draft_order: Mapped[list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # When set, the season is settled: enrichment leaves it alone and its scores stop
    # moving. Without this a finished league keeps recalculating from live APIs, so a
    # final standing quietly changes months after everyone agreed who won.
    frozen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None)

    players: Mapped[list["Player"]] = relationship(
        back_populates="league", cascade="all, delete-orphan", order_by="Player.id")
    entries: Mapped[list["Entry"]] = relationship(
        back_populates="league", cascade="all, delete-orphan",
        order_by="(Entry.player_id, Entry.round)")

    __table_args__ = (
        CheckConstraint(f"status IN {STATUSES}", name="ck_league_status"),
        CheckConstraint("rounds >= 1 AND rounds <= 30", name="ck_league_rounds"),
    )


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))

    league: Mapped[League] = relationship(back_populates="players")
    entries: Mapped[list["Entry"]] = relationship(
        back_populates="player", cascade="all, delete-orphan")
    watches: Mapped[list["Watch"]] = relationship(
        back_populates="player", cascade="all, delete-orphan")

    # Case-insensitive uniqueness is enforced in application code at setup time; the
    # constraint here catches the exact-duplicate case at the storage layer.
    __table_args__ = (UniqueConstraint("league_id", "name", name="uq_player_per_league"),)


class Entry(Base):
    """One drafted film on one player's roster, plus everything scored about it."""

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    round: Mapped[int] = mapped_column(Integer)
    pick_number: Mapped[int | None] = mapped_column(Integer, default=None)

    tmdb_id: Mapped[int | None] = mapped_column(Integer, default=None)
    title: Mapped[str | None] = mapped_column(String(300), default=None)
    # Stored rather than re-fetched: a roster renders on every page load, and TMDB should
    # not be called to draw a list of films that have not changed.
    poster_path: Mapped[str | None] = mapped_column(String(200), default=None)

    # Scoring inputs, all nullable: an undrafted or unreleased film has none of them.
    imdb: Mapped[float | None] = mapped_column(Float, default=None)
    letterboxd: Mapped[float | None] = mapped_column(Float, default=None)
    rt_crit: Mapped[float | None] = mapped_column(Float, default=None)
    rt_aud: Mapped[float | None] = mapped_column(Float, default=None)
    budget: Mapped[float | None] = mapped_column(Float, default=None)
    gross: Mapped[float | None] = mapped_column(Float, default=None)
    roi: Mapped[float | None] = mapped_column(Float, default=None)
    bo_rank: Mapped[int | None] = mapped_column(Integer, default=None)
    awards: Mapped[str | None] = mapped_column(Text, default=None)

    # Derived scores. Cached calculations, recomputed on every write -- never authoritative.
    rating_score: Mapped[float] = mapped_column(Float, default=0)
    financial_score: Mapped[float] = mapped_column(Float, default=0)
    penalties: Mapped[float] = mapped_column(Float, default=0)
    penalty_notes: Mapped[str] = mapped_column(Text, default="")
    watch_points: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)

    # Per-field provenance ({field: {origin, provider, at}}). Metadata about the row rather
    # than league data, and never queried relationally, so JSON is the honest shape.
    sources: Mapped[dict] = mapped_column(JSON, default=dict)

    league: Mapped[League] = relationship(back_populates="entries")
    player: Mapped[Player] = relationship(back_populates="entries")
    watches: Mapped[list["Watch"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan")

    __table_args__ = (
        # The draft guarantee: two players cannot end up with the same film, even if their
        # picks race. Previously this was an application-level check on a stale read.
        UniqueConstraint("league_id", "tmdb_id", name="uq_film_per_league"),
        UniqueConstraint("league_id", "player_id", "round", name="uq_slot_per_player"),
    )


class Watch(Base):
    """A single person having watched a single film.

    A row rather than a list on the entry: that is what makes two people ticking different
    boxes at the same moment safe, and what lets the leaderboard attribute a point to the
    watcher rather than the film's owner.
    """

    __tablename__ = "watches"

    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entry: Mapped[Entry] = relationship(back_populates="watches")
    player: Mapped[Player] = relationship(back_populates="watches")
