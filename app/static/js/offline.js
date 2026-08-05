/* ============================================================
   SmartGarbage — Offline Form Queue
   Queues form submissions in IndexedDB when offline,
   then replays them when connectivity is restored.

   Photos: File inputs are compressed in-browser (canvas → JPEG,
   max ~1280px at ~0.82 quality — the same limits as the server-side
   Pillow resize) BEFORE being stored in IndexedDB, so a citizen in
   low-signal areas can attach photo evidence to a complaint and it
   arrives intact once connectivity returns — without a multi-MB
   Blob squatting in the offline queue on a low-end phone.
   ============================================================ */

const OFFLINE_DB_NAME = 'smartgarbage-offline';
// v2 adds the hasPhotoIdx index so the sync badge can count photo items with
// store.count()/index.count() instead of pulling every Blob into memory.
const OFFLINE_DB_VERSION = 2;
const OFFLINE_STORE = 'pending-forms';
const OFFLINE_PHOTO_INDEX = 'hasPhotoIdx';

// Largest single RAW photo we're willing to DECODE offline (bytes). Photos
// are compressed client-side (canvas → JPEG ~1280px) before being stored, so
// the IndexedDB footprint of even a multi-MB capture is ~100-600KB — this cap
// guards against decoding absurdly huge files on low-end phones rather than
// protecting storage (which compression already shrinks). Larger files are
// skipped (not queued) rather than blowing up the phone mid-trip.
const MAX_PHOTO_BYTES = 12 * 1024 * 1024; // 12 MB

// Compression limits — mirror the server-side Pillow resize
// (MAX_IMAGE_DIM = 1280, JPEG_QUALITY = 82 in app/routes/__init__.py) so what
// the phone stores ≈ what the server would store anyway.
const MAX_IMAGE_DIM = 1280;      // longest edge, px
const JPEG_QUALITY = 0.82;       // 0-1, matches server JPEG_QUALITY=82

function openOfflineDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(OFFLINE_STORE)) {
                db.createObjectStore(OFFLINE_STORE, { keyPath: 'id', autoIncrement: true });
            }
            // v2: index on the hasPhoto flag so counting never reads photo blobs.
            const store = e.target.transaction.objectStore(OFFLINE_STORE);
            if (!store.indexNames.contains(OFFLINE_PHOTO_INDEX)) {
                store.createIndex(OFFLINE_PHOTO_INDEX, 'hasPhoto');
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// Compute the resized dimensions for a canvas draw: longest edge capped at
// maxEdge (1280), aspect ratio preserved, never upscaled. Pure + exported so
// Node smoke-tests can pin the math without a DOM.
function scaleDimensions(width, height, maxEdge = MAX_IMAGE_DIM) {
    if (!width || !height) return { width, height };
    const scale = Math.min(1, maxEdge / Math.max(width, height));
    return {
        width: Math.max(1, Math.round(width * scale)),
        height: Math.max(1, Math.round(height * scale))
    };
}

// Compress an image File down to JPEG ≤1280px at 0.82 via canvas — mirrors the
// server-side Pillow resize so the offline queue stays small on low-end
// phones. NEVER throws and NEVER loses the photo: any failure (no DOM in Node,
// decode error on exotic formats like HEIC, canvas OOM) falls back to the
// original file so evidence still queues.
async function compressPhoto(file) {
    try {
        if (typeof window === 'undefined' || typeof document === 'undefined') {
            return { blob: file, type: file.type };  // Node tests: no DOM
        }
        let source, width, height;
        if (typeof createImageBitmap === 'function') {
            // Explicit 'from-image' (the spec default) so EXIF orientation is
            // honored consistently even on browsers where the default drifts.
            source = await createImageBitmap(file, { imageOrientation: 'from-image' });
            width = source.width; height = source.height;
        } else {
            const img = new Image();
            const url = URL.createObjectURL(file);
            try {
                await new Promise((res, rej) => {
                    img.onload = res; img.onerror = rej;
                    img.src = url;
                });
                width = img.naturalWidth; height = img.naturalHeight;
                source = img;
            } finally {
                URL.revokeObjectURL(url);
            }
        }
        const dims = scaleDimensions(width, height);
        const canvas = document.createElement('canvas');
        canvas.width = dims.width;
        canvas.height = dims.height;
        const ctx = canvas.getContext('2d');
        // White backing so transparent PNGs don't go black as JPEG.
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, dims.width, dims.height);
        try {
            ctx.drawImage(source, 0, 0, dims.width, dims.height);
        } finally {
            // Always release the decoded bitmap — if drawImage throws (e.g.
            // SVG canvas tainting) and we skip this, a 12MP decoded bitmap
            // would sit in memory until GC on exactly the low-end phones this
            // feature targets.
            if (typeof source.close === 'function') source.close();
        }
        const blob = await new Promise((resolve) =>
            canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
        );
        if (blob && blob.size > 0) {
            return { blob, type: 'image/jpeg' };
        }
    } catch (e) {
        // Decode/canvas failure (HEIC, canvas OOM on low-end phones, …) — keep
        // the original file so evidence survives. Log for diagnosis since this
        // is a realistic failure mode on the very devices this targets.
        console.warn('Photo compression failed — queueing original:', e);
    }
    return { blob: file, type: file.type || 'application/octet-stream' };
}

