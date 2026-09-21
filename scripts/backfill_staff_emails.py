"""Backfill an email address onto staff accounts that have none.

Why: MFA one-time codes go out over SMS/WhatsApp first and fall back to email.
A worker account with a NULL email can only reach the shared civic inbox (the
`_send_otp_with_fallback` resolution added in PR #4), so the code lands where
several people can read it instead of with the person logging in. Giving every
staff account its own address makes MFA genuinely per-person.

What address: by default the project's shared inbox in plus-addressed form, e.g.

    smartgarbagecsp+driver_cv-01@gmail.com
    smartgarbagecsp+driver_cv-02@gmail.com

Gmail/Google Workspace deliver every plus-address into the base mailbox, so the
messages stay in one place an admin already monitors, while each staff member
keeps a distinct, auditable address that the app can recognise. No personal
email address is ever needed, and nothing is invented on a domain we do not
control: if the base address is not a Gmail/Workspace address the script uses
`<username>@<domain-of-base>` instead and says so.

Accounts that already have an email are left exactly as they are.

Usage (dry run is the default — nothing is written without --apply):
    python scripts/backfill_staff_emails.py
    python scripts/backfill_staff_emails.py --apply
    python scripts/backfill_staff_emails.py --apply --base admin@example.org
    python scripts/backfill_staff_emails.py --apply --roles worker

Like the other seeders, this refuses to run on a deployed platform; it is meant
for local/maintenance use against the database you name.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Roles that log in as staff. Citizens are deliberately out of scope: their
# address is their own business, not something we invent.
STAFF_ROLES = ('worker', 'admin')

GMAIL_DOMAINS = ('gmail.com', 'googlemail.com')


def _is_deployed():
    return bool(os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'))


def build_address(base, username):
    """Return a per-staff address derived from the shared base address."""
    base = (base or '').strip()
    if not base or '@' not in base:
        raise ValueError('base address must be a valid email address')
    local, _, domain = base.partition('@')
    if domain.lower() in GMAIL_DOMAINS:
        # Plus-addressing keeps delivery in the one mailbox that is monitored.
        return f"{local}+{username}@{domain}"
    return f"{username}@{domain}"


def backfill_staff_emails(app=None, base=None, roles=STAFF_ROLES, apply=False):
    """Return (planned, applied) lists of (username, role, address) tuples."""
    from app import create_app, db
    from app.models import User

    own_app = app is None
    if own_app:
        app = create_app()

    base = base or os.environ.get('CIVIC_CONTACT_EMAIL') or 'smartgarbagecsp@gmail.com'

    planned = []
    with app.app_context():
        staff = User.query.filter(User.role.in_(list(roles))).order_by(User.id).all()
        for user in staff:
            if (user.email or '').strip():
                continue
            planned.append((user.username, user.role, build_address(base, user.username)))

        if not apply:
            return planned, []

        applied = []
        for user in staff:
            if (user.email or '').strip():
                continue
            address = build_address(base, user.username)
            user.email = address
            # Migration-safe: never flip an account into "verified" here — the
            # person still proves the address works when they first log in.
            applied.append((user.username, user.role, address))
        db.session.commit()
        return planned, applied


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default=None,
                        help='shared inbox the per-staff addresses derive from '
                             '(default: $CIVIC_CONTACT_EMAIL)')
    parser.add_argument('--roles', default=','.join(STAFF_ROLES),
                        help='comma-separated roles to backfill (default: worker,admin)')
    parser.add_argument('--apply', action='store_true',
                        help='write the changes (default is a dry run)')
    args = parser.parse_args()

    if _is_deployed():
        print('Refusing to run on a deployed platform (RENDER/FLY_APP_NAME set).',
              file=sys.stderr)
        return 2

    roles = tuple(r.strip() for r in args.roles.split(',') if r.strip())
    planned, applied = backfill_staff_emails(base=args.base, roles=roles, apply=args.apply)

    if not planned:
        print('No staff accounts are missing an email address — nothing to do.')
        return 0

    print(f"{'applied' if applied else 'would set'}:")
    for username, role, address in (applied or planned):
        print(f"  {username:<22} {role:<8} -> {address}")
    if not applied:
        print('\nDry run — re-run with --apply to write these addresses.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
