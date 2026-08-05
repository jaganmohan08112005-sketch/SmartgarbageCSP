"""Seed a realistic PAYT invoice history across several citizens and months.

For local development / demoing only. Populates:
  - A few extra citizen accounts (so the admin ledger and the citizen eco
    leaderboard have more than one household).
  - For each citizen, the most recent N calendar months of PAYT invoices with a
    realistic mix of statuses so every billing feature has data:
        * Paid      — older months (paid_at, UPI/Razorpay transaction ref)
        * Unpaid    — the current billing cycle AND some months old enough that
                      the dunning job flags them overdue (> 30 days)
        * Waived    — one forgiven unpaid invoice (refund_reason set)
        * Refunded  — one Razorpay-paid invoice reversed via refund_id
  - Amounts mirror the app's real billing rule (routes/citizen.py):
        base   = weight_kg * 1.5            (₹1.5/kg, only bills when >= 100 kg)
        penalty = 1.0 + (100 - compliance) / 100   (1.0x .. 2.0x)
        amount = round(base * penalty, 2)

Safe to re-run: citizens and (user, period) invoice pairs that already exist are
skipped. `--force` wipes ALL PAYT invoices and the extra seed citizens first so
the demo can be reset cleanly. NEVER runs on a deployed platform (guarded by the
same RENDER/FLY_APP_NAME check used by the app itself).

Usage:
    python scripts/seed_payt_invoices.py            # default: 5 months
    python scripts/seed_payt_invoices.py --months 6
    python scripts/seed_payt_invoices.py --force    # reset + reseed
"""
import argparse
import calendar
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Demo-only accounts — publicly-known credentials, so the same guard that keeps
# the app's own demo seeder off production applies here too.
DEMO_PASSWORD = "24331A4441CITIZEN"

# (username, phone, email, green_points). The first entry is the app's existing
# demo citizen; the rest are extra households created on first run.
SEED_CITIZENS = [
    ("24331A4441CITIZEN", "+919876543211", "citizen@example.com", 195),
    ("ramesh_n",           "+919876510001", "ramesh.n@example.com",   142),
    ("lakshmi_k",          "+919876510002", "lakshmi.k@example.com",   87),
    ("suresh_p",           "+919876510003", "suresh.p@example.com",   231),
    ("anitha_s",           "+919876510004", "anitha.s@example.com",    64),
    ("venkat_m",           "+919876510005", "venkat.m@example.com",   118),
    ("priya_r",            "+919876510006", "priya.r@example.com",    176),
]

# Weight band (kg/month) per citizen index — households stay roughly consistent.
_WEIGHT_BANDS = [
    (140, 210), (100, 165), (180, 260), (120, 190),
    (100, 150), (160, 235), (130, 200),
]


