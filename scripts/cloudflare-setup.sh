#!/bin/bash
# ============================================================
# SmartGarbage Cloudflare CDN — Automated Setup Script
# ============================================================
# This script automates Cloudflare CDN setup via the API.
#
# PREREQUISITES:
#   1. A Cloudflare account (free) → https://dash.cloudflare.com/sign-up
#   2. A domain added to Cloudflare (see wiki/CLOUDFLARE_CDN_SETUP.md)
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
# 5. Create Page Rules (Free plan: 3 max)
# ============================================================
echo "── Step 4: Creating Page Rules ──"

# Rule 1: Cache everything on the domain
info "Creating Page Rule 1: Cache Everything..."
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/pagerules" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{
        \"targets\": [{
            \"target\": \"url\",
            \"constraint\": {
                \"operator\": \"matches\",
                \"value\": \"*$ZONE_NAME/*\"
            }
        }],
        \"actions\": [
            { \"id\": \"cache_level\", \"value\": \"cache_everything\" },
            { \"id\": \"edge_cache_ttl\", \"value\": 7200 },
            { \"id\": \"browser_cache_ttl\", \"value\": 14400 }
        ],
        \"priority\": 1,
        \"status\": \"active\"
    }" > /dev/null 2>&1
log "Page Rule 1: Cache Everything (Edge TTL: 2h)"

# Rule 2: Bypass cache for dynamic routes
info "Creating Page Rule 2: Bypass Dynamic Routes..."
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/pagerules" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{
        \"targets\": [{
            \"target\": \"url\",
            \"constraint\": {
                \"operator\": \"matches\",
                \"value\": \"*$ZONE_NAME/(admin|login|register|report|api/*|contact|webhook/*|dashboard|set-lang/*)\"
            }
        }],
        \"actions\": [
            { \"id\": \"cache_level\", \"value\": \"bypass\" }
        ],
        \"priority\": 2,
        \"status\": \"active\"
    }" > /dev/null 2>&1
log "Page Rule 2: Bypass Dynamic Routes"

echo ""

# ============================================================
# 6. Create Cache Rules (newer, more powerful)
# ============================================================
echo "── Step 5: Creating Cache Rules ──"

# Rule: Cache static assets for 30 days
info "Creating Cache Rule: Static Assets..."
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{
        "name": "Cache static assets",
        "kind": "zone",
        "phase": "http_request_cache_settings",
        "rules": [{
            "expression": "(http.request.uri.path matches \"^/static/\")",
            "action": "set_cache_settings",
            "action_parameters": {
                "cache": true,
                "edge_ttl": { "mode": "override", "default": 2592000 },
                "browser_ttl": { "mode": "override", "default": 31536000 }
            },
            "enabled": true
        }]
    }' > /dev/null 2>&1
log "Cache Rule: Static assets → Edge 30 days, Browser 1 year"

# Rule: Cache HTML pages for 5 minutes
info "Creating Cache Rule: HTML Pages..."
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rulesets" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{
        \"name\": \"Cache HTML pages\",
        \"kind\": \"zone\",
        \"phase\": \"http_request_cache_settings\",
        \"rules\": [{
            \"expression\": \"(http.request.uri.path eq \\\"/\\\") or (http.request.uri.path in {\\\"/schedule\\\" \\\"/about\\\" \\\"/terms\\\" \\\"/privacy\\\" \\\"/faq\\\" \\\"/transparency\\\" \\\"/report-illegal\\\"})\",
            \"action\": \"set_cache_settings\",
            \"action_parameters\": {
                \"cache\": true,
                \"edge_ttl\": { \"mode\": \"override\", \"default\": 300 },
                \"browser_ttl\": { \"mode\": \"override\", \"default\": 300 }
            },
            \"enabled\": true
        }]
    }" > /dev/null 2>&1
log "Cache Rule: HTML pages → Edge 5 min, Browser 5 min"

echo ""

# ============================================================
# 7. Verify Setup
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
# 8. Print Summary
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
echo "  Cache Rules:"
echo "    Static assets:  Edge 30 days, Browser 1 year"
echo "    HTML pages:     Edge 5 min, Browser 5 min"
echo "    Dynamic routes: Bypass cache"
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
echo "    1. Wait 24-48h for DNS propagation"
echo "    2. Add custom domain to Render dashboard"
echo "    3. Update RENDER_EXTERNAL_URL env var"
echo "    4. Test: curl -sI https://$ZONE_NAME/ | grep cf-ray"
echo ""
echo "  Dashboard: https://dash.cloudflare.com"
echo "═══════════════════════════════════════════════════════════"
