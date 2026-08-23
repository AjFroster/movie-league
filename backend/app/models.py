from pydantic import BaseModel


class Movie(BaseModel):
    owner: str
    round: int
    movie: str
    imdb: float | None = None
    letterboxd: float | None = None
    rt_crit: float | None = None
    rt_aud: float | None = None
    budget: float | None = None
    gross: float | None = None
    roi: float | None = None
    bo_rank: int | None = None
    awards: str | None = None
    who_watched: list[str] = []
    rating_score: float = 0
    financial_score: float = 0
    penalties: float = 0
    penalty_notes: str = ""
    watch_points: float = 0
    total: float = 0
    sources: dict[str, dict] = {}

