# Cloud Run image. Build context is backend/:
#     gcloud run deploy movie-league --source backend --region <region>
FROM python:3.12-slim

# Pinned to 3.12 for the same reason CI is: a new Python release should not be able to
# change what runs in production without anyone editing a file.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not re-resolve the whole tree on every build.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Cloud Run injects PORT and expects the container to listen on it; 8080 is its default
# and a sane fallback for `docker run` locally.
#
# `exec` so uvicorn becomes PID 1 and receives SIGTERM directly. Without it the shell is
# PID 1, swallows the signal, and every deploy waits out the 10-second kill timeout.
#
# Migrations are NOT run here. Cloud Run can start several instances at once, and several
# `alembic upgrade head` racing on one database is how you get a half-applied schema. Run
# it once, by hand, before the first deploy -- see .planning/hosting.md.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
