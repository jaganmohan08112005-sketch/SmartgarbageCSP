#!/bin/bash
# ============================================================
# SmartGarbage Cloudflare CDN — Automated Setup Script
# ============================================================
# This script automates Cloudflare CDN setup via the API.
#
# PREREQUISITES:
#   1. A Cloudflare account (free) → https://dash.cloudflare.com/sign-up
#   2. A domain added to Cloudflare (see docs/CLOUDFLARE_CDN_SETUP.md)
#   3. Cloudflare API token → https://dash.cloudflare.com/profile/api-tokens
#
# USAGE:
#   export CF_API_TOKEN="your-api-token"
#   export CF_ZONE_ID="your-zone-id"
#   bash scripts/cloudflare-setup.sh
#
# HOW TO GET YOUR CREDENTIALS:
#   1. Go to https://dash.cloudflare.com/profile/api-tokens
#   2. Click "Create Token"
#   3. Use "Edit zone DNS" template
#   4. Select your zone (domain)
#   5. Copy the token → CF_API_TOKEN
#   6. Go to your domain → Overview → copy Zone ID → CF_ZONE_ID
# ============================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; exit 1; }
info()  { echo -e "${BLUE}ℹ${NC} $1"; }

# ============================================================
# 1. Validate Prerequisites
# ============================================================
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  SmartGarbage Cloudflare CDN Setup"
echo "═══════════════════════════════════════════════════════════"
echo ""

if [ -z "${CF_API_TOKEN:-}" ]; then
    error "Set CF_API_TOKEN first:\n  export CF_API_TOKEN='your-api-token'\n\nGet it from: https://dash.cloudflare.com/profile/api-tokens"
fi

if [ -z "${CF_ZONE_ID:-}" ]; then
    error "Set CF_ZONE_ID first:\n  export CF_ZONE_ID='your-zone-id'\n\nFind it at: https://dash.cloudflare.com → your domain → Overview"
fi

ORIGIN="smartgarbage.onrender.com"

# Verify API access
info "Verifying Cloudflare API access..."
ZONE_INFO=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json")

if echo "$ZONE_INFO" | grep -q '"success":true'; then
    ZONE_NAME=$(echo "$ZONE_INFO" | python -c "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null || echo "unknown")
    log "Connected to zone: $ZONE_NAME"
else
    error "Invalid API token or Zone ID. Check your credentials."
fi

echo ""

# ============================================================
# 2. Add DNS Records
# ============================================================
echo "── Step 1: Adding DNS records ──"

# Add root domain CNAME
info "Adding CNAME for @ (root domain)..."
DNS_RESULT=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{
        \"type\": \"CNAME\",
        \"name\": \"@\",
        \"content\": \"$ORIGIN\",
        \"ttl\": 1,
        \"proxied\": true
    }")

if echo "$DNS_RESULT" | grep -q '"success":true'; then
    log "CNAME @ → $ORIGIN (proxied ✅)"
else
    EXISTING=$(echo "$DNS_RESULT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors',[{}])[0].get('code',''))" 2>/dev/null)
    if [ "$EXISTING" = "81057" ]; then
        warn "CNAME @ already exists — skipping"
    else
        warn "Could not add CNAME @: $(echo "$DNS_RESULT" | head -c 200)"
    fi
fi

# Add www CNAME
info "Adding CNAME for www..."
DNS_RESULT=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{
        \"type\": \"CNAME\",
        \"name\": \"www\",
        \"content\": \"$ORIGIN\",
        \"ttl\": 1,
        \"proxied\": true
    }")

if echo "$DNS_RESULT" | grep -q '"success":true'; then
    log "CNAME www → $ORIGIN (proxied ✅)"
else
    EXISTING=$(echo "$DNS_RESULT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors',[{}])[0].get('code',''))" 2>/dev/null)
    if [ "$EXISTING" = "81057" ]; then
        warn "CNAME www already exists — skipping"
    else
        warn "Could not add CNAME www: $(echo "$DNS_RESULT" | head -c 200)"
    fi
fi

echo ""

# ============================================================
# 3. Configure SSL
# ============================================================
echo "── Step 2: Configuring SSL ──"

# Set SSL mode to Full (Strict)
info "Setting SSL to Full (Strict)..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/ssl" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"strict"}' > /dev/null 2>&1
log "SSL mode: Full (Strict)"

