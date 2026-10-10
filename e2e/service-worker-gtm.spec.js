// @ts-check
// End-to-end regression guard for the service-worker / Google Tag Manager bug.
//
// Symptom (seen live): once the PWA service worker controls a page, a
// cross-origin script request — notably Google Tag Manager's gtag/js — fails
// with `net::ERR_FAILED`, because the worker intercepted the fetch and the
// worker's own CSP policy container blocked the host. That silently breaks
// analytics for every returning (SW-controlled) visit.
//
// `tests/js/service_worker_fetch.test.js` asserts the routing decision in
// Node; this spec asserts the real browser symptom: on a page the worker
// actually controls, the GTM script request must return HTTP 200.
//
// The target defaults to the deployment under test (playwright.config.js
// SMARTGARBAGE_BASE_URL). A red run here means the *deployed* worker is
// intercepting cross-origin scripts and must be updated.
import { test, expect } from '@playwright/test';

// A real GTM loader URL (the id from base.html's ANALYTICS_ID) with a unique
// marker so we can pick our request out of the page's own GTM traffic.
const GTM_SMOKE_URL = 'https://www.googletagmanager.com/gtag/js?id=G-VD9JP0DCXC&sg_e2e=1';
const GTM_MARKER = 'sg_e2e=1';

test('service worker does not block the Google Tag Manager script', async ({ page }) => {
  const statuses = [];
  const failures = [];
  page.on('response', (r) => {
    if (r.url().includes(GTM_MARKER)) statuses.push(r.status());
  });
  page.on('requestfailed', (r) => {
    if (r.url().includes(GTM_MARKER)) failures.push(r.failure()?.errorText || 'unknown');
  });

  // 1. Load the app and let its service worker install/activate.
  await page.goto('/');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));

  // 2. Reload so the page itself is under the worker's control — only then does
  //    the worker's fetch handler see the page's subresource requests.
  await page.reload({ waitUntil: 'load' });
  expect(
    await page.evaluate(() => !!navigator.serviceWorker.controller),
    'service worker did not take control of the page',
  ).toBeTruthy();

  // Ignore anything the page requested during those two loads; judge only the
  // request we trigger now, under worker control.
  statuses.length = 0;
  failures.length = 0;

  // 3. Request the GTM script exactly as the page would (a <script> element, so
  //    it is governed by script-src — the path that actually broke).
  const loaded = await page.evaluate(
    (url) =>
      new Promise((resolve) => {
        const s = document.createElement('script');
        s.src = url;
        s.async = true;
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.head.appendChild(s);
        setTimeout(() => resolve(false), 15000);
      }),
    GTM_SMOKE_URL,
  );

  expect(failures, `GTM request failed under service-worker control: ${failures.join(', ')}`)
    .toHaveLength(0);
  expect(statuses, 'GTM script request did not return HTTP 200').toContain(200);
  expect(loaded, 'GTM script element never fired its load event').toBeTruthy();
});
