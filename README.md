# clientall — online booking for auto studios and beauty (multi-tenant PWA)

One Next.js build + one FastAPI + one SQLite database serve many studios at `/s/<slug>/`; each studio is a folder `tenants/<slug>/business.json` + photos.
Clients book without registration; owners manage bookings, prices, hours and photos from a phone-friendly cabinet at `/s/<slug>/owner`.

* Business types: auto service, car wash, private beauty master, beauty studio (one engine, four profiles).
* Run and deploy: **SETUP.md** · New studio: **CLONE-IN-6-MINUTES.md** · What was tested and what was not: **ACCEPTANCE.md**
* Quick start: `pnpm db:seed && pnpm dev:api` and, in another shell, `pnpm dev:web` → http://localhost:3000/s/graphite
# clientus
