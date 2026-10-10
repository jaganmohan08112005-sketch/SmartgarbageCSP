// @ts-check
// Real SmartGarbage smoke test.
//
// Historically this directory held the Playwright scaffold's example spec,
// which navigated to playwright.dev — so the workflow passed while telling us
// nothing about SmartGarbage. These tests instead exercise the actual portal:
// the target defaults to the production deployment (see the BASE_URL block in
// playwright.config.js) and can be pointed anywhere else, e.g. at a local
// stack started with `python scripts/run_local_stack.py`:
//
//   SMARTGARBAGE_BASE_URL=http://127.0.0.1:5057 npx playwright test
//
// Keep this file fast and dependency-free: it is the canary that proves a
// deploy is actually serving the site, not the place for deep feature tests.
import { test, expect } from '@playwright/test';

// The homepage hero heading (index.html `<h1>`), our clearest proof that the
// real portal rendered rather than an error page or an unrelated site.
const HERO_HEADING = 'Waste Collection Schedules & Missed Pickup Reports in Chintalavalasa';

// Public, DB-light pages every deployment must serve (verified 200 in prod).
const PUBLIC_PAGES = [
  ['about', '/about'],
  ['contact', '/contact'],
  ['faq', '/faq'],
  ['schedule', '/schedule'],
  ['transparency', '/transparency'],
  ['login', '/login'],
];

test.describe('SmartGarbage smoke', () => {
  test('homepage renders the SmartGarbage shell', async ({ page }) => {
    const response = await page.goto('/');
    expect(response, 'homepage navigation produced no response').not.toBeNull();
    expect(response.ok(), `homepage returned HTTP ${response.status()}`).toBeTruthy();

    // Title from index.html's `{% block title %}`.
    await expect(page).toHaveTitle(
      /Waste Collection & Missed Pickup Reports \| Chintalavalasa/,
    );
    // Hero heading proves the real content rendered.
    await expect(page.locator('h1')).toContainText('Waste Collection Schedules');
    // Document language + brand in the nav.
    expect(await page.locator('html').getAttribute('lang')).toBe('en');
    await expect(
      page.getByRole('link', { name: /SmartGarbage/ }).first(),
    ).toBeVisible();
  });

  for (const [name, path] of PUBLIC_PAGES) {
    test(`public page "${name}" loads with a heading`, async ({ page }) => {
      const response = await page.goto(path);
      expect(
        response?.ok(),
        `${name} (${path}) returned HTTP ${response?.status()}`,
      ).toBeTruthy();
      // Every accessible page should expose a top-level heading.
      await expect(page.locator('h1').first()).toBeVisible();
    });
  }

  test('/health reports the database reachable', async ({ request }) => {
    const response = await request.get('/health');
    // 200 when fully healthy; 503 when a non-DB probe (mail/queue posture) is
    // merely degraded — that is not a smoke-test failure.
    expect([200, 503], `unexpected /health status ${response.status()}`).toContain(
      response.status(),
    );

    const body = await response.json();
    expect(body.checks?.database?.status).toBe('pass');
  });

  test('PWA wiring is served', async ({ request }) => {
    const sw = await request.get('/sw.js');
    expect(sw.ok()).toBeTruthy();
    expect(sw.headers()['content-type']).toContain('javascript');
    const swBody = await sw.text();
    // Version-agnostic invariants: these hold across worker versions, unlike
    // the cache-tier names that the JS unit tests cover. A stale/empty/HTML
    // response would fail all of them.
    expect(swBody).toContain('CACHE_PREFIX');
    expect(swBody).toContain('SW_VERSION');
    expect(swBody).toContain("addEventListener('fetch'");
    expect(swBody).toContain('caches');

    const manifest = await request.get('/manifest.json');
    expect(manifest.ok()).toBeTruthy();
    const mf = await manifest.json();
    expect(mf.name).toContain('SmartGarbage');
    expect(mf.short_name).toBe('SmartGarbage');
    expect(mf.start_url).toBe('/?source=pwa');
  });

  test('crawler discovery files are served', async ({ request }) => {
    const robots = await request.get('/robots.txt');
    expect(robots.ok()).toBeTruthy();
    expect(await robots.text()).toContain('Sitemap:');

    const sitemap = await request.get('/sitemap.xml');
    expect(sitemap.ok()).toBeTruthy();
    expect(await sitemap.text()).toContain('<urlset');

    const llms = await request.get('/llms.txt');
    expect(llms.ok()).toBeTruthy();
    expect(await llms.text()).toContain('SmartGarbage');
  });

  test('unknown routes return 404', async ({ request }) => {
    const response = await request.get('/smoke-test-does-not-exist');
    expect(response.status()).toBe(404);
  });
});
