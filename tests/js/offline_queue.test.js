/* ============================================================
   SmartGarbage — offline.js helper smoke-tests
   Run with:  node tests/js/offline_queue.test.js
   (Pure Node — no browser, no test framework, no network.)

   Covers the exported helpers added for the offline-photo
   pipeline:
     - collectFormPayload: FormData -> { body, photos, skippedPhotos }
     - buildReplayRequest: queued item -> fetch() init (multipart
       when photos exist, urlencoded otherwise), tagged with the
       X-Offline-Replay marker for the admin delivery dashboard
   ============================================================ */
const assert = require('node:assert');
const { collectFormPayload, buildReplayRequest, hasQueuedPhotos, refreshCsrfToken,
        pendingSyncLabel, compressPhoto, scaleDimensions,
        MAX_PHOTO_BYTES, MAX_IMAGE_DIM, JPEG_QUALITY } = require('../../app/static/js/offline.js');

// refreshCsrfToken needs global fetch — stub it for the test.
const realFetch = global.fetch;
function stubFetch(responder) {
    global.fetch = async (url, init) => {
        const body = responder(url, init);
        return {
            ok: true,
            text: async () => body
        };
    };
}
function restoreFetch() {
    global.fetch = realFetch;
}

(async function run() {


let passed = 0;
function ok(cond, label) {
    if (!cond) throw new Error('FAIL: ' + label);
    passed += 1;
    console.log('  ✓ ' + label);
}

// ── scaleDimensions (canvas resize math, mirrors server Pillow 1280px) ──
console.log('scaleDimensions');
{
    ok(scaleDimensions(4000, 3000).width === 1280, 'longest edge capped at 1280');
    ok(scaleDimensions(4000, 3000).height === 960, 'aspect ratio preserved (4000x3000 -> 1280x960)');
    ok(scaleDimensions(2000, 1000).width === 1280, 'wide image capped on width');
    ok(scaleDimensions(2000, 1000).height === 640, 'wide image scaled proportionally');
    ok(scaleDimensions(800, 600).width === 800 && scaleDimensions(800, 600).height === 600, 'small image never upscaled');
    ok(scaleDimensions(1000, 2000).width === 640 && scaleDimensions(1000, 2000).height === 1280, 'portrait capped on height');
    ok(MAX_IMAGE_DIM === 1280 && JPEG_QUALITY === 0.82, 'constants mirror server Pillow limits');
}

// ── compressPhoto (graceful no-DOM fallback) ─────────────────
console.log('compressPhoto');
{
    // Node has no window/document/canvas: the compressor must return the
    // original file untouched (never throw, never lose the photo).
    const f = new File([new Uint8Array([9, 9, 9])], 'raw.png', { type: 'image/png' });
    const out = await compressPhoto(f);
    ok(out.blob === f, 'no-DOM fallback returns the original file');
    ok(out.type === 'image/png', 'no-DOM fallback preserves the original mime');
}

// ── collectFormPayload (async; injectable compressor) ────────
console.log('collectFormPayload');

{
    const fd = new FormData();
    fd.append('name', 'Ravi');
    fd.append('ward', 'Ward 1 - MVGR College Area');
    const photo = new File([new Uint8Array([1, 2, 3, 4])], 'evidence.jpg', { type: 'image/jpeg' });
    fd.append('photo', photo);
    const p = await collectFormPayload(fd);
    ok(p.body.name === 'Ravi' && p.body.ward === 'Ward 1 - MVGR College Area', 'text fields land in body');
    ok(p.photos.length === 1, 'one photo captured');
    ok(p.photos[0].name === 'photo' && p.photos[0].filename === 'evidence.jpg', 'photo field + filename preserved');
    ok(p.photos[0].type === 'image/jpeg', 'photo mime preserved');
    ok(p.skippedPhotos === 0, 'no skipped photos');
}

{
    // With a fake compressor injected, the blob is the compressed output —
    // proves collectFormPayload routes photos through the compressor.
    const fd = new FormData();
    fd.append('photo', new File([new Uint8Array([1, 2, 3, 4])], 'big.jpg', { type: 'image/jpeg' }));
    const fakeCompress = async () => ({ blob: new Blob(['compressed']), type: 'image/jpeg' });
    const p = await collectFormPayload(fd, fakeCompress);
    ok(p.photos[0].blob instanceof Blob && p.photos[0].type === 'image/jpeg', 'injected compressor output used');
}

{
    // Empty file input (user never picked a file) must be ignored, not queued.
    const fd = new FormData();
    fd.append('name', 'Ravi');
    fd.append('photo', new File([], ''));
    const p = await collectFormPayload(fd);
    ok(p.photos.length === 0, 'empty file input skipped');
    ok(p.body.name === 'Ravi', 'fields still collected when file empty');
}

{
    // Oversized file is skipped but counted, and the form still queues.
    const fd = new FormData();
    fd.append('description', 'huge dump');
    const big = new File([new Uint8Array(MAX_PHOTO_BYTES + 1)], 'huge.jpg', { type: 'image/jpeg' });
    fd.append('photo', big);
    const p = await collectFormPayload(fd);
    ok(p.photos.length === 0, 'oversized photo not queued');
    ok(p.skippedPhotos === 1, 'oversized photo counted as skipped');
    ok(p.body.description === 'huge dump', 'form fields still collected with skipped photo');
}

// ── buildReplayRequest ────────────────────────────────────────
console.log('buildReplayRequest');

{
    // No photos → application/x-www-form-urlencoded body.
    const init = buildReplayRequest({ method: 'POST', body: { name: 'Ravi', csrf_token: 'abc' } });
    ok(init.method === 'POST', 'method preserved');
    ok(init.headers['Content-Type'] === 'application/x-www-form-urlencoded', 'urlencoded content-type when no photos');
    ok(typeof init.body === 'string' && init.body.includes('name=Ravi'), 'urlencoded body has fields');
}

{
    // Replays must be tagged so the admin dashboard can count queue deliveries.
    const init = buildReplayRequest({ method: 'POST', body: {}, attempts: 2 });
    ok(init.headers['X-Offline-Replay'] === '1', 'replay marker header present');
    ok(init.headers['X-Offline-Attempts'] === '2', 'replay attempts header present');
    const fresh = buildReplayRequest({ method: 'POST', body: {} });
    ok(fresh.headers['X-Offline-Attempts'] === '0', 'attempts default to 0 when absent');
}

{
    // Photo replays carry the same marker headers (without manual Content-Type).
    const blob = new Blob([new Uint8Array([7, 7, 7])], { type: 'image/jpeg' });
    const init = buildReplayRequest({
        method: 'POST', body: {}, attempts: 1,
        photos: [{ name: 'photo', filename: 'p.jpg', type: 'image/jpeg', blob }]
    });
    ok(init.headers['X-Offline-Replay'] === '1', 'photo replay marker header present');
    ok(init.headers['X-Offline-Attempts'] === '1', 'photo replay attempts header present');
    ok(!init.headers['Content-Type'], 'photo replay still omits manual Content-Type');
}

{
    // With photos → FormData multipart, no manual Content-Type header.
    const blob = new Blob([new Uint8Array([9, 9, 9])], { type: 'image/png' });
    const item = {
        method: 'POST',
        body: { name: 'Ravi', csrf_token: 'abc' },
        photos: [{ name: 'photo', filename: 'dump.png', type: 'image/png', blob }]
    };
    const init = buildReplayRequest(item);
    ok(init.body instanceof FormData, 'multipart FormData body when photos present');
    ok(!init.headers || !init.headers['Content-Type'], 'no manual Content-Type (browser sets multipart boundary)');
    ok(init.body.has('name') && init.body.get('name') === 'Ravi', 'text fields included in multipart');
    const f = init.body.get('photo');
    ok(f instanceof File, 'photo re-wrapped as File');
    ok(f.name === 'dump.png', 'photo filename preserved for request.files');
    ok(f.type === 'image/png', 'photo mime preserved');
}

{
    // Default method is POST when absent.
    const init = buildReplayRequest({ body: {} });
    ok(init.method === 'POST', 'defaults to POST');
}

// ── hasQueuedPhotos ────────────────────────────────────────────
console.log('hasQueuedPhotos');
{
    ok(!hasQueuedPhotos({ body: {} }), 'no photos -> false');
    ok(!hasQueuedPhotos({ photos: [] }), 'empty photos array -> false');
    ok(hasQueuedPhotos({ photos: [{ name: 'photo' }] }), 'photos present -> true');
}

// ── refreshCsrfToken ───────────────────────────────────────────
console.log('refreshCsrfToken');

{
    // Fresh token is pulled from the form page and swapped into the body.
    stubFetch(() => '<form><input type="hidden" name="csrf_token" value="NEW-TOKEN"></form>');
    const item = { url: '/report', body: { name: 'Ravi', csrf_token: 'OLD-TOKEN' } };
    const refreshed = await refreshCsrfToken(item);
    ok(refreshed === true, 'refresh reports success');
    ok(item.body.csrf_token === 'NEW-TOKEN', 'stale token replaced with fresh one');

    // No token in body -> skipped, unchanged.
    const noToken = { url: '/x', body: { name: 'Ravi' } };
    ok((await refreshCsrfToken(noToken)) === false, 'no stored token -> skipped');

    // Form page without a csrf_token -> keep stored token.
    stubFetch(() => '<html><body>no form</body></html>');
    const plain = { url: '/y', body: { name: 'Ravi', csrf_token: 'KEEP-ME' } };
    ok((await refreshCsrfToken(plain)) === false, 'no token in page -> not refreshed');
    ok(plain.body.csrf_token === 'KEEP-ME', 'stored token preserved when page lacks one');

    // Attribute-order robustness: token rendered by Flask-WTF's default order
    // (id=... name=... type=... value=...) must still be found.
    stubFetch(() => '<input id="csrf_token" name="csrf_token" type="hidden" value="ORDERED-TOKEN">');
    const ordered = { url: '/z', body: { name: 'Ravi', csrf_token: 'OLD' } };
    ok((await refreshCsrfToken(ordered)) === true, 'attribute-order variant matched');
    ok(ordered.body.csrf_token === 'ORDERED-TOKEN', 'token swapped for reordered attributes');
}

restoreFetch();

// ── pendingSyncLabel (persistent sync-pending indicator copy) ──
console.log('pendingSyncLabel');
{
    ok(pendingSyncLabel(0, 0) === 'No reports waiting to sync', 'empty queue label');
    ok(pendingSyncLabel(1, 0) === '1 report waiting to sync', 'singular noun');
    ok(pendingSyncLabel(2, 0) === '2 reports waiting to sync', 'plural noun');
    ok(pendingSyncLabel(3, 1) === '3 reports waiting to sync (1 with photo)', 'photo count surfaced');
    ok(pendingSyncLabel(2, 2) === '2 reports waiting to sync (2 with photo)', 'all-photo label');
    ok(pendingSyncLabel(1, 1) === '1 report waiting to sync (1 with photo)', 'singular + photo');
}

console.log(`\nAll ${passed} offline.js assertions passed ✓`);
})().catch((err) => {
    console.error(err);
    process.exit(1);
});
