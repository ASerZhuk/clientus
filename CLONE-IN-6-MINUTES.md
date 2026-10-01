# New studio in ~6 minutes

Everything studio-specific lives in **one folder**: `tenants/<slug>/business.json` + photos. No source code changes.

| min | step | command |
|---|---|---|
| 0:00 | scaffold from the starter kit of a business type (placeholder photos generated) | `pnpm tenant:new pitstop --name "Pit Stop" --type auto` |
| 0:30 | drop in the studio's real photos, same file names: `hero.jpg` (main), `logo.png`, `work-1..4.jpg` | copy into `tenants/pitstop/` |
| 1:00 | edit `business.json`: name, tagline, phone, address, accent `#RRGGBB`, timezone, 3 info cards, hours, posts, services | editor |
| 4:00 | check | `pnpm tenant:validate pitstop` (readable errors: missing photo, bad time, unknown post…) |
| 4:30 | publish as **preview** (sample link, demo data marked, no notifications, noindex) | `pnpm tenant:publish pitstop` |
| 5:00 | owner account (no public sign-up) | `OWNER_PW='long password' pnpm owner:create pitstop boss@mail.com --password-env OWNER_PW` |
| 5:20 | probe the live link (manifest, service worker, deep links, icons, slots) | `pnpm tenant:verify pitstop --api http://127.0.0.1:8000 --web https://book.example.com` |
| 5:40 | send `https://book.example.com/s/pitstop/`; when checked: | `pnpm tenant:publish pitstop --activate` |

## Business types (`business_type`)

| `--type` | Business | What changes |
|---|---|---|
| `auto` (default) | Auto service / detailing | posts and bays, multi-day jobs, car + plate in the booking form |
| `wash` | Car wash | boxes, short services, 30-minute step, car required, quick cancellation |
| `beauty_master` | One beauty master | exactly one resource (the master), no master choice, comment field instead of car |
| `beauty_studio` | Beauty studio | several masters, each with **own weekly hours, days off, photo, specialisation**; customer picks a master or «любой свободный»; per-master price/duration per service |

The type decides vocabulary («пост» / «бокс» / «мастер»), form fields, which cabinet screens exist and which limits are enforced
(e.g. own hours only for `beauty_studio`, multi-day services only for `auto`). `tenant:validate` explains any violation. Switching the type of a live studio is a deliberate CLI action (change the file and republish), not a cabinet setting.

For a studio, list masters with their own schedule and who does what:
```json
"business_type": "beauty_studio",
"resources": [
  {"key": "anna", "name": "Анна", "description": "Стилист", "photo": "anna.jpg",
   "hours": {"mon": ["10:00","19:00"], "sat": null},
   "exceptions": [{"date": "2026-10-05", "closed": true, "note": "отпуск"}]}
],
"services": [
  {"key": "cut", "name": "Стрижка", "price": 2500, "duration_min": 60,
   "resources": ["anna", {"key": "maria", "price": 1800, "duration_min": 75}]}
]
```
A master without `hours` follows the studio's hours. Hours are resolved per master: own day off → studio holiday → own weekly hours → studio hours.

## business.json essentials

```json
{
  "slug": "pitstop", "name": "Pit Stop", "tagline": "…", "phone": "+7 …", "address": "…",
  "timezone": "Europe/Moscow", "currency": "RUB", "accent": "#4690FF",
  "images": { "logo": "logo.png", "hero": "hero.jpg" },
  "info_cards": [ {"title": "{services}", "text": "услуг в прайсе", "icon": "wrench"}, "… exactly 3; {services} {resources} {min_price} and {resources_word:место|места|мест} are filled live" ],
  "gallery": [ {"key": "work-1", "image": "work-1.jpg", "caption": "…"} ],
  "booking": { "slot_step_min": 60, "lead_time_min": 120, "max_advance_days": 60, "cancel_before_hours": 24, "reminder_hours": 24 },
  "hours": { "mon": ["09:00", "19:00"], "sun": null },
  "exceptions": [ {"date": "2026-11-04", "closed": true, "note": "holiday"} ],
  "resources": [ {"key": "bay-1", "name": "Post 1"} ],
  "services": [ {"key": "wash", "name": "Wash", "price": 2500, "duration_min": 120, "buffer_min": 30, "resources": ["bay-1"], "keywords": ["wash"]} ]
}
```
* By default every service can be booked on **any** place (omit `resources` in a service). List `resources` only when a job needs special equipment, e.g. wheel alignment only on the alignment stand.
* `hours` = the moments a car can be **accepted** (first start .. last start). Work may run past closing; a 2-day service (`duration_min: 2880`) keeps its post occupied for both days.
* `price` is in major units; `keywords` help the assistant recognise the service in questions.
* The 3 info cards are the tiles under the title: a short bold value (`title`, e.g. "5" or "от 3 500 ₽") and a caption (`text`, e.g. "услуг в прайсе"); the owner edits them in the cabinet. Icons: wrench, images, tag, shield, camera, clock, user, sparkle, star, car, drop, check.
* Accent, name and logo also drive the install icon, splash screens and the theme: nothing else to change.

## Re-publishing is safe

Run `tenant:publish` again after changing `business.json` or photos. Existing **bookings, payments, owner-uploaded photos are never touched**.
Things the owner edited in the cabinet (phone, services, hours, logo…) are kept and reported (`kept owner edits`); add `--force` to make the file win.
Services dropped from the file are hidden, not deleted, so history stays intact.

## What the owner does himself (cabinet `/s/<slug>/owner`)
Services, prices, durations, posts, working hours and days off, address/phone/logo/main photo, the 3 info cards, gallery
(add card / replace one photo / change one caption), bookings (create, move, cancel, status, payments/refunds), post blocks, notifications, assistant.
