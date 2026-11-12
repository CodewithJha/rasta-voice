# 13 — Free-host deploy

- **Labels:** `area:app`, `day:3`, `deploy`
- **Owner:** Member B: app & realtime
- **Target day:** Day 3 (14–15 Nov 2026). A live URL makes the 14 Nov post better. If the host slips, the post still goes out with a note that the desk is in the repo, and you keep going until the URL works before the 15 Nov deadline.
- **Depends on:** issues 09 and 10, so the deployed UI is the rider toggle and the live slate, not the skeleton alone. The Docker build must still succeed if you point it at the skeleton, but don't open the PR until 09 and 10 are merged.

## Description

One free host, one process. Hugging Face Spaces (Docker SDK) is the default. Render's free web service is the backup if Spaces rejects the repo. Do not pay, and do not add a database.

`Dockerfile` at the repo root:

- `python:3.12-slim`
- Install Node only for the frontend build, or build the frontend in a first stage and copy `frontend/dist`.
- `pip install` the three Python packages from `requirements-dev.txt` is wrong for production (it pulls pytest). Install `gnani_client`, `backend`, and `benchmark` with `pip install` of those directories, plus the runtime deps already in their pyprojects. `benchmark` is imported only if you choose to ship the demo mix from there; the simulate route is self-contained, so the image does not need `benchmark` to boot. Leave it out of the image unless the image gets huge either way and you'd rather keep one Dockerfile simple. Prefer leaving it out.
- `npm ci && npm run build` in `frontend/`.
- Copy `frontend/dist` to a path the API serves.
- `CMD` runs `uvicorn rasta.main:app --host 0.0.0.0 --port 7860` (Spaces) or `$PORT` if you document Render. Pick one host and one port. Don't write both and leave the reader to guess. If you pick Spaces, add a `README.md` paragraph... no, don't bury host notes in the product README. Add `docs/DEPLOY.md` with the click path: create a public Space, SDK Docker, set secrets `GNANI_API_KEY`, `GNANI_MOCK`, `LLM_PROVIDER`, `GROQ_API_KEY` or `GEMINI_API_KEY`. Secrets are Space secrets, never `ENV` lines in the Dockerfile.

Static files: in `main.py`, mount `StaticFiles` at `/` **after** the API routes, with `html=True`, only when the dist directory exists. Check that `/api/health` still wins over the mount. A test uses `TestClient` against an app that has a temp dist with an `index.html`, gets HTML from `/`, and JSON from `/api/health`.

`GNANI_MOCK=1` must boot with no key, so the public Space is not a blank error before credits land. When the key is set, set `GNANI_MOCK=0` in the Space secrets and say so in `docs/DEPLOY.md`.

No analytics snippet. No third-party tracker.

## Files to touch

- `Dockerfile` (new)
- `.dockerignore` (new) — exclude `.venv`, `node_modules`, `benchmark/data/audio`, `.env`
- `docs/DEPLOY.md` (new)
- `backend/rasta/main.py` (static mount only, after the routers)
- `backend/tests/test_static.py` (new)

## Do not touch

`benchmark/` data, `frontend/src/*` except if the production build needs a `base` path. Spaces serves the app at `/`, so Vite's default base is correct. Don't add a rewrite.

## Input / output contract

`GET /api/health` → the JSON the skeleton already returns, on the deployed URL.

`GET /` → the built `index.html`.

The browser on the deployed origin calls `/api/...` on the same origin. Vite's dev proxy is irrelevant in prod. If the frontend hardcodes `http://127.0.0.1:8000`, remove that before you call this done. Today it uses relative `/api`, which is what you want. Don't "fix" it into an absolute URL.

## Acceptance criteria

- [ ] `docker build -t rasta .` succeeds. Run it if Docker is available. If Docker is not available in your environment, say so in the PR and still run a local `uvicorn` against the built dist.
- [ ] Container or local prod-mode serves `/` as HTML and `/api/health` as JSON.
- [ ] `POST /api/ingest/sample` on that server returns `customer_unreachable` when `GNANI_MOCK=1`.
- [ ] `docs/DEPLOY.md` lists the secrets by name and says not to commit them.
- [ ] The image has no `.env` file (`docker run --rm rasta ls -a | rg env` finds nothing, or you never `COPY .env`).
- [ ] The public URL is pasted at the top of `docs/DEPLOY.md` once the Space is up.

## How to test

```bash
docker build -t rasta .
docker run --rm -e GNANI_MOCK=1 -p 7860:7860 rasta
curl -s localhost:7860/api/health
curl -s -o /dev/null -w "%{http_code}\n" localhost:7860/
curl -s -X POST localhost:7860/api/ingest/sample
```

Open the site in a browser, run the canned drop, toggle noisy, and confirm the slate polls. That is the same check as issues 09 and 10, on the deployed origin.
