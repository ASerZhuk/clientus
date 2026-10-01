# Operator handbook (you, running the platform)

One person can run this: everything below is either a click in the panel or one command.

## 1. First setup
```sh
OPERATOR_PW='a long password (12+ chars)' pnpm admin:create you@mail.com --password-env OPERATOR_PW
```
Open `https://<your platform domain>/admin` and sign in (session 12 h, separate from studio owners, `SameSite=Strict`, CSRF-protected, 6 attempts / 10 min).
Set in `.env`: `PLATFORM_NAME`, `PLATFORM_URL` (what «Работает на …» says and links to), `PLATFORM_HOSTS` (your platform domain), `PLATFORM_IPS` (your server's IP for DNS checks), `INTERNAL_TOKEN` (random, the same for API and web).

## 2. Studio lifecycle (one-time sales, no subscriptions)
```
sample (preview) ──tenant:handover / «Боевая»──► live (lifetime)
```
| State | Customers | Owner cabinet |
|---|---|---|
| preview | can book, demo data, no notifications, noindex | full |
| live | full | full |
| suspended (by you) | site visible, **booking disabled** (message + phone) | **read-only** |
| disabled | 404 | — |

Activation never starts a trial and never expires (`TRIAL_DAYS=0`). Suspension is a manual switch (panel or `pnpm plan:set my-studio --suspend` / `--resume`), e.g. for a chargeback or an abuse case.
The date-based machinery (trial, paid periods, grace) is still in the code for the day you add subscriptions: set `TRIAL_DAYS` or use `--paid-days`; nothing uses it by default.
Everything else is in **SALES.md**: `pnpm tenant:sample`, `tenant:handover`, `tenant:export`.

## 3. Packages
`standard` 3 500 ₽ (branding shown) · `domain` 4 000 ₽ (own domain, branding shown) · `self_hosted` 7 000 ₽ (own server, branding hidden). Defined in `api/app/plans.py`, overridable with `PLANS_FILE`.
There are **no usage limits**. The plan gates only two things: own domains (`standard` refuses `domain:add` unless `--force`) and the «Работает на …» line (hidden only for `self_hosted`).
The panel's «Продано на» tile is the sum of package prices of live studios.

## 4. Customer domains (manual, on request)
1. Customer sends `book.customer.ru` and, at their registrar, adds an **A record → your server's IP** (`PLATFORM_IPS`).
2. You add it: panel → studio → «Свои домены», or `pnpm domain:add my-studio book.customer.ru` (plan must include a custom domain, or `--force`).
3. `pnpm domain:verify book.customer.ru` (or «Проверить» in the panel) checks the DNS; `--force` activates without proof.
4. Caddy issues the HTTPS certificate on the first visit, **only** for domains the API lists (`/api/internal/tls-allowed`). Check: `pnpm tenant:verify my-studio --web https://book.customer.ru --custom`.
5. On that domain the studio lives at the root (`/`, `/services`, `/my`, `/owner`); its install icon/manifest scope is `/`. The domain can never reach other studios, `/admin` or internal endpoints (404). The `https://<platform>/s/<slug>/` address keeps working.
Remove: `pnpm domain:remove book.customer.ru`. `pnpm domain:list` shows all.

## 5. Support actions (panel → studio)
* **Owner** — create or reset the owner's password (shown once, never stored in clear).
* **Войти в кабинет** — opens the owner's cabinet in a new tab for 2 hours; audited.
* **Журнал** — every plan/status/domain/owner/impersonation action with the actor and time.

## 6. Not automated yet (stage 3 of the plan)
Taking payments for subscriptions (you mark periods as paid by hand), self-service sign-up and domain setup, online prepayment by studio customers (ЮKassa of the studio), self-hosted installer and licence keys.
