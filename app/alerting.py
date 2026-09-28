"""Failure alerting for the SmartGarbage portal.

The uptime workflow (.github/workflows/uptime.yml) can only see what an
anonymous HTTP probe sees: down, slow, or /health reporting unhealthy. It
cannot see a runtime error inside a single request — an unhandled exception
renders a 500 page for that one visitor while every probe stays green. This
module closes that gap: when a 500 escapes, we open (or update) a GitHub
issue, which emails the owner through GitHub notifications.

Rs. 0 design, no new dependencies:
  - `requests` is already a runtime dependency.
  - Credentials: ALERT_GITHUB_TOKEN env (a free fine-grained PAT with
    "issues: write") when set; otherwise the machine's stored git credential
    (handy locally, where the landing pass already uses it). On Render only
    the env var exists — a PAT costs nothing to mint.
  - Gated by env so tests, local dev, and CI never file issues:
      ALERT_ISSUES=1                 enable the reporter (off unless set)
      ALERT_GITHUB_TOKEN=ghp_...     PAT with "issues: write" (Render path)
      ALERT_GITHUB_REPO=owner/name   target repo (default: the live repo)
  - Deduplicated per outage window (fingerprint + UTC day): the first
    occurrence files the issue, later ones add a recurrence comment.
  - Runs in a fire-and-forget daemon thread: the failing request must never
    wait on the GitHub API (the same lesson as the MAIL_TIMEOUT hang fix).
  - Fails soft: every failure path is swallowed and logged. Alerting must
    never turn a 500 into a bigger problem.
"""

import logging
import os
import subprocess
import threading
import time

import requests

logger = logging.getLogger(__name__)

_ALERT_TIMEOUT = 10  # seconds — alerting must never hang a request for long
_DEFAULT_REPO = 'jaganmohan08112005-sketch/SmartgarbageCSP'

_tls = threading.local()


def _alerting_enabled():
    return os.environ.get('ALERT_ISSUES') == '1'


def _repo():
    return os.environ.get('ALERT_GITHUB_REPO', _DEFAULT_REPO)


def _api_url(endpoint):
    return f'https://api.github.com/repos/{_repo()}/{endpoint}'


def _github_token():
    """Resolve the GitHub token without ever logging it.

    ALERT_GITHUB_TOKEN (the production path — Render has no stored git
    credential) wins; otherwise the machine's stored https://github.com
    credential is used so local runs need zero setup. None when neither.
    """
    env_token = os.environ.get('ALERT_GITHUB_TOKEN')
    if env_token:
        return env_token
    try:
        proc = subprocess.run(
            ['git', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n',
            capture_output=True, text=True, timeout=_ALERT_TIMEOUT,
        )
        for line in proc.stdout.splitlines():
            if line.startswith('password='):
                return line.split('=', 1)[1].strip()
    except Exception as exc:  # never let alerting break the request
        logger.warning("alerting: credential lookup failed: %s", exc)
    return None


def _window_key(fingerprint):
    """Outage window: exception type + UTC day. New day => new issue."""
    return f'{fingerprint} — {time.strftime("%Y-%m-%d", time.gmtime())}'


def _find_open_issue(headers, key):
    """Return the number of the open 500-alert issue for this window.

    The search is an exact-title phrase so distinct fingerprints and
    different days get distinct issues; the title check is belt-and-suspenders
    against search-index fuzziness.
    """
    try:
        resp = requests.get(
            'https://api.github.com/search/issues',
            headers=headers,
            params={'q': f'repo:{_repo()} is:issue is:open "[500] {key}" in:title',
                    'per_page': 5},
            timeout=_ALERT_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        for item in resp.json().get('items', []):
            title = item.get('title') or ''
            if '[500]' in title and key in title:
                return item['number']
    except Exception:
        logger.exception("alerting: issue search failed")
    return None


def _report_exception(exc, fingerprint, path):
    """File or update the GitHub issue for one error window. Fails soft."""
    try:
        token = _github_token()
        if not token:
            logger.warning("alerting: no GitHub credential; 500 not filed")
            return
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github+json',
        }
        stamp = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())
        key = _window_key(fingerprint)
        existing = _find_open_issue(headers, key)
        if existing:
            requests.post(
                _api_url(f'issues/{existing}/comments'),
                headers=headers,
                json={'body': (f"🔁 Recurred at {stamp} on `{path}`:\n"
                               f"```\n{exc}\n```")},
                timeout=_ALERT_TIMEOUT,
            )
            logger.info("alerting: updated issue #%s", existing)
            return
        body = (
            f"## Runtime error (500)\n\n"
            f"**Path:** `{path}`\n"
            f"**First seen:** {stamp}\n\n"
            f"```\n{exc}\n```\n\n"
            f"The full traceback is in the Render logs for this timestamp. "
            f"This issue is filed automatically by `app/alerting.py` "
            f"(ALERT_ISSUES=1): the first occurrence in a window opens the "
            f"issue, later occurrences add recurrence comments. The uptime "
            f"workflow never closes this — resolve manually after a fix "
            f"ships."
        )
        resp = requests.post(
            _api_url('issues'),
            headers=headers,
            json={
                'title': f'[500] {key} — {path}',
                'body': body,
                'labels': ['runtime-error'],
            },
            timeout=_ALERT_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            logger.info("alerting: filed issue #%s", resp.json().get('number'))
        else:
            logger.warning("alerting: issue create failed: HTTP %s",
                           resp.status_code)
    except Exception:
        logger.exception("alerting: failed to report 500")


def report_exception(exc, path):
    """Public entry point for error handlers.

    No-op unless ALERT_ISSUES=1, so local dev, tests, and CI never file
    issues. Per-request re-entrancy guard: one report even if handling the
    exception raises again.
    """
    if not _alerting_enabled():
        return
    if getattr(_tls, 'reporting', False):
        return
    _tls.reporting = True
    try:
        fingerprint = type(exc).__name__ or 'Exception'
        # Offload: a failing request must not wait on the GitHub API (the
        # same failure class as the MAIL_TIMEOUT hang). Daemon thread dies
        # quietly with the worker if the process is going away anyway.
        threading.Thread(
            target=_report_exception, args=(exc, fingerprint, path),
            daemon=True, name='sg-alert-500',
        ).start()
    finally:
        _tls.reporting = False
