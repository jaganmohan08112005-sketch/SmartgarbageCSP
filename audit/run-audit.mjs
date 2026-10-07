// Machine-audited accessibility & performance pass for the deployed SmartGarbage site.
//
//   node audit/run-audit.mjs
//
// Runs Lighthouse (desktop, simulated throttling) and axe-core (WCAG 2.0/2.1/2.2 A+AA)
// against every key page and writes raw JSON plus a markdown summary to audit/out/.
//
// Env:
//   AUDIT_BASE_URL   override the target (default https://smartgarbage.onrender.com)
//   CHROME_PATH      Chromium binary for Lighthouse (defaults to chrome-launcher's lookup)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import lighthouse from 'lighthouse';
import * as chromeLauncher from 'chrome-launcher';
import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';
import { AUTHED_PAGES, AXE_TAGS, isLoopback, loginStaff } from './auth.mjs';

const BASE = (process.env.AUDIT_BASE_URL || 'https://smartgarbage.onrender.com').replace(/\/+$/, '');

// Authenticated staff pages (/worker, /admin) are axe-scanned after a real
// login + MFA. On a loopback target — the seeded local stack the CI workflow
// boots — the pass always runs; remote targets have neither the staff fixtures
// nor the developer OTP, so it is skipped there unless AUDIT_AUTH=1 forces it.
const AUTH_MODE = process.env.AUDIT_AUTH; // '1' force · '0' disable · unset = auto
const authEnabled = AUTH_MODE === '1' ? true : AUTH_MODE === '0' ? false : isLoopback(BASE);

// Key citizen-facing pages (all verified 200 on the live deployment).
const PAGES = [
  ['home', '/'],
  ['schedule', '/schedule'],
  ['report', '/report'],
  ['transparency', '/transparency'],
  ['impact', '/impact'],
  ['contact', '/contact'],
  ['about', '/about'],
  ['faq', '/faq'],
  ['track', '/track'],
  ['login', '/login'],
];

const CATEGORIES = ['performance', 'accessibility', 'best-practices', 'seo'];
// AXE_TAGS (WCAG 2.0/2.1/2.2 Level A + AA) and the authenticated-page login
// flow live in ./auth.mjs so every entry point scans with identical config.
const AXE_PAGES = [...PAGES.map(([name]) => name), ...AUTHED_PAGES.map((t) => t.name)];
const DESKTOP = { mobile: false, width: 1350, height: 940, deviceScaleFactor: 1 };

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'out');
fs.mkdirSync(OUT, { recursive: true });

const round = (n) => (n == null ? null : Math.round(n));
const pct = (n) => (n == null ? '-' : Math.round(n * 100));

