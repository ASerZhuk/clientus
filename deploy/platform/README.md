# Clientus platform server (prod + test on one VPS)

Next.js is built on your PC (`output: "standalone"`); the server only runs it. No Node dependencies are installed
and nothing is compiled on the server, so 2 GB RAM is enough.

```
/srv/clientus/
  prod/ test/                one instance each, never share data
    .env                     secrets and ports (prod: API 8000, web 3000; test: API 8001, web 3001)
    data/                    app.db, media/, vapid_private.pem
    releases/<timestamp>/    uploaded releases (last 5 kept)
    current -> releases/…    the live one; switching is atomic
    venv/                    Python of api/.python-version (installed by uv), rebuilt only when requirements change
    backups/                 database copy before every deploy (last 10) and nightly backups (prod)
```
Services: `clientus-api@prod`, `clientus-web@prod`, `clientus-worker@prod` (and `@test`). Caddy serves both domains
and customer domains (certificates on demand, prod only).

## Once

1. Rent a VPS (Ubuntu 24.04, 2 vCPU, 2–4 GB). Point A records of `PROD_DOMAIN` and `TEST_DOMAIN` to its IP.
2. `cp scripts/server.env.example scripts/server.env` and fill it in (the file is not committed).
3. `sh scripts/server.sh setup` — packages, user `clientus` with your SSH key, folders, fresh secrets per instance,
   services, Caddy, firewall (22/80/443), swap, nightly backup.
4. Optional: put the LLM token into `/srv/clientus/<instance>/.env` (`VSELLM_TOKEN=`), then restart via the next deploy.

## Every release

```
sh scripts/server.sh deploy test     # local tests -> build -> upload -> migrate -> switch -> health check
# check on phones at https://TEST_DOMAIN
sh scripts/server.sh deploy prod     # needs a clean git tree and typing "yes"
```
A failed health check switches back to the previous release automatically. Manual: `sh scripts/server.sh rollback prod`.
Migrations are not undone by a rollback; the database copy taken right before the deploy is in `backups/`.

## Studios and accounts

```
sh scripts/server.sh cli prod admin:create you@mail.ru           # operator panel /admin
sh scripts/server.sh cli prod tenant:publish alexmotors          # tenants/<slug>/business.json from the release
sh scripts/server.sh cli prod tenant:handover alexmotors --email owner@…   # go live + owner + password
sh scripts/server.sh status prod  |  sh scripts/server.sh logs prod
```
