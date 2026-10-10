# WWW Canonicalization Setup

SEO auditors flag that the `www` host doesn't redirect to the apex domain. Once
a custom domain is live, `www.<domain>` and `<domain>` are separate hostnames;
the Flask middleware in `app/__init__.py` (`redirect_www`, gated on
`_is_deployed()`) already **301-redirects `www.<domain>` to the bare domain**, so
the only requirement is that the `www` host actually resolves to the app.

> **Earlier revisions of this guide told you to add
> `www.smartgarbage.onrender.com` as a custom domain. That is impossible** —
> `onrender.com` belongs to Render, and you cannot add a subdomain of a domain
> you do not control. The steps below use the custom domain
> (`smartgarbage.eu.org`).

## Steps (custom domain)

1. **Render** → your service → **Settings → Custom Domains** → **Add Custom
   Domain**: add **both** the apex (`smartgarbage.eu.org`) and the `www` host
   (`www.smartgarbage.eu.org`). Render issues TLS for each.
2. **Cloudflare** → **DNS → Records**: both proxied CNAMEs must point at the
   Render origin (the orange cloud must be ON). `scripts/cloudflare-setup.sh`
   creates them:

   | Type | Name | Content | Proxy |
   |---|---|---|---|
   | CNAME | `@` | `smartgarbage.onrender.com` | 🟠 Proxied |
   | CNAME | `www` | `smartgarbage.onrender.com` | 🟠 Proxied |

3. That's it — the app's middleware handles the redirect. No Render "redirect
   rule" and no Cloudflare Page Rule is required.

## How the redirect works

`app/__init__.py` registers a `before_request` hook that, in production,
301-redirects any request whose host starts with `www.` to the same URL with the
`www.` stripped. It only fires on the deployed platform, so local development is
unaffected. Because it derives the target from `request.host`, it works for
whatever custom domain is configured — there is no per-domain code change.

> **Alternative (edge redirect):** a Cloudflare **Redirect Rule** or **Bulk
> Redirect** `www.<domain>/*` → `https://<domain>/$1` (301) does the same at the
> edge and avoids a round-trip to the origin. Optional — the app already covers
> it.

## Verification

```bash
# www must 301 to the apex domain
curl -sI https://www.smartgarbage.eu.org/ | grep -iE "^(HTTP|location)"
#   HTTP/2 301
#   location: https://smartgarbage.eu.org/
```

If `www` fails to resolve, the CNAME is missing or not proxied, or the domain
has not been added in the Render dashboard.
