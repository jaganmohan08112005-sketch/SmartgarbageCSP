const CACHE_NAME = 'smartgarbage-pwa-v3';
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
