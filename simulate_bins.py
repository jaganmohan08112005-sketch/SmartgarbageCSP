"""Continuous IoT telemetry simulator for SmartGarbage.

Posts realistic, incremental fill-level increases to /api/bin-telemetry for
every seeded SmartBin so the admin control-room map updates live (via the
flask-socketio bin_update push) without needing real ESP32 hardware.

Usage:
    python simulate_bins.py            # loop forever, ~5s between ticks
    python simulate_bins.py --once    # single tick then exit
    python simulate_bins.py --host http://localhost:5000 --interval 3
"""
import argparse
import random
import time

import requests

DEFAULT_HOST = "http://localhost:5000"


def tick(host):
    """Send one telemetry frame per bin. Returns (sent, failed)."""
    # Read the live bin list from the API so we always target real hardware IDs.
    try:
        bins = requests.get(f"{host}/api/bins", timeout=5).json()
    except Exception as e:
        print(f"[sim] could not fetch bins: {e}")
        return 0, 0

    sent = failed = 0
    for b in bins:
        level = int(b.get("level", 0))
        # Drift upward, occasionally dip after a hypothetical collection.
        delta = random.choice([0, 2, 3, 5, 7, -10])
        new_level = max(0, min(100, level + delta))
        payload = {
            "hardware_id": b["hardware_id"],
            "level": new_level,
            "temperature": round(random.uniform(24.0, 34.0), 1),
            "methane": random.randint(40, 220),
            "battery_level": random.randint(70, 100),
        }
        try:
            r = requests.post(f"{host}/api/bin-telemetry", json=payload, timeout=5)
            if r.status_code == 200:
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    print(f"[sim] ticked {sent} bins ({failed} failed)")
    return sent, failed


def main():
    ap = argparse.ArgumentParser(description="SmartGarbage IoT telemetry simulator")
    ap.add_argument("--host", default=DEFAULT_HOST, help="Base URL of the running app")
    ap.add_argument("--interval", type=float, default=5.0, help="Seconds between ticks")
    ap.add_argument("--once", action="store_true", help="Run a single tick and exit")
    args = ap.parse_args()

    if args.once:
        tick(args.host)
        return
    print(f"[sim] streaming telemetry to {args.host} every {args.interval}s (Ctrl+C to stop)")
    try:
        while True:
            tick(args.host)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[sim] stopped.")


if __name__ == "__main__":
    main()
