#!/bin/sh
# API for Playwright: throwaway data dir, migrated + seeded, on port 18100.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
export DATA_DIR=$(mktemp -d)
export SECRET_KEY=e2e-secret
export VSELLM_TOKEN=  # e2e checks the rule-based assistant, no external LLM
export SEED_OWNER_PASSWORD=e2e-owner-password
cd "$ROOT/api"
.venv/bin/python -m app.cli db:seed >/dev/null
# a customer domain for aqua-wash and the platform operator (both used by e2e/platform.spec.ts)
.venv/bin/python -m app.cli domain:add aqua-wash book.aqua.test --force >/dev/null
.venv/bin/python -m app.cli domain:verify book.aqua.test --force >/dev/null
# one studio on the own-server package (no branding)
.venv/bin/python -m app.cli plan:set loft-beauty --plan self_hosted >/dev/null
# a live (activated) studio: subscription rules are enforced only for live studios, not samples
.venv/bin/python -m app.cli tenant:publish "$ROOT/web/e2e/fixtures/tenants/anna-nails" --activate >/dev/null
OPERATOR_PW=e2e-operator-password .venv/bin/python -m app.cli admin:create boss@platform.test --password-env OPERATOR_PW >/dev/null
exec .venv/bin/uvicorn app.main:app --port 18100 --log-level warning
