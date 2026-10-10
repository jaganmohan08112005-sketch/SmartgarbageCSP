# SmartGarbage — Machine-Audited Accessibility & Performance Report

**Target:** http://127.0.0.1:5057 (local reproduction stack — pgserver + Flask, seeded demo data)
**Run (post-remediation):** 2026-10-02 · artifact `audit/out/summary.md` generated `2026-10-02T13:46:25Z`
**Prior baseline (pre-remediation, live):** https://smartgarbage.onrender.com, 2026-10-02
**Page coverage:** 10 key public pages — `/`, `/schedule`, `/report`, `/transparency`, `/impact`, `/contact`, `/about`, `/faq`, `/track`, `/login` (all verified HTTP 200) — plus the authenticated staff portals `/worker` and `/admin`, which are axe-scanned after a real staff login (MFA developer OTP) on the local stack.

**Toolchain**

| Tool | Version | Scope |
| --- | --- | --- |
| Lighthouse | 13.5.0 | Desktop form factor, simulated throttling; categories performance / accessibility / best-practices / SEO |
| axe-core | 4.13.0 | WCAG 2.0 / 2.1 / 2.2 Level A + AA tags (`wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`) |
| Chromium | Playwright build (chromium-1243) | Shared browser engine for both tools |

Reproduce with `npm run audit` (writes raw per-page JSON to `audit/out/`). Runner: [`audit/run-audit.mjs`](../audit/run-audit.mjs).

The authenticated staff pages are part of the gate: [`audit/check-audit.mjs`](../audit/check-audit.mjs) enforces **0 axe WCAG A/AA violations** on `worker`/`admin` too (axe-only entries — no Lighthouse — because the scan runs inside a real login session). CI sets `AUDIT_EXPECT_AUTHED=worker,admin` so a silently skipped login pass fails the build rather than passing quiet. Quick re-check of just those pages: `npm run audit:auth`.

> **Measurement caveats.** All figures are **lab data** measured from a single client, not field (CrUX) data. The post-remediation run was taken against a **local stack** (`http://127.0.0.1:5057`) rather than Render, because the fixes were being verified before deploy — so **performance figures are not directly comparable to the earlier live-Render baseline** (no free-tier cold-start network tail here). The **accessibility and axe figures are markup-driven and target-independent**, and are directly comparable. Lighthouse applies simulated CPU/network throttling. Treat the numbers as a reproducible baseline for regression tracking, not certified benchmarks. The remediation is **not yet deployed**: Render still serves the pre-remediation build until these changes land on `main`.

---

## 1. Scorecard

| Page | Lighthouse Perf | Lighthouse A11y | Best Practices | SEO | axe violations | axe rules passed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `home` | 26 | **100** | 100 | 100 | **0** | 30 |
| `schedule` | 60 | **100** | 100 | 100 | **0** | 29 |
| `report` | 47 | **100** | 100 | 100 | **0** | 29 |
| `transparency` | 60 | **100** | 100 | 100 | **0** | 29 |
| `impact` | 50 | **100** | 100 | 100 | **0** | 28 |
| `contact` | 69 | **100** | 100 | 100 | **0** | 29 |
| `about` | 62 | **100** | 100 | 100 | **0** | 29 |
| `faq` | 48 | **100** | 100 | 100 | **0** | 28 |
| `track` | 61 | **100** | 100 | 100 | **0** | 28 |
| `login` | 66 | **100** | 100 | 100 | **0** | 30 |
| **mean** | **55** | **100** | **100** | **100** | **0** | **28.9** |

**Headline:** accessibility is now **clean across the board** — every page scores **Lighthouse accessibility 100** with **zero axe violations** and full Best-Practices/SEO marks. Performance remains the weak axis (mean **55**), still driven primarily by **layout shift (CLS)** and **late LCP**.

**Delta vs. the 2026-10-02 pre-remediation baseline:**

| Metric | Baseline | Now | Note |
| --- | ---: | ---: | --- |
| Mean Lighthouse accessibility | 89 | **100** | markup-driven, directly comparable |
| Mean axe violations / page | 2.4 | **0** | markup-driven, directly comparable |
| Mean Best Practices | 96 | **100** | |
| Mean SEO | 99 | **100** | `/about` went from 92 → 100 |
| Mean Performance | 34 | 55 | **not comparable** — baseline was measured on live Render, this run on a local stack |

---

## 2. Lighthouse scores (0–100, desktop)

| Page | Performance | Accessibility | Best Practices | SEO |
| --- | ---: | ---: | ---: | ---: |
| `home` | 26 | 100 | 100 | 100 |
| `schedule` | 60 | 100 | 100 | 100 |
| `report` | 47 | 100 | 100 | 100 |
| `transparency` | 60 | 100 | 100 | 100 |
| `impact` | 50 | 100 | 100 | 100 |
| `contact` | 69 | 100 | 100 | 100 |
| `about` | 62 | 100 | 100 | 100 |
| `faq` | 48 | 100 | 100 | 100 |
| `track` | 61 | 100 | 100 | 100 |
| `login` | 66 | 100 | 100 | 100 |
| **mean** | **55** | **100** | **100** | **100** |

