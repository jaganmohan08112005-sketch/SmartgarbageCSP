"""
eu.org Domain Approval Monitor
===============================
Polls DNS every 60 seconds to detect when smartgarbage.eu.org is approved.
When approved, plays a sound + desktop notification + logs to file.

Usage:
    python monitor_euorg.py              # Check every 60s
    python monitor_euorg.py --interval 30  # Check every 30s
    python monitor_euorg.py --once         # Check once and exit
"""
import subprocess
import sys
import time
import json
import os
from datetime import datetime

DOMAIN = "smartgarbage.eu.org"
DNS_SERVERS = ["8.8.8.8", "1.1.1.1"]
LOG_FILE = "euorg_monitor.log"
STATE_FILE = "euorg_monitor_state.json"

# ── Colors for terminal output ──
class C:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def check_dns():
    """Check if the domain resolves on any DNS server."""
    for server in DNS_SERVERS:
        try:
            result = subprocess.run(
                ["nslookup", DOMAIN, server],
                capture_output=True, text=True, timeout=10
            )
            # Check BOTH stdout and stderr for failure indicators
            combined = result.stdout + result.stderr
            # Domain does NOT resolve if these failure messages appear
            if any(msg in combined for msg in [
                "Non-existent domain",
                "NXDOMAIN",
                "can't find",
                "server can't find",
            ]):
                continue
            # Domain resolves — extract IP or confirm delegation
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line and not line.startswith("Server:") and not line.startswith("Address:") and "Name:" not in line:
                    if any(c.isdigit() for c in line) and "." in line:
                        return True, server, line
            # No IP found but no error — domain is delegated but has no A record
            return True, server, "delegated (no A record)"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return False, None, None


def check_ns_delegation():
    """Check if eu.org has delegated NS records to Hurricane Electric."""
    for server in DNS_SERVERS:
        try:
            result = subprocess.run(
                ["nslookup", "-type=NS", DOMAIN, server],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout
            if "he.net" in output.lower() or "ns1.he.net" in output.lower():
                return True, server
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return False, None


def play_notification_sound():
    """Play a notification sound (Windows/Mac/Linux)."""
    try:
        # Windows
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 300)
            time.sleep(0.1)
        return
    except ImportError:
        pass
    try:
        # macOS
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=5)
        return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        # Linux
        subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], timeout=5)
        return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def show_desktop_notification(title, message):
    """Show a desktop notification."""
    try:
        # Windows
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="SmartGarbage",
            timeout=30
        )
        return
    except ImportError:
        pass
    try:
        # macOS
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}"'
        ], timeout=5)
        return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        # Linux
        subprocess.run(["notify-send", title, message], timeout=5)
        return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def save_state(status, details):
    """Save monitoring state to file."""
    state = {
        "domain": DOMAIN,
        "status": status,
        "details": details,
        "last_check": datetime.now().isoformat(),
        "approved_at": datetime.now().isoformat() if status == "APPROVED" else None,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_state():
    """Load previous monitoring state."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return None


def print_banner():
    print(f"""
{C.BOLD}{C.GREEN}╔══════════════════════════════════════════════════╗
║         eu.org Domain Approval Monitor           ║
║         Domain: {DOMAIN:<31}║
╚══════════════════════════════════════════════════╝{C.RESET}

{C.DIM}Checking DNS every 60 seconds...
Press Ctrl+C to stop.{C.RESET}
""")


def print_approved(domain, server, record):
    print(f"""
{C.BOLD}{C.GREEN}🎉🎉🎉 DOMAIN APPROVED! 🎉🎉🎉{C.RESET}

{C.BOLD}Domain:{C.RESET}  {domain}
{C.BOLD}DNS:{C.RESET}      Resolving on {server}
{C.BOLD}Record:{C.RESET}   {record}
{C.BOLD}Time:{C.RESET}     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{C.BOLD}{C.CYAN}Next steps:{C.RESET}
  1. Log in to Cloudflare: https://dash.cloudflare.com
  2. Add site: {domain}
  3. Select Free plan
  4. Add CNAME record pointing to smartgarbage.onrender.com
  5. Create Page Rule: Cache Everything
  6. Add custom domain in Render dashboard
  7. TTFB will drop from ~0.7s to <0.1s!

{C.DIM}Full setup guide: CLOUDFLARE_QUICK_START.md{C.RESET}
""")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Monitor eu.org domain approval")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--once", action="store_true", help="Check once and exit")
    args = parser.parse_args()

    print_banner()

    # Check if already approved from previous run
    state = load_state()
    if state and state.get("status") == "APPROVED":
        print(f"{C.YELLOW}Domain was already approved at {state.get('approved_at')}.{C.RESET}")
        print(f"Run the Cloudflare setup if you haven't already.")
        return

    check_count = 0
    try:
        while True:
            check_count += 1
            now = datetime.now().strftime("%H:%M:%S")
            print(f"{C.DIM}[{now}] Check #{check_count}...{C.RESET}", end=" ", flush=True)

            # Check DNS resolution
            resolves, server, record = check_dns()

            if resolves:
                print(f"{C.GREEN}RESOLVING!{C.RESET}")
                log(f"DOMAIN APPROVED — resolving on {server}: {record}", "APPROVED")

                # Check NS delegation
                ns_ok, ns_server = check_ns_delegation()
                if ns_ok:
                    log(f"NS delegation confirmed via {ns_server}", "APPROVED")

                # Notify!
                play_notification_sound()
                show_desktop_notification(
                    "🎉 Domain Approved!",
                    f"{DOMAIN} is now live! Set up Cloudflare CDN now."
                )
                print_approved(DOMAIN, server, record)
                save_state("APPROVED", {"server": server, "record": record})
                return
            else:
                print(f"{C.RED}Not yet{C.RESET}")
                if check_count % 5 == 0:
                    log(f"Still pending (check #{check_count})")

            if args.once:
                return

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}Monitor stopped. Run again to resume checking.{C.RESET}")
        save_state("STOPPED", {"last_check": datetime.now().isoformat(), "checks": check_count})


if __name__ == "__main__":
    main()