# Enable Always Use HTTPS
info "Enabling Always Use HTTPS..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/always_use_https" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"on"}' > /dev/null 2>&1
log "Always Use HTTPS: ON"

# Enable Automatic HTTPS Rewrites
info "Enabling Automatic HTTPS Rewrites..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/automatic_https_rewrites" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"on"}' > /dev/null 2>&1
log "Automatic HTTPS Rewrites: ON"

echo ""

# ============================================================
# 4. Enable Performance Features
# ============================================================
echo "── Step 3: Enabling performance features ──"

# Enable Brotli
info "Enabling Brotli compression..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/brotli" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"on"}' > /dev/null 2>&1
log "Brotli compression: ON"

# Enable HTTP/3
info "Enabling HTTP/3 (QUIC)..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/http3" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"on"}' > /dev/null 2>&1
log "HTTP/3 (QUIC): ON"

# Enable Early Hints
info "Enabling 103 Early Hints..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/103" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"on"}' > /dev/null 2>&1
log "103 Early Hints: ON"

# Enable WebSockets
info "Enabling WebSockets..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/websockets" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"value":"on"}' > /dev/null 2>&1
log "WebSockets: ON"

echo ""

# ============================================================
# 5. Cache Rules (ordered: bypass -> static -> public HTML)
# ============================================================
# Cache Rules are evaluated in order and the FIRST match wins, so the bypass
# rule is listed first: authenticated/private routes are never edge-cached,
# even though a later rule might otherwise match them. Page Rules were dropped
# deliberately -- the old "Cache Everything" Page Rule cached the entire zone
# (citizen and admin pages included) for two hours, the exact failure mode the
# guide warns about. The origin also sends `Cache-Control: no-store` on
# authenticated pages, as a second layer.
echo "-- Step 4: Creating Cache Rules --"

info "Writing ordered Cache Rules (bypass -> static -> public HTML)..."

CACHE_RULES=$(cat <<'JSON'
{
  "rules": [
    {
      "description": "Bypass dynamic, authenticated and always-fresh routes",
      "expression": "(starts_with(http.request.uri.path, \"/admin\") or starts_with(http.request.uri.path, \"/login\") or starts_with(http.request.uri.path, \"/logout\") or starts_with(http.request.uri.path, \"/register\") or starts_with(http.request.uri.path, \"/dashboard\") or starts_with(http.request.uri.path, \"/report\") or starts_with(http.request.uri.path, \"/api/\") or starts_with(http.request.uri.path, \"/webhook/\") or starts_with(http.request.uri.path, \"/set-lang\") or starts_with(http.request.uri.path, \"/payt\") or starts_with(http.request.uri.path, \"/track\") or starts_with(http.request.uri.path, \"/mfa\") or starts_with(http.request.uri.path, \"/notifications\") or http.request.uri.path eq \"/robots.txt\" or http.request.uri.path eq \"/sitemap.xml\" or http.request.uri.path eq \"/feed.xml\")",
      "action": "set_cache_settings",
      "action_parameters": { "cache": false },
      "enabled": true
    },
    {
      "description": "Cache static assets (content-hashed, immutable)",
      "expression": "starts_with(http.request.uri.path, \"/static/\")",
      "action": "set_cache_settings",
      "action_parameters": {
        "cache": true,
        "edge_ttl": { "mode": "override", "default": 2592000 },
        "browser_ttl": { "mode": "override", "default": 31536000 }
      },
      "enabled": true
    },
    {
      "description": "Cache public HTML pages (5 min edge / 1 min browser)",
      "expression": "(http.request.uri.path eq \"/\" or http.request.uri.path eq \"/schedule\" or http.request.uri.path eq \"/about\" or http.request.uri.path eq \"/faq\" or http.request.uri.path eq \"/transparency\" or http.request.uri.path eq \"/privacy\" or http.request.uri.path eq \"/terms\")",
      "action": "set_cache_settings",
      "action_parameters": {
        "cache": true,
        "edge_ttl": { "mode": "override", "default": 300 },
        "browser_ttl": { "mode": "override", "default": 60 }
      },
      "enabled": true
    }
  ]
}
JSON
)

