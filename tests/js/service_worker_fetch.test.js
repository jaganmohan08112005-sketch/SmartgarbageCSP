/* ============================================================
   SmartGarbage — sw.js fetch-routing regression test
   Run with:  node tests/js/service_worker_fetch.test.js
   (Pure Node — no browser, no test framework, no network.)

   WHY THIS EXISTS
   ---------------
   app/static/sw.js must NOT intercept arbitrary cross-origin requests. A
   service worker's own fetch() is governed by the CSP policy container of the
   script that registered it (/sw.js), whose connect-src is narrow. Intercepting
   a cross-origin subresource therefore routed e.g. Google Tag Manager through
   the worker's blocked fetch and produced net::ERR_FAILED — analytics never
   loaded. The handler therefore only intercepts an explicit allowlist of
   external assets (web font + OpenStreetMap tiles) and lets every other
   cross-origin request pass straight to the browser.

   This test loads sw.js in a sandboxed ServiceWorkerGlobalScope, fires the
   real 'fetch' listener with cross-origin and same-origin requests, and
   asserts that respondWith() is called ONLY for same-origin and for the
   allowlisted CDN hosts. If a future change widens interception to GTM or
   other third-party scripts, that assertion fails loudly instead of silently
   breaking analytics.

   Set SG_SW_PATH=<file> to run the same assertions against another copy
   (used to prove the test fails on the pre-fix worker).
   ============================================================ */
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SW_PATH = process.env.SG_SW_PATH ||
    path.join(__dirname, '..', '..', 'app', 'static', 'sw.js');
const ORIGIN = 'https://smartgarbage.example';

function loadServiceWorker(fetchImpl) {
    const src = fs.readFileSync(SW_PATH, 'utf8');
    const listeners = Object.create(null);
    const fakeCache = {
        put: async () => {}, match: async () => undefined,
        keys: async () => [], delete: async () => {},
    };
    const context = {
        self: {
            location: { origin: ORIGIN },
            addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
            skipWaiting: () => {},
            clients: { claim: async () => {}, matchAll: async () => [], openWindow: () => {} },
            registration: { showNotification: async () => {} },
        },
        caches: {
            open: async () => fakeCache, match: async () => undefined,
            keys: async () => [], delete: async () => {},
        },
        // Any network the worker performs resolves to a 200; the point of this
        // test is WHETHER the worker responds, not what it returns.
        fetch: fetchImpl || (async () => new Response('ok', { status: 200 })),
        console,
        URL, Request, Response, Headers, FormData, File, Blob,
        indexedDB: { open: () => ({}) },
        setTimeout, clearTimeout, setInterval, clearInterval,
    };
    vm.createContext(context);
    vm.runInContext(src, context, { filename: path.basename(SW_PATH) });
    return { listeners };
}

// The handler only reads request.method / .url / .mode, so plain objects keep
// the test independent of Node's Request-mode restrictions (e.g. 'navigate').
function dispatch(onFetch, request) {
    const evt = {
        request,
        responded: false,
        response: undefined,
        respondWith(p) { this.responded = true; this.response = Promise.resolve(p); },
        waitUntil() {},
    };
    onFetch(evt);
    return evt;
}

(async function run() {
    let passed = 0;
    function ok(cond, label) {
        if (!cond) throw new Error('FAIL: ' + label);
        passed += 1;
        console.log('  ✓ ' + label);
    }

    const { listeners } = loadServiceWorker();
    assert.ok(listeners.fetch && listeners.fetch.length === 1,
        'sw.js must register exactly one fetch listener');
    const onFetch = listeners.fetch[0];

    console.log('unlisted cross-origin requests are NEVER intercepted');
    // The regression guard: respondWith must stay untouched for these.
    for (const [label, url] of [
        ['Google Tag Manager', 'https://www.googletagmanager.com/gtag/js?id=G-VD9JP0DCXC'],
        ['Google Analytics collect', 'https://www.google-analytics.com/g/collect?v=2&tid=G-VD9JP0DCXC'],
        ['jsDelivr CDN script', 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js'],
        ['unpkg Leaflet script', 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'],
        ['cdnjs stylesheet', 'https://cdnjs.cloudflare.com/ajax/libs/x/x.css'],
    ]) {
        const evt = dispatch(onFetch, { method: 'GET', url, mode: 'cors' });
        ok(evt.responded === false && evt.response === undefined,
            `${label} -> no respondWith (browser fetches directly, outside worker CSP)`);
    }

    console.log('allowlisted external assets ARE intercepted (offline font + tiles)');
    for (const [label, url] of [
        ['Google Fonts file', 'https://fonts.gstatic.com/s/outfit/v15/abc123.woff2'],
        ['OpenStreetMap tile (a.)', 'https://a.tile.openstreetmap.org/12/3418/2212.png'],
        ['OpenStreetMap tile (b.)', 'https://b.tile.openstreetmap.org/12/3418/2213.png'],
        ['OpenStreetMap tile (bare host)', 'https://tile.openstreetmap.org/12/3418/2212.png'],
    ]) {
        const evt = dispatch(onFetch, { method: 'GET', url, mode: 'no-cors' });
        ok(evt.responded === true, `${label} -> intercepted (cache-first CDN tier)`);
        // Cache-miss + network failure must yield a real Response, never undefined.
        const res = await evt.response.catch(() => undefined);
        ok(res instanceof Response, `${label} -> resolves to a real Response, not undefined`);
    }

    console.log('offline cache miss on an allowlisted asset degrades safely');
    {
        // Network down + nothing cached: the CDN tier must still resolve a
        // real Response (504), never undefined — undefined would surface as
        // net::ERR_FAILED on the page.
        const offline = loadServiceWorker(async () => { throw new Error('offline'); });
        const evt = dispatch(offline.listeners.fetch[0], {
            method: 'GET', url: 'https://a.tile.openstreetmap.org/12/3418/2212.png', mode: 'no-cors',
        });
        ok(evt.responded === true, 'offline tile -> still intercepted');
        const res = await evt.response;
        ok(res instanceof Response && res.status === 504,
            'offline tile -> real 504 Response (no undefined respondWith)');
    }

    console.log('same-origin requests ARE still handled (positive controls)');
    const nav = dispatch(onFetch, { method: 'GET', url: ORIGIN + '/', mode: 'navigate' });
    ok(nav.responded === true, 'same-origin navigation intercepted (page cache/SWR intact)');
    if (nav.response) await nav.response.catch(() => {});

    const css = dispatch(onFetch, { method: 'GET', url: ORIGIN + '/static/style.css', mode: 'no-cors' });
    ok(css.responded === true, 'same-origin static asset intercepted (cache-first intact)');
    if (css.response) await css.response.catch(() => {});

    console.log('non-GET requests are never intercepted');
    const post = dispatch(onFetch, {
        method: 'POST', url: 'https://www.googletagmanager.com/gtag/js', mode: 'cors',
    });
    ok(post.responded === false, 'cross-origin POST -> no respondWith');

    console.log(`\nAll ${passed} service-worker fetch-routing assertions passed ✓`);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
