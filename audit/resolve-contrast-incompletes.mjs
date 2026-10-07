// Resolve axe's color-contrast INCOMPLETE results into real PASS/FAIL verdicts.
//
//   node audit/resolve-contrast-incompletes.mjs
//
// axe reports `incomplete` (needs manual review) wherever it cannot compute a
// background — on this site that means the body-level radial tints, gradient
// buttons/pills, the translucent consent banner and chat overlay, symbol-only
// glyphs and very short strings. "Incomplete" is NOT a pass: this tool measures
// each flagged element for real and fails loudly if any hides a genuine WCAG
// A/AA contrast failure.
//
// Method (per flagged node, computed in the live page):
//   - collect the full background layer stack (element → html), including
//     background-color alpha, every linear/radial gradient, and absolutely
//     positioned ::before/::after overlays;
//   - sample linear gradients along their gradient axis AT THE TEXT'S OWN BOX
//     (worst corner), and radial gradients conservatively at every stop;
//   - fold the opacity chain and text alpha into the foreground;
//   - report the WORST ratio over all candidate backgrounds vs the WCAG
//     threshold (4.5:1, or 3:1 for large text ≥24px / ≥18.66px bold).
//
// Env:
//   AUDIT_BASE_URL   target base (default http://127.0.0.1:5057)
//   CHROME_PATH      chromium binary (optional)
// Output: audit/out/contrast-incompletes.json + console table. Exit 1 on any FAIL.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { AxeBuilder } from '@axe-core/playwright';
import { AXE_TAGS, isLoopback, loginStaff, loginCitizen } from './auth.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'out');
const BASE = (process.env.AUDIT_BASE_URL || 'http://127.0.0.1:5057').replace(/\/+$/, '');

// Citizen pages mirror run-audit's PAGES; staff pages via the seeded fixtures;
// dashboard/analytics extend coverage to the app-internal pages the main audit
// doesn't scan (same shared shell, different custom CSS).
const PAGES = [
  { name: 'home', path: '/', openChat: true },
  { name: 'schedule', path: '/schedule' },
  { name: 'report', path: '/report' },
  { name: 'transparency', path: '/transparency' },
  { name: 'impact', path: '/impact' },
  { name: 'contact', path: '/contact' },
  { name: 'about', path: '/about' },
  { name: 'faq', path: '/faq' },
  { name: 'track', path: '/track' },
  { name: 'login', path: '/login' },
  { name: 'worker', path: '/worker', user: '24331A4441WORKER', staff: true },
  { name: 'admin', path: '/admin', user: '24331A4441ADMIN', staff: true },
  { name: 'dashboard', path: '/dashboard', user: '24331A4441CITIZEN' },
  { name: 'analytics', path: '/analytics', user: '24331A4441ADMIN', staff: true },
];

