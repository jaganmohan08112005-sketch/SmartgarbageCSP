// Gate for `npm run audit`: fail (exit 1) when accessibility regresses or axe
// reports any WCAG A/AA violation, so the fixes can't silently rot.
//
//   npm run audit          # writes audit/out/summary.json
//   node audit/check-audit.mjs
//
// Coverage policy:
//   - citizen pages: Lighthouse accessibility >= AUDIT_MIN_A11Y AND 0 axe
//     violations (unchanged).
//   - authenticated staff pages (/worker, /admin): 0 axe violations. The
//     runner flags these axe entries with `authed: true` because they are
//     scanned inside a real login + MFA session, where a Lighthouse run
//     cannot easily share the session — so they are axe-only. If a Lighthouse
//     result IS present for one of them anyway, it is still enforced.
//     An axe entry WITHOUT the `authed` flag still requires a Lighthouse
//     result, so the flag can't be dropped to dodge the Lighthouse gate.
//
// Reads the machine-readable summary the runner already writes, so it needs no
// browser and can be re-run against a saved artifact at any time.
//
// Env:
//   AUDIT_MIN_A11Y      minimum Lighthouse accessibility score per page (default 100)
//   AUDIT_SUMMARY       path to summary.json (default audit/out/summary.json)
//   AUDIT_EXPECT_AUTHED comma-separated page names that MUST appear in the
//                       results (CI sets `worker,admin`, so a silently skipped
//                       auth pass fails the build instead of passing quietly)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUMMARY = process.env.AUDIT_SUMMARY || path.join(HERE, 'out', 'summary.json');
const MIN_A11Y = Number(process.env.AUDIT_MIN_A11Y ?? 100);
const EXPECTED_AUTHED = (process.env.AUDIT_EXPECT_AUTHED || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

if (!fs.existsSync(SUMMARY)) {
  console.error(`check-audit: ${SUMMARY} not found — run "npm run audit" first.`);
  process.exit(1);
}

let data;
try {
  data = JSON.parse(fs.readFileSync(SUMMARY, 'utf8'));
} catch (e) {
  console.error(`check-audit: could not parse ${SUMMARY}: ${e.message}`);
  process.exit(1);
}

const lh = data.lighthouse || {};
const axe = data.axe || {};
const pages = [...new Set([...Object.keys(lh), ...Object.keys(axe)])].sort();

if (!pages.length) {
  console.error('check-audit: summary.json contains no page results.');
  process.exit(1);
}

const failures = [];

// Coverage contract first: pages the caller requires must actually be present,
// otherwise a skipped auth pass would look like a clean audit.
for (const name of EXPECTED_AUTHED) {
  if (!axe[name]) {
    failures.push(
      `${name}: expected authenticated page missing from the audit results (auth pass skipped or runner out of date)`,
    );
  }
}

for (const name of pages) {
  const a = axe[name];
  const isAuthed = a?.authed === true;

  const l = lh[name];
  if (isAuthed) {
    // axe-only page by policy — but never ignore a Lighthouse result that
    // does exist for it.
    if (l) {
      if (l.error) {
        failures.push(`${name}: Lighthouse errored — ${l.error}`);
      } else if (typeof l.scores?.accessibility === 'number' && l.scores.accessibility < MIN_A11Y) {
        failures.push(`${name}: Lighthouse accessibility ${l.scores.accessibility} < ${MIN_A11Y}`);
      }
    }
  } else if (!l) {
    failures.push(`${name}: no Lighthouse result`);
  } else if (l.error) {
    failures.push(`${name}: Lighthouse errored — ${l.error}`);
  } else if (typeof l.scores?.accessibility !== 'number' || l.scores.accessibility < MIN_A11Y) {
    failures.push(`${name}: Lighthouse accessibility ${l.scores?.accessibility ?? '-'} < ${MIN_A11Y}`);
  }

  if (!a) {
    failures.push(`${name}: no axe result`);
  } else if (a.error) {
    failures.push(`${name}: axe errored — ${a.error}`);
  } else if ((a.violations?.length || 0) > 0) {
    const ids = a.violations.map((v) => `${v.id}(${v.nodes})`).join(', ');
    failures.push(`${name}: ${a.violations.length} axe violation(s) — ${ids}`);
  }
}

if (failures.length) {
  console.error('\nAccessibility audit gate FAILED:');
  for (const f of failures) console.error('  ✗ ' + f);
  console.error(
    `\nThresholds: Lighthouse accessibility >= ${MIN_A11Y} on every citizen page, ` +
      '0 axe WCAG A/AA violations on every page (authenticated pages are axe-gated).',
  );
  process.exit(1);
}

const authedCount = pages.filter((n) => axe[n]?.authed === true).length;
console.log(
  `\nAccessibility audit gate PASSED — ${pages.length} pages ` +
    `(${authedCount} authenticated, axe-only), Lighthouse accessibility >= ${MIN_A11Y} on citizen pages, ` +
    '0 axe WCAG A/AA violations.',
);
