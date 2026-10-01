"""Pipeline CLI:  python -m app.cli <command>

  tenant:new <slug> [--name N] [--type auto|wash|beauty_master|beauty_studio]
                                      scaffold tenants/<slug>/ from a business-type starter kit + placeholder images
  tenant:sample <slug> --name N [--type T --phone P --address A --photos DIR]   prospect preview in one command
  tenant:handover <slug> --email E [--plan P]   sale closed: go live (lifetime) + owner + message text
  tenant:export <slug> --domain D     package for the customer's own server (no branding, own DB)
  tenant:validate <slug>              check business.json and images (no database needed)
  tenant:publish <slug> [--activate]  upsert into the database (preview by default), safe to repeat
  tenant:verify <slug> [--api U --web U]  probe the running site
  owner:create <slug> <email>         create/reset the owner (password from --password-env or prompt)
  admin:create <email>                create the platform operator (admin panel /admin)
  domain:add|list|verify|remove       customer domains (pending -> DNS check -> active)
  plan:set <slug> [--plan p --trial-days N --paid-days N --suspend|--resume]   tenant:list
  db:migrate | db:seed | vapid:generate
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from . import tenants
from .config import API_ROOT, get_settings


def _path(slug_or_path: str) -> Path:
    p = Path(slug_or_path)
    return p if p.exists() else tenants.tenants_root() / slug_or_path


def _migrate() -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().db_url)
    command.upgrade(cfg, "head")


def _fail(problems: list[str], title: str = "business config is not valid") -> int:
    print(f"✗ {title}:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return 1


def cmd_new(args) -> int:
    import json

    from . import profiles
    from .services import placeholder_art

    root = tenants.tenants_root() / args.slug
    if root.exists() and any(root.iterdir()):
        print(f"✗ {root} already exists", file=sys.stderr)
        return 1
    cfg = profiles.starter_config(args.type, args.slug, args.name or args.slug.replace("-", " ").title())
    people = [r["key"] for r in cfg["resources"]] if profiles.get_profile(args.type).kind == "person" else []
    for r in cfg["resources"]:
        if r["key"] in people:
            r["photo"] = f"{r['key']}.jpg"
    art = "beauty" if people else "car"
    placeholder_art.write_set(root, cfg["accent"], cfg["name"][:1].upper(), works=3, kind=art, people=people)
    (root / "business.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ created {root} ({profiles.get_profile(args.type).label})\n  1. replace hero.jpg / logo.png / work-*.jpg" + (" / master photos" if people else "") + " with real photos\n  2. edit business.json (name, prices, hours, address)\n  3. pnpm tenant:validate " + args.slug)
    return 0


def _public_base() -> str:
    return (get_settings().origins or ["http://localhost:3000"])[0]


def cmd_sample(args) -> int:
    """One command per prospect: folder + business.json + photos + validated preview publication."""
    import json
    import shutil

    from PIL import Image

    from . import profiles
    from .services import media, placeholder_art

    root = tenants.tenants_root() / args.slug
    if root.exists() and any(root.iterdir()):
        print(f"✗ {root} already exists", file=sys.stderr)
        return 1
    profile = profiles.get_profile(args.type)
    cfg = profiles.starter_config(args.type, args.slug, args.name)
    for key in ("phone", "address", "timezone", "accent", "tagline", "description"):
        value = getattr(args, key, None)
        if value:
            cfg[key] = value
    people = [r["key"] for r in cfg["resources"]] if profile.kind == "person" else []
    for r in cfg["resources"]:
        if r["key"] in people:
            r["photo"] = f"{r['key']}.jpg"
    root.mkdir(parents=True)
    photos = sorted(p for p in Path(args.photos).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if args.photos else []
    art = "beauty" if people else "car"
    placeholder_art.write_set(root, cfg["accent"], args.name[:1].upper(), works=3, kind=art, people=people)  # fills anything not supplied
    if photos:
        def put(src: Path, dst: str) -> None:
            data, _ext = media.process_image(src.read_bytes(), max_side=2400)
            (root / dst).write_bytes(data)
        put(photos[0], "hero.jpg")
        works = photos[1:6]
        for i, src in enumerate(works, 1):
            put(src, f"work-{i}.jpg")
        for i in range(len(works) + 1, 4):  # placeholders of the generated set that the prospect did not supply
            (root / f"work-{i}.jpg").unlink(missing_ok=True)
        cfg["gallery"] = [{"key": f"work-{i}", "image": f"work-{i}.jpg", "caption": ""} for i in range(1, len(works) + 1)]
    if args.logo:
        Image.open(args.logo).convert("RGBA").save(root / "logo.png")
    (root / "business.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        tenants.validate(root)
        _migrate()
        report = tenants.publish(root, activate=False)
    except tenants.ConfigProblem as exc:
        shutil.rmtree(root, ignore_errors=True)
        return _fail(exc.problems)
    print(f"✓ sample ready ({profile.label}): {report['status']}\n  link for the prospect: {_public_base()}/s/{args.slug}/\n  edit {root}/business.json (real prices, hours, services) and run: pnpm tenant:publish {args.slug}")
    return 0


def cmd_handover(args) -> int:
    password = os.environ.get(args.password_env) if args.password_env else None
    try:
        r = tenants.handover(args.slug, args.email, args.plan, password)
    except tenants.ConfigProblem as exc:
        return _fail(exc.problems)
    base = _public_base()
    print(f"✓ {args.slug} is live (package: {r['plan']}, lifetime). Message for the customer:\n")
    print(f"""Здравствуйте! Ваша онлайн-запись готова.

