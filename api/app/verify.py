"""tenant:verify - probe a running site (API + web) for one studio."""
import json
import re
import sys

import httpx


def run(slug: str, api: str, web: str, custom: bool = False) -> int:
    """custom=True: `web` is the customer's own domain (the studio lives at its root)."""
    base = "" if custom else f"/s/{slug}"
    api, web = api.rstrip("/"), web.rstrip("/")
    results: list[tuple[bool, str]] = []

    def check(ok: bool, label: str) -> None:
        results.append((ok, label))
        print(("✓ " if ok else "✗ ") + label)

    with httpx.Client(timeout=15, follow_redirects=True) as http:
        try:
            r = http.get(f"{api}/api/s/{slug}")
        except httpx.HTTPError as exc:
            print(f"✗ API unreachable at {api}: {exc}", file=sys.stderr)
            return 1
        check(r.status_code == 200, f"API config for '{slug}' answers 200")
        if r.status_code != 200:
            return 1
        cfg = r.json()
        name = cfg["name"]
        check(bool(cfg["services"]) and all(s["bookable"] for s in cfg["services"]), f"{len(cfg['services'])} services, all have a working post")
        check(bool(cfg["hero_url"]) and http.get(api + cfg["hero_url"]).status_code == 200, "hero photo is served")
        check(len(cfg["info_cards"]) == 3, "three info cards")
        sid = cfg["services"][0]["id"]
        slots = http.get(f"{api}/api/s/{slug}/slots", params={"service_id": sid, "days": 14}).json()
        free = sum(1 for d in slots["days"].values() for s in d if s["available"])
        check(free > 0, f"free slots for the first service in the next 14 days: {free}")

        m = http.get(f"{web}{base}/manifest.webmanifest")
        check(m.status_code == 200, "manifest.webmanifest answers 200")
        if m.status_code == 200:
            man = m.json()
            check(man.get("id") == f"{base}/" and man.get("scope") == f"{base}/" and man.get("start_url", "").startswith(f"{base}/"), "manifest id/scope/start_url belong to this studio")
            check(man.get("name") == name, "manifest name matches the studio")
            icons = [http.get(web + i["src"] if i["src"].startswith("/") else i["src"]).status_code for i in man.get("icons", [])]
            check(bool(icons) and all(c == 200 for c in icons), f"{len(icons)} manifest icons reachable")
        sw = http.get(f"{web}{base}/sw.js")
        check(sw.status_code == 200 and "javascript" in sw.headers.get("content-type", ""), "service worker script served under the studio scope")
        check(sw.headers.get("service-worker-allowed") == f"{base}/", "Service-Worker-Allowed limits scope to the studio")

        for path in ("", "services", "my", "owner"):
            url = f"{web}{base}/{path}" if (base or path) else f"{web}/"
            page = http.get(url)
            html = page.text
            ok = page.status_code == 200 and name in html and f"{base}/manifest.webmanifest" in html
            check(ok, f"{base}/{path} returns the right studio shell (deep link)")
        home = http.get(f"{web}{base}/" if base else f"{web}/").text
        check(bool(re.search(r'rel="apple-touch-icon"[^>]+' + re.escape(slug), home)) or f"/api/media/{slug}/pwa/apple-touch-icon.png" in home, "apple-touch-icon is this studio's")
        check(http.get(f"{web}/s/definitely-missing-studio/").status_code == 404, "unknown studio returns 404" if not custom else "other studios are not reachable on this domain (404)")
        if custom:
            check(http.get(f"{web}/admin").status_code == 404, "the operator panel is not exposed on a customer domain")
        if cfg["is_preview"]:
            check('noindex' in home, "preview page is noindex")
            print("ℹ status: preview (sample). Activate after checks: pnpm tenant:publish " + slug + " --activate")
        else:
            print("ℹ status: active")
    failed = [label for ok, label in results if not ok]
    print(json.dumps({"slug": slug, "passed": len(results) - len(failed), "failed": len(failed)}))
    return 1 if failed else 0