def _is_deployed():
    return bool(os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'))


def _status_for(month_idx, citizen_idx):
    """Status pattern: oldest months paid, current cycle unpaid, plus one
    waived and one refunded spread across citizens for the ledger demo."""
    if month_idx == 0:
        return 'Refunded' if citizen_idx == 1 else 'Paid'
    if month_idx == 1:
        return 'Waived' if citizen_idx == 3 else 'Paid'
    if month_idx == 2:
        return 'Unpaid' if citizen_idx % 2 == 0 else 'Paid'
    if month_idx == 3:
        return 'Unpaid' if citizen_idx % 3 == 0 else 'Paid'
    return 'Unpaid'  # current billing cycle


def _payment_method_for(citizen_idx, month_idx, status):
    if status == 'Paid':
        return 'Razorpay' if (citizen_idx + month_idx) % 2 == 0 else 'UPI'
    if status == 'Refunded':
        return 'Razorpay'  # refunds require a Razorpay payment to reverse
    return None


def seed_payt_invoices(app=None, months=5, force=False):
    """Create citizens + PAYT history. Returns a summary dict of counts.

    Runs inside the provided app (tests) or a fresh app from create_app().
    """
    if _is_deployed():
        raise RuntimeError("Refusing to seed demo data on a deployed platform.")

    from app import create_app, db
    from app.models import Notification, PAYTInvoice, User, utcnow
    from werkzeug.security import generate_password_hash

    app = app or create_app()
    with app.app_context():
        # ── Optional clean reset ──
        if force:
            PAYTInvoice.query.delete()
            for uname, *_ in SEED_CITIZENS:
                extra = User.query.filter_by(username=uname).first()
                if extra and uname != "24331A4441CITIZEN":
                    # Drop user-scoped rows that reference the account BEFORE
                    # the user — dunning creates Notifications for invoice
                    # owners, and Postgres enforces the FK (SQLite ignores it).
                    Notification.query.filter_by(user_id=extra.id).delete()
                    db.session.delete(extra)
            db.session.commit()

        # ── Ensure the citizen accounts exist ──
        users = []
        for uname, phone, email, gp in SEED_CITIZENS:
            user = User.query.filter_by(username=uname).first()
            if user is None:
                user = User(
                    username=uname,
                    password_hash=generate_password_hash(DEMO_PASSWORD),
                    role="citizen",
                    phone=phone,
                    email=email,
                    is_approved=True,
                    green_points=gp,
                )
                db.session.add(user)
                db.session.flush()
            users.append(user)
        db.session.commit()

        # ── Build the trailing `months` calendar periods (oldest → newest) ──
        now = utcnow()
        first = datetime(now.year, now.month, 1)
        periods = []
        for m in range(months - 1, -1, -1):
            y, mo = first.year, first.month - m
            while mo <= 0:
                mo += 12
                y -= 1
            periods.append((y, mo, f"{calendar.month_name[mo]} {y}"))

        created = skipped = 0
        for citizen_idx, user in enumerate(users):
            rng = random.Random(f"payt-seed:{user.username}")
            for month_idx, (y, mo, period_name) in enumerate(periods):
                if PAYTInvoice.query.filter_by(
                        user_id=user.id, period=period_name).first():
                    skipped += 1
                    continue

                status = _status_for(month_idx, citizen_idx)
                low, high = _WEIGHT_BANDS[citizen_idx % len(_WEIGHT_BANDS)]
                weight_kg = round(rng.uniform(low, high), 1)
                compliance = round(rng.uniform(55.0, 100.0), 1)
                # Mirror routes/citizen.py exactly (SWM Rules 2026 penalties).
                landfill_kg = round(weight_kg * (1 - compliance / 100.0), 1)
                segregation_kg = round(weight_kg - landfill_kg, 1)
                penalty = round(1.0 + (100.0 - compliance) / 100.0, 2)
                base = round(weight_kg * 1.5, 2)
                amount = round(base * penalty, 2)

                issued_at = datetime(y, mo, 1, hour=9, minute=30) + timedelta(
                    days=rng.randint(0, 3), minutes=rng.randint(0, 59))

                inv = PAYTInvoice(
                    user_id=user.id,
                    period=period_name,
                    weight_kg=weight_kg,
                    bin_pickups=rng.randint(0, 6),
                    segregation_kg=segregation_kg,
                    landfill_kg=landfill_kg,
                    compliance_score=compliance,
                    penalty_multiplier=penalty,
                    base_amount_rs=base,
                    amount_rs=amount,
                    status=status,
                    issued_at=issued_at,
                    payment_method=_payment_method_for(citizen_idx, month_idx, status),
                    billing_status=(
                        'Verified' if status in ('Paid', 'Refunded')
                        else 'Self-Reported'),
                    verified_weight_kg=(
                        weight_kg if status in ('Paid', 'Refunded') else None),
                    discrepancy_pct=(
                        0.0 if status in ('Paid', 'Refunded') else None),
                )
                if status in ('Paid', 'Refunded'):
                    inv.paid_at = issued_at + timedelta(days=rng.randint(1, 9))
                    inv.transaction_ref = (
                        f"pay_{rng.randint(10**13, 10**14 - 1)}"
                        if inv.payment_method == 'Razorpay'
                        else f"{rng.randint(100000000000, 999999999999)}"
                    )
                if status == 'Refunded':
                    inv.refund_id = f"rzp_refund_{rng.randint(10**13, 10**14 - 1)}"
                    inv.refunded_at = inv.paid_at + timedelta(days=rng.randint(2, 14))
                    inv.refund_reason = "Duplicate charge — refunded by admin"
                if status == 'Waived':
                    inv.refund_reason = "Waived by admin (low-income household)"
                    inv.refunded_at = issued_at + timedelta(days=rng.randint(15, 25))
                db.session.add(inv)
                created += 1

        db.session.commit()

        # ── Summary + dunning preview ──
        all_inv = PAYTInvoice.query.all()
        by_status = {}
        for i in all_inv:
            by_status[i.status] = by_status.get(i.status, 0) + 1
        overdue = sum(
            1 for i in all_inv
            if i.status == 'Unpaid' and i.issued_at < utcnow() - timedelta(days=30))
        summary = {
            "invoices": len(all_inv),
            "created": created,
            "skipped": skipped,
            "by_status": by_status,
            "dunning_eligible": overdue,
            "citizens": len(users),
        }
        print(f"Done. Created {created} invoice(s), skipped {skipped} existing; "
              f"total {len(all_inv)}. Status mix: {by_status}. "
              f"Dunning-eligible (Unpaid >30d): {overdue}.")
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=5,
                        help="number of trailing calendar months to seed")
    parser.add_argument("--force", action="store_true",
                        help="delete all PAYT invoices + extra seed citizens first")
    args = parser.parse_args()
    seed_payt_invoices(months=args.months, force=args.force)
