"""Free mail-connectivity self-check for the SmartGarbage portal.

Render blackholes outbound SMTP ports 25/465/587: a socket connect to
`smtplib.SMTP('smtp.brevo.com', 25/465/587)` neither succeeds nor is refused —
it just blocks. The send path already guards every request with a short
MAIL_TIMEOUT, but a blocked relay at *boot* would stall every web worker, and
`/health` would stay `healthy` while every OTP/verification mail sat in the
queue and never left.

This module moves the check out of the request path and into the app boot
when `create_app()` finishes its mail configuration. It reports the live
relay posture into ``app.config['mail']`` (plus ``app.config['mail_initialized']``),
and exposes a tiny health consumer so the public API can say what the mail
stack is actually doing instead of pretending it's fine.

Design notes
------------
* Non-blocking: the probe runs once with ``timeout = MAIL_TIMEOUT``
  (default 10 s) and only when ``MAIL_SERVER`` is configured. A blocked or
  misconfigured relay fails fast and leaves a warning in the logs — the app
  keeps serving, and ``/health`` reports it.
* CHEAP: one TCP connect + one TLS/STARTTLS handshake + one login, on every
  boot. It does not send a message; it only proves the route works.
* Firewall-locked local dev: an unset ``MAIL_SERVER`` skips the probe on all
  forks (mailman locmem / no-gateway paths) — never breaks local runs.
* Fail-safe: any exception (DNS, timeout, login rejected) is logged and
  converted into a clear ``mail.transport = 'unreachable'`` state plus a
  ``warning`` health verdict (exactly like the queue-starvation posture), so
  the operator is alerted the instant Mailnesia ignores the IP again.
"""

import logging
import os
import socket
import smtplib

logger = logging.getLogger(__name__)

# How long a relay's handoff is allowed to take before we call it "blocked".
# Matches MAIL_TIMEOUT's intent (10s render-by-default) but short enough that
# a blackholed port (25/465/587) fails far faster than a human would notice.
_PROBE_TIMEOUT = 8

# A port on 127.0.0.1 is guaranteed to refuse us immediately (RST, not a drop),
# which is exactly what we use to exercise the same code path locally without
# needing a real relay. Used by the unit tests to bring the probe to life.
_LOCALHOST_REJECT_HOST = '127.0.0.1'

# Default relay address and port, per this project's documented config —
# configurable via env so the same code serves local dev and live renders.
_MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
_MAIL_PORT = int(os.environ.get('MAIL_PORT', 25))
_MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'false').lower() in ('true', '1', 'yes')
_MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
_MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')


def _configured():
    """Real gateway = MAIL_SERVER is set (any value)."""
    return bool(_MAIL_SERVER and _MAIL_SERVER.strip())


def _smtp_connection():
    """Return an open (or closed-at-connect) smtplib.SMTP. Never raises."""
    try:
        conn = smtplib.SMTP(_MAIL_SERVER, _MAIL_PORT, timeout=_PROBE_TIMEOUT)
    except (socket.timeout, socket.error, OSError) as exc:
        return {'ok': False, 'error': f'tcp-connect-failed: {exc}'}
    try:
        if _MAIL_USE_TLS:
            conn.starttls()
        if _MAIL_USERNAME:
            conn.login(_MAIL_USERNAME, _MAIL_PASSWORD)
        return {'ok': True, 'error': None}
    except (socket.timeout, socket.error, OSError, NotImplementedError) as exc:
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
        return {'ok': False, 'error': f'auth-or-handshake-failed: {exc}'}
    finally:
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass


def probe():
    """Run the relay check and return a health-ready posture dict.

    Safe to call many times (idempotent and cheap) — a single boot-time probe
    sets the default verdict; subsequent calls refresh it only if the config
    changes, so nothing in the request path ever triggers a probe again.
    """
    if not _configured():
        return {
            'initialized': False,
            'transport': 'unconfigured',
            'pingable': None,
            'warning': None,
            'detail': 'no MAIL_SERVER configured — plain-text mailman path is used',
        }

    result = _smtp_connection()
    if result['ok']:
        return {
            'initialized': True,
            'transport': 'smtp',
            'pingable': True,
            'warning': None,
            'detail': f'relay { _MAIL_SERVER }:{_MAIL_PORT} accepts mail after tls/login',
        }

    # Report the specific failure so the network team sees the actual symptom
    # (dropped connection vs tls-down vs auth-rejected) instead of a generic
    # "mail down" — the difference between "Render is blocking the port" and
    # "Brevo revoked our app password" is exactly the distinction that earns
    # a 20-minute vs 3-minute fix.
    return {
        'initialized': False,
        'transport': 'smtp',
        'pingable': False,
        'warning': result['error'],
        'detail': f'relay { _MAIL_SERVER }:{_MAIL_PORT} unreachable at the smtp level',
    }


def init_mail_health(app):
    """Hook create_app() calls after the MAIL_* config is loaded.

    Records the probe result in app.config so the /health route reads
    app.config['mail'] (single source of truth, initialized exactly once).
    """
    app.config['mail'] = probe()
    app.config['mail_initialized'] = True
    if not app.config['mail']['warning']:
        logger.info("mail probe: relay %s:%s ok",
                    _MAIL_SERVER, _MAIL_PORT)
    else:
        logger.warning("mail probe: %s", app.config['mail']['warning'])


def mail_health(app=None):
    """Read-only health consumer used by /health.

    ``app`` is optional (tests use it to inject a fake); called with the
    live app in production, with a dict of defaults in test doubles.
    Never raises and never blocks on the network.
    """
    if app is None:
        return _default_mail_posture()
    if app.config.get('mail_initialized'):
        return app.config['mail']
    # Boot-time probe not run (e.g. a worker boot that was skipped): treat
    # unconfigured as unknown, unreachable as a warning — never a 503, since
    # mailman still delivers plain-text and the request path is unaffected.
    mail = app.config.get('mail', {})
    if not mail.get('transport'):
        return _default_mail_posture()
    return mail


def _default_mail_posture():
    return {
        'initialized': False,
        'transport': 'unconfigured',
        'pingable': None,
        'warning': None,
        'detail': 'no MAIL_SERVER configured',
    }