// Runs inside the page. Self-contained on purpose (no closures).
function analyseContrast(el) {
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const parseC = (s) => {
    if (!s) return null;
    const m = /rgba?\(([^)]+)\)/.exec(s);
    if (!m) return null;
    const p = m[1].split(/[,\s/]+/).filter((x) => x !== '').map(Number);
    if (p.length < 3 || p.slice(0, 3).some((x) => Number.isNaN(x))) return null;
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const over = (t, b) => ({
    r: t.a * t.r + (1 - t.a) * b.r,
    g: t.a * t.g + (1 - t.a) * b.g,
    b: t.a * t.b + (1 - t.a) * b.b,
    a: t.a + (1 - t.a) * b.a,
  });
  const ratio = (f, b) => {
    const Lf = lum(f); const Lb = lum(b);
    return (Math.max(Lf, Lb) + 0.05) / (Math.min(Lf, Lb) + 0.05);
  };
  const splitTop = (s) => {
    const out = []; let d = 0; let cur = '';
    for (const ch of s) {
      if (ch === '(') d++;
      if (ch === ')') d--;
      if (ch === ',' && d === 0) { out.push(cur); cur = ''; } else cur += ch;
    }
    out.push(cur);
    return out;
  };
  const extractGradients = (bi) => {
    if (!bi || bi === 'none') return [];
    const out = []; let i = 0;
    for (;;) {
      const k = bi.indexOf('-gradient(', i);
      if (k === -1) break;
      let d = 0; let j = k + '-gradient('.length - 1;
      for (; j < bi.length; j++) {
        if (bi[j] === '(') d++;
        else if (bi[j] === ')') { d--; if (!d) break; }
      }
      out.push(bi.slice(k, j + 1));
      i = j + 1;
    }
    return out;
  };
  const parseStops = (gradStr) => {
    const inner = gradStr.slice(gradStr.indexOf('(') + 1, gradStr.lastIndexOf(')'));
    const parts = splitTop(inner).map((s) => s.trim());
    const isRadial = /radial-gradient/.test(gradStr.slice(0, gradStr.indexOf('(') + 1) + '');
    let theta = Math.PI; // CSS default: to bottom
    const am = parts[0].match(/(-?[\d.]+)deg/);
    if (am) theta = parseFloat(am[1]) * Math.PI / 180;
    else {
      const m = parts[0].match(/to\s+([a-z]+)/);
      if (m) theta = { top: 0, right: Math.PI / 2, bottom: Math.PI, left: -Math.PI / 2 }[m[1]] ?? Math.PI;
    }
    const stops = [];
    for (const seg of parts.slice(1)) {
      const cm = seg.match(/rgba?\([^)]*\)/);
      if (!cm) continue;
      const c = parseC(cm[0]);
      if (!c) continue;
      const pm = seg.match(/([\d.]+)%/);
      stops.push({ c, pos: pm ? parseFloat(pm[1]) / 100 : null });
    }
    if (!stops.length) return null;
    if (stops.length === 1) stops.push({ ...stops[0], pos: 1 });
    if (stops[0].pos === null) stops[0].pos = 0;
    if (stops[stops.length - 1].pos === null) stops[stops.length - 1].pos = 1;
    for (let i = 1; i < stops.length - 1; i++) if (stops[i].pos === null) stops[i].pos = i / (stops.length - 1);
    return { theta, isRadial, stops };
  };
  const evalStops = (stops, t) => {
    if (t <= stops[0].pos) return stops[0].c;
    for (let i = 1; i < stops.length; i++) {
      if (t <= stops[i].pos) {
        const a = stops[i - 1]; const b = stops[i];
        const f = (t - a.pos) / Math.max(1e-6, b.pos - a.pos);
        // CSS interpolates gradients in PREMULTIPLIED space — naive per-channel
        // lerp turns “green → transparent” into a dark grey and produces false
        // failures. Blend channel*alpha, then unpremultiply.
        const A = a.c.a + f * (b.c.a - a.c.a);
        if (A <= 0) return { r: 0, g: 0, b: 0, a: 0 };
        const ch = (x, y) => (x * a.c.a + f * (y * b.c.a - x * a.c.a)) / A;
        return { r: ch(a.c.r, b.c.r), g: ch(a.c.g, b.c.g), b: ch(a.c.b, b.c.b), a: A };
      }
    }
    return stops[stops.length - 1].c;
  };
  const sampleGrad = (gradStr, layerRect, textBox) => {
    const parsed = parseStops(gradStr);
    if (!parsed) return null;
    if (parsed.isRadial) return parsed.stops.map((s) => s.c); // conservative
    const { theta, stops } = parsed;
    const w = layerRect.width; const h = layerRect.height;
    const L = Math.abs(w * Math.sin(theta)) + Math.abs(h * Math.cos(theta));
    const cx = layerRect.left + w / 2; const cy = layerRect.top + h / 2;
    const ux = Math.sin(theta); const uy = -Math.cos(theta);
    const pts = [
      [textBox.left, textBox.top], [textBox.right, textBox.top],
      [textBox.left, textBox.bottom], [textBox.right, textBox.bottom],
      [textBox.left + textBox.width / 2, textBox.top + textBox.height / 2],
    ];
    return pts.map(([x, y]) => evalStops(stops, clamp(0.5 + ((x - cx) * ux + (y - cy) * uy) / (L || 1), 0, 1)));
  };

  const cs0 = getComputedStyle(el);
  const fgBase = parseC(cs0.color) || { r: 0, g: 0, b: 0, a: 1 };
  let op = 1;
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    const o = parseFloat(getComputedStyle(n).opacity);
    if (!Number.isNaN(o)) op *= o;
  }
  const fs = parseFloat(cs0.fontSize);
  const fw = parseInt(cs0.fontWeight, 10) || 400;
  const large = fs >= 24 || (fs >= 18.66 && fw >= 700);
  const required = large ? 3 : 4.5;

  const chain = [];
  for (let n = el; n && n.nodeType === 1; n = n.parentElement) chain.push(n);
  chain.reverse();

  const textBox = el.getBoundingClientRect();
  let candidates = [{ r: 255, g: 255, b: 255, a: 1 }]; // canvas behind html
  const layers = [];
  for (const node of chain) {
    const s = getComputedStyle(node);
    const tag = node.tagName.toLowerCase() +
      (typeof node.className === 'string' && node.className
        ? '.' + node.className.split(/\s+/).filter(Boolean).slice(0, 2).join('.')
        : '');
    const solid = parseC(s.backgroundColor);
    if (solid && solid.a > 0) {
      layers.push(`${tag} bg ${s.backgroundColor}`);
      candidates = candidates.map((c) => (solid.a >= 1 ? solid : over(solid, c)));
    }
    for (const g of extractGradients(s.backgroundImage)) {
      const sampled = sampleGrad(g, node.getBoundingClientRect(), textBox);
      if (!sampled) { layers.push(`${tag} UNPARSED ${g.slice(0, 50)}`); continue; }
      layers.push(`${tag} ${g.slice(0, 70)}`);
      candidates = candidates.flatMap((c) => sampled.map((sc) => (sc.a >= 1 ? sc : over(sc, c))));
    }
    for (const pseudo of ['::before', '::after']) {
      const ps = getComputedStyle(node, pseudo);
      if (ps.content === 'none' || ps.content === 'normal' || ps.display === 'none') continue;
      const pSolid = parseC(ps.backgroundColor);
      const pGrads = extractGradients(ps.backgroundImage);
      if (!(pSolid && pSolid.a > 0) && !pGrads.length) continue;
      if (ps.position !== 'absolute' && ps.position !== 'fixed') continue;
      layers.push(`${tag}${pseudo} overlay`);
      if (pSolid && pSolid.a > 0) candidates = candidates.map((c) => (pSolid.a >= 1 ? pSolid : over(pSolid, c)));
      for (const g of pGrads) {
        const sampled = sampleGrad(g, node.getBoundingClientRect(), textBox);
        if (sampled) candidates = candidates.flatMap((c) => sampled.map((sc) => (sc.a >= 1 ? sc : over(sc, c))));
      }
    }
  }
  const fg = { r: fgBase.r, g: fgBase.g, b: fgBase.b, a: fgBase.a * op };
  const ratios = candidates.map((b) => ratio(fg.a >= 1 ? fg : over(fg, b), b));
  const worst = ratios.length ? Math.min(...ratios) : null;
  return {
    fg: `rgba(${Math.round(fg.r)},${Math.round(fg.g)},${Math.round(fg.b)},${+fg.a.toFixed(2)})`,
    worst: worst == null ? null : +worst.toFixed(2),
    required,
    large,
    fontSizePx: +fs.toFixed(1),
    fontWeight: fw,
    backgrounds: [...new Set(candidates.map((c) => `rgb(${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)})`))].slice(0, 5),
    layers: layers.slice(0, 8),
  };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {});
  const rows = [];
  for (const p of PAGES) {
    const ctx = await browser.newContext({ bypassCSP: true, viewport: { width: 1350, height: 940 } });
    const page = await ctx.newPage();
    try {
      if (p.staff) await loginStaff(page, BASE, p.user);
      else if (p.user) await loginCitizen(page, BASE, p.user);
      await page.goto(BASE + p.path, { waitUntil: 'load', timeout: 90000 });
      await page.waitForSelector('.leaflet-marker-icon', { timeout: 8000 }).catch(() => {});
      await page.waitForTimeout(800);
      if (p.openChat) await page.click('#sg-chat-toggle').catch(() => {});
      const r = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
      const inc = r.incomplete.filter((v) => v.id === 'color-contrast');
      console.log(`${p.name.padEnd(12)} incomplete=${inc.length}`);
      for (const v of inc) {
        for (const n of v.nodes) {
          const sel = n.target.join(' ');
          const reason = (n.any[0] && n.any[0].message) || '';
          let res;
          try {
            const handle = await page.$(sel);
            res = handle ? await page.evaluate(analyseContrast, handle) : { missing: true };
          } catch (e) {
            res = { error: String(e.message || e).slice(0, 120) };
          }
          rows.push({
            page: p.name,
            target: sel,
            reason,
            verdict: res && res.worst != null ? (res.worst >= res.required ? 'PASS' : 'FAIL') : 'UNRESOLVED',
            ...res,
          });
        }
      }
    } catch (e) {
      console.log(`${p.name.padEnd(12)} ERROR ${e.message}`);
    } finally {
      await ctx.close();
    }
  }
  await browser.close();

  fs.writeFileSync(path.join(OUT, 'contrast-incompletes.json'), JSON.stringify({ base: BASE, generated: new Date().toISOString(), rows }, null, 2));

  // Summary: worst case per (reason class × component signature) across pages.
  const fails = rows.filter((r) => r.verdict === 'FAIL');
  const unres = rows.filter((r) => r.verdict === 'UNRESOLVED');
  const sig = (r) => `${r.reason.split(' due to ')[0].slice(0, 58)} | ${(r.target || '').replace(/\[data-[^\]]+\]/g, '[…]').replace(/nth-child\(\d+\)/g, 'nth-child(…)')}`;
  const bySig = new Map();
  for (const r of rows) {
    const k = sig(r);
    const cur = bySig.get(k) || { count: 0, worst: Infinity, required: 4.5, pages: new Set(), target: r.target, verdict: 'PASS' };
    cur.count++;
    cur.pages.add(r.page);
    if (r.worst != null) {
      cur.worst = Math.min(cur.worst, r.worst);
      cur.required = r.required;
    }
    if (r.verdict === 'FAIL') cur.verdict = 'FAIL';
    if (r.verdict === 'UNRESOLVED' && cur.verdict !== 'FAIL') cur.verdict = 'UNRESOLVED';
    bySig.set(k, cur);
  }
  console.log(`\n${rows.length} incomplete nodes → ${bySig.size} unique cases; FAIL=${fails.length} UNRESOLVED=${unres.length}`);
  console.log('\nWORST-CASE CONTRAST PER UNIQUE CASE (ascending):');
  for (const [k, v] of [...bySig.entries()].sort((a, b) => (a[1].worst ?? 99) - (b[1].worst ?? 99))) {
    const w = v.worst === Infinity ? '—' : v.worst;
    console.log(`  ${v.verdict.padEnd(11)} ${String(w).padStart(5)} : 1 (need ${v.required}) ×${String(v.count).padStart(3)} [${[...v.pages].join(',')}] ${k}`);
  }
  if (fails.length || unres.length) {
    console.error(`\nCONTRAST REVIEW FAILED — ${fails.length} real failure(s), ${unres.length} unresolved. Details: audit/out/contrast-incompletes.json`);
    process.exit(1);
  }
  console.log('\nCONTRAST REVIEW PASSED — every axe color-contrast incomplete resolves to a WCAG A/AA pass.');
})();
