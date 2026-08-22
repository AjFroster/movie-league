"""Drive a real server through a whole season, then clean up after itself.

Different from the test suite on purpose. Those run in-process against an in-memory
database, so they never exercise the things that actually break a deployment: migrations
applying to a real file, the startup guard, uvicorn serving, CORS, JSON over the wire.

This boots the app the way production does and talks to it over HTTP.

    python -m scripts.smoke_test [--base-url URL]

With no --base-url it starts its own server on a throwaway database and stops it after.
Against a running instance it creates a league, drafts it, and deletes it -- but a crash
mid-run can leave one behind, so every league it makes is named with SMOKE_PREFIX and
--clean removes strays.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

SMOKE_PREFIX = "smoke-test-"
PLAYERS = ["Ann", "Bob", "Cal"]
ROUNDS = 2


class Failed(Exception):
    pass


def check(condition, message):
    if not condition:
        raise Failed(message)


def step(name):
    print(f"  {name:<52}", end="", flush=True)


def ok(detail=""):
    print(f"ok {detail}")


def run_journey(base):
    client = httpx.Client(base_url=base, timeout=20)

    step("health")
    r = client.get("/api/health")
    check(r.status_code == 200 and r.json()["status"] == "ok", f"health said {r.status_code}")
    ok()

    name = f"{SMOKE_PREFIX}{uuid.uuid4().hex[:8]}"
    step("create a league")
    r = client.post("/api/leagues", json={"name": name, "year": 2027, "players": PLAYERS,
                                          "rounds": ROUNDS, "pick_seconds": 0,
                                          "visibility": "private"})
    check(r.status_code == 201, f"create said {r.status_code}: {r.text[:200]}")
    league = r.json()["league_id"]
    ok(f"id={league}")

    try:
        step("open the draft")
        r = client.post(f"/api/leagues/{league}/draft/start")
        check(r.status_code == 200, f"start said {r.status_code}: {r.text[:200]}")
        check(len(r.json()["order"]) == len(PLAYERS), "draft order is the wrong size")
        ok(f"order={','.join(r.json()['order'])}")

        step("draft every slot")
        picked = []
        for n in range(len(PLAYERS) * ROUNDS):
            state = client.get(f"/api/leagues/{league}/draft").json()
            clock = state["on_the_clock"]
            check(clock is not None, f"nobody on the clock at pick {n + 1}")
            r = client.post(f"/api/leagues/{league}/draft/pick",
                            json={"player": clock["player"], "tmdb_id": 900000 + n,
                                  "title": f"Smoke Film {n}"})
            check(r.status_code == 200, f"pick {n + 1} said {r.status_code}: {r.text[:200]}")
            picked.append(clock["player"])
        ok(f"{len(picked)} picks")

        step("the draft snakes")
        first_round, second_round = picked[:len(PLAYERS)], picked[len(PLAYERS):]
        check(first_round == list(reversed(second_round)), f"not a snake: {picked}")
        ok()

        step("the board reports complete")
        state = client.get(f"/api/leagues/{league}/draft").json()
        check(state["status"] == "complete", f"status is {state['status']}")
        check(state["picks_made"] == state["total_picks"], "picks_made != total_picks")
        ok()

        step("a watch moves the standings")
        before = {r["owner"]: r["total"]
                  for r in client.get(f"/api/leagues/{league}/leaderboard").json()}
        r = client.post(f"/api/leagues/{league}/movies/{PLAYERS[0]}/1/watch",
                        json={"viewer": PLAYERS[0], "watched": True})
        check(r.status_code == 200, f"watch said {r.status_code}: {r.text[:200]}")
        after = {r["owner"]: r["total"]
                 for r in client.get(f"/api/leagues/{league}/leaderboard").json()}
        check(after[PLAYERS[0]] == before[PLAYERS[0]] + 5,
              f"own watch scored {after[PLAYERS[0]] - before[PLAYERS[0]]}, expected 5")
        ok("+5")

        step("the backup carries the draft")
        r = client.get("/api/export")
        check(r.status_code == 200, f"export said {r.status_code}")
        exported = next((lg for lg in r.json()["leagues"] if lg["name"] == name), None)
        check(exported is not None, "the league is missing from the archive")
        check(sum(1 for e in exported["entries"] if e["pick_number"] is not None)
              == len(PLAYERS) * ROUNDS, "pick numbers missing from the archive")
        ok()

        step("settle the season")
        r = client.post(f"/api/leagues/{league}/freeze")
        check(r.status_code == 200 and r.json()["frozen_at"], "freeze did not stick")
        ok()
    finally:
        step("delete the league")
        r = client.delete(f"/api/leagues/{league}")
        if r.status_code == 204:
            ok()
        else:
            print(f"LEFT BEHIND (status {r.status_code})")

    step("it is really gone")
    check(client.get(f"/api/leagues/{league}/draft").status_code == 404, "league still readable")
    ok()
    client.close()


def clean_strays(base):
    client = httpx.Client(base_url=base, timeout=20)
    leagues = client.get("/api/leagues").json()
    strays = [lg for lg in leagues if lg["name"].startswith(SMOKE_PREFIX)]
    for lg in strays:
        client.delete(f"/api/leagues/{lg['id']}")
        print(f"  removed stray {lg['name']}")
    print(f"  {len(strays)} stray league(s) removed")
    client.close()


def boot_own_server(db_path):
    """A real uvicorn on a real file database, migrations and all."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}",
           "CORS_ORIGIN": "http://localhost:5173"}
    # Local identity: one user, permissions still enforced. Set empty rather than removed,
    # because main.py calls load_dotenv() and backend/.env would put CLERK_ISSUER back --
    # load_dotenv does not override a variable that is already present.
    env["CLERK_ISSUER"] = ""
    env["CLERK_JWKS_URL"] = ""

    root = Path(__file__).resolve().parent.parent
    print("  applying migrations", end="", flush=True)
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                            cwd=root, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise Failed(f"alembic failed:\n{result.stderr[-800:]}")
    print(" ok")

    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app",
                               "--port", "8111", "--log-level", "warning"],
                              cwd=root, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    base = "http://127.0.0.1:8111"
    for _ in range(60):
        if server.poll() is not None:
            raise Failed(f"server exited early:\n{server.stdout.read()[-800:]}")
        try:
            httpx.get(f"{base}/api/health", timeout=1)
            return server, base
        except httpx.HTTPError:
            time.sleep(0.5)
    server.terminate()
    raise Failed("server never became healthy")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", help="run against a server that is already up")
    parser.add_argument("--clean", action="store_true",
                        help="delete leftover smoke leagues and exit")
    args = parser.parse_args()

    server = None
    tmp = None
    try:
        if args.base_url:
            base = args.base_url.rstrip("/")
            print(f"target: {base}")
        else:
            tmp = tempfile.TemporaryDirectory()
            db = Path(tmp.name) / "smoke.db"
            print(f"target: a fresh server on {db}")
            server, base = boot_own_server(db)

        if args.clean:
            clean_strays(base)
            return 0

        run_journey(base)
        print("\nsmoke test passed")
        return 0
    except Failed as e:
        print(f"\nFAILED: {e}")
        return 1
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)
        if tmp:
            tmp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
