// Fast re-check of ONLY the authenticated staff pages (/worker, /admin):
//
//   node audit/run-auth-a11y.mjs        # ~30s — no Lighthouse, no citizen pages
//
// `npm run audit` covers these pages too (and check-audit.mjs gates them in
// CI); this exists so an a11y fix on the staff portals doesn't need a
// multi-minute Lighthouse loop just to re-verify. Same rules, same login flow
// (shared with the main runner via ./auth.mjs), same exit-code contract:
// non-zero when any axe WCAG A/AA violation or error is found.
//
// Env:
//   AUDIT_BASE_URL   target base (default http://127.0.0.1:5057)
//   AUDIT_AUTH       '1' forces the pass even on non-loopback targets
//   CHROME_PATH      chromium binary (optional)
import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';
import { AUTHED_PAGES, AXE_TAGS, isLoopback, loginStaff } from './auth.mjs';

const BASE = (process.env.AUDIT_BASE_URL || 'http://127.0.0.1:5057').replace(/\/+$/, '');

if (!isLoopback(BASE) && process.env.AUDIT_AUTH !== '1') {
  console.log(
    `Skipped: ${BASE} is not the seeded local stack (no staff fixtures / dev OTP). ` +
      'Point AUDIT_BASE_URL at the local stack or set AUDIT_AUTH=1 to force.',
  );
  process.exit(0);
}

(async () => {
  const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
  let failures = 0;
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
      console.log(`AXE ${t.path.padEnd(9)} violations=${r.violations.length} passes=${r.passes.length} incomplete=${r.incomplete.length}`);
      for (const v of r.violations) {
        console.log(`  ✗ ${v.id} [${v.impact}] ${v.help} — ${v.nodes.length} node(s)`);
        for (const n of v.nodes.slice(0, 5)) console.log(`      ${n.target.join(' ')}`);
      }
      failures += r.violations.length;
    } catch (e) {
      console.log(`AXE ${t.path.padEnd(9)} ERROR ${e.message}`);
      failures += 1;
    } finally {
      await ctx.close();
    }
  }
  await browser.close();
  if (failures) {
    console.error(`\nAuthenticated-page audit FAILED — ${failures} axe WCAG A/AA violation(s).`);
    process.exit(1);
  }
  console.log('\nAuthenticated-page audit PASSED — 0 axe WCAG A/AA violations.');
})();