// Split a FormData into plain text fields + queued photos.
// Returns { body: {field: value}, photos: [{name, filename, type, blob}], skippedPhotos: int }
// Photos are compressed in-browser before queueing (canvas → JPEG ≤1280px) so
// the IndexedDB queue stays small on low-end phones; oversized RAW files are
// counted and omitted — the form still queues, just without that attachment.
// `compress` is injectable so Node smoke-tests can exercise the wiring with a
// fake compressor (no DOM/canvas available there).
async function collectFormPayload(formData, compress = compressPhoto) {
    const body = {};
    const photos = [];
    let skippedPhotos = 0;
    for (const [key, value] of formData.entries()) {
        if (value instanceof File) {
            if (value.size > 0 && value.size <= MAX_PHOTO_BYTES) {
                const processed = await compress(value);
                photos.push({
                    name: key,
                    filename: value.name,
                    type: processed.type || value.type || 'application/octet-stream',
                    blob: processed.blob   // compressed JPEG Blob, or original on fallback
                });
            } else if (value.size > MAX_PHOTO_BYTES) {
                skippedPhotos += 1;
            }
            // Empty file inputs (no selection) are ignored entirely.
        } else {
            body[key] = value;
        }
    }
    return { body, photos, skippedPhotos };
}

async function queueFormSubmission(url, method, payload) {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_STORE);
    store.add({
        url,
        method,
        body: payload.body,
        photos: payload.photos || [],
        // Stored as a NUMBER (0/1), not a boolean: IndexedDB only accepts
        // number/string/Date/binary/array as keys, so a `true` value would
        // never enter the hasPhotoIdx index and index.count() below would
        // throw DataError — silently killing the pending-sync badge.
        hasPhoto: (payload.photos || []).length > 0 ? 1 : 0,
        attempts: 0,
        timestamp: Date.now()
    });
    const result = await new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
        try {
            const reg = await navigator.serviceWorker.ready;
            await reg.sync.register('sg-replay-queue');
        } catch (e) { }
    }
    return result;
}

async function getQueuedSubmissions() {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readonly');
    const store = tx.objectStore(OFFLINE_STORE);
    const request = store.getAll();
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// Count everything still waiting in the queue without materializing the
// photo Blobs. `total` = all queued records (store.count), `photos` = items
// carrying photo evidence (index count on hasPhoto). Legacy v1 records lack
// the hasPhoto field and fall out of the index — they still count toward
// `total` and are correctly replayed, they just don't claim a photo badge
// until re-queued; acceptable for the one-time v1->v2 upgrade.
async function countQueuedSubmissions() {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readonly');
    const store = tx.objectStore(OFFLINE_STORE);
    const totalReq = store.count();
    // Fail soft if the index is ever missing (corrupt/partial v1 upgrade):
    // photo count degrades to 0 rather than throwing synchronously.
    const index = store.indexNames.contains(OFFLINE_PHOTO_INDEX)
        ? store.index(OFFLINE_PHOTO_INDEX) : null;
    const photosReq = index ? index.count(1) : null;  // key === 1 (number-encoded)
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve({
            total: totalReq.result,
            photos: photosReq ? photosReq.result : 0
        });
        tx.onerror = () => reject(tx.error);
    });
}

