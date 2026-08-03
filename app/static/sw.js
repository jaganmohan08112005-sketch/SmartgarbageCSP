const CACHE_NAME = 'smartgarbage-pwa-v7';
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
    '/offline',
    '/static/style.css',
    '/static/chintalavalasa_locations.js',
    '/static/js/offline.js',
    '/static/manifest.json',
    'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
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
self.addEventListener('fetch', evt => {
    const req = evt.request;
    if (req.method !== 'GET') return; // never cache POST/PUT/etc.

    if (req.mode === 'navigate') {
        evt.respondWith(
            fetch(req).then(res => {
                const copy = res.clone();
                caches.open(CACHE_NAME).then(c => c.put(req, copy));
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
                // Refresh in background.
                fetch(req).then(res => {
                    caches.open(CACHE_NAME).then(c => c.put(req, res.clone()));
                }).catch(() => {});
                return cached;
            }
            return fetch(req).then(res => {
                if (res.ok && (res.type === 'basic' || res.type === 'cors')) {
                    const copy = res.clone();
                    caches.open(CACHE_NAME).then(c => c.put(req, copy));
                }
                return res;
            });
        })
    );
});
