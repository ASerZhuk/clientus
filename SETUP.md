# SETUP

Stack: Next.js 16 (App Router, React 19, TS strict) · Astryx design system · TanStack Query · Zod · Serwist ·
FastAPI · SQLite (WAL) via SQLAlchemy 2 + Alembic · pywebpush (VAPID). No Supabase, Vercel, Cloudflare, Docker or external LLM.

```
api/        FastAPI app, Alembic migrations, pytest, worker (outbox -> Web Push), tenant CLI
web/        Next.js app (client PWA + owner cabinet), Vitest, Playwright
tenants/    one folder per studio: business.json + photos  (pipeline INPUT; the database is the runtime source)
deploy/     Caddyfile, nginx.conf, systemd units, backup.sh
scripts/    py.sh (CLI shim used by package.json), e2e-api.sh
```

## 1. Local run

Requirements: Python 3.12+ (tested on 3.14), Node 22+, pnpm 11, `sqlite3` CLI (backup only).

```sh
cp .env.example .env                                  # then edit (see §2)
python3 -m venv api/.venv && api/.venv/bin/pip install -r api/requirements-dev.txt
pnpm --dir web install
pnpm db:seed                                          # DEVELOPMENT/E2E ONLY: publishes 5 sample studios from web/e2e/fixtures/tenants (real studios live in tenants/) as previews: graphite, demo-tenant (auto), aqua-wash (wash), loft-beauty (beauty_studio), anna-nails (beauty_master)
pnpm dev:api                                          # http://127.0.0.1:8000   (docs: /api/docs)
pnpm dev:web                                          # http://localhost:3000/s/graphite
pnpm worker                                           # optional: push-notification worker
```

Sample owners (dev only): `owner@graphite.example`, `owner@demo-tenant.example`, password = `SEED_OWNER_PASSWORD`
(default `demo-owner-2026`). Cabinet: `/s/graphite/owner`.

Tests:

```sh
pnpm test:api      # pytest: 90 tests (concurrency, isolation, slots/timezones, business profiles, payments, assistants, outbox, pipeline)
pnpm test:web      # Vitest: formatting, timezone conversion, Zod schemas, ICS
pnpm --dir web typecheck
pnpm build && pnpm test:e2e   # Playwright: client books -> owner sees it -> time is occupied (mobile + desktop)
```
Playwright starts its own throwaway API (port 18100, temp data dir) and `next start` (13100). If Playwright's own
Chromium download is unavailable, point `PW_CHROMIUM=/path/to/chrome`.

## 2. Environment variables (`.env`, never committed)

| Variable | Meaning |
|---|---|
| `DATA_DIR` | folder with `app.db` (SQLite) and `media/` (all photos). Relative paths are relative to the repo root. **Back this up.** |
| `SECRET_KEY` | random 64 hex chars (`openssl rand -hex 32`). Signs re-issuable booking access tokens. Changing it invalidates unretrieved retries only; issued links keep working (only their hash is stored). |
| `COOKIE_SECURE` | `true` in production (HTTPS only cookies) |
| `PUBLIC_ORIGINS` | comma-separated site origins, e.g. `https://book.example.com` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY_PATH`, `VAPID_SUBJECT` | Web Push (see §3) |
| `INTERNAL_API_URL` | where Next.js reaches FastAPI server-side (`http://127.0.0.1:8000`) |
| `NEXT_PUBLIC_LIQUID_GL` | `1` enables the experimental real-glass lens on the hero button (default off, see ACCEPTANCE.md) |

Secrets exist only on the server: the browser talks to `/api/*` on its own origin and never sees a key.

## 3. VAPID keys (Web Push)

