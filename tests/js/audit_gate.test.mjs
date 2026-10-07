/* ============================================================
   SmartGarbage — a11y audit gate: unit tests
   Run with:  node tests/js/audit_gate.test.mjs
   (Pure Node — no network, no browser.)

   Feeds synthetic audit summaries to audit/check-audit.mjs so the
   CI accessibility gate — including the authenticated /worker and
   /admin pages — can't silently weaken or lose coverage.
   ============================================================ */
import assert from 'node:assert';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CHECKER = path.join(HERE, '..', '..', 'audit', 'check-audit.mjs');

function runGate(summary, extraEnv = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sg-audit-gate-'));
  const file = path.join(dir, 'summary.json');
  fs.writeFileSync(file, JSON.stringify(summary));
  const res = spawnSync(process.execPath, [CHECKER], {
    encoding: 'utf8',
    env: { ...process.env, AUDIT_SUMMARY: file, ...extraEnv },
  });
  return { code: res.status, output: `${res.stdout || ''}${res.stderr || ''}` };
}

// Minimal shape check-audit.mjs actually reads.
const citizenOk = () => ({
  lighthouse: { home: { scores: { accessibility: 100 } } },
  axe: { home: { violations: [] } },
});
const authedAxe = (violations = []) => ({
  authed: true,
  url: 'http://127.0.0.1:5057/worker',
  violations,
  passes: 30,
  incomplete: 0,
  inapplicable: 0,
});

let n = 0;
const ok = async (label, fn) => { await fn(); n++; console.log('  \u2713 ' + label); };

console.log('a11y audit gate');

await ok('passes a clean citizen page', () => {
  const r = runGate(citizenOk());
  assert.equal(r.code, 0, r.output);
});

await ok('passes an authenticated page scanned with axe only (no Lighthouse result)', () => {
  const s = citizenOk();
  s.axe.worker = authedAxe();
  const r = runGate(s);
  assert.equal(r.code, 0, r.output);
});

await ok('fails on an authenticated-page axe violation (label/contrast regressions)', () => {
  const s = citizenOk();
  s.axe.worker = authedAxe([{ id: 'aria-command-name', nodes: 1 }]);
  const r = runGate(s);
  assert.equal(r.code, 1);
  assert.match(r.output, /aria-command-name\(1\)/);
});

await ok('fails on an authenticated-page axe error (staff login broke)', () => {
  const s = citizenOk();
  s.axe.admin = { authed: true, url: 'http://127.0.0.1:5057/admin', error: 'no developer OTP on the MFA page' };
  const r = runGate(s);
  assert.equal(r.code, 1);
  assert.match(r.output, /axe errored/);
});

await ok('AUDIT_EXPECT_AUTHED fails when an expected page is missing from the results', () => {
  const r = runGate(citizenOk(), { AUDIT_EXPECT_AUTHED: 'worker,admin' });
  assert.equal(r.code, 1);
  assert.match(r.output, /worker: expected authenticated page missing/);
  assert.match(r.output, /admin: expected authenticated page missing/);
});

await ok('AUDIT_EXPECT_AUTHED passes when both pages are present', () => {
  const s = citizenOk();
  s.axe.worker = authedAxe();
  s.axe.admin = { ...authedAxe(), url: 'http://127.0.0.1:5057/admin' };
  const r = runGate(s, { AUDIT_EXPECT_AUTHED: 'worker,admin' });
  assert.equal(r.code, 0, r.output);
});

await ok('an axe entry without the authed flag still needs a Lighthouse result', () => {
  const s = citizenOk();
  s.axe.worker = { violations: [] }; // flag lost — must NOT be treated as axe-only
  const r = runGate(s);
  assert.equal(r.code, 1);
  assert.match(r.output, /no Lighthouse result/);
});

await ok('still enforces Lighthouse a11y on an authenticated page when a result exists', () => {
  const s = citizenOk();
  s.axe.worker = authedAxe();
  s.lighthouse.worker = { scores: { accessibility: 90 } };
  const r = runGate(s);
  assert.equal(r.code, 1);
  assert.match(r.output, /Lighthouse accessibility 90 < 100/);
});

await ok('still fails a citizen page below the threshold', () => {
  const s = citizenOk();
  s.lighthouse.home.scores.accessibility = 99;
  const r = runGate(s);
  assert.equal(r.code, 1);
  assert.match(r.output, /Lighthouse accessibility 99 < 100/);
});

await ok('still fails a citizen page with an axe violation', () => {
  const s = citizenOk();
  s.axe.home = { violations: [{ id: 'color-contrast', nodes: 2 }] };
  const r = runGate(s);
  assert.equal(r.code, 1);
  assert.match(r.output, /color-contrast\(2\)/);
});

console.log(`\nAll ${n} audit-gate assertions passed \u2713`);
