# Deferred Items — Phase 02: Live API Enrichment

Out-of-scope discoveries logged during execution, per the executor's scope-boundary rule
(fix only what the current task's changes directly touch; log the rest here instead).

## From 02-06 (Documentation + secret-hygiene guards)

- **README.md "Running locally" section still says `pip install -r requirements.txt`.**
  This project's `backend/.venv` was created by `uv` and has no `pip` (same fact this plan's
  new "Running the tests" section documents correctly for `requirements-dev.txt`). The
  "Running locally" section was not in 02-06-PLAN.md's Task 1 scope (which only specified
  edits to "Auto-fetching data", "Editing scores", and a new "Running the tests" section), so
  it was left untouched rather than fixed opportunistically. A correct replacement command
  would need to handle the case where `backend/.venv` does not yet exist on a fresh clone
  (`uv venv` first), which is a slightly bigger change than a one-line swap — worth a small
  follow-up plan or task rather than a same-task drive-by edit.
