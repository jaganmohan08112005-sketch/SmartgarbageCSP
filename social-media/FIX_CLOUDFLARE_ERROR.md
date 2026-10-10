# Why Cloudflare Pages failed — and the correct fix

## ❌ What happened

```
✘ [ERROR] Could not detect a directory containing static files
```

**Cloudflare Pages = static hosting only** (HTML, CSS, JS).
**SmartGarbage = Flask (Python backend)** — it needs a server to run, so Pages
cannot host it.

---

## ✅ The correct fix

Keep the Flask app on **Render** and put **Cloudflare's CDN** in front of a
domain you own. That gives edge caching (TTFB <100ms), free SSL, DDoS
protection and Brotli compression with no code changes.

**Follow: [`docs/CLOUDFLARE_CDN_SETUP.md`](../docs/CLOUDFLARE_CDN_SETUP.md)** —
the single canonical setup guide.

> ⚠️ **Correction to earlier advice:** you cannot add `smartgarbage.onrender.com`
> to your own Cloudflare account — that hostname belongs to Render. Cloudflare
> can only proxy a **domain you control**, which then points its CNAME at the
> Render origin `smartgarbage.onrender.com`. See the canonical guide for the
> exact steps.

---

## ❌ Hosting platforms that cannot run this app

These serve static files only — the Flask backend will not run:

- Cloudflare Pages
- Vercel
- Netlify
- GitHub Pages

## ✅ What to use

- **Render** (current) — add Cloudflare CDN in front, per the canonical guide.
- Any container/PaaS host that runs Python — but Cloudflare is the CDN, not the host.

For the project's supported deployment path, see `DEPLOY.md`.
