/* ================================================================
   SmartGarbage Service Worker v12
   Three-tier caching: Static assets, HTML pages, CDN resources
   ================================================================ */

const SW_VERSION = 'v12';
const CACHE_PREFIX = 'smartgarbage';

// ── Cache tiers ──────────────────────────────────────────────────
const STATIC_CACHE  = `${CACHE_PREFIX}-static-${SW_VERSION}`;   // Immutable assets
const PAGES_CACHE   = `${CACHE_PREFIX}-pages-${SW_VERSION}`;    // HTML pages
const CDN_CACHE     = `${CACHE_PREFIX}-cdn-${SW_VERSION}`;      // External CDN

// ── Cache size limits (LRU eviction) ────────────────────────────
const MAX_STATIC_ENTRIES = 80;
const MAX_PAGES_ENTRIES  = 30;
const MAX_CDN_ENTRIES    = 20;

// ── Immutable assets (cache-first, never revalidate) ─────────────
const IMMUTABLE_ASSETS = [
    '/static/css/critical.css',
    '/static/style.css',
    '/static/fonts/outfit-v15.woff2',
    '/static/js/offline.js',
    '/static/js/global.min.js',
    '/static/chintalavalasa_locations.js',
    '/static/vendor/bootstrap.min.css',
    '/static/vendor/bootstrap.bundle.min.js',
    '/static/manifest.json',
    '/static/icon-192.png',
    '/static/icon-512.png',
];

// ── Pages to prefetch after first load (background) ──────────────
const PREFETCH_PAGES = [
    '/schedule',
    '/report',
    '/faq',
    '/transparency',
    '/about',
];

// ── Sensitive routes (never cache for offline) ───────────────────
const SENSITIVE_ROUTES = ['/admin', '/dashboard', '/payt', '/login', '/mfa', '/register'];

// ── Offline database ─────────────────────────────────────────────
const OFFLINE_DB_NAME = 'smartgarbage-offline';
const OFFLINE_STORE = 'pending-forms';

/* ================================================================
   INSTALL — precache immutable assets + offline page
   ================================================================ */
self.addEventListener('install', evt => {
    evt.waitUntil(
        (async () => {
            const staticCache = await caches.open(STATIC_CACHE);

            // Precache immutable assets (best-effort — don't fail install if one is missing)
            await Promise.allSettled(
                IMMUTABLE_ASSETS.map(url =>
                    fetch(url).then(res => {
                        if (res.ok) return staticCache.put(url, res);
                    }).catch(() => {})
                )
            );

            // Cache the offline page
            const pagesCache = await caches.open(PAGES_CACHE);
            try {
                const offlineRes = await fetch('/offline');
                if (offlineRes.ok) await pagesCache.put('/offline', offlineRes);
            } catch (e) {}

            console.log(`[SW ${SW_VERSION}] Installed — ${IMMUTABLE_ASSETS.length} assets precached`);
        })()
    );
    self.skipWaiting();
});

/* ================================================================
   ACTIVATE — clean old caches + claim clients + prefetch
   ================================================================ */
self.addEventListener('activate', evt => {
    evt.waitUntil(
        (async () => {
            // Delete old versioned caches
            const keys = await caches.keys();
            await Promise.all(
                keys
                    .filter(k => k.startsWith(CACHE_PREFIX) && !k.includes(SW_VERSION))
                    .map(k => caches.delete(k))
            );

            // Claim all clients immediately
            await self.clients.claim();

            // Background prefetch of critical pages
            prefetchPages();

            console.log(`[SW ${SW_VERSION}] Activated — old caches cleaned`);
        })()
    );
});

/* ================================================================
   FETCH — smart routing by resource type
   ================================================================ */
