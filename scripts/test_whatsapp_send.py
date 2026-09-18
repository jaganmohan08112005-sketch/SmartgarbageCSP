#!/usr/bin/env python3
"""One-command self-test for the Meta WhatsApp Cloud credentials.

Verifies, in order:
  1. Both env vars present (WHATSAPP_CLOUD_TOKEN, WHATSAPP_CLOUD_PHONE_NUMBER_ID)
  2. Token is valid and has whatsapp_business_messaging      -> GET /{phone-id}
  3. A real text message send to WHATSAPP_TEST_TO (or --to)  -> POST /messages

Run from the project root after pasting credentials into .env (or exporting):

    python scripts/test_whatsapp_send.py --to 919876543210

Exit codes: 0 = a real WhatsApp message was accepted by Meta;
            1 = configuration/credential failure (the exact Meta error is
                printed so you know what to fix in the App Dashboard).
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Load .env if present (same parser as the preview launcher).
env_file = os.path.join(ROOT, '.env')
if os.path.exists(env_file):
    with open(env_file, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

import requests


def fail(step, msg):
    print(f"  FAIL [{step}] {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--to', help='recipient phone in E.164 digits, e.g. 919876543210 '
                                 '(defaults to $WHATSAPP_TEST_TO)')
    args = ap.parse_args()

    token = os.environ.get('WHATSAPP_CLOUD_TOKEN', '').strip()
    phone_id = os.environ.get('WHATSAPP_CLOUD_PHONE_NUMBER_ID', '').strip()

    print('1. Env vars present?')
    if not token or not phone_id:
        fail('env', 'WHATSAPP_CLOUD_TOKEN / WHATSAPP_CLOUD_PHONE_NUMBER_ID missing.\n'
                    '   Paste them into .env (local) or Render -> Environment (live).')
    print(f'  OK  token {token[:8]}... phone_number_id {phone_id}')

    print('2. Token valid for this number?')
    r = requests.get(f'https://graph.facebook.com/v21.0/{phone_id}',
                     params={'access_token': token}, timeout=10)
    if r.status_code != 200:
        err = (r.json() or {}).get('error', {})
        fail('auth', f"Meta rejected the token/ID (HTTP {r.status_code}: "
                     f"{err.get('code')} {err.get('message', '')[:200]}).\n"
                     "   Fix: App Dashboard -> WhatsApp -> API Setup -> regenerate the "
                     "access token; make sure Phone Number ID (not the phone number) is copied.")
    display = (r.json() or {}).get('display_phone_number', '?')
    name = (r.json() or {}).get('verified_name', '?')
    print(f'  OK  number +{display} ("{name}")')

    to = (args.to or os.environ.get('WHATSAPP_TEST_TO', '')).strip()
    if not to:
        print('3. Send test: SKIPPED (no --to given). Credentials are VALID — '
              'run with --to 91XXXXXXXXXX to receive a real message.')
        return
    to = ''.join(c for c in to if c.isdigit())

    print(f'3. Sending test text to +{to} ...')
    r = requests.post(
        f'https://graph.facebook.com/v21.0/{phone_id}/messages',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        json={'messaging_product': 'whatsapp', 'recipient_type': 'individual',
              'to': to, 'type': 'text',
              'text': {'preview_url': False,
                       'body': 'SmartGarbage test: your WhatsApp OTP channel is live.'}},
        timeout=15)
    if r.status_code // 100 == 2:
        print('  OK  Meta accepted the message — check the phone for the WhatsApp text.')
        print('      (If nothing arrived, the recipient must have messaged the test')
        print('       number once — "Hi" — or be added under API Setup -> To.)')
        print('ALL GREEN')
        return
    err = (r.json() or {}).get('error', {})
    code = err.get('code')
    if code == 131047:
        fail('send', "no open 24h service window with this recipient.\n"
                     "   Fix: from the recipient's phone, send 'Hi' to the test number\n"
                     "   (or add it under API Setup -> To), then re-run.")
    if code == 131030:
        fail('send', 'recipient not in the allowed recipient list.\n'
                     '   Fix: App Dashboard -> WhatsApp -> API Setup -> To -> add the number.')
    fail('send', f"HTTP {r.status_code}: {code} {err.get('message', '')[:220]}")


if __name__ == '__main__':
    main()
