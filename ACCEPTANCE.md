# ACCEPTANCE — what was actually run (2026-09-29, Linux, Python 3.14, Node 22, Chromium 1234)

## Automated checks (all green at the end of the session)
| Suite | Result |
|---|---|
| `pytest` (api) | **90 passed** |
| `vitest` (web) | **15 passed** |
| `tsc --noEmit` (app + service worker) | clean |
| `next build` | OK |
| Playwright (Chromium, iPhone-14 profile + desktop 1280px) | **12 passed** (client/owner flow, wrong password, deep links, desktop, beauty studio with master choice, private master, car wash, salon owner schedule, custom domain in a real browser, domain isolation, branding by plan, operator suspend/resume) |
| `tenant:verify` against a running stack, `graphite` and `demo-tenant` | 18/18 checks each |

Backend tests by requirement: parallel booking of one resource/time — exactly one wins (service level and two parallel HTTP requests: `201` + `409`);
the UNIQUE `(resource_id, cell)` index rejects an overlap even when the application check is bypassed; two posts; multi-day occupancy;
post block shares the table with bookings; failed reschedule keeps the original row and cells; Idempotency-Key replay returns the same booking and the same access token
(only its hash is stored); price/duration/tenant/status in the client body → 422; historical price survives a service price edit; payments, refunds (cannot exceed paid), stats (visits ≠ completed ≠ money received ≠ scheduled value);
tenant isolation (owner of A cannot read/change B's booking, cookie is path-scoped, token is bound to its studio, ORM session filters every query and refuses foreign writes, composite FKs reject cross-tenant rows);
CSRF + Origin check, cookie flags (HttpOnly, SameSite=Lax), rate limits (login, booking, atomic counters); client assistant cannot reach owner intents or client data, owner assistant changes nothing
(rows counted before/after), capability objects have no writer methods; intent parsing tested separately (examples, dates, ambiguity → clarifying question); outbox: jobs written with the booking, dedupe, preview sends nothing,
lease is exclusive between workers and expires, cancel skips reminder, move replaces reminder, dead subscription disabled, transient failure retried with backoff, no VAPID → honest `skipped`; slots: weekly hours, exceptions, timezone day boundaries, DST-gap day (23 h), lead time, horizon;
pipeline: validation messages, preview → activation, re-publish keeps bookings/owner photos/owner edits (`--force` overrides), the three gallery actions touch only their own photo, upload re-encoding.

Playwright flow: client picks a service → date → time → contact → confirms → sees details; "Моя запись" shows it from the on-device token; a second visitor sees that day marked unavailable
(2-day job in the single suitable post); owner logs in, finds the booking in the week view, opens it and marks the car accepted; wrong password shows an error; manifests/deep links belong to the right studio; 404 for unknown slug.

## Business profiles (stage 1 of the product plan)
Four profiles on one engine: `auto`, `wash`, `beauty_master`, `beauty_studio` (see CLONE-IN-6-MINUTES.md). Verified by tests: per-master weekly hours and union of moments; resolution order of exceptions (own day off / studio holiday / extra shift on a closed day);
booking checks the chosen master's hours, «любой свободный» picks the master who works; per-master price and duration are snapshotted into the booking and occupy the right span; masters are public only where customers choose; the API rejects `resource_id`
where the profile forbids it and requires a car only where the profile asks; owner endpoints for masters (description, photo, own schedule, days off) and per-master offers are refused for profiles without the feature; the private-master profile is limited to one resource; starter kits of all four types validate and publish;
assistant lists masters only in profiles where they are public. In the UI (Playwright): the sheet gets a «Выберите мастера» step (5 steps) only for studios, salon forms have no car fields, wash keeps the car requirement, vocabulary («бокс», «мастер») follows the profile.
Not done yet (later stages of the plan): choosing/changing the type in a self-service wizard, per-profile visual themes beyond accent/hero proportions/section order, custom domains, super-admin, billing, self-hosted installer, online prepayment.

## Platform layer (stage 2 of the product plan): plans, domains, operator panel
Verified by tests: the subscription state machine (preview / trial / active / past_due with 7-day grace / suspended / disabled, paid period beats trial, manual suspend wins); a suspended studio refuses customer bookings (`402`), its cabinet is read-only but can be read and left; grace period still books;
plan limits for resources and monthly bookings enforced for customers **and** owners (`PLANS_FILE` overrides); branding depends on the plan; domain normalisation (rejects IPs, ports, single labels, platform hosts), plan gate, uniqueness, DNS check, only *active* domains resolve;
`/api/internal/host` needs the token and `/api/internal/tls-allowed` answers only from loopback and only for served domains (a disabled studio's domain is refused); operator login (own accounts, `SameSite=Strict`, CSRF, Origin check, rate limit, studio owners are not operators),
overview/subscription/status/owner-reset/impersonation/domain endpoints and the audit log; a generated owner password works for its own studio only; CLI `admin:create`, `domain:*`, `plan:set`, `tenant:list`.
In a real browser (Chromium with `*.test` mapped to localhost): a customer domain serves the studio at the root with clean links, its manifest has scope `/`, a full booking works there, `/s/<other>`, `/admin` and unknown hosts return 404, the operator panel logs in, suspends a live studio (customers see the notice, the owner is read-only) and resumes it.
**Not verified:** a real domain with a real certificate (Caddy on-demand TLS was not run, no DNS/server), `tenant:verify --custom` against a live domain, service-worker behaviour on a custom domain on a device, prices in `plans.py` (placeholders). The Next.js log shows harmless "destination stream closed early" errors when a browser aborts a proxied image request.

## One-time sales model (packages, sample → handover → export)
The product was simplified to the sales model of the owner: three one-time packages (`standard` 3 500 ₽, `domain` 4 000 ₽, `self_hosted` 7 000 ₽), **no usage limits**, activation is lifetime (no trial), «Работает на …» is hidden only for `self_hosted`. Migration 0004 maps old tier names.
`tenant:sample` builds a validated preview for a prospect in one command (optionally from his photo folder); `tenant:handover` makes it live, creates the owner and prints the customer message; `tenant:export` builds a package for the customer's own server.
Verified by tests: the export contains only that studio (database rows, photos, owner with the same password hash, bookings; no other studio's names or emails anywhere in the archive; no dev files, no operator/session/audit data), foreign-key and integrity checks pass,
`.env` has fresh secrets, is readable by both a shell and systemd, and disables the operator panel; the exported database boots as an independent installation (the owner logs in with the old password, history is intact, branding is hidden, the domain resolves, a new booking works, the other studio is gone);
export refuses preview studios, invalid domains and unknown studios; sample/handover workflow with real photos and CLI guards; lifetime activation and opt-in trials.
By hand: the exported web source was built (`next build`) outside the repository, then the exported package was run as a customer would (API + web + Host header of the customer domain): studio at the root, `/admin` and `/api/admin` return 404, other studios unreachable, owner login works, no branding.
**Not verified:** `install.sh` on a clean Ubuntu/Debian server (only `sh -n` syntax check; a full `pnpm install` could not be completed here because the npm registry timed out), Caddy certificate issuance, the systemd units on a real host, push keys on a customer server.

## Design vs. the reference (https://studio-booking-theta.vercel.app/s/graphite/)
Screens were compared side by side in a mobile viewport and the UI was rebuilt to that language: header with round logo + profile icon, inset rounded hero card with glass «Записаться ↗», title + tagline, three info tiles,
«Запись в студию» card with halftone glow and accent pill, helper card, address/hours card, «Услуги» panel with «Все услуги →», vertical «Работы студии», install card, glass pill bottom navigation, round sparkle FAB,
booking as a bottom sheet with «Шаг N из 4» progress, «Услуги и цены», «Здесь будет ваша запись», profile and install pages, Inter font (self-hosted).
Deliberate differences: the reference's «Запись с ИИ» is called **«Помощник записи»** here because the assistant is deterministic (no LLM, as required); no e-mail magic-link login on the profile page (it links to «Моя запись» and the owner cabinet);
prices have no «от» variant. Not compared pixel-for-pixel; desktop layout is the same single column.

## Manually verified (screenshots of mobile viewport)
Home (hero, info cards, prices, booking card, gallery, contacts), owner schedule / booking sheet / studio settings. Russian Astryx strings via `ru-RU` locale. Pipeline run end to end:
`tenant:new → validate → publish (preview) → activation refused without owner → owner:create → verify → --activate → republish`. `backup.sh` produced a valid, integrity-checked copy.

## NOT verified (be sure to test before relying on it)
* **Real devices.** No iPhone/Android was available: install to Home Screen, standalone display, splash screens, safe-area/keyboard behaviour, and real-Safari quirks are **untested**. Only Chromium (headless) was used.
* **Web Push delivery.** No VAPID keys in this environment and no real push endpoint. Verified: key generation, outbox logic with a fake sender, honest UI states. **Not verified:** an actual notification arriving on a phone (and iOS requires the installed PWA).
* **VPS deployment.** Nothing was deployed (no server/credentials, no SSH). systemd units, Caddy/nginx configs are written but were not run on a server; HTTPS/certificates untested.
* **liquid-gl real glass.** Integrated (`web/src/components/ui/liquid.ts`, hero button only, snapshot limited to `#hero`, label stays DOM text) but in headless software WebGL it rendered as a black box, and no GPU device was available,
  so it is **off by default** (`NEXT_PUBLIC_LIQUID_GL=1` to try). The default is CSS glass (`backdrop-filter`). liquid-gl ignores `position: fixed`, so the bottom navigation uses CSS glass regardless.
* Accessibility with a screen reader; contrast audit beyond Astryx defaults; performance budgets; load testing.
* `astryx docs tokens` was not read (tokens used: `--color-*` overrides in `web/src/lib/theme.ts`); `astryx doctor` warns that no theme is wired via `package.json` (theme is provided at runtime by `<Theme>`).

## Deviations from the brief (deliberate)
* `IMPLEMENTATION-PLAN.md` was a short brief without stages 1–8, without GRAPHITE data and without Astryx commands; stages were defined by me, GRAPHITE Detailing demo data is invented (`tenants/graphite`).
* **shadcn/ui and Vaul were not added**: Astryx already ships `BottomSheet`, `AlertDialog`, forms, layout; a second token system was avoided. One sheet implementation is used everywhere (`AppSheet` → Astryx `BottomSheet`).
* Demo photos of `graphite` (hero + 3 works) are the sample images served by the reference site https://studio-booking-theta.vercel.app; `demo-tenant` and `tenant:new` use generated placeholder art (`services/placeholder_art.py`). Real photos replace them by file name.
* Instants are stored as UTC epoch minutes; occupancy cells are 15 minutes (slot step must be a multiple of 15).
* `tenant_id` filtering is done by SQLAlchemy session events + composite FKs (SQLite has no RLS/EXCLUDE), as agreed.
* Node `next start` (no `output: standalone`) is used; Next.js proxies `/api` at runtime only for dev/single-origin use — production proxies straight to FastAPI.

## Known limits
Client access is a link kept in the browser (`localStorage`); clearing site data loses it (the owner can issue a new link from the booking sheet). Owner cookie is scoped per studio path, so one browser can hold sessions for several studios.
The owner password is set only via CLI (`owner:create`); there is no password-reset UI.