self.addEventListener('fetch', evt => {
    const req = evt.request;
    if (req.method !== 'GET') return;

    const url = new URL(req.url);
    const isSameOrigin = url.origin === self.location.origin;
    const isSensitive = SENSITIVE_ROUTES.some(p => url.pathname.startsWith(p));

    // ── Navigation requests (HTML pages) ─────────────────────────
    if (req.mode === 'navigate') {
        if (isSensitive) {
            evt.respondWith(networkFirstPages(req, true));
        } else {
            evt.respondWith(staleWhileRevalidatePages(req));
        }
        return;
    }

    // ── Same-origin static assets (cache-first) ──────────────────
    if (isSameOrigin && isStaticAsset(url.pathname)) {
        evt.respondWith(cacheFirstStatic(req));
        return;
    }

    // ── Same-origin HTML/API requests (stale-while-revalidate) ───
    if (isSameOrigin && !isSensitive) {
        evt.respondWith(staleWhileRevalidate(req));
        return;
    }

    // ── Cross-origin CDN resources (stale-while-revalidate) ──────
    if (!isSameOrigin) {
        evt.respondWith(staleWhileRevalidateCDN(req));
        return;
    }

    // ── Sensitive routes — network only ──────────────────────────
    evt.respondWith(fetch(req));
});

/* ================================================================
   CACHING STRATEGIES
   ================================================================ */

// ── Strategy: Network-first for HTML pages ───────────────────────
// Serves cached version instantly, updates in background.
// Falls back to /offline page when completely offline.
async function networkFirstPages(req, isSensitive) {
    try {
        const res = await fetch(req);
        if (res.ok && res.status === 200 && !res.redirected && !isSensitive) {
            const cache = await caches.open(PAGES_CACHE);
            cache.put(req, res.clone());
            // Evict old pages if over limit
            trimCache(PAGES_CACHE, MAX_PAGES_ENTRIES);
        }
        return res;
    } catch (e) {
        // Network failed — try cache
        const cached = await caches.match(req);
        if (cached) return cached;

        // Last resort — offline page
        const offline = await caches.match('/offline');
        return offline || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
    }
}

// ── Strategy: Stale-while-revalidate for HTML pages ────────────
// Serves cached version instantly, updates in background.
// This gives instant repeat visits (<10ms) even on cold starts.
async function staleWhileRevalidatePages(req) {
    const cached = await caches.match(req);

    // Fetch in background to update cache
    const fetchPromise = fetch(req).then(res => {
        if (res.ok && res.status === 200 && !res.redirected) {
            const cache = caches.open(PAGES_CACHE);
            cache.then(c => {
                c.put(req, res.clone());
                trimCache(PAGES_CACHE, MAX_PAGES_ENTRIES);
            });
        }
        return res;
    }).catch(() => cached); // Network failed, return cached

    // Return cached immediately if available, otherwise wait for network
    return cached || fetchPromise;
}

// ── Strategy: Cache-first for immutable static assets ────────────
// Never revalidates — assets have cache-busting ?v= timestamps.
async function cacheFirstStatic(req) {
    const cached = await caches.match(req);
    if (cached) return cached;

    try {
        const res = await fetch(req);
        if (res.ok) {
            const cache = await caches.open(STATIC_CACHE);
            cache.put(req, res.clone());
            trimCache(STATIC_CACHE, MAX_STATIC_ENTRIES);
        }
        return res;
    } catch (e) {
        return new Response('', { status: 408 });
    }
}

// ── Strategy: Stale-while-revalidate for same-origin ─────────────
// Serve cached instantly, update cache in background.
async function staleWhileRevalidate(req) {
    const cached = await caches.match(req);

    // Fetch in background to update cache
    const fetchPromise = fetch(req).then(res => {
        if (res.ok && res.status === 200) {
            const cache = caches.open(PAGES_CACHE);
            cache.then(c => c.put(req, res.clone()));
        }
        return res;
    }).catch(() => cached);

    return cached || fetchPromise;
}

// ── Strategy: Stale-while-revalidate for CDN ─────────────────────
// Serve cached instantly, refresh in background (longer TTL).
async function staleWhileRevalidateCDN(req) {
    const cached = await caches.match(req);

    const fetchPromise = fetch(req).then(res => {
        if (res.ok && res.status === 200) {
            const cache = caches.open(CDN_CACHE);
            cache.then(c => {
                c.put(req, res.clone());
                trimCache(CDN_CACHE, MAX_CDN_ENTRIES);
            });
        }
        return res;
    }).catch(() => cached);

    return cached || fetchPromise;
}

