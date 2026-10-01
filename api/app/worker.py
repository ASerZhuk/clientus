"""Background worker: python -m app.worker  (systemd unit: deploy/nook-worker.service)"""
import logging
import signal
import time

from sqlalchemy import delete

from . import db as database
from .models import IdempotencyKey, OwnerSession, RateCounter, now_s
from .services import push

log = logging.getLogger("worker")
_stop = False


def _signal(*_):
    global _stop
    _stop = True


def housekeeping() -> None:
    with database.write_session() as db:
        db.execute(delete(OwnerSession).where(OwnerSession.expires_at < now_s()))
        db.execute(delete(RateCounter).where(RateCounter.window_start < now_s() - 86400))
        db.execute(delete(IdempotencyKey).where(IdempotencyKey.created_at < now_s() - 14 * 86400))


def main(poll_seconds: int = 5) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)
    last_cleanup = 0.0
    log.info("worker started (VAPID %s)", "configured" if push.vapid_configured() else "NOT configured: jobs are skipped")
    while not _stop:
        counts = push.run_once()
        if counts:
            log.info("processed %s", counts)
        if time.time() - last_cleanup > 3600:
            housekeeping()
            last_cleanup = time.time()
        if not counts:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