async function runLighthouse() {
  const chrome = await chromeLauncher.launch({
    chromePath: process.env.CHROME_PATH || undefined,
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });
  const out = {};
  try {
    for (const [name, pagePath] of PAGES) {
      const url = BASE + pagePath;
      try {
        const runner = await lighthouse(url, {
          port: chrome.port,
          output: 'json',
          logLevel: 'error',
          onlyCategories: CATEGORIES,
          formFactor: 'desktop',
          screenEmulation: { ...DESKTOP, disabled: false },
          throttlingMethod: 'simulate',
        });
        const lhr = runner.lhr;
        const scores = {};
        for (const c of CATEGORIES) scores[c] = pct(lhr.categories[c]?.score);

        const a11yRefs = new Set((lhr.categories.accessibility?.auditRefs || []).map((r) => r.id));
        const a11yFails = Object.values(lhr.audits)
          .filter((a) => a11yRefs.has(a.id) && typeof a.score === 'number' && a.score < 1)
          .map((a) => ({ id: a.id, title: a.title, nodes: a.details?.items?.length ?? null }));
        const perfRefs = new Set((lhr.categories.performance?.auditRefs || []).map((r) => r.id));
        const perfFails = Object.values(lhr.audits)
          .filter((a) => perfRefs.has(a.id) && typeof a.score === 'number' && a.score < 0.9)
          .map((a) => ({ id: a.id, title: a.title, score: Math.round(a.score * 100) }));

        const m = lhr.audits;
        out[name] = {
          url,
          scores,
          metrics: {
            fcp_ms: round(m['first-contentful-paint']?.numericValue),
            lcp_ms: round(m['largest-contentful-paint']?.numericValue),
            tbt_ms: round(m['total-blocking-time']?.numericValue),
            cls: m['cumulative-layout-shift']?.numericValue ?? null,
            speed_index_ms: round(m['speed-index']?.numericValue),
            tti_ms: round(m['interactive']?.numericValue),
            server_response_ms: round(m['server-response-time']?.numericValue),
            total_byte_weight_kb: m['total-byte-weight']?.numericValue
              ? Math.round(m['total-byte-weight'].numericValue / 1024)
              : null,
          },
          a11y_failing_audits: a11yFails,
          perf_failing_audits: perfFails,
        };
        fs.writeFileSync(path.join(OUT, `${name}.lighthouse.json`), JSON.stringify(lhr));
        console.log(`LH  ${name.padEnd(13)} perf=${scores.performance} a11y=${scores.accessibility} bp=${scores['best-practices']} seo=${scores.seo}`);
      } catch (e) {
        out[name] = { url, error: String((e && e.message) || e) };
        console.log(`LH  ${name.padEnd(13)} ERROR ${e.message}`);
      }
    }
  } finally {
    await chrome.kill();
  }
  return out;
}

async function runAxe() {
  const browser = await chromium.launch();
  const out = {};
  try {
    for (const [name, pagePath] of PAGES) {
      const url = BASE + pagePath;
      const ctx = await browser.newContext({ bypassCSP: true, viewport: { width: 1350, height: 940 } });
      const page = await ctx.newPage();
      try {
        await page.goto(url, { waitUntil: 'load', timeout: 90000 });
        await page.waitForTimeout(2000);
        const r = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
        out[name] = {
          url,
          violations: r.violations.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            tags: v.tags,
            nodes: v.nodes.length,
            targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')),
          })),
          passes: r.passes.length,
          incomplete: r.incomplete.length,
          inapplicable: r.inapplicable.length,
        };
        fs.writeFileSync(path.join(OUT, `${name}.axe.json`), JSON.stringify(r));
        console.log(`AXE ${name.padEnd(13)} violations=${r.violations.length} passes=${r.passes.length} incomplete=${r.incomplete.length}`);
      } catch (e) {
        out[name] = { url, error: String((e && e.message) || e) };
        console.log(`AXE ${name.padEnd(13)} ERROR ${e.message}`);
      } finally {
        await ctx.close();
      }
    }

    // Authenticated staff pages: drive the real login + MFA flow in a fresh
    // context, then axe-scan. `authed: true` marks these as axe-only entries
    // for check-audit.mjs (a Lighthouse run can't easily share the session).
    // A login failure records an ERROR entry so the gate fails loudly instead
    // of silently dropping coverage.
    if (!authEnabled) {
      console.log(`AXE auth pages    skipped (${BASE} is not loopback — set AUDIT_AUTH=1 to force)`);
      return out;
    }
    for (const t of AUTHED_PAGES) {
      const ctx = await browser.newContext({ bypassCSP: true, viewport: { width: 1350, height: 940 } });
      const page = await ctx.newPage();
      try {
        await loginStaff(page, BASE, t.user);
        await page.goto(BASE + t.path, { waitUntil: 'load', timeout: 90000 });
        const landed = new URL(page.url()).pathname;
        if (landed === '/login' || landed === '/mfa-verify') {
          throw new Error(`staff login did not complete — still on ${landed}`);
        }
        // Wait until Leaflet has actually mounted markers before scanning —
        // the unnamed-marker class of bug only exists once they render.
        await page.waitForSelector('.leaflet-marker-icon', { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(800); // tiles/popups settle
        const r = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
        out[t.name] = {
          url: BASE + t.path,
          authed: true,
          violations: r.violations.map((v) => ({
            id: v.id,
            impact: v.impact,
            help: v.help,
            tags: v.tags,
            nodes: v.nodes.length,
            targets: v.nodes.slice(0, 5).map((n) => n.target.join(' ')),
          })),
          passes: r.passes.length,
          incomplete: r.incomplete.length,
          inapplicable: r.inapplicable.length,
        };
        fs.writeFileSync(path.join(OUT, `${t.name}.axe.json`), JSON.stringify(r));
        console.log(`AXE ${t.name.padEnd(13)} auth  violations=${r.violations.length} passes=${r.passes.length} incomplete=${r.incomplete.length}`);
      } catch (e) {
        out[t.name] = { url: BASE + t.path, authed: true, error: String((e && e.message) || e) };
        console.log(`AXE ${t.name.padEnd(13)} auth  ERROR ${e.message}`);
      } finally {
        await ctx.close();
      }
    }
  } finally {
    await browser.close();
  }
  return out;
}

