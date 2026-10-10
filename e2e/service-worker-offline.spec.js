// @ts-check
// Offline-first regression guard for the PWA service worker.
//
// `e2e/service-worker-gtm.spec.js` proves the worker does NOT interfere with
// cross-origin requests (Google Tag Manager passes straight through). This
// spec proves the other half of the contract: for its OWN origin the worker
// caches the app and still serves it when the network is gone.
//
// Sequence, starting from a cold cache (Playwright hands every test a fresh
// browser context, so CacheStorage begins empty):
//   1. load `/` once so the worker installs, activates and populates its
//      versioned caches (precache of immutable assets + prefetch of pages);
//   2. reload so the document itself is under the worker's control;
//   3. then — depending on the test — inspect the caches, or cut the network
//      and assert the app still renders (the only possible source is now the
//      worker's CacheStorage).
//
// The target defaults to the deployment under test (playwright.config.js
// SMARTGARBAGE_BASE_URL). Run it against a local stack with:
//
//   SMARTGARBAGE_BASE_URL=http://127.0.0.1:5057 npx playwright test service-worker-offline
import { test, expect } from '@playwright/test';

// The homepage hero heading (index.html `<h1>`): proof the real portal
// rendered rather than the worker's offline placeholder.
const HERO_HEADING = 'Waste Collection Schedules';

// An immutable asset the worker precaches at install (sw.js IMMUTABLE_ASSETS)
// and serves cache-first. If subresources did not survive offline the shell
// would render unstyled/without JS — usable HTML but not a working app.
const STATIC_ASSET = '/static/css/critical.css';

// A route the worker never prefetches and this test never visits, so it is a
// genuine cache miss — used to exercise the /offline fallback path.
const UNCACHED_ROUTE = '/contact';

/**
 * Load the app once so the worker installs, then make the page worker-
 * controlled and let the shell settle into the cache.
 * @param {import('@playwright/test').Page} page
 */
async function installWorker(page) {
  await page.goto('/');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));

  // Reload so the document itself is under the worker's control — only then
  // does the fetch handler see (and cache) the navigation and its subresources.
  await page.reload({ waitUntil: 'load' });
  expect(
    await page.evaluate(() => !!navigator.serviceWorker.controller),
    'service worker did not take control of the page',
  ).toBeTruthy();
}

/**
 * Poll the origin's CacheStorage until `url` is present. CacheStorage is
 * shared between the page and its service worker, so the page can inspect it.
 * @param {import('@playwright/test').Page} page
 * @param {string} url
 */
async function waitForCached(page, url) {
  await expect
    .poll(
      () => page.evaluate(async (u) => !!(await caches.match(u)), url),
      { message: `worker never cached ${url}`, timeout: 30000 },
    )
    .toBe(true);
}

test.describe('service worker cold-cache population', () => {
  test('caches the app shell, offline fallback and static assets', async ({ page }) => {
    await installWorker(page);

    // The app root must be cached by the page-navigation strategy — this is
    // the assertion that caught a real v16 clone race which silently skipped
    // the homepage (it was never served offline, only its prefetched pages).
    await waitForCached(page, '/');
    // The install-time fallback the worker answers uncached navigations with.
    await waitForCached(page, '/offline');
    // A cache-first immutable asset, so the shell renders styled offline too.
    await waitForCached(page, STATIC_ASSET);
  });
});

test.describe('service worker serves the app offline', () => {
  // `context.setOffline()` only severs a SERVICE WORKER's own network access
  // on Chromium. On Firefox the worker keeps reaching the network with
  // `navigator.onLine` false (a green run would prove nothing), and on WebKit
  // an offline navigation fails with an internal error. Request interception
  // does not fill the gap either: Playwright does not intercept fetches the
  // worker itself makes. The true-offline contract is therefore asserted on
  // Chromium; the cache-population contract above, and cross-origin
  // pass-through in service-worker-gtm.spec.js, still run on all browsers.
  test.beforeEach(({ browserName }) => {
    test.skip(
      browserName !== 'chromium',
      'offline network emulation only severs a service worker’s own fetches on Chromium',
    );
  });

  test('serves the cached app shell offline after a cold cache', async ({ page, context }) => {
    await installWorker(page);
    // The reload above is a navigation, so the worker's stale-while-
    // revalidate page strategy stores `/`. Wait for it before cutting the net.
    await waitForCached(page, '/');

    await context.setOffline(true);
    expect(await page.evaluate(() => navigator.onLine), 'network was not cut').toBe(false);

    const response = await page.goto('/', { waitUntil: 'load' });
    expect(response?.status(), 'offline homepage did not return HTTP 200').toBe(200);
    expect(
      response?.fromServiceWorker(),
      'offline homepage was not served by the service worker',
    ).toBe(true);
    await expect(page.locator('h1')).toContainText(HERO_HEADING);
  });

  test('serves precached static assets offline', async ({ page, context }) => {
    await installWorker(page);
    await waitForCached(page, STATIC_ASSET);

    await context.setOffline(true);

    const ok = await page.evaluate(async (u) => {
      try {
        const res = await fetch(u);
        return res.ok;
      } catch {
        return false;
      }
    }, STATIC_ASSET);
    expect(ok, `${STATIC_ASSET} was not served from the cache while offline`).toBe(true);
  });

  test('falls back to the offline page for an uncached route', async ({ page, context }) => {
    await installWorker(page);
    // The worker caches `/offline` during install; an uncached navigation
    // while offline should be answered with it.
    await waitForCached(page, '/offline');

    await context.setOffline(true);

    const response = await page.goto(UNCACHED_ROUTE, { waitUntil: 'load' });
    expect(response?.status(), 'offline fallback did not return HTTP 200').toBe(200);
    await expect(page.locator('h1')).toContainText(/You'?re offline/i);
  });
});