Сайт для клиентов: {base}/s/{args.slug}/
Кабинет владельца: {base}/s/{args.slug}/owner
Почта для входа: {r['email']}
Пароль: {r['password']}

В кабинете вы меняете услуги, цены, график, фото и видите все записи. Ссылку на сайт разместите в соцсетях, на карте и на визитке.
Если что-то нужно поправить — напишите мне.""")
    return 0


def cmd_export(args) -> int:
    from .services import exporter

    try:
        result = exporter.export_studio(args.slug, out_dir=Path(args.out), domain=args.domain, with_bookings=not args.no_bookings)
    except (exporter.ExportError, tenants.ConfigProblem) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    print(f"✓ package: {result['archive']} ({result['size_mb']:.1f} MB)\n  owners kept: {result['owners']}, bookings: {result['bookings']}\n  send it to the customer; on the server: tar xzf … && cd … && sudo sh install.sh")
    return 0


def cmd_validate(args) -> int:
    try:
        cfg = tenants.validate(_path(args.slug))
    except tenants.ConfigProblem as exc:
        return _fail(exc.problems)
    print(f"✓ {cfg.slug}: {len(cfg.services)} services, {len(cfg.resources)} resources, {len(cfg.gallery)} gallery photos")
    return 0


def cmd_publish(args) -> int:
    _migrate()
    try:
        if args.activate:
            problems = tenants.activation_problems(_path(args.slug))
            if problems:
                return _fail(problems, "cannot activate yet")
        report = tenants.publish(_path(args.slug), activate=args.activate, force=args.force)
    except tenants.ConfigProblem as exc:
        return _fail(exc.problems)
    print(f"✓ {report['slug']} published → status: {report['status']}" + (" (new)" if report["created"] else ""))
    if report["kept_owner_edits"]:
        print("  kept owner edits (use --force to overwrite):", ", ".join(sorted(set(report["kept_owner_edits"]))))
    if report["status"] == "preview":
        print("  preview: demo data is marked, no notifications are sent. Activate with --activate after checking.")
    return 0


def cmd_owner(args) -> int:
    password = os.environ.get(args.password_env) if args.password_env else None
    password = password or getpass.getpass("Password (min 10 chars): ")
    try:
        state = tenants.create_owner(args.slug, args.email, password)
    except tenants.ConfigProblem as exc:
        return _fail(exc.problems)
    print(f"✓ owner {args.email} {state} for {args.slug}")
    return 0


def cmd_admin(args) -> int:
    password = os.environ.get(args.password_env) if args.password_env else None
    password = password or getpass.getpass("Operator password (min 12 chars): ")
    try:
        state = tenants.create_operator(args.email, password)
    except tenants.ConfigProblem as exc:
        return _fail(exc.problems)
    print(f"✓ operator {args.email} {state}. Panel: /admin")
    return 0


def _tenant_row(db, slug: str):
    from sqlalchemy import select

    from .models import Tenant

    t = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if not t:
        raise tenants.ConfigProblem([f"tenant '{slug}' not found"])
    return t


def cmd_domain(args) -> int:
    from sqlalchemy import select

    from . import db as database
    from .models import Tenant, TenantDomain
    from .services import domains

    try:
        with database.write_session() as db:
            if args.action == "list":
                rows = db.execute(select(TenantDomain, Tenant.slug).join(Tenant, Tenant.id == TenantDomain.tenant_id).order_by(TenantDomain.id)).all()
                for d, slug in rows:
                    print(f"{d.host:40} {slug:20} {d.status}")
                print(f"{len(rows)} domain(s)")
                return 0
            if args.action == "add":
                dom = domains.add_domain(db, _tenant_row(db, args.slug), args.host, force=args.force)
                print(f"✓ {dom.host} added (pending). Customer DNS: A record -> {get_settings().platform_ips or '<PLATFORM_IPS not set>'}\n  then: pnpm domain:verify {dom.host}")
                return 0
            host = domains.normalize_host(args.host)
            dom = db.scalar(select(TenantDomain).where(TenantDomain.host == host))
            if not dom:
                print(f"✗ {host} is not registered", file=sys.stderr)
                return 1
            if args.action == "remove":
                db.delete(dom)
                print(f"✓ {host} removed")
                return 0
            check = domains.dns_check(host)
            print(f"  resolves to: {', '.join(check['resolved']) or 'nothing'}; expected: {', '.join(check['expected']) or '(PLATFORM_IPS not set)'}")
            if check["ok"] or args.force:
                domains.activate(db, dom)
                print(f"✓ {host} is active" + (" (forced)" if not check["ok"] else ""))
                return 0
            print("✗ DNS does not point at this platform yet (use --force to activate anyway)", file=sys.stderr)
            return 1
    except (domains.DomainError, tenants.ConfigProblem) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1


def cmd_plan(args) -> int:
    from . import db as database
    from .plans import all_plans
    from .services import subscription
    from .models import now_s

    day = 86400
    try:
        with database.write_session() as db:
            t = _tenant_row(db, args.slug)
            if args.plan:
                if args.plan not in all_plans():
                    print(f"✗ plan must be one of {', '.join(all_plans())}", file=sys.stderr)
                    return 1
                t.plan = args.plan
            if args.trial_days is not None:
                t.trial_ends_at = now_s() + args.trial_days * day
            if args.paid_days:
                base = t.paid_until if t.paid_until and t.paid_until > now_s() else now_s()
                t.paid_until = base + args.paid_days * day
            if args.suspend:
                t.suspended = True
            if args.resume:
                t.suspended = False
            info = subscription.overview(db, t)
            print(f"✓ {t.slug}: plan {t.plan}, state {info['state']}, days left {info['days_left']}, suspended={t.suspended}")
    except tenants.ConfigProblem as exc:
        return _fail(exc.problems)
    return 0


def cmd_list(args) -> int:
    from sqlalchemy import select

    from . import db as database
    from .models import Tenant
    from .services import subscription

    with database.read_session() as db:
        for t in db.scalars(select(Tenant).order_by(Tenant.id)):
            print(f"{t.slug:22} {t.status:9} plan={t.plan:7} state={subscription.state_of(t)}")
    return 0


def cmd_verify(args) -> int:
    from .verify import run

    return run(args.slug, args.api, args.web, custom=args.custom)


def _apply_seed_plan(slug: str, path) -> None:
    """Demo studios get the plan written in their business.json (seed only; live plans are the operator's)."""
    from sqlalchemy import select

    from . import db as database
    from .models import Tenant

    cfg, _ = tenants.load_config(path)
    with database.write_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
        t.plan = cfg.plan


def cmd_seed(args) -> int:
    _migrate()
    password = os.environ.get("SEED_OWNER_PASSWORD", "demo-owner-2026")
    seed_dir = Path(os.environ.get("SEED_DIR") or (API_ROOT.parent / "web" / "e2e" / "fixtures" / "tenants"))
    for slug in ("graphite", "demo-tenant", "aqua-wash", "loft-beauty", "anna-nails"):
        path = seed_dir / slug
        if not path.exists():
            print(f"✗ {path} missing", file=sys.stderr)
            return 1
        tenants.publish(path, activate=False)
        _apply_seed_plan(slug, path)
        tenants.create_owner(slug, f"owner@{slug}.example", password)
        print(f"✓ {slug}: preview published, owner owner@{slug}.example")
    op_password = os.environ.get("SEED_OPERATOR_PASSWORD", "demo-operator-2026")
    tenants.create_operator("operator@platform.example", op_password)
    print("✓ operator operator@platform.example (panel: /admin)")
    print("  dev passwords: owners", password, "| operator", op_password, "(dev only; never use in production)")
    return 0


def cmd_vapid(args) -> int:
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    import base64

    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"✗ {out} exists (use --force)", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    v = Vapid()
    v.generate_keys()
    v.save_key(str(out))
    out.chmod(0o600)
    raw = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    print(f"✓ private key: {out}\nVAPID_PUBLIC_KEY={base64.urlsafe_b64encode(raw).decode().rstrip('=')}\nVAPID_PRIVATE_KEY_PATH={out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("tenant:new"); s.add_argument("slug"); s.add_argument("--name"); s.add_argument("--type", default="auto", choices=list(__import__("app.profiles", fromlist=["TYPES"]).TYPES)); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("tenant:sample"); s.add_argument("slug"); s.add_argument("--name", required=True); s.add_argument("--type", default="auto", choices=list(__import__("app.profiles", fromlist=["TYPES"]).TYPES)); s.add_argument("--phone"); s.add_argument("--address"); s.add_argument("--timezone"); s.add_argument("--accent"); s.add_argument("--tagline"); s.add_argument("--photos", help="folder with the prospect's photos: first = main photo, next = works"); s.add_argument("--logo"); s.set_defaults(fn=cmd_sample)
    s = sub.add_parser("tenant:handover"); s.add_argument("slug"); s.add_argument("--email", required=True); s.add_argument("--plan", choices=["standard", "domain", "self_hosted"]); s.add_argument("--password-env"); s.set_defaults(fn=cmd_handover)
    s = sub.add_parser("tenant:export"); s.add_argument("slug"); s.add_argument("--domain", required=True, help="the customer's domain on their own server"); s.add_argument("--out", default="exports"); s.add_argument("--no-bookings", action="store_true"); s.set_defaults(fn=cmd_export)
    s = sub.add_parser("tenant:validate"); s.add_argument("slug"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("tenant:publish"); s.add_argument("slug"); s.add_argument("--activate", action="store_true"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_publish)
    s = sub.add_parser("tenant:verify"); s.add_argument("slug"); s.add_argument("--api", default=os.environ.get("VERIFY_API_URL", "http://127.0.0.1:8000")); s.add_argument("--web", default=os.environ.get("VERIFY_WEB_URL", "http://127.0.0.1:3000")); s.add_argument("--custom", action="store_true", help="--web is the studio's own domain (studio at the root)"); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("owner:create"); s.add_argument("slug"); s.add_argument("email"); s.add_argument("--password-env"); s.set_defaults(fn=cmd_owner)
    s = sub.add_parser("admin:create"); s.add_argument("email"); s.add_argument("--password-env"); s.set_defaults(fn=cmd_admin)
    s = sub.add_parser("domain:add"); s.add_argument("slug"); s.add_argument("host"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_domain, action="add")
    s = sub.add_parser("domain:list"); s.set_defaults(fn=cmd_domain, action="list")
    s = sub.add_parser("domain:verify"); s.add_argument("host"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_domain, action="verify")
    s = sub.add_parser("domain:remove"); s.add_argument("host"); s.set_defaults(fn=cmd_domain, action="remove")
    s = sub.add_parser("plan:set"); s.add_argument("slug"); s.add_argument("--plan"); s.add_argument("--trial-days", type=int); s.add_argument("--paid-days", type=int); s.add_argument("--suspend", action="store_true"); s.add_argument("--resume", action="store_true"); s.set_defaults(fn=cmd_plan)
    s = sub.add_parser("tenant:list"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("db:migrate"); s.set_defaults(fn=lambda a: (_migrate(), print("✓ migrated"), 0)[2])
    s = sub.add_parser("db:seed"); s.set_defaults(fn=cmd_seed)
    s = sub.add_parser("vapid:generate"); s.add_argument("--out", default=str(get_settings().data_dir / "vapid_private.pem")); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_vapid)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