// Pure label builder (Node-testable): "2 reports waiting to sync", with the
// photo count surfaced when any pending item carries evidence.
function pendingSyncLabel(total, photos) {
    const noun = total === 1 ? 'report' : 'reports';
    if (total === 0) return 'No reports waiting to sync';
    if (photos > 0) {
        return total + ' ' + noun + ' waiting to sync (' + photos + ' with photo)';
    }
    return total + ' ' + noun + ' waiting to sync';
}

// Refresh the persistent pending-sync indicator: the header badge (every
// page, via base.html) and the offline page's detail slot. Hidden when the
// queue is empty; a click triggers an immediate replay when online (or sends
// the citizen to the offline page when not). Best-effort — never throws on
// missing elements or an unavailable IndexedDB.
async function renderSyncIndicator() {
    try {
        const { total, photos } = await countQueuedSubmissions();
        const label = pendingSyncLabel(total, photos);

        const badge = document.getElementById('syncPendingBadge');
        if (badge) {
            badge.textContent = total > 0 ? ('🕓 ' + label) : '';
            badge.classList.toggle('d-none', total === 0);
            badge.setAttribute('aria-label', label);
        }

        const slot = document.getElementById('syncPendingSlot');
        if (slot) {
            slot.textContent = label;
            slot.classList.toggle('d-none', total === 0);
        }
    } catch (e) {
        // IndexedDB unavailable or page mid-teardown — leave the indicator as-is.
    }
}

// Click-to-sync: force an immediate replay when online; otherwise send the
// citizen to the offline page where the pending queue is spelled out.
// Confirms the tap with a toast so the user knows the sync started.
async function onSyncBadgeClick() {
    if (navigator.onLine) {
        // Counting is cosmetic — never let a count failure block the replay.
        let total = null;
        try {
            ({ total } = await countQueuedSubmissions());
        } catch (e) { /* IndexedDB unavailable — replay anyway. */ }
        offlineToast(total === null
            ? '🔄 Syncing saved reports…'
            : '🔄 Syncing ' + total + ' saved ' + (total === 1 ? 'report' : 'reports') + '…');
        await replayQueuedSubmissions();
    } else if (window.location.pathname !== '/offline') {
        window.location.href = '/offline';
    }
}

async function removeQueuedSubmission(id) {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_STORE);
    store.delete(id);
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

// Tiny toast used only when the page hasn't defined its own `showToast`
// (dashboard.html and admin.js define richer ones). This keeps the offline
// queue functional on every page, not just the dashboard.
function offlineToast(msg) {
    let toast = document.getElementById('offlineToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'offlineToast';
        toast.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);' +
            'background:#0f5132;color:#fff;padding:12px 20px;border-radius:12px;z-index:9999;' +
            'box-shadow:0 4px 16px rgba(0,0,0,0.25);font-weight:600;max-width:90vw;text-align:center;';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    clearTimeout(offlineToast._timer);
    offlineToast._timer = setTimeout(() => { toast.style.opacity = '0'; }, 4000);
}

// A stale CSRF token (rotated session) would keep a replay 400-ing forever;
// give each queued item a few attempts, then drop it so the queue doesn't
// grow unboundedly with undeliverable submissions.
const MAX_REPLAY_ATTEMPTS = 3;

