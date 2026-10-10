/* ============================================================
   SmartGarbage — service-worker deploy-drift check: unit tests
   Run with:  node tests/js/sw_drift.test.mjs
   (Pure Node — no network, no framework.)

   Covers the pure helpers behind scripts/check_sw_drift.mjs so the "live
   worker lags the repo" rule can't silently regress.
   ============================================================ */
import assert from 'node:assert';
import {
  extractVersion,
  versionNumber,
  classify,
  fetchLiveVersion,
} from '../../scripts/check_sw_drift.mjs';

let n = 0;
const ok = async (label, fn) => { await fn(); n++; console.log('  \u2713 ' + label); };

console.log('sw drift check');

await ok('extractVersion reads the SW_VERSION constant', () => {
  assert.equal(extractVersion("const SW_VERSION = 'v16';"), 'v16');
  assert.equal(extractVersion('const SW_VERSION = "3";'), '3');
});

await ok('extractVersion tolerates extra spacing', () => {
  assert.equal(extractVersion('const  SW_VERSION="v7";'), 'v7');
});

await ok('extractVersion returns null when absent', () => {
  assert.equal(extractVersion('/* no version here */'), null);
  assert.equal(extractVersion(''), null);
});

await ok('versionNumber normalizes v-prefixed and bare numbers', () => {
  assert.equal(versionNumber('v16'), 16);
  assert.equal(versionNumber('16'), 16);
  assert.equal(versionNumber('v0'), 0);
  assert.ok(Number.isNaN(versionNumber('nope')));
  assert.ok(Number.isNaN(versionNumber(null)));
});

await ok('classify: live lagging the repo is drift', () => {
  assert.equal(classify('v16', 'v12'), 'drift');
  assert.equal(classify('v16', 'v15'), 'drift');
});

await ok('classify: equal versions are current', () => {
  assert.equal(classify('v16', 'v16'), 'ok');
  assert.equal(classify('16', 'v16'), 'ok');
});

await ok('classify: live ahead of repo is not drift', () => {
  assert.equal(classify('v12', 'v16'), 'ahead');
});

await ok('classify: unparseable versions are unknown', () => {
  assert.equal(classify('v16', null), 'unknown');
  assert.equal(classify('v16', 'oops'), 'unknown');
});

await ok('fetchLiveVersion extracts the version from a 200 response', async () => {
  const fakeFetch = async () => ({ ok: true, status: 200, text: async () => "const SW_VERSION = 'v16';" });
  assert.equal(await fetchLiveVersion('https://x/sw.js', fakeFetch), 'v16');
});

await ok('fetchLiveVersion throws on a non-200 response', async () => {
  const fakeFetch = async () => ({ ok: false, status: 404, text: async () => 'not found' });
  await assert.rejects(() => fetchLiveVersion('https://x/sw.js', fakeFetch), /HTTP 404/);
});

console.log(`\nAll ${n} sw-drift assertions passed \u2713`);