```sh
pnpm vapid:generate            # writes api data/vapid_private.pem (chmod 600), prints VAPID_PUBLIC_KEY=...
```
Put the printed public key into `.env` as `VAPID_PUBLIC_KEY`, set `VAPID_PRIVATE_KEY_PATH` and `VAPID_SUBJECT=mailto:you@domain`,
restart API and worker. Without keys the app stays honest: the UI says notifications are unavailable, jobs are marked `skipped: push_not_configured`,
and the calendar (.ics) fallback remains. Push on iPhone works only for a site installed to the Home Screen (iOS 16.4+); the UI explains this and never promises it in a plain Safari tab.

## 4. Production on a VPS (Ubuntu example)

```sh
sudo useradd -r -m -d /srv/clientus clientus
sudo -u clientus git clone <repo> /srv/clientus && cd /srv/clientus
sudo -u clientus python3 -m venv api/.venv && sudo -u clientus api/.venv/bin/pip install -r api/requirements.txt
sudo -u clientus pnpm --dir web install --frozen-lockfile && sudo -u clientus pnpm build
sudo -u clientus cp .env.example .env && sudo -u clientus nano .env      # DATA_DIR=/srv/clientus/data, COOKIE_SECURE=true, real SECRET_KEY...
sudo -u clientus mkdir -p data && pnpm db:migrate
sudo cp deploy/clientus-*.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now clientus-api clientus-web clientus-worker
```

**HTTPS reverse proxy**, either one:
* Caddy: copy `deploy/Caddyfile` to `/etc/caddy/Caddyfile`, set your domain, `sudo systemctl reload caddy` (certificates are automatic).
* Nginx: `deploy/nginx.conf` + `sudo certbot --nginx -d book.example.com`.

Both send `/api/*` (API + photos) to `127.0.0.1:8000` and everything else to Next.js `127.0.0.1:3000`, preserving the Host
(the API compares `Origin` with `X-Forwarded-Host`/`Host` for unsafe requests). Run uvicorn with `--proxy-headers` (already in the unit) so per-client rate limits use the real IP.

**Backups** — SQLite + photos live in `DATA_DIR`:
```sh
sudo crontab -u clientus -e   ->   15 3 * * *  DATA_DIR=/srv/clientus/data /srv/clientus/deploy/backup.sh
```
`backup.sh` uses `sqlite3 .backup` (safe while the API writes), archives `media/`, keeps 14 days. Restore: stop `clientus-api`/`clientus-worker`, copy `app-*.db` to `DATA_DIR/app.db`, untar `media-*.tar.gz` into `DATA_DIR`, start services. Copy backups off the server too.

**Updating**: `git pull && pip install -r api/requirements.txt && pnpm --dir web install --frozen-lockfile && pnpm build && pnpm db:migrate && sudo systemctl restart clientus-api clientus-web clientus-worker`.
Migrations are Alembic (`api/alembic/versions`); republishing studios never touches bookings.

## 4b. Selling, packages, custom domains, customer servers
See **SALES.md** (how a sale works, commands, message templates) and **OPERATOR.md**: `pnpm admin:create`, the `/admin` panel, plan limits, subscription lifecycle and how to connect a customer's own domain
(`deploy/Caddyfile` already contains the on-demand-TLS block; nginx needs one server block per domain).

## 5. Publishing a studio (summary; details in CLONE-IN-6-MINUTES.md)

```sh
pnpm tenant:new my-studio --name "My Studio" --type auto   # auto | wash | beauty_master | beauty_studio
pnpm tenant:validate my-studio
pnpm tenant:publish my-studio                    # preview (marked demo data, no notifications, noindex)
pnpm owner:create my-studio owner@mail.com --password-env OWNER_PW
pnpm tenant:verify my-studio --api http://127.0.0.1:8000 --web https://book.example.com
pnpm tenant:publish my-studio --activate         # goes live; demo rows are removed
```
Link for the owner: `https://book.example.com/s/my-studio/` (clients) and `/s/my-studio/owner` (cabinet).

## Dev shortcut
`sh scripts/dev-stack.sh` starts API (:8010), worker and the production web build (:3000) in the background; `sh scripts/dev-stack.sh stop` stops them.