/* ================================================================
   HELPERS
   ================================================================ */

// Check if a pathname is a static asset
function isStaticAsset(pathname) {
    return pathname.startsWith('/static/') ||
           pathname.endsWith('.css') ||
           pathname.endsWith('.js') ||
           pathname.endsWith('.woff2') ||
           pathname.endsWith('.png') ||
           pathname.endsWith('.jpg') ||
           pathname.endsWith('.svg') ||
           pathname.endsWith('.ico');
}

// Evict oldest entries when cache exceeds max size (LRU)
async function trimCache(cacheName, maxEntries) {
    try {
        const cache = await caches.open(cacheName);
        const keys = await cache.keys();
        if (keys.length > maxEntries) {
            // Delete oldest entries (first in cache = oldest)
            const toDelete = keys.slice(0, keys.length - maxEntries);
            await Promise.all(toDelete.map(k => cache.delete(k)));
        }
    } catch (e) {}
}

// Background prefetch of critical pages after activation
async function prefetchPages() {
    try {
        const cache = await caches.open(PAGES_CACHE);
        await Promise.allSettled(
            PREFETCH_PAGES.map(url =>
                fetch(url).then(res => {
                    if (res.ok) return cache.put(url, res);
                }).catch(() => {})
            )
        );
        console.log(`[SW ${SW_VERSION}] Prefetched ${PREFETCH_PAGES.length} pages`);
    } catch (e) {}
}

/* ================================================================
   BACKGROUND SYNC — replay offline form submissions
   ================================================================ */
self.addEventListener('sync', evt => {
    if (evt.tag === 'sg-replay-queue') {
        evt.waitUntil(replayQueuedSubmissions());
    }
});

async function openOfflineDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(OFFLINE_DB_NAME);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(OFFLINE_STORE)) {
                db.createObjectStore(OFFLINE_STORE, { keyPath: 'id', autoIncrement: true });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function replayQueuedSubmissions() {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_STORE);
    const items = await new Promise((resolve, reject) => {
        const req = store.getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });

    for (const item of items) {
        try {
            const init = buildReplayRequest(item);
            const response = await fetch(item.url, init);
            if (response.ok && !response.url.includes('/login')) {
                store.delete(item.id);
            }
        } catch (e) {
            // Leave in queue for next sync attempt
        }
    }
}

function buildReplayRequest(item) {
    const method = item.method || 'POST';
    const hasPhotos = Array.isArray(item.photos) && item.photos.length > 0;
    if (!hasPhotos) {
        const params = new URLSearchParams();
        Object.entries(item.body || {}).forEach(([key, value]) => params.append(key, value));
        return {
            method,
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: params.toString()
        };
    }
    const form = new FormData();
    Object.entries(item.body || {}).forEach(([key, value]) => form.append(key, value));
    for (const photo of item.photos) {
        const file = new File([photo.blob], photo.filename || 'photo.jpg', { type: photo.type });
        form.append(photo.name, file, file.name);
    }
    return { method, body: form };
}

/* ================================================================
   MESSAGE HANDLER — allow pages to control caching
   ================================================================ */
self.addEventListener('message', evt => {
    const data = evt.data;
    if (!data) return;

    if (data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }

    if (data.type === 'CACHE_URLS') {
        // Allow pages to request specific URLs be cached
        (async () => {
            const cache = await caches.open(PAGES_CACHE);
            await Promise.allSettled(
                (data.urls || []).map(url =>
                    fetch(url).then(res => {
                        if (res.ok) return cache.put(url, res);
                    }).catch(() => {})
                )
            );
        })();
    }

    if (data.type === 'GET_CACHE_STATS') {
        // Report cache sizes back to the page
        (async () => {
            const stats = {};
            for (const name of [STATIC_CACHE, PAGES_CACHE, CDN_CACHE]) {
                try {
                    const cache = await caches.open(name);
                    const keys = await cache.keys();
                    stats[name] = keys.length;
                } catch (e) {
                    stats[name] = -1;
                }
            }
            evt.source.postMessage({ type: 'CACHE_STATS', stats });
        })();
    }
});
