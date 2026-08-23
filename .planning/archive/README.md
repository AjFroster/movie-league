# Archive

A record of what was done, not a description of what exists.

These are the artifacts of a GSD milestone that finished on 19 August 2026: three phases
covering the UI redesign, live API enrichment, and the scoring formula. They are accurate
about that work and were never updated afterwards, which is fine for a record and misleading
for a description. Moving them here is what makes the difference visible.

| File | What it is |
|---|---|
| `ROADMAP.md` | The three phases of that milestone, all complete |
| `REQUIREMENTS.md` | The requirements those phases were checked against |
| `STATE.md` | GSD workflow state, frozen at the moment the milestone ended |
| `DRAFT-UI-PROMPT.md` | The design brief that produced the draft board |
| `phases/` | Per-phase plans and summaries |

**`../TODO.md` is the live roadmap.** Everything after 19 August — accounts, public and
private leagues, theming, the live draft, CI, the test layers — is recorded there.

## What used to be here

`codebase/` held eight generated documents describing the architecture: `ARCHITECTURE.md`,
`STACK.md`, `STRUCTURE.md`, `TESTING.md`, `CONVENTIONS.md`, `CONCERNS.md`, `INTEGRATIONS.md`
and `REVIEW.md`. They were generated on 8 July and never regenerated, and by August they
documented `app/storage.py` (deleted), called `league_data.json` the "sole persistent data
store" (it is SQLite now), and mentioned Clerk, SQLAlchemy, Alembic, the draft and polling
exactly zero times between them.

They were deleted rather than regenerated. A generated snapshot with nothing keeping it
current is wrong again within weeks, and wrong documentation costs more than none: it is
read first and believed. This project documents itself in comments next to the code, which
cannot drift from what it describes.

`git log -- .planning/codebase/` has them if they are ever wanted back.
