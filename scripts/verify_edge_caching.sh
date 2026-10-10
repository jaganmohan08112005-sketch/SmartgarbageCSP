#!/usr/bin/env bash
# ============================================================
# SmartGarbage — Cloudflare edge-cache & TTFB verification
# ============================================================
# Confirms the custom domain is actually being served through YOUR Cloudflare
# zone with edge caching, and reports TTFB. Run it after the custom domain is
# live and `scripts/cloudflare-setup.sh` has configured the cache rules.
#
#   bash scripts/verify_edge_caching.sh                # defaults to smartgarbage.eu.org
#   bash scripts/verify_edge_caching.sh example.org
#
# Expected on a correctly configured zone:
#   - cf-ray header present            (Cloudflare is in front)
#   - vary does NOT contain Cookie     (LLM/CDN cacheable)
#   - /static/style.css -> cf-cache-status: HIT
#   - / -> MISS then HIT
#   - TTFB < 0.1s on a HIT  (vs ~1.2s cold at the Render origin)
#
# Exit codes:
#   0  every check passed
#   1  one or more checks failed (or the host was unreachable)
# ============================================================

set -uo pipefail

HOST="${1:-${EDGE_HOST:-smartgarbage.eu.org}}"
HOST="${HOST#http://}"; HOST="${HOST#https://}"; HOST="${HOST%%/*}"
BASE="https://$HOST"
MAX_TIME=30
SAMPLES=5

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()    { echo -e "${GREEN}PASS${NC} $1"; }
bad()   { echo -e "${RED}FAIL${NC} $1"; FAILED=1; }
warn()  { echo -e "${YELLOW}WARN${NC} $1"; }
info()  { echo -e "${BLUE}INFO${NC} $1"; }
FAILED=0

hdr() { curl -sI --max-time "$MAX_TIME" "$1" 2>/dev/null; }
cf_status() { hdr "$1" | tr -d '\r' | awk -F': ' 'tolower($1)=="cf-cache-status"{print $2}' | head -1; }

echo ""
echo "==========================================================="
echo "  Edge caching & TTFB verification — $BASE"
echo "==========================================================="
echo ""

if ! hdr "$BASE/" >/dev/null 2>&1; then
    bad "could not reach $BASE/ — check DNS, the Render custom domain, and Cloudflare proxying"
    echo ""; exit 1
fi

# ── 1. Cloudflare in front ───────────────────────────────────
if hdr "$BASE/" | tr -d '\r' | grep -qi '^cf-ray:'; then
    ok "Cloudflare is in front (cf-ray present)"
else
    bad "no cf-ray header — the domain is not proxied by Cloudflare (orange cloud OFF?)"
fi

# ── 2. Vary must not leak Cookie ─────────────────────────────
VARY=$(hdr "$BASE/" | tr -d '\r' | awk -F': ' 'tolower($1)=="vary"{print $2}' | head -1)
if echo "$VARY" | grep -qi 'cookie'; then
    bad "vary contains Cookie ('$VARY') — HTML will never be edge-cached"
else
    ok "vary is cache-friendly (${VARY:-<none>})"
fi

# ── 3. Static asset cached ───────────────────────────────────
STATIC_STATUS=$(cf_status "$BASE/static/style.css")
case "$STATIC_STATUS" in
    HIT)      ok "static asset cached (cf-cache-status: HIT)" ;;
    MISS)     warn "static asset MISS — re-run; the next request should be a HIT" ;;
    "")       bad "no cf-cache-status on /static/style.css — not going through Cloudflare" ;;
    *)        bad "static asset cf-cache-status: $STATIC_STATUS (expected HIT)" ;;
esac

# ── 4. HTML MISS -> HIT ──────────────────────────────────────
FIRST=$(cf_status "$BASE/"); sleep 1; SECOND=$(cf_status "$BASE/")
info "HTML cf-cache-status: first=${FIRST:-<none>} second=${SECOND:-<none>}"
case "${SECOND:-$FIRST}" in
    HIT)  ok "public HTML is edge-cached (HIT)" ;;
    MISS|EXPIRED) warn "HTML still $SECOND — the public-HTML cache rule may not be deployed" ;;
    DYNAMIC) bad "HTML is DYNAMIC — no cache rule matches / (see docs/CLOUDFLARE_CDN_SETUP.md Step 5)" ;;
    *)    warn "HTML cf-cache-status: ${SECOND:-<none>}" ;;
esac

# ── 5. TTFB samples ──────────────────────────────────────────
echo ""
info "TTFB over $SAMPLES requests to $BASE/ ..."
TIMES=""
for i in $(seq 1 "$SAMPLES"); do
    t=$(curl -o /dev/null -s --max-time "$MAX_TIME" -w '%{time_starttransfer}' "$BASE/" 2>/dev/null)
    printf "  sample %d: %ss\n" "$i" "${t:-n/a}"
    TIMES="$TIMES $t"
done
STATS=$(echo "$TIMES" | awk '{n=0;min=1e9;max=0;sum=0;for(i=1;i<=NF;i++){v=$i+0;if(v<=0)continue;n++;if(v<min)min=v;if(v>max)max=v;sum+=v}if(n>0)printf "%.3f %.3f %.3f", min, sum/n, max}')
if [ -n "$STATS" ]; then
    MIN=$(echo "$STATS" | cut -d' ' -f1); AVG=$(echo "$STATS" | cut -d' ' -f2); MAX=$(echo "$STATS" | cut -d' ' -f3)
    info "TTFB min=${MIN}s avg=${AVG}s max=${MAX}s"
    if awk "BEGIN{exit !($MIN < 0.1)}"; then
        ok "fastest TTFB ${MIN}s < 0.1s target (edge cache hit)"
    else
        warn "fastest TTFB ${MIN}s >= 0.1s target — expected only once HTML is a cache HIT"
    fi
else
    warn "no TTFB samples collected"
fi

echo ""
echo "==========================================================="
if [ "$FAILED" = "0" ]; then
    echo -e "  ${GREEN}All critical checks passed.${NC}"
else
    echo -e "  ${RED}Some checks failed — see above.${NC}"
fi
echo "  Guide: docs/CLOUDFLARE_CDN_SETUP.md"
echo "==========================================================="
echo ""
exit "$FAILED"
