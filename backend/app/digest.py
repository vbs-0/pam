"""Daily email digest: once a day after 08:00 IST, people who opted in get one plain-text email listing what needs
attention (bills due, budgets near or over, card dues). Nothing is sent when there is nothing to say.

The loop runs inside the API process (there is a single worker). `digest_run` records the day, so a restart or a second
process never sends twice; each person's `last_sent_on` is a second guard.
"""

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, text

from app import mail
from app.config import settings

log = logging.getLogger("pam")
IST = ZoneInfo("Asia/Kolkata")
SEND_FROM_HOUR = 8
GROUPS = {
    "BILL_DUE": "bills",
    "BILL_OVERDUE": "bills",
    "BUDGET_OVER": "budgets",
    "BUDGET_NEAR": "budgets",
    "CARD_DUE": "cards",
    "CARD_LIMIT": "cards",
}


def compose(alerts: list[dict]) -> str:
    lines = [f"- {a['title']}. {a['detail']}" for a in alerts]
    return (
        "Here is what needs a look in your PAM register today:\n\n"
        + "\n".join(lines)
        + f"\n\nOpen PAM: {settings.app_url}\n\nYou get this because you turned on the daily email in Settings. "
        "You can switch it off there at any time.\n"
    )


def send_digests(conn: Connection, day: date) -> int:
    """Send today's digest to everyone who opted in and has something to look at. Returns how many were sent."""
    from app.api.analytics import alerts
    from app.api.common import run_id
    from app.households import is_real

    try:
        run = run_id(conn)
    except Exception:  # no successful run yet: nothing to summarise
        return 0
    people = conn.execute(
        text(
            "SELECT p.app_user_id, p.bills, p.budgets, p.cards, u.email, u.profile_user_id FROM notify_pref p "
            "JOIN app_user u USING (app_user_id) WHERE p.email_digest AND NOT u.disabled AND u.role = 'CUSTOMER' "
            "AND (p.last_sent_on IS NULL OR p.last_sent_on < :d)"
        ),
        {"d": day},
    ).all()
    sent = 0
    for p in people:
        if not is_real(p.profile_user_id):
            continue
        try:
            wanted = {k for k in ("bills", "budgets", "cards") if getattr(p, k)}
            items = [a for a in alerts(p.profile_user_id, run, conn)["alerts"] if GROUPS.get(a["type"]) in wanted]
            if items and mail.send(
                p.email, f"PAM: {len(items)} thing{'s' if len(items) != 1 else ''} to look at today", compose(items)
            ):
                sent += 1
            conn.execute(
                text("UPDATE notify_pref SET last_sent_on = :d WHERE app_user_id = :i"), {"d": day, "i": p.app_user_id}
            )
            conn.commit()
        except Exception:
            conn.rollback()
            log.exception("digest for %s failed", p.app_user_id)
    return sent


def run_once(day: date) -> int | None:
    """One pass if today's digest has not run yet. Returns the number sent, or None when it was already done."""
    import app.db

    with app.db.engine.connect() as conn:
        if (
            conn.execute(
                text("INSERT INTO digest_run (day) VALUES (:d) ON CONFLICT DO NOTHING RETURNING 1"), {"d": day}
            ).first()
            is None
        ):
            conn.rollback()
            return None
        conn.commit()
        n = send_digests(conn, day)
        conn.execute(text("UPDATE digest_run SET sent = :n WHERE day = :d"), {"n": n, "d": day})
        conn.commit()
        return n


async def digest_loop() -> None:
    """Check every 15 minutes; do nothing unless mail is configured and it is past 08:00 IST."""
    while True:
        try:
            now = datetime.now(IST)
            if mail.configured() and now.hour >= SEND_FROM_HOUR:
                n = await asyncio.to_thread(run_once, now.date())
                if n is not None:
                    log.info("daily digest sent to %d people", n)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("digest loop error")
        await asyncio.sleep(900)