function summarise(lh, axe) {
  const now = new Date().toISOString();
  const L = [];
  L.push('# SmartGarbage — machine-audited accessibility & performance');
  L.push('');
  L.push(`- **Target:** ${BASE}`);
  L.push(`- **Generated:** ${now}`);
  L.push('- **Lighthouse:** desktop form factor, simulated throttling, categories performance / accessibility / best-practices / SEO');
  L.push(`- **axe-core:** WCAG 2.0/2.1/2.2 Level A + AA tags (${AXE_TAGS.join(', ')})`);
  L.push(authEnabled
    ? `- **Authenticated pages:** ${AUTHED_PAGES.map((t) => `\`${t.path}\``).join(', ')} — axe-scanned after a real staff login (axe only; Lighthouse covers citizen pages)`
    : '- **Authenticated pages:** skipped (non-loopback target — set AUDIT_AUTH=1 to force)');
  L.push('');

  L.push('## Lighthouse scores (0–100, desktop)');
  L.push('');
  L.push('| Page | Performance | Accessibility | Best Practices | SEO |');
  L.push('| --- | ---: | ---: | ---: | ---: |');
  let sumPerf = 0, sumA11y = 0, nPerf = 0, nA11y = 0;
  for (const [name] of PAGES) {
    const s = lh[name]?.scores || {};
    L.push(`| \`${name}\` | ${s.performance ?? '-'} | ${s.accessibility ?? '-'} | ${s['best-practices'] ?? '-'} | ${s.seo ?? '-'} |`);
    if (typeof s.performance === 'number') { sumPerf += s.performance; nPerf++; }
    if (typeof s.accessibility === 'number') { sumA11y += s.accessibility; nA11y++; }
  }
  L.push(`| **mean** | **${nPerf ? Math.round(sumPerf / nPerf) : '-'}** | **${nA11y ? Math.round(sumA11y / nA11y) : '-'}** | | |`);
  L.push('');

  L.push('## Core Web Vitals (Lighthouse lab, desktop)');
  L.push('');
  L.push('| Page | FCP (ms) | LCP (ms) | TBT (ms) | CLS | Speed Index (ms) | TTFB (ms) | Weight (KB) |');
  L.push('| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |');
  for (const [name] of PAGES) {
    const m = lh[name]?.metrics;
    if (!m) { L.push(`| \`${name}\` | - | - | - | - | - | - | - |`); continue; }
    L.push(`| \`${name}\` | ${m.fcp_ms ?? '-'} | ${m.lcp_ms ?? '-'} | ${m.tbt_ms ?? '-'} | ${m.cls != null ? m.cls.toFixed(3) : '-'} | ${m.speed_index_ms ?? '-'} | ${m.server_response_ms ?? '-'} | ${m.total_byte_weight_kb ?? '-'} |`);
  }
  L.push('');

  L.push('## axe-core WCAG 2.0/2.1/2.2 A+AA violations');
  L.push('');
  L.push('| Page | Violations | Critical | Serious | Moderate | Minor | Rules passed |');
  L.push('| --- | ---: | ---: | ---: | ---: | ---: | ---: |');
  const allViol = new Map();
  for (const name of AXE_PAGES) {
    const a = axe[name];
    if (!a || a.error) { L.push(`| \`${name}\` | - | - | - | - | - | - |`); continue; }
    const c = { critical: 0, serious: 0, moderate: 0, minor: 0 };
    for (const v of a.violations) c[v.impact] = (c[v.impact] || 0) + 1;
    L.push(`| \`${name}\` | ${a.violations.length} | ${c.critical || 0} | ${c.serious || 0} | ${c.moderate || 0} | ${c.minor || 0} | ${a.passes} |`);
    for (const v of a.violations) {
      const cur = allViol.get(v.id) || { impact: v.impact, help: v.help, pages: [] };
      cur.pages.push(name);
      allViol.set(v.id, cur);
    }
  }
  L.push('');

  L.push('## Distinct WCAG rules violated (site-wide)');
  L.push('');
  if (!allViol.size) {
    L.push('None — every scanned page passed all matching WCAG A/AA rules.');
  } else {
    L.push('| Rule | Impact | Help | Affected pages |');
    L.push('| --- | --- | --- | --- |');
    for (const [id, v] of [...allViol.entries()].sort((a, b) => b[1].pages.length - a[1].pages.length)) {
      L.push(`| \`${id}\` | ${v.impact} | ${v.help} | ${v.pages.join(', ')} |`);
    }
  }
  L.push('');

  L.push('## Lighthouse accessibility audits still failing');
  L.push('');
  const lhA11y = new Map();
  for (const [name] of PAGES) {
    for (const f of lh[name]?.a11y_failing_audits || []) {
      const cur = lhA11y.get(f.id) || { title: f.title, pages: [] };
      cur.pages.push(name);
      lhA11y.set(f.id, cur);
    }
  }
  if (!lhA11y.size) {
    L.push('None.');
  } else {
    L.push('| Audit | Title | Affected pages |');
    L.push('| --- | --- | --- |');
    for (const [id, v] of lhA11y) L.push(`| \`${id}\` | ${v.title} | ${v.pages.join(', ')} |`);
  }
  L.push('');

  L.push('## Lighthouse performance audits below 90');
  L.push('');
  const lhPerf = new Map();
  for (const [name] of PAGES) {
    for (const f of lh[name]?.perf_failing_audits || []) {
      const cur = lhPerf.get(f.id) || { title: f.title, pages: [], worst: 100 };
      cur.pages.push(name);
      cur.worst = Math.min(cur.worst, f.score);
      lhPerf.set(f.id, cur);
    }
  }
  if (!lhPerf.size) {
    L.push('None.');
  } else {
    L.push('| Audit | Title | Worst score | Affected pages |');
    L.push('| --- | --- | ---: | --- |');
    for (const [id, v] of lhPerf) L.push(`| \`${id}\` | ${v.title} | ${v.worst} | ${v.pages.join(', ')} |`);
  }
  L.push('');
  L.push('_Raw per-page Lighthouse and axe JSON are in `audit/out/`. Reproduce with `npm run audit`._');
  return L.join('\n') + '\n';
}

(async () => {
  console.log('Audit target:', BASE);
  const lh = await runLighthouse();
  const axe = await runAxe();
  fs.writeFileSync(
    path.join(OUT, 'summary.json'),
    JSON.stringify({ base: BASE, generated: new Date().toISOString(), lighthouse: lh, axe }, null, 2),
  );
  fs.writeFileSync(path.join(OUT, 'summary.md'), summarise(lh, axe));
  console.log('\nWrote', path.join(OUT, 'summary.md'));
})();
