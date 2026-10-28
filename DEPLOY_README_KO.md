# SORT 5 Online Multiplayer v4.2 (30 missions)

## Scope
- Based on v4.1 engine, 6 cities / 30 missions, 60 mission-card images, 4-player online multiplayer (with AI filling seats).
- Existing base AI remains active by default. Experimental Bayesian inference and scheduler remain off unless explicitly enabled.
- Same Vercel + Upstash Redis deployment architecture as previous live Seoul build.
- Room information is persisted in Upstash with a 24-hour TTL. Do not reuse old browser room codes after upgrading; create a new room.
- This is an **online test candidate**, not a release whose live Vercel behavior has been verified.

## Deploy to existing GitHub repository
1. Keep a copy or tag of the existing working live version (rollback).
2. Place **the contents of this folder at the repository root** (not the ZIP file, not a nested folder). Replace `server.py`, `mission_rules.py`, `requirements.txt` and `static/`; ensure `static/assets/` has all images.
3. Commit and push to `main` (GitHub Desktop is preferable for uploading folders). Vercel deploys the connected repo automatically.
4. In Vercel project Settings → Environment Variables, confirm either `KV_REST_API_URL` + `KV_REST_API_TOKEN`, or `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`, are available in Production. Do not paste tokens into GitHub.
5. Check `<your-vercel-domain>/health` returns `"storage":"upstash"`. This only proves the environment variables are present, not that Redis commands succeed.
6. Create a new room and test on two devices, ideally with 2 humans + 2 AI. Then check Berlin #03 (offer), New York #02 (simultaneous setup), London #04 (number guess), Paris #02 (forced feedback).

## Safety and settings
- `SORT5_ALLOW_DEBUG` should be **unset** in Production. Public debug inspect is disabled by default.
- `SORT5_SCHEDULER` should remain unset/off unless conducting separate experiments.
- Keep any Bayesian experimental toggles disabled; see `server.py` for experimental flags.
- The full 30-mission browser E2E and production Upstash tests are not yet verified.
- Existing rooms may be incompatible with new game-state structures. Restart rooms after deployment.
- If production fails, roll back in Vercel Deployments to the previous working deployment.

## Local check
`python3 -m pip install -r requirements.txt`
`python3 -m pytest -q tests`
`python3 -m uvicorn server:APP --host 127.0.0.1 --port 8000`
Open `http://localhost:8000`.
