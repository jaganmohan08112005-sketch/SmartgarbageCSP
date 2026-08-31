const CACHE_NAME = 'smartgarbage-pwa-v10';
const OFFLINE_DB_NAME = 'smartgarbage-offline';
const OFFLINE_STORE = 'pending-forms';

// Core citizen + public pages precached on install so they work fully offline.
// (Rural Andhra deployments hit spotty connectivity — offline-first matters here.)
const PRECACHE = [
    '/',
    '/login',
    '/dashboard',
    '/schedule',
    '/report',
    '/transparency',
    '/faq',
    '/offline',
    '/static/css/critical.css',
    '/static/style.css',
    '/static/fonts/outfit-v15.woff2',
    '/static/chintalavalasa_locations.js',
    '/static/js/offline.js',
    '/static/manifest.json',
    '/static/vendor/bootstrap.min.css',
    '/static/vendor/bootstrap.bundle.min.js',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

// Install: precache core assets + the offline fallback page.
self.addEventListener('install', evt => {
    evt.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('SmartGarbage SW: precaching assets');
            return cache.addAll(PRECACHE);
        })
    );
    self.skipWaiting();
});

// Activate: drop stale caches from previous versions.
self.addEventListener('activate', evt => {
    evt.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

// Background Sync: replay queued offline submissions when connectivity returns,
// even if the tab is closed.
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

// Fetch:
//  - Navigation requests (HTML pages): network-first, fall back to cached
//    page, then to the dedicated /offline page when fully offline.
//  - Static assets: cache-first with background refresh.
// Sensitive routes that should never be stored in static CacheStorage for offline fallback
const SENSITIVE_ROUTES = ['/admin', '/dashboard', '/payt', '/login', '/mfa'];

self.addEventListener('fetch', evt => {
    const req = evt.request;
    if (req.method !== 'GET') return; // never cache POST/PUT/etc.

    const url = new URL(req.url);
    const isSensitive = SENSITIVE_ROUTES.some(path => url.pathname.startsWith(path));

    if (req.mode === 'navigate') {
        evt.respondWith(
            fetch(req).then(res => {
                // Only cache non-sensitive, valid 200 OK non-redirected HTML pages
                if (res.ok && res.status === 200 && !res.redirected && !isSensitive) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(req, copy));
                }
                return res;
            }).catch(() =>
                caches.match(req).then(cached =>
                    cached || caches.match('/offline')
                )
            )
        );
        return;
    }

    evt.respondWith(
        caches.match(req).then(cached => {
            if (cached) {
                // Refresh in background if response is valid.
                fetch(req).then(res => {
                    if (res.ok && res.status === 200 && !isSensitive) {
                        caches.open(CACHE_NAME).then(c => c.put(req, res.clone()));
                    }
                }).catch(() => {});
                return cached;
            }
            return fetch(req).then(res => {
                if (res.ok && res.status === 200 && (res.type === 'basic' || res.type === 'cors') && !isSensitive) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(req, copy));
                }
                return res;
            });
        })
    );
});