// Photos are irreplaceable evidence — a replay that keeps failing (e.g. the
// session/CSRF token rotated while the citizen was offline) must NOT be
// silently deleted. Photo items are retried on every replay pass (replays
// only fire on `online`/DOMContentLoaded, so this can't hammer a server) and
// get a fresh CSRF token via refreshCsrfToken() — which gives them a real
// recovery path: reconnect, replay succeeds once the session is valid again.
// Plain text items keep the drop-after-3 behavior above.

// Guard against concurrent replay runs (DOMContentLoaded + the `online`
// listener firing close together) which could double-submit the same item.
let replayInFlight = false;

// Fetch the queued record, apply a mutation, and write it back — the single
// place that knows the record must be merged (a bare put({id, ...}) would
// silently drop the queued url/method/body/photos payload).
async function updateQueuedRecord(id, mutator) {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_STORE);
    const existing = await new Promise((resolve, reject) => {
        const req = store.get(id);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
    if (existing) {
        mutator(existing);
        store.put(existing);
    }
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function markReplayAttempt(id, attempts) {
    await updateQueuedRecord(id, (rec) => { rec.attempts = attempts; });
}

// Build the fetch() body for one queued item.
//   - With photos: multipart/form-data. DO NOT set Content-Type manually —
//     the browser generates the multipart boundary itself; a hand-written
//     header would corrupt the body framing.
//   - Without photos: application/x-www-form-urlencoded (what Flask's
//     request.form parses for plain forms).
function hasQueuedPhotos(item) {
    return Array.isArray(item.photos) && item.photos.length > 0;
}

// Every replay carries a marker header so the server can tell queue-delivered
// submissions apart from live form posts — that's how the admin "offline
// delivery" dashboard counts complaints/photos that arrived via the queue.
const REPLAY_HEADER = 'X-Offline-Replay';
const REPLAY_ATTEMPTS_HEADER = 'X-Offline-Attempts';

function buildReplayRequest(item) {
    const method = item.method || 'POST';
    const replayHeaders = {
        [REPLAY_HEADER]: '1',
        [REPLAY_ATTEMPTS_HEADER]: String(item.attempts || 0)
    };
    const hasPhotos = hasQueuedPhotos(item);
    if (!hasPhotos) {
        const params = new URLSearchParams();
        Object.entries(item.body || {}).forEach(([key, value]) => params.append(key, value));
        return {
            method,
            headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...replayHeaders },
            body: params.toString()
        };
    }
    const form = new FormData();
    Object.entries(item.body || {}).forEach(([key, value]) => form.append(key, value));
    for (const photo of item.photos) {
        // IndexedDB returns the blob as a Blob; re-wrap it in a File so the
        // server's request.files sees the original filename + mime type.
        const file = new File([photo.blob], photo.filename || 'photo.jpg', { type: photo.type });
        form.append(photo.name, file, file.name);
    }
    return { method, headers: replayHeaders, body: form };
}

// Refresh a stale CSRF token before replaying a PHOTO item. Sessions expire
// (1h) and Flask-WTF tokens are session-bound, so a queued offline submission
// replayed hours later carries a dead token that would 400 forever. GET the
// form page (same-origin cookies are sent automatically), pull the fresh
// token out of the rendered HTML, and swap it into the queued body.
// Best-effort: returns false on any failure and the replay proceeds with the
// stored token. Only photo items refresh (they're the ones that persist) —
// plain items get the 3-attempt drop, and /report is rate-limited at 15/hour,
// so we avoid burning that budget on GET+POST pairs for non-photo forms.
async function refreshCsrfToken(item) {
    if (!item.body || typeof item.body.csrf_token !== 'string') return false;
    try {
        const res = await fetch(item.url, { method: 'GET', credentials: 'same-origin' });
        if (!res.ok) return false;
        const html = await res.text();
        // Robust to attribute order: matches `name="csrf_token" ... value="..."`
        // whether the token is rendered by hand or by Flask-WTF's default order.
        const match = html.match(/name="csrf_token"[^>]*value="([^"]+)"/);
        if (match && match[1]) {
            item.body.csrf_token = match[1];
            return true;
        }
    } catch (e) {
        // Network blip or CSP-blocked fetch — keep the stored token.
    }
    return false;
}