No page is below 100 on accessibility, Best Practices or SEO.

---

## 3. Core Web Vitals (Lighthouse lab, desktop)

| Page | FCP (ms) | LCP (ms) | TBT (ms) | CLS | Speed Index (ms) | TTFB (ms) | Weight (KB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `home` | 2138 | 3439 | 1442 | 0.181 | 4694 | 218 | 331 |
| `schedule` | 1143 | 2004 | 442 | 0.123 | 2490 | 17 | 204 |
| `report` | 1097 | 2880 | 639 | 0.124 | 2591 | 9 | 209 |
| `transparency` | 986 | 1998 | 482 | 0.125 | 2294 | 19 | 204 |
| `impact` | 976 | 2898 | 567 | 0.125 | 2529 | 135 | 204 |
| `contact` | 988 | 1984 | 292 | 0.125 | 2165 | 13 | 204 |
| `about` | 993 | 2296 | 366 | 0.125 | 2202 | 9 | 333 |
| `faq` | 951 | 2029 | 1774 | 0.125 | 3119 | 11 | 205 |
| `track` | 927 | 2823 | 326 | 0.125 | 2155 | 9 | 203 |
| `login` | 1291 | 2022 | 300 | 0.120 | 2315 | 10 | 204 |

**Reading the numbers**

- **CLS is dramatically improved** — now **0.12–0.18** (from 0.17–1.38 on the live baseline) and roughly a flat 0.12 on every page except `/home`. It is **still above the 0.1 "good" threshold**, so it remains the single largest lever on Performance.
- **LCP** is 2.0–3.4 s (good ≤ 2.5 s), with `/home` (3.4 s), `/impact` (2.9 s), `/report` (2.9 s) and `/track` (2.8 s) worst.
- **TBT** 292–1442 ms indicates main-thread work (script parse/execute), worst on `/home` (1442 ms) and `/faq` (1774 ms).
- **TTFB** 9–218 ms reflects the **local stack**, not the free-tier host — the earlier live cold-start tails (309–449 ms) are not represented here.
- Total page weight is modest (203–333 KB), so bytes are not the main problem; **shift and script execution** are.

### Lighthouse performance audits below 90 (site-wide)

| Audit | Title | Worst score | Affected pages |
| --- | --- | ---: | --- |
| `first-contentful-paint` | First Contentful Paint | 24 | home, schedule, report, transparency, impact, contact, about, faq, login |
| `largest-contentful-paint` | Largest Contentful Paint | 25 | all 10 |
| `speed-index` | Speed Index | 5 | all 10 |
| `total-blocking-time` | Total Blocking Time | 0 | all 10 |
| `max-potential-fid` | Max Potential First Input Delay | 0 | all 10 |
| `cumulative-layout-shift` | Cumulative Layout Shift | 67 | all 10 |
| `interactive` | Time to Interactive | 50 | home, report, impact, faq, track |
| `mainthread-work-breakdown` | Minimize main-thread work | 0 | home, schedule, report, transparency, impact, contact, about, faq, login |
| `layout-shifts` | Avoid large layout shifts | 0 | all 10 |
| `unminified-css` | Minify CSS | 0 | all 10 |
| `unused-css-rules` | Reduce unused CSS | 0 | all 10 |
| `unused-javascript` | Reduce unused JavaScript | 0 | home, schedule, report, transparency, impact, contact, about, faq, track |
| `cls-culprits-insight` | Layout shift culprits | 0 | all 10 |
| `image-delivery-insight` | Improve image delivery | 0 | home, about |
| `network-dependency-tree-insight` | Network dependency tree | 0 | all 10 |
| `forced-reflow-insight` | Forced reflow | 0 | schedule, login |
| `lcp-discovery-insight` | LCP request discovery | 0 | about |

---

## 4. axe-core WCAG 2.0/2.1/2.2 A+AA violations

| Page | Violations | Critical | Serious | Moderate | Minor | Rules passed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `home` | **0** | 0 | 0 | 0 | 0 | 30 |
| `schedule` | **0** | 0 | 0 | 0 | 0 | 29 |
| `report` | **0** | 0 | 0 | 0 | 0 | 29 |
| `transparency` | **0** | 0 | 0 | 0 | 0 | 29 |
| `impact` | **0** | 0 | 0 | 0 | 0 | 28 |
| `contact` | **0** | 0 | 0 | 0 | 0 | 29 |
| `about` | **0** | 0 | 0 | 0 | 0 | 29 |
| `faq` | **0** | 0 | 0 | 0 | 0 | 28 |
| `track` | **0** | 0 | 0 | 0 | 0 | 28 |
| `login` | **0** | 0 | 0 | 0 | 0 | 30 |

**Distinct WCAG rules violated (site-wide): none.** Every scanned page passed all matching WCAG A/AA rules, and **Lighthouse reports no failing accessibility audits** on any page.

### Needs-review items (axe `incomplete`, not violations)

Each page still reports **one `incomplete` (`color-contrast`) result** — elements whose background colour axe cannot compute because it sits over a **gradient** (e.g. the hero `.nav-link.active`, `h1`, `.fs-5` hero description and hero outline buttons on `/`). These are **manual-review items, not failures**; they are unchanged from the baseline and require a human check rather than a code fix (a static contrast pair could be added to the audit config to automate them).

---

## 5. Remediation history — what closed the three rule families

The pre-remediation baseline failed the **same three rule families on every page**. All are now resolved and covered by the remediation in `app/static/style.css` (plus one template change in `app/templates/base.html`):

| Rule (baseline) | WCAG SC | Root cause | Fix applied | Status |
| --- | --- | --- | --- | --- |
| `target-size` | 2.5.8 Target Size (Minimum) | Header search button measured **18 × 59.6 px** | `.sg-nav-search .input-group > button.btn { min-width: 44px; min-height: 24px; display: inline-flex; align-items: center; justify-content: center }` | ✅ fixed |
| `link-in-text-block` | 1.4.1 Use of Color | Footer tel link `#16212b` on `#5b6b7a` = **2.97:1**, no non-colour affordance | Persistent underline on in-text links (`p a.text-decoration-none, li a.text-decoration-none, .card p a.text-decoration-none { text-decoration: underline !important; text-underline-offset: 2px }`) **and** raised contrast | ✅ fixed |
| `color-contrast` | 1.4.3 Contrast (Minimum) | Muted/secondary tokens below 4.5:1 on tinted backgrounds (`.text-muted` on `bg-success-subtle`, `border-danger` cards, `.text-danger` link, `.btn-outline-info`, `.sg-stat-label`) | Darkened `--sg-muted` `#5b6b7a → #495057`; `.text-danger → #b91c1c`; `.sg-stat-label` → token; added `.text-secondary`/`code` overrides; fixed Bootstrap `bg-*-opacity-10`; restyled `.btn-outline-info` | ✅ fixed |

Additionally, `label-content-name-mismatch` (WCAG 2.5.3), which the baseline Lighthouse run reported on all pages for the navbar language button, was fixed in `base.html` by replacing `aria-label="Language"` with a `visually-hidden` span whose text contains the visible label (`EN` / `తె`). Dark-mode contrast was repaired in the same pass, since Lighthouse measured the OS-dark theme while Playwright axe measured light.

---

## 6. Performance remediation plan

Accessibility is done; the remaining work is performance. Highest leverage first:

1. **CLS (still the top lever):** the flat **0.12** on nine pages and **0.18** on `/home` sit just above the 0.1 "good" threshold. Reserve space for images/media (`width`/`height` or `aspect-ratio`), avoid injecting banners/alerts above existing content, and make real-time (Socket.IO) updates non-shifting (reserve a fixed alert region). Inspect `cls-culprits-insight` per page.
2. **LCP:** preload the hero/LCP asset and any web font; ensure the LCP element is discoverable in the initial HTML (`lcp-discovery-insight` on `/about`).
3. **Script weight / TBT:** split/differ/defer non-critical JS; the worst TBT is `/faq` (1774 ms) and `/home` (1442 ms). Trim unused JavaScript (`unused-javascript`).
4. **Image delivery:** `image-delivery-insight` fires on `/home` and `/about` — serve smaller/responsive formats.
5. **CSS delivery:** `unminified-css` and `unused-css-rules` now score **0** site-wide — route `style.css` through minification and trim unused rules (critical CSS is already inlined for the first paint).
6. **Free-tier tails:** the earlier live baseline showed 309–449 ms TTFB spikes on `/impact`, `/contact`, `/track`, `/login`; keep-alive mitigates cold starts, and edge caching (Cloudflare) is the intended fix once the custom domain is live.

**Suggested regression gate (optional):** wire `npm run audit` into CI and fail when Lighthouse accessibility < 100, any axe `serious`/`critical` violation appears, or CLS > 0.1.

---

## 7. Verdict

- **Accessibility:** **clean.** Every audited page scores **Lighthouse accessibility 100** with **zero axe violations** across WCAG 2.0/2.1/2.2 A+AA, and **no failing Lighthouse accessibility audits**. The three rule families that blocked the baseline (target size, in-text link distinction, muted-text contrast) are fixed, as is the language-button label-content mismatch. The only residual items are section 4 "needs-review" gradient-contrast checks, which are manual, not failures.
- **Performance:** improved but still the weak axis. CLS is down to ~0.12 (from up to 1.38) and remains the dominant lever; LCP/TBT and CSS/JS delivery are the next wins. The local-stack figures exclude the live-host cold-start tail, so a post-deploy live re-run is advisable.
- **Trustworthy signals:** Best Practices **100** and SEO **100** across the board, with **0** axe violations, indicate a well-built, standards-aware frontend whose remaining defects are performance polish, not structure.

_Raw artifacts (per-page `*.lighthouse.json`, `*.axe.json`, `summary.json`, `summary.md`) are written to `audit/out/` and are git-ignored. Re-run with `npm run audit`._