CACHE_RESULT=$(curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets/phases/http_request_cache_settings/entrypoint" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "$CACHE_RULES")

if echo "$CACHE_RESULT" | grep -q '"success":true'; then
    log "Cache Rules set: bypass dynamic -> static (30d/1y) -> public HTML (5min/1min)"
else
    warn "Could not set Cache Rules: $(echo "$CACHE_RESULT" | head -c 300)"
fi

echo ""

# ============================================================
# 6. Verify Setup
# ============================================================
echo "── Step 6: Verifying setup ──"

# Check DNS resolution
info "Checking DNS resolution..."
RESOLVED=$(dig +short "$ZONE_NAME" CNAME 2>/dev/null || echo "")
if echo "$RESOLVED" | grep -q "$ORIGIN"; then
    log "DNS resolves correctly: $ZONE_NAME → $ORIGIN"
else
    warn "DNS may not have propagated yet. Check in 5-10 minutes."
fi

# Check if Cloudflare is proxying
info "Checking Cloudflare proxy..."
CF_RAY=$(curl -sI "https://$ZONE_NAME/" 2>/dev/null | grep -i "cf-ray" | head -1 || echo "")
if [ -n "$CF_RAY" ]; then
    log "Cloudflare is active: $CF_RAY"
else
    warn "Cloudflare not detected yet. DNS may still be propagating."
fi

# Check cache status
info "Checking cache status..."
CF_CACHE=$(curl -sI "https://$ZONE_NAME/" 2>/dev/null | grep -i "cf-cache-status" | head -1 || echo "")
if [ -n "$CF_CACHE" ]; then
    log "Cache status: $CF_CACHE"
else
    warn "Cache status not available yet."
fi

echo ""

# ============================================================
# 7. Print Summary
# ============================================================
echo "═══════════════════════════════════════════════════════════"
echo "  Setup Complete! 🎉"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  Domain:     https://$ZONE_NAME"
echo "  Origin:     https://$ORIGIN"
echo "  SSL:        Full (Strict)"
echo "  Proxy:      ON (orange cloud)"
echo ""
echo "  Cache Rules (ordered, first match wins):"
echo "    Bypass:         /admin /login /dashboard /report /api/ /webhook/ ..."
echo "    Static assets:  Edge 30 days, Browser 1 year"
echo "    Public HTML:    Edge 5 min, Browser 1 min"
echo ""
echo "  Features:"
echo "    ✅ Brotli compression"
echo "    ✅ HTTP/3 (QUIC)"
echo "    ✅ 103 Early Hints"
echo "    ✅ Always Use HTTPS"
echo "    ✅ WebSockets"
echo ""
echo "  Expected TTFB:"
echo "    Cold start:    <100ms (from edge)"
echo "    Repeat visit:  <10ms (from edge cache)"
echo ""
echo "  Next steps:"
echo "    1. Wait for DNS to propagate (Cloudflare nameservers)"
echo "    2. Add the custom domain (apex + www) in the Render dashboard"
echo "    3. Verify edge caching + TTFB:"
echo "         bash scripts/verify_edge_caching.sh $ZONE_NAME"
echo ""
echo "  Dashboard: https://dash.cloudflare.com"
echo "═══════════════════════════════════════════════════════════"
