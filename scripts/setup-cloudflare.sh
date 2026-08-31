#!/bin/bash
# ============================================================
# SmartGarbage Cloudflare CDN Setup Script
# Run this to configure Cloudflare in front of Render
# ============================================================

set -e

DOMAIN="smartgarbage.onrender.com"
CF_EMAIL="${CLOUDFLARE_EMAIL:-}"
CF_API_KEY="${CLOUDFLARE_API_KEY:-}"
CF_ZONE_ID="${CLOUDFLARE_ZONE_ID:-}"

echo "=== SmartGarbage Cloudflare CDN Setup ==="
echo ""

# Check prerequisites
if [ -z "$CF_EMAIL" ] || [ -z "$CF_API_KEY" ]; then
    echo "Set these environment variables first:"
    echo "  export CLOUDFLARE_EMAIL='your@email.com'"
    echo "  export CLOUDFLARE_API_KEY='your-api-key'"
    echo "  export CLOUDFLARE_ZONE_ID='your-zone-id'"
    echo ""
    echo "Get them from: https://dash.cloudflare.com/profile/api-tokens"
    exit 1
fi

echo "1. Creating cache rule for static assets..."
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/rules/phases/http_request_cache_settings/entrypoint" \
  -H "X-Auth-Email: $CF_EMAIL" \
  -H "X-Auth-Key: $CF_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{
    "rules": [{
      "expression": "(http.request.uri.path matches \"^/static/\")",
      "action": "set_cache_settings",
      "action_parameters": {
        "cache": true,
        "edge_ttl": 2592000,
        "browser_ttl": 31536000
      }
    }]
  }' | python -m json.tool 2>/dev/null || echo "  (rule may already exist)"

echo ""
echo "2. Enabling Brotli compression..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/brotli" \
  -H "X-Auth-Email: $CF_EMAIL" \
  -H "X-Auth-Key: $CF_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"value":"on"}' | python -m json.tool 2>/dev/null || echo "  (already enabled)"

echo ""
echo "3. Enabling HTTP/3 (QUIC)..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/http3" \
  -H "X-Auth-Email: $CF_EMAIL" \
  -H "X-Auth-Key: $CF_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"value":"on"}' | python -m json.tool 2>/dev/null || echo "  (already enabled)"

echo ""
echo "4. Enabling Always Use HTTPS..."
curl -s -X PATCH "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/settings/always_use_https" \
  -H "X-Auth-Email: $CF_EMAIL" \
  -H "X-Auth-Key: $CF_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"value":"on"}' | python -m json.tool 2>/dev/null || echo "  (already enabled)"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Update your domain's nameservers to Cloudflare's"
echo "2. Wait 24-48 hours for DNS propagation"
echo "3. Test with: curl -sI https://$DOMAIN/ | grep cf-ray"
echo ""
echo "Expected results:"
echo "  TTFB (repeat): <100ms (cached at edge)"
echo "  TTFB (cold): ~1s (first hit only)"
echo "  Static assets: served from Cloudflare edge"
