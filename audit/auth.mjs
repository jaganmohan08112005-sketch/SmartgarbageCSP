// Shared config + login flow for the AUTHENTICATED staff-page audit pass.
//
// The citizen pages in run-audit.mjs are scanned anonymously; /worker and
// /admin need a session. scripts/run_local_stack.py (the stack the CI
// workflow boots before auditing) seeds staff fixture accounts with
// password == username, and staff logins go through MFA — on a loopback
// request the MFA page flashes the developer OTP, which we scrape and submit.
// Remote targets (the runner's default is prod) have neither the fixtures nor
// the dev OTP, so callers skip the pass there (see isLoopback).
//
// Kept dependency-free so it is trivially unit-testable.

// WCAG 2.0 / 2.1 / 2.2, Level A + AA. Non-WCAG "best-practice" rules are
// excluded — the same tag set the citizen-page gate has always used.
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

// Staff portals covered by the gate. `name` becomes the summary.json key.
export const AUTHED_PAGES = [
  { name: 'worker', path: '/worker', user: '24331A4441WORKER' },
  { name: 'admin', path: '/admin', user: '24331A4441ADMIN' },
];

// True when baseUrl points at a loopback host, i.e. the seeded local stack
// where the staff fixtures and the developer OTP exist.
export function isLoopback(baseUrl) {
  try {
    const host = new URL(baseUrl).hostname;
    return host === '127.0.0.1' || host === 'localhost' || host === '::1' || host.endsWith('.localhost');
  } catch {
    return false;
  }
}

// Drives the real login → MFA flow inside `page`'s browser context. Throws on
// anything unexpected (no dev OTP, login bounced) so callers record a loud
// error instead of axe-scanning the wrong document.
export async function loginStaff(page, baseUrl, user) {
  await page.goto(baseUrl + '/login', { waitUntil: 'load', timeout: 60000 });
  await page.fill('#lg_username', user);
  await page.fill('#lg_password', user); // seeded fixture: password == username
  await page.click('#password-login button[type=submit]');
  await page.waitForURL('**/mfa-verify', { timeout: 30000 });
  const otpText = await page.locator('.alert-success').first().innerText();
  const otp = otpText.match(/(\d{6})/);
  if (!otp) {
    throw new Error(`no developer OTP on the MFA page for ${user} — is this the seeded local stack?`);
  }
  await page.fill('#otp', otp[1]);
  // Scoped to the verify form: the navbar search form also owns a submit button.
  await page.click('form[action="/mfa-verify"] button[type=submit]');
  await page.waitForURL((u) => !u.pathname.endsWith('/mfa-verify'), { timeout: 30000 });
}

// Citizen accounts skip MFA entirely — the login POST lands straight on the
// dashboard. Used by review tools that need non-staff app pages.
export async function loginCitizen(page, baseUrl, user) {
  await page.goto(baseUrl + '/login', { waitUntil: 'load', timeout: 60000 });
  await page.fill('#lg_username', user);
  await page.fill('#lg_password', user); // seeded fixture: password == username
  await page.click('#password-login button[type=submit]');
  await page.waitForURL((u) => !u.pathname.endsWith('/login'), { timeout: 30000 });
}
