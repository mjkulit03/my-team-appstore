"""Background worker: flush pending escalations to the notification channels.

Designed to be safe to run repeatedly, so a GitHub Actions cron job, a local
`python -m notifications.worker`, or a request-time call all behave the same.

Usage:
    python -m notifications.worker          # process and print a summary
    python -m notifications.worker --dry-run # report without sending
"""

from __future__ import annotations

import argparse
import json
import sys

import store
from .config import get_settings
from .notifier import Notifier


def run_once(dry_run: bool = False) -> dict:
    """Deliver every pending escalation that has not been notified yet.

    Returns a summary dict. Never raises for delivery failures — those are
    recorded against the escalation so the worker keeps making progress.
    """
    settings = get_settings()
    notifier = Notifier(settings)

    pending = [
        item
        for item in store.list_escalations(status="pending")
        if not item.get("notified_at")
    ]

    summary = {
        "notifications_enabled": settings.enabled,
        "channels": settings.active_channels(),
        "pending": len(pending),
        "sent": 0,
        "failed": 0,
        "dropped": 0,
        "dry_run": dry_run,
        "results": [],
    }

    for item in pending:
        subject = f"[{item['severity'].upper()}] {item['title']}"
        body = "\n".join(
            [
                item["summary"],
                "",
                f"Escalation : {item['id']}",
                f"Type      : {item['kind']}",
                f"Raised at : {item['created_at']}",
                "",
                "This needs a human decision.",
            ]
        )

        if dry_run:
            summary["results"].append(
                {"escalation_id": item["id"], "channel": "dry-run", "ok": True, "detail": "not sent (dry run)"}
            )
            continue

        results = notifier.send(subject, body)
        ok = any(r.ok for r in results)
        detail = "; ".join(f"{r.channel}: {'ok' if r.ok else r.detail}" for r in results)
        summary["results"].append(
            {"escalation_id": item["id"], "ok": ok, "detail": detail}
        )

        if ok:
            store.mark_notified(item["id"], {"ok": True, "detail": detail})
            summary["sent"] += 1
        elif not settings.active_channels():
            # Nothing is configured to deliver anything, so retrying on every run
            # would achieve nothing. Mark it handled to stop the churn, but say so
            # loudly in the summary so a misconfiguration is not silent.
            store.mark_notified(item["id"], {"ok": False, "detail": detail, "dropped": True})
            summary["dropped"] += 1
        else:
            # A real channel exists but failed: leave the item pending so the next
            # run retries instead of silently losing the alert.
            summary["failed"] += 1

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dispatch pending human-approval escalations.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be sent without sending.")
    parser.add_argument("--json", action="store_true", help="Emit the summary as JSON.")
    args = parser.parse_args(argv)

    summary = run_once(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"escalations pending: {summary['pending']} | "
            f"sent: {summary['sent']} | failed: {summary['failed']} | dropped: {summary['dropped']}"
        )
        print(f"notifications enabled: {summary['notifications_enabled']} | channels: {summary['channels'] or 'none configured'}")
        for result in summary["results"]:
            state = "ok" if result["ok"] else "FAILED"
            print(f"  [{state}] {result['escalation_id']}: {result.get('detail', '')}")
        if summary["dropped"]:
            print("  ! some escalations were dropped because no notification channel is configured")

    # A delivery failure should be visible to the scheduler but must not look
    # like a crash of the worker itself.
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())