async function replayQueuedSubmissions() {
    if (replayInFlight) return;
    replayInFlight = true;
    try {
        await doReplay();
    } finally {
        replayInFlight = false;
    }
}

async function doReplay() {
    const items = await getQueuedSubmissions();
    for (const item of items) {
        try {
            // Session rotation is exactly what stalls a delayed offline submit:
            // grab a fresh CSRF token from the form page before replaying.
            // Scoped to photo items only — see refreshCsrfToken() for why.
            if (hasQueuedPhotos(item)) await refreshCsrfToken(item);
            const init = buildReplayRequest(item);
            const response = await fetch(item.url, init);
            // A logged-out replay follows the 302 to /login and would look like
            // a 200 success — but the complaint was never created. Treat any
            // redirect to /login as a failed replay, not a delivery.
            const delivered = response.ok && !response.url.includes('/login');
            if (delivered) {
                await removeQueuedSubmission(item.id);
                console.log('Replayed queued submission:', item.url);
            } else {
                const hasPhotos = hasQueuedPhotos(item);
                const attempts = (item.attempts || 0) + 1;
                if (hasPhotos) {
                    // Photos are never auto-dropped — evidence survives, and a
                    // later reconnect (valid session, fresh token) delivers it.
                    await markReplayAttempt(item.id, attempts);
                    console.warn('Photo replay rejected (' + response.status +
                        '), attempt ' + attempts + ' — kept for retry:', item.url);
                } else if (attempts >= MAX_REPLAY_ATTEMPTS) {
                    await removeQueuedSubmission(item.id);
                    console.warn('Dropped queued submission after ' + attempts + ' attempts:', item.url);
                } else {
                    await markReplayAttempt(item.id, attempts);
                    console.warn('Replay rejected (' + response.status + '), attempt ' + attempts + ':', item.url);
                }
            }
        } catch (e) {
            console.warn('Failed to replay queued submission:', item.url, e);
        }
    }
    renderSyncIndicator();  // delivered items leave the queue — badge shrinks
}

function setupOfflineForms() {
    const forms = document.querySelectorAll('form[data-offline-queue]');
    forms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            if (navigator.onLine) return; // normal submit when online
            e.preventDefault();
            const url = form.action || window.location.href;
            const method = form.method || 'POST';
            const formData = new FormData(form);
            const payload = await collectFormPayload(formData);
            try {
                await queueFormSubmission(url, method, payload);
                let msg = '📥 Form saved offline — will sync when you reconnect';
                if (payload.photos.length > 0) {
                    msg = '📸 Form + photo saved offline — will sync when you reconnect';
                }
                if (payload.skippedPhotos > 0) {
                    msg += ' (photo too large to save)';
                }
                offlineToast(msg);
                renderSyncIndicator();  // badge reflects the newly queued report
            } catch (err) {
                offlineToast('⚠️ Could not save offline. Please reconnect and retry.');
            }
        });
    });
}

// Expose pure helpers for Node smoke-tests without polluting the browser globals.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        collectFormPayload, buildReplayRequest, hasQueuedPhotos, refreshCsrfToken,
        pendingSyncLabel, compressPhoto, scaleDimensions,
        MAX_PHOTO_BYTES, MAX_IMAGE_DIM, JPEG_QUALITY
    };
}

// Browser-only wiring. The guard keeps this file require()able from Node for
// the smoke-tests (window doesn't exist there).
if (typeof window !== 'undefined') {
    window.addEventListener('online', () => {
        console.log('Back online — replaying queued submissions');
        replayQueuedSubmissions();
        renderSyncIndicator();
    });

    window.addEventListener('DOMContentLoaded', () => {
        setupOfflineForms();
        // Replay anything queued from a previous offline session right away.
        if (navigator.onLine) replayQueuedSubmissions();
        // Paint the persistent badge (hidden when nothing is queued).
        const badge = document.getElementById('syncPendingBadge');
        if (badge) badge.addEventListener('click', onSyncBadgeClick);
        renderSyncIndicator();
    });
}
