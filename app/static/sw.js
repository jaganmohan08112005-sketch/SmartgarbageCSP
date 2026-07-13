const CACHE_NAME = 'garbage-pwa-v2';
// Offline pages and static assets to cache
const assets = [
    '/',
    '/worker',
    '/static/style.css',
    '/static/chintalavalasa_locations.js',
    '/static/manifest.json',
    'https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
    'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

// Install Event
self.addEventListener('install', evt => {
    evt.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            console.log('Caching site assets...');
            return cache.addAll(assets);
        })
    );
});

// Activate Event - clean old caches
self.addEventListener('activate', evt => {
    evt.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.filter(key => key !== CACHE_NAME)
                    .map(key => caches.delete(key))
            );
        })
    );
});

// Fetch Event - network-first or cache-fallback to ensure offline usability
self.addEventListener('fetch', evt => {
    evt.respondWith(
        fetch(evt.request).then(networkRes => {
            // Put a copy of successfully fetched request in cache
            if (evt.request.method === 'GET') {
                const resClone = networkRes.clone();
                caches.open(CACHE_NAME).then(cache => {
                    cache.put(evt.request, resClone);
                });
            }
            return networkRes;
        }).catch(() => {
            // Network failure: fallback to cache
            return caches.match(evt.request).then(cacheRes => {
                if (cacheRes) {
                    return cacheRes;
                }
                // If the worker is accessing /worker page offline, return the cached worker layout
                if (evt.request.url.includes('/worker')) {
                    return caches.match('/worker');
                }
                return caches.match('/');
            });
        })
    );
});

