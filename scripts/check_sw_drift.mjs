// Deploy-drift check: compare the service worker version in the repo with the
// one actually served by the live deployment.
//
// Why: a stale service worker is silent. Production can keep serving an old
// sw.js (a failed/absent deploy, a build pinned to an older branch, or a CDN
// holding an old copy) while the repo has moved on — exactly the state that let
// the v12 worker keep blocking Google Tag Manager after the v16 fix landed.
// Nothing in the app surfaces that mismatch, so this check does.
//
//   node scripts/check_sw_drift.mjs
//
// Exit codes:
//   0  live service worker is current (same version as the repo)
//   1  DRIFT — the live worker lags the repo (stale deploy)
//   2  INCONCLUSIVE — the live worker could not be read/parsed (network, 404,
//      missing SW_VERSION); treat as a warning, not a drift
//
// Env:
//   SW_PATH       path to the repo worker (default app/static/sw.js)
//   LIVE_SW_URL   deployed worker URL (default https://smartgarbage.onrender.com/sw.js)
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);

/** Pull the `SW_VERSION = 'vNN'` constant out of a worker source string. */
export function extractVersion(source) {
  const m = /SW_VERSION\s*=\s*['"]([^'"]+)['"]/.exec(source || '');
  return m ? m[1].trim() : null;
}

/** 'v16' -> 16, '16' -> 16, anything else -> NaN. */
export function versionNumber(version) {
  const m = /v?(\d+)/i.exec(String(version ?? ''));
  return m ? Number(m[1]) : NaN;
}

/**
 * Classify the pair of versions.
 *   'ok'        live === repo (current)
 *   'drift'     live <  repo (the live worker lags — stale deploy)
 *   'ahead'     live >  repo (the checkout is behind the deployment)
 *   'unknown'   either side unparseable
 */
export function classify(repoVersion, liveVersion) {
  const repo = versionNumber(repoVersion);
  const live = versionNumber(liveVersion);
  if (Number.isNaN(repo) || Number.isNaN(live)) return 'unknown';
  if (live < repo) return 'drift';
  if (live > repo) return 'ahead';
  return 'ok';
}

/** Fetch the live worker and return its version (or null on any failure). */
export async function fetchLiveVersion(url, fetchImpl = globalThis.fetch) {
  const res = await fetchImpl(url, { headers: { 'Cache-Control': 'no-cache' } });
  if (!res.ok) throw new Error(`${url} returned HTTP ${res.status}`);
  return extractVersion(await res.text());
}

export async function main() {
  const swPath = process.env.SW_PATH || path.join(ROOT, 'app', 'static', 'sw.js');
  const liveUrl = process.env.LIVE_SW_URL || 'https://smartgarbage.onrender.com/sw.js';

  let repoVersion;
  try {
    repoVersion = extractVersion(fs.readFileSync(swPath, 'utf8'));
  } catch (err) {
    console.error(`::warning::could not read repo worker at ${swPath}: ${err.message}`);
    console.error('INCONCLUSIVE — cannot read the repo version.');
    return 2;
  }
  console.log(`repo  (${swPath}): SW_VERSION=${repoVersion ?? '<not found>'}`);

  let liveVersion;
  try {
    liveVersion = await fetchLiveVersion(liveUrl);
  } catch (err) {
    console.error(`::warning::could not read live worker at ${liveUrl}: ${err.message}`);
    console.error('INCONCLUSIVE — cannot compare versions.');
    return 2;
  }
  console.log(`live  (${liveUrl}): SW_VERSION=${liveVersion ?? '<not found>'}`);

  const verdict = classify(repoVersion, liveVersion);
  if (verdict === 'ok') {
    console.log(`OK — live worker is current (${liveVersion}).`);
    return 0;
  }
  if (verdict === 'drift') {
    console.error(`DRIFT — live worker ${liveVersion} lags repo ${repoVersion}. ` +
      'The deployment is serving a stale service worker.');
    return 1;
  }
  if (verdict === 'ahead') {
    console.warn(`WARNING — live worker ${liveVersion} is ahead of repo ${repoVersion} ` +
      '(checkout behind the deployment); not a stale-deploy drift.');
    return 0;
  }
  console.error('INCONCLUSIVE — could not parse SW_VERSION on one side.');
  return 2;
}

// Run only when invoked directly (so tests can import the pure helpers).
// Use exitCode, not process.exit(): tearing the process down while undici is
// still closing its fetch handle trips a libuv assertion on Windows.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then((code) => { process.exitCode = code; });
}
