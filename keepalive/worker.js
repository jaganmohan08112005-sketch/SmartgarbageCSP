// Cloudflare Worker keep-alive for smartgarbage.onrender.com.
//
// WHY: Render free web services sleep after ~15 min of idle traffic and
// Supabase free pauses after 7 days of no DB activity. This worker fires on
// a Cloudflare cron trigger (keepalive/wrangler.toml) and pings /health,
// which runs `SELECT 1` against the database — so both stay warm.
//
// WHY CLOUDFLARE (vs GitHub Actions): GitHub's free-tier scheduler delays
// `schedule` events for low-activity repos (this repo's keepalive fired
// ~hourly, not every 5 minutes). Cloudflare Workers cron triggers run at the
// exact cadence on the free plan (100k requests/day; this needs ~288/day),
// and the account is the same one used for the custom-domain zone.
//
// Deploy: `npx wrangler deploy` from this directory (see wrangler.toml).
// The ping is fire-and-forget: a failure just logs — this is a keep-alive,
// not a monitoring alert.

export default {
  async scheduled(_event, _env, _ctx) {
    const url = 'https://smartgarbage.onrender.com/health';
    const started = Date.now();
    try {
      const res = await fetch(url, { method: 'GET', headers: { 'user-agent': 'sg-keepalive-worker' } });
      console.log(`keepalive ${new Date().toISOString()} -> HTTP ${res.status} in ${Date.now() - started}ms`);
    } catch (err) {
      console.error(`keepalive failed: ${err}`);
    }
  },
};
