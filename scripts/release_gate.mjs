#!/usr/bin/env node
/* EPICENTRE release gate: proves that no screen of the site reads as advice (the red gates (README, Limits) red gates 1, 4, 5; the official case's
   responsible boundaries; design doc rulings R1, R16, R18, R20, R22). For every investor (Robert, Mateo, Amira, Too Canadian?),
   both depths (Simple, Detailed) and every dial position (each point of tipping_point.curve, 0..40 %), after pressing Replay and
   letting it reach its end frame, it reads every visible text (plus inputs, CSS-generated text and screen-reader text; also the
   thread drawer and the navigator-off view at the asked size) and fails on
   (a) advice or forecast words (buy, sell, hold as a verb, you should, we recommend, safe, allowed, holds up to, fits you, will
       fall / rise, guaranteed, expected return; acheter, vendre, vous devriez, recommandé, sécuritaire), except inside a quoted
       investor question and the disclaimers (scripts/gate_rules.mjs, node-tested by tests/web_gate_test.mjs);
   (b) at any size other than the asked one: a verdict word (Inside your limits, Outside your limits, Inside, with caveats) or a
       green status element on what follows the dial (the #replay stage, the #dial ruler, and anything that changed with it);
   (c) a " · " meta string (R16);
   (d) a missing "Educational simulation. This is not financial advice." or "This already happened; it is not a forecast.";
   (e) any console error, uncaught exception or failed request;
   (f) a document wider than the viewport at 390 px.
   Usage:
     node scripts/release_gate.mjs                         # the static build in publish_pages.py's output dir, else :8899
     node scripts/release_gate.mjs --site /tmp/site        # serve a static build folder
     node scripts/release_gate.mjs --url http://127.0.0.1:8899/
     node scripts/release_gate.mjs --build --runs /tmp/epi_runs_v1   # build this checkout first (publish_pages.py --dry-run)
     options: --investors robert,mateo --depths simple,detailed --viewports 1440x900,390x844 --port 9560 --report gate.md
              --json gate.json --dump states.jsonl (every state's texts, to audit) --shots DIR (one screenshot per check and
              section, at most --max-shots 10) --no-extra (skip the drawer and navigator-off screens) --no-lock --probe (find
              Chrome and the site, then exit)
   Exit 0 = pass, 1 = findings (the report lists check, section, investor, depth, size and the offending text), 2 = no site / no
   Chrome / a broken run. One headless Chrome at a time: it takes the team's lock (/tmp/epi_chrome.lock) per viewport. */
import { createServer } from "node:http";
import { existsSync, readFileSync, writeFileSync, mkdirSync, rmdirSync, statSync, readdirSync } from "node:fs";
import { join, resolve, extname, dirname, relative } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { launch, findChrome, sleep } from "./cdp.mjs";
import { adviceHits, verdictHits, metaHits, REQUIRED, norm, ranges, isGreen } from "./gate_rules.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const INVESTORS = ["robert", "mateo", "amira", "canadian"];
const NAMES = { robert: "Robert", mateo: "Mateo", amira: "Amira", canadian: "Too Canadian?" };

/* ---- arguments ---- */
function parseArgs(argv) {
  const o = { investors: INVESTORS, depths: ["simple", "detailed"], viewports: ["1440x900", "390x844"], port: 9560, lock: true,
    maxShots: 10, replayTimeout: 30000, extra: true };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], next = () => argv[++i];
    if (a === "--url") o.url = next();
    else if (a === "--site") o.site = next();
    else if (a === "--build") o.build = true;
    else if (a === "--runs") o.runs = next();
    else if (a === "--investors") o.investors = next().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--depths") o.depths = next().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--viewports") o.viewports = next().split(",").map((s) => s.trim()).filter(Boolean);
    else if (a === "--port") o.port = Number(next());
    else if (a === "--report") o.report = next();
    else if (a === "--json") o.json = next();
    else if (a === "--shots") o.shots = next();
    else if (a === "--max-shots") o.maxShots = Number(next());
    else if (a === "--no-lock") o.lock = false;
    else if (a === "--dump") o.dump = next();
    else if (a === "--no-extra") o.extra = false;
    else if (a === "--probe") o.probe = true;
    else if (a === "--help" || a === "-h") o.help = true;
    else if (/^https?:\/\//.test(a)) o.url = a;
    else if (existsSync(a)) o.site = a;
    else throw new Error(`unknown argument: ${a}`);
  }
  for (const id of o.investors) if (!INVESTORS.includes(id)) throw new Error(`unknown investor: ${id}`);
  return o;
}

/* ---- the site: a URL, a static build folder (served here), or the defaults ---- */
const isBuild = (dir) => !!dir && existsSync(join(dir, "index.html")) && existsSync(join(dir, "runs", "index.json"));
const pagesOut = () => process.env.EPI_PAGES_OUT || join(tmpdir(), "epi_pages_site");   // publish_pages.py --out's default

async function answers(url) {
  try {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 2500);
    const res = await fetch(url, { signal: ctl.signal }); clearTimeout(t);
    return res.ok;
  } catch { return false; }
}

function python() {
  for (const p of [process.env.PYTHON, join(ROOT, ".venv", "bin", "python"), resolve(ROOT, "..", "poly-datathon-2026", ".venv", "bin", "python"), "python3"]) {
    if (!p) continue;
    if (p === "python3" || existsSync(p)) return p;
  }
  return "python3";
}

function buildSite(runs) {
  const out = join(tmpdir(), `epi-gate-site-${process.pid}`);
  const args = [join(ROOT, "scripts", "publish_pages.py"), "--dry-run", "--out", out];
  if (runs) args.push("--runs", runs);
  const done = spawnSync(python(), args, { cwd: ROOT, encoding: "utf8", timeout: 300000 });
  if (done.status !== 0 || !isBuild(out)) throw new Error(`the static build failed: ${(done.stderr || done.stdout || "").slice(-800)}`);
  return out;
}

async function resolveSite(o) {
  if (o.url) return { url: o.url, kind: "url", label: o.url };
  if (o.build) { const dir = buildSite(o.runs); return { dir, kind: "build", label: `a fresh static build of ${ROOT} (${dir})` }; }
  if (o.site) {
    if (!isBuild(o.site)) throw new Error(`${o.site} is not a static build (index.html + runs/index.json)`);
    return { dir: resolve(o.site), kind: "site", label: `the static build in ${resolve(o.site)}` };
  }
  if (isBuild(pagesOut())) return { dir: pagesOut(), kind: "site", label: `the static build in ${pagesOut()} (publish_pages.py's output)` };
  if (await answers("http://127.0.0.1:8899/")) return { url: "http://127.0.0.1:8899/", kind: "url", label: "the local server on :8899" };
  return null;
}

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".woff2": "font/woff2", ".woff": "font/woff", ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8", ".pdf": "application/pdf" };

/* a static server like GitHub Pages: files only, a folder answers its index.html, anything else is a 404 */
function serve(dir) {
  const root = resolve(dir);
  const server = createServer((req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://x").pathname);
    let file = resolve(join(root, path));
    if (!file.startsWith(root)) { res.writeHead(403).end(); return; }
    try { if (statSync(file).isDirectory()) file = join(file, "index.html"); } catch { /* missing: 404 below */ }
    if (!existsSync(file)) { res.writeHead(404, { "content-type": "text/plain" }).end("404 Not Found"); return; }
    res.writeHead(200, { "content-type": MIME[extname(file).toLowerCase()] || "application/octet-stream", "cache-control": "no-store" });
    res.end(readFileSync(file));
  });
  return new Promise((r) => server.listen(0, "127.0.0.1", () => r({ server, url: `http://127.0.0.1:${server.address().port}/` })));
}

/* ---- the team's one-Chrome lock (8 GB Mac): taken per browser session, always released ---- */
const LOCK = process.env.EPI_CHROME_LOCK || "/tmp/epi_chrome.lock";
let locked = false;
async function takeLock(on, maxWaitMs = 20 * 60000) {
  if (!on) return;
  const t0 = Date.now();
  for (;;) {
    try { mkdirSync(LOCK); locked = true; return; }
    catch (e) { if (e.code !== "EEXIST") throw e; }
    if (Date.now() - t0 > maxWaitMs) throw new Error(`the Chrome lock ${LOCK} stayed taken for ${Math.round(maxWaitMs / 60000)} minutes`);
    await sleep(3000);
  }
}
function dropLock() { if (locked) { try { rmdirSync(LOCK); } catch { /* already gone */ } locked = false; } }
process.on("exit", dropLock);
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { dropLock(); process.exit(130); });

/* ---- the probe that runs inside the page (installed once per load as window.__gate; returns plain data) ---- */
function pageProbe(isGreenFn) {
  const SECTIONS = new Set(["bar", "hero", "replay", "dial", "money", "deep", "scenario", "checklist", "why", "investors", "how", "record", "footer"]);
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "TITLE", "META", "LINK", "defs", "symbol"]);
  const raf2 = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  let refs = [];
  function sectionOf(el) {
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) {
      if (n.id && SECTIONS.has(n.id) && n.hasAttribute("data-module")) return n.id;
    }
    const o = el.closest("[role=dialog], [role=alertdialog], .depth, .presenter-hint, .server-note, .skip-link, [class*=tour], [class*=thread], [class*=drawer]");
    if (o) return "overlay:" + (o.id || String(o.getAttribute("class") || o.tagName).split(/\s+/).slice(0, 2).join("."));
    return "page";
  }
  function subOf(el, sec) {
    if (sec !== "replay") return "";
    if (el.closest(".rp-race")) return "race chart";
    if (el.closest(".rp-strip")) return "dial strip";
    return "";
  }
  function pathOf(el) {
    const parts = [];
    for (let n = el; n && parts.length < 4; n = n.parentElement) {
      if (n.id && SECTIONS.has(n.id) && n.hasAttribute("data-module")) break;
      const cls = String(n.getAttribute("class") || "").split(/\s+/).filter((c) => c && !/^is-/.test(c)).slice(0, 2);
      parts.unshift(n.tagName.toLowerCase() + (n.id ? "#" + n.id : "") + (cls.length ? "." + cls.join(".") : ""));
    }
    return parts.join(" > ");
  }
  const csCache = new Map();
  const cs = (el) => { let c = csCache.get(el); if (!c) { c = getComputedStyle(el); csCache.set(el, c); } return c; };
  const visCache = new Map();
  function boxEl(el) { let n = el; while (n && n.parentElement && cs(n).display === "contents") n = n.parentElement; return n; }
  function shown(el) {                       // rendered: displayed, not visibility:hidden, not opacity 0 on it or an ancestor
    el = boxEl(el);
    if (visCache.has(el)) return visCache.get(el);
    let v = typeof el.checkVisibility === "function"
      ? el.checkVisibility({ opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true }) : true;
    if (v && el.closest("[hidden]") && cs(el).display === "none") v = false;
    visCache.set(el, v);
    return v;
  }
  const fixedCache = new Map();
  function fixedOf(el) {
    if (!el || el === document.documentElement) return false;
    if (fixedCache.has(el)) return fixedCache.get(el);
    const v = cs(el).position === "fixed" || fixedOf(el.parentElement);
    fixedCache.set(el, v);
    return v;
  }
  const clipCache = new Map();
  function clipOf(el) {                      // the box that clips el: the intersection of every overflow:hidden/clip ancestor
    if (!el || el === document.body || el === document.documentElement) return null;
    if (clipCache.has(el)) return clipCache.get(el);
    let c = clipOf(el.parentElement);
    const s = cs(el);
    const hides = (v) => v === "hidden" || v === "clip";
    if (hides(s.overflowX) || hides(s.overflowY)) {
      const r = el.getBoundingClientRect();
      const box = { l: hides(s.overflowX) ? r.left : -1e9, r: hides(s.overflowX) ? r.right : 1e9, t: hides(s.overflowY) ? r.top : -1e9, b: hides(s.overflowY) ? r.bottom : 1e9 };
      c = c ? { l: Math.max(c.l, box.l), r: Math.min(c.r, box.r), t: Math.max(c.t, box.t), b: Math.min(c.b, box.b) } : box;
    }
    clipCache.set(el, c);
    return c;
  }
  function onScreen(el, rects) {             // some rect has area, lies inside its clip box and is reachable by scrolling
    const c = clipOf(el), fx = fixedOf(el), vw = innerWidth, vh = innerHeight;
    for (const r of rects) {
      if (r.width < 0.5 || r.height < 0.5) continue;
      if (c && (r.right <= c.l + 0.5 || r.left >= c.r - 0.5 || r.bottom <= c.t + 0.5 || r.top >= c.b - 0.5)) continue;
      if (fx && (r.right <= 0 || r.left >= vw || r.bottom <= 0 || r.top >= vh)) continue;
      if (r.right + scrollX <= 0 || r.bottom + scrollY <= 0) continue;
      return true;
    }
    return false;
  }
  function srOnly(el) {
    const r = boxEl(el).getBoundingClientRect(), s = cs(boxEl(el));
    if (r.width <= 1.5 || r.height <= 1.5) return true;
    if (/rect\(\s*0(px)?[,\s]+0(px)?[,\s]+0(px)?[,\s]+0(px)?\s*\)/.test(s.clip || "")) return true;
    return /inset\(\s*50%/.test(s.clipPath || "");
  }
  const INLINE = new Set(["inline", "contents"]);
  function blockOf(el) {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      if (n instanceof SVGTextElement) return n;
      if (n instanceof SVGElement) continue;
      if (!INLINE.has(cs(n).display)) return n;
    }
    return document.body;
  }
  function inAriaHidden(el) { return !!el.closest("[aria-hidden=true]"); }
  function pseudoText(el, which) {
    const p = getComputedStyle(el, which);
    const c = p.content;
    if (!c || c === "none" || c === "normal" || p.display === "none") return "";
    let out = "";
    for (const m of c.matchAll(/"((?:[^"\\]|\\.)*)"|attr\(\s*([\w-]+)\s*\)/g)) out += m[1] !== undefined ? m[1].replace(/\\(.)/g, "$1") : (el.getAttribute(m[2]) || "");
    return out.trim();
  }
  function tokens() {
    const root = getComputedStyle(document.documentElement), out = [];
    for (const n of ["--clear", "--status-ok", "--inside", "--ok", "--pass", "--green"]) { const v = root.getPropertyValue(n).trim(); if (v) out.push(v); }
    return out;
  }

  function snapshot(opts = {}) {
    csCache.clear(); visCache.clear(); fixedCache.clear(); clipCache.clear(); refs = [];
    const t0 = performance.now(), groups = new Map(), green = [], marks = new Map(), toks = tokens();
    const add = (el, where, text) => {
      const blk = where === "text" || where === "a11y" ? blockOf(el) : el;
      const key = blk;
      let g = groups.get(key);
      if (!g) { g = { el: blk, parts: {} }; groups.set(key, g); }
      g.parts[where] = (g.parts[where] || "") + text;
    };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    for (let t = walker.nextNode(); t; t = walker.nextNode()) {
      const el = t.parentElement;
      if (!el || SKIP.has(el.tagName) || el.closest("noscript, template, svg defs, svg symbol")) continue;
      if (!t.nodeValue || !t.nodeValue.trim()) { if (t.nodeValue) { const g = groups.get(blockOf(el)); if (g) for (const k of Object.keys(g.parts)) g.parts[k] += " "; } continue; }
      if (!shown(el)) continue;
      range.selectNodeContents(t);
      const rects = [...range.getClientRects()];
      if (srOnly(el)) { if (!inAriaHidden(el)) add(el, "a11y", t.nodeValue); continue; }
      if (!onScreen(boxEl(el), rects)) continue;
      add(el, "text", t.nodeValue);
    }
    const all = document.body.querySelectorAll("*");
    for (const el of all) {
      if (SKIP.has(el.tagName) || el.closest("svg defs, svg symbol, noscript, template")) continue;
      const vis = shown(el);
      if (vis && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|search|)$/.test(el.type || ""))) && String(el.value || "").trim()) add(el, "input", el.value);
      if (!inAriaHidden(el)) for (const a of ["aria-label", "aria-valuetext", "aria-description", "title", "alt"]) {
        const v = el.getAttribute(a);
        if (v && v.trim() && (vis || a === "aria-label")) add(el, "a11y", (groups.get(el) && groups.get(el).parts.a11y ? " " : "") + v);
      }
      if (!vis) continue;
      if (!(el instanceof SVGElement) || el instanceof SVGTextElement) {
        const b = pseudoText(el, "::before"), a = pseudoText(el, "::after");
        if (b || a) add(el, "pseudo", [b, a].filter(Boolean).join(" … "));
      }
      if (opts.green) {
        const r = el.getBoundingClientRect();
        if (r.width < 1 && r.height < 1) continue;
        if (!onScreen(el, [r])) continue;
        const s = cs(el), why = [];
        const ownText = [...el.childNodes].some((n) => n.nodeType === 3 && n.nodeValue.trim());
        if (ownText && isGreenFn(s.color, toks)) why.push(`text colour ${s.color}`);
        if (el instanceof SVGElement && !(el instanceof SVGSVGElement) && !(el instanceof SVGGElement)) {
          if (s.fill && s.fill !== "none" && isGreenFn(s.fill, toks)) why.push(`fill ${s.fill}`);
          if (s.stroke && s.stroke !== "none" && parseFloat(s.strokeWidth) > 0 && isGreenFn(s.stroke, toks)) why.push(`stroke ${s.stroke}`);
        }
        if (r.width * r.height > 4 && isGreenFn(s.backgroundColor, toks)) why.push(`background ${s.backgroundColor}`);
        for (const side of ["Top", "Right", "Bottom", "Left"]) {
          if (parseFloat(s[`border${side}Width`]) > 0 && s[`border${side}Style`] !== "none" && isGreenFn(s[`border${side}Color`], toks)) { why.push(`border ${s[`border${side}Color`]}`); break; }
        }
        if (el.getAttribute("data-tone") === "inside") why.push('data-tone="inside"');
        const href = el.tagName.toLowerCase() === "use" ? (el.getAttribute("href") || el.getAttribute("xlink:href") || "") : "";
        if (/#i-in$/.test(href)) why.push("the check icon (#i-in)");
        if (el.tagName.toLowerCase() === "path" && /^M7\.5 12\.3l3 3/.test(el.getAttribute("d") || "")) why.push("the check icon");
        if (why.length) {                    // one entry per status element: an icon's shapes join the block that shows them
          let anchor = el;
          while (anchor instanceof SVGElement && anchor.parentElement) anchor = anchor.parentElement;
          const toned = anchor.closest("[data-tone]");
          anchor = toned && sectionOf(toned) === sectionOf(anchor) && toned.getAttribute("data-tone") === "inside" ? toned : blockOf(anchor);
          let m = marks.get(anchor);
          if (!m) { m = new Set(); marks.set(anchor, m); }
          for (const w of why) m.add(w);
        }
      }
    }
    for (const [anchor, why] of marks) {
      refs.push(anchor);
      const sec = sectionOf(anchor);
      green.push({ sec, sub: subOf(anchor, sec), path: pathOf(anchor), why: [...why].sort().join("; "),
        text: String(anchor.innerText || anchor.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120), ref: refs.length - 1 });
    }
    const out = [];
    for (const g of groups.values()) {
      for (const [where, text] of Object.entries(g.parts)) {
        const t = text.replace(/\s+/g, " ").trim();
        if (!t) continue;
        refs.push(g.el);
        const sec = sectionOf(g.el);
        out.push({ sec, sub: subOf(g.el, sec), path: pathOf(g.el), where, text: t.slice(0, 1200), ref: refs.length - 1 });
      }
    }
    const de = document.documentElement, vw = innerWidth;
    let overflow = [];
    if (opts.overflow && de.scrollWidth > vw) {
      for (const el of all) {
        if (!shown(el)) continue;
        const r = el.getBoundingClientRect();
        if (r.right <= vw + 0.5 || r.width < 1) continue;
        const c = clipOf(el.parentElement);
        if (c && c.r <= vw + 0.5) continue;
        let scroller = false;
        for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) { const o = cs(n).overflowX; if (o === "auto" || o === "scroll") { scroller = true; break; } }
        if (scroller) continue;
        overflow.push({ el, right: Math.round(r.right), width: Math.round(r.width) });
      }
      overflow = overflow.filter((o) => !overflow.some((p) => p !== o && o.el.contains(p.el) && p.right >= o.right - 1))
        .sort((a, b) => b.right - a.right).slice(0, 6)
        .map((o) => { refs.push(o.el); const sec = sectionOf(o.el); return { sec, sub: subOf(o.el, sec), path: pathOf(o.el), right: o.right, width: o.width,
          text: String(o.el.innerText || o.el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 100), ref: refs.length - 1 }; });
    }
    return { items: out, green, overflow, scrollWidth: de.scrollWidth, bodyScrollWidth: document.body.scrollWidth, vw, ms: Math.round(performance.now() - t0) };
  }

  function slider() {
    const all = [...document.querySelectorAll("#dial [role=slider], #replay [role=slider]")];
    return all.find((s) => shown(s)) || all[0] || null;
  }
  function dialState() {
    csCache.clear(); visCache.clear();
    const s = slider(), st = window.__epi && window.__epi.store ? window.__epi.store.get() : {};
    const curve = st.result && st.result.tipping_point && Array.isArray(st.result.tipping_point.curve) ? st.result.tipping_point.curve : [];
    return { has: !!s, now: s ? Number(s.getAttribute("aria-valuenow")) : null, max: s ? Number(s.getAttribute("aria-valuemax")) : null,
      min: s ? Number(s.getAttribute("aria-valuemin")) : null, weights: curve.map((c) => (c && typeof c.weight === "number" ? Math.round(c.weight * 1000) / 10 : null)),
      weightIndex: st.weightIndex === undefined ? null : st.weightIndex, pilot: st.result ? st.result.pilot : null };
  }
  async function key(k) {
    const s = slider();
    if (!s) return false;
    s.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
    await raf2();
    return true;
  }
  async function replayToEnd(timeoutMs) {
    const store = window.__epi.store, phases = [];
    const off = store.on("phase", (p) => phases.push(p));
    const btn = document.querySelector("#hero .hx-go") || [...document.querySelectorAll("#hero button")].find((b) => /^\s*Replay\s*$/.test(b.textContent));
    const t0 = performance.now();
    if (btn) btn.click(); else store.set({ replay: Date.now() });
    const motion = window.EPI_MOTION !== false && !matchMedia("(prefers-reduced-motion: reduce)").matches;
    let ended = false;
    while (performance.now() - t0 < timeoutMs) {
      await wait(120);
      const skip = document.querySelector("#replay .rp-skip"), again = document.querySelector("#replay .rp-again");
      const started = phases.includes("reading") || (!motion && performance.now() - t0 > 400);
      if (started && store.get().phase === "landed" && (!skip || skip.hidden) && (!again || !again.hidden)) { ended = true; break; }
    }
    off();
    return { pressed: btn ? "the Replay button" : "store.replay (no Replay button found)", ended, ms: Math.round(performance.now() - t0), phases };
  }
  async function questions() {
    const out = [];
    for (const id of ["robert", "mateo", "amira", "canadian"]) {
      try { const r = await window.__epi.data.loadRun(id); if (r && typeof r.question === "string") out.push(r.question); } catch (e) { /* no run */ }
    }
    const st = window.__epi.store.get();
    if (st.question) out.push(st.question);
    return out;
  }
  async function setDepth(d) {
    const b = document.querySelector(`.depth-opt[data-depth="${d}"]`);
    if (b) b.click(); else window.__epi.store.set({ depth: d });
    await raf2();
    return { via: b ? "the Simple / Detailed switch" : "store.depth (no switch found)", depth: window.__epi.store.get().depth };
  }
  async function pickInvestor(id) {
    const chip = document.querySelector(`#hero .hx-chip[data-id="${id}"]`);
    if (chip) chip.click(); else window.__epi.store.set({ investor: id });
    const t0 = performance.now();
    while (performance.now() - t0 < 15000) {
      const st = window.__epi.store.get();
      if (st.result && st.result.pilot === id) break;
      await wait(100);
    }
    await raf2();
    return { via: chip ? "its investor chip" : "store.investor (no chip found)", ok: window.__epi.store.get().result && window.__epi.store.get().result.pilot === id };
  }
  async function extra(which) {             // the screens a click opens: the thread drawer on the first number, the navigator off
    if (which === "drawer") {
      const b = [...document.querySelectorAll("#why [data-fact]")].find((x) => shown(x));
      if (!b) return { ok: false, why: "no number to open in #why" };
      b.click(); await wait(500); await raf2();
      return { ok: !!window.__epi.store.get().thread, why: `the drawer for ${b.getAttribute("data-fact")}` };
    }
    if (which === "drawer-close") { window.__epi.store.set({ thread: null }); await wait(400); return { ok: true }; }
    const sw = [...document.querySelectorAll("#why button, #why [role=switch], #why input[type=checkbox]")].find((x) => shown(x) && /navigator/i.test(x.textContent + " " + (x.getAttribute("aria-label") || "")));
    if (!sw) return { ok: false, why: "no navigator switch in #why" };
    sw.click(); await wait(400); await raf2();
    return { ok: true, why: String(sw.textContent || sw.getAttribute("aria-label") || "").trim().slice(0, 60) };
  }
  function focusRef(i) { const el = refs[i]; if (el && el.scrollIntoView) el.scrollIntoView({ block: "center" }); return !!el; }
  window.__gate = { snapshot, dialState, key, replayToEnd, questions, setDepth, pickInvestor, extra, focusRef, raf2, wait };
  return true;
}

/* ---- the walk: one browser session per viewport; every investor, both depths, Replay to the end frame, every dial size ---- */
const withQuery = (base, params) => { const u = new URL(base); for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v); return u.href; };
const PROBE_SRC = `(${pageProbe.toString()})(${isGreen.toString()})`;

async function boot(chrome, url) {
  await chrome.goto(url);
  await chrome.waitFor("window.__epi && document.documentElement.classList.contains('is-booted')", 45000);
  const ready = await chrome.evaluate("Promise.resolve(window.__epi.ready()).then((x) => x !== false)");
  await chrome.evaluate(PROBE_SRC);
  return ready;
}

async function session(o, base, vp, ctx) {
  const [W, H] = vp.split("x").map(Number), phone = W < 600;
  await takeLock(o.lock);
  const t0 = Date.now();
  let chrome = null;
  try {
    chrome = await launch({ port: o.port, W, H, dsf: phone ? 2 : 1, mobile: phone, maxMs: 6 * 60000 });
    ctx.browser = ctx.browser || (await chrome.send("Browser.getVersion")).product;
    let seenErr = 0, booted = false;
    const phase = async (label, state, fn) => {          // errors and failed requests are charged to the step that raised them
      const mark = chrome.logs.length;
      let out;
      try { out = await fn(); }
      catch (e) { ctx.setup.push({ ...state, step: label, text: String(e && e.message || e).slice(0, 400) }); out = null; }
      const app = await chrome.evaluate("Array.isArray(window.__errors) ? window.__errors.slice() : []").catch(() => []);
      const fresh = app.slice(seenErr); seenErr = app.length;
      const here = [];
      for (const l of chrome.logs.slice(mark)) {
        if (l.kind === "error") { const e = { ...state, step: label, source: l.source, text: l.text, url: l.url }; ctx.errors.push(e); here.push(e); }
        else ctx.warnings.push({ ...state, step: label, text: l.text });
      }
      const same = (a, b) => { const x = norm(a).slice(0, 40), y = norm(b).slice(0, 40); return !!x && !!y && (norm(a).includes(y) || norm(b).includes(x)); };
      for (const t of fresh) if (!here.some((e) => same(e.text, String(t)))) {   // the page's own error list adds only what the console missed
        ctx.errors.push({ ...state, step: label, source: "window.__errors", text: String(t).slice(0, 600), url: "" });
      }
      return out;
    };
    for (const [k, id] of o.investors.entries()) {
      const st = { vp, investor: id };
      let ok = false;
      if (k > 0 && booted) {
        const r = await phase("switch investor", st, () => chrome.evaluate(`window.__gate.pickInvestor(${JSON.stringify(id)})`));
        ok = !!(r && r.ok);
        if (!ok) ctx.setup.push({ ...st, step: "switch investor", text: `the ${NAMES[id]} chip did not bring that run; reloading with ?investor=${id}` });
      }
      if (!ok) {
        booted = false; seenErr = 0;
        const ready = await phase("page load", st, () => boot(chrome, withQuery(base, { investor: id })));
        booted = ready !== null;
        if (!booted) continue;
        const pilot = await chrome.evaluate("window.__epi.store.get().result && window.__epi.store.get().result.pilot");
        if (pilot !== id) { ctx.setup.push({ ...st, step: "page load", text: `no saved run for ${NAMES[id]} on this site (the page shows ${pilot || "none"})` }); continue; }
      }
      if (!ctx.questions.length) ctx.questions = await chrome.evaluate("window.__gate.questions()");
      for (const depth of o.depths) {
        const sd = { ...st, depth };
        await phase(`depth ${depth}`, sd, () => chrome.evaluate(`window.__gate.setDepth(${JSON.stringify(depth)})`));
        const rp = await phase(`Replay (${depth})`, sd, () => chrome.evaluate(`window.__gate.replayToEnd(${o.replayTimeout})`));
        if (rp && !rp.ended) ctx.setup.push({ ...sd, step: `Replay (${depth})`, text: `pressing ${rp.pressed} did not reach the end frame in ${Math.round(rp.ms / 1000)} s (phases: ${rp.phases.join(" > ") || "none"})` });
        if (rp) ctx.replays.push({ ...sd, ms: rp.ms, ended: rp.ended, pressed: rp.pressed });
        await sleep(700);                                  // the last line fades in; counters land (<= 600 ms)
        await phase(`dial (${depth})`, sd, async () => {
          const ds = await chrome.evaluate("window.__gate.dialState()");
          const asked = ds.has && Number.isInteger(ds.now) ? ds.now : null;
          const label = (i) => (i === null ? "no dial" : ds.weights[i] !== undefined && ds.weights[i] !== null ? `${ds.weights[i]} %` : `#${i}`);
          const take = async (i, isAsked) => {
            const snap = await chrome.evaluate(`window.__gate.snapshot(${JSON.stringify({ green: true, overflow: phone })})`);
            ctx.snapMs.push(snap.ms);
            return { ...sd, index: i, size: label(i), weight: i === null ? null : ds.weights[i], asked: isAsked, phone, ...snap };
          };
          const askedSnap = await take(asked, true);
          await ctx.check(askedSnap, null, chrome);
          ctx.states += 1;
          if (!ds.has) { ctx.noDial.add(`${NAMES[id]}`); return; }
          ctx.dial[id] = { asked, askedSize: label(asked), min: ds.min, max: ds.max, weights: ds.weights };
          for (let i = ds.min ?? 0; i <= ds.max; i++) {
            await chrome.evaluate(`window.__gate.key(${JSON.stringify(i === (ds.min ?? 0) ? "Home" : "ArrowRight")})`);
            await sleep(110);
            const now = await chrome.evaluate("window.__gate.dialState()");
            if (now.now !== i) { ctx.setup.push({ ...sd, step: `dial (${depth})`, text: `the dial did not move to ${label(i)} (it reads ${now.now})` }); continue; }
            await ctx.check(await take(i, i === asked), askedSnap, chrome);
            ctx.states += 1;
          }
          await chrome.evaluate(`window.__gate.key("End")`);
        });
      }
      if (!phone && o.extra) {                           // the screens a click opens, at the asked size, desktop only
        for (const [which, label, undo] of [["drawer", "the thread drawer", "drawer-close"], ["navigator", "the navigator switched off", "navigator"]]) {
          const se = { ...st, depth: o.depths[o.depths.length - 1] };
          await phase(label, se, async () => {
            const r = await chrome.evaluate(`window.__gate.extra(${JSON.stringify(which)})`);
            if (!r.ok) { ctx.notes.push(`${NAMES[id]}: ${label} not checked (${r.why})`); return; }
            const snap = await chrome.evaluate(`window.__gate.snapshot(${JSON.stringify({ green: false, overflow: false })})`);
            await ctx.check({ ...se, index: null, size: label, weight: null, asked: true, phone, ...snap, step: label }, null, chrome);
            ctx.states += 1;
            await chrome.evaluate(`window.__gate.extra(${JSON.stringify(undo)})`);
          });
        }
      }
    }
  } finally {
    if (chrome) await chrome.close().catch(() => {});
    dropLock();
    ctx.sessions.push({ vp, seconds: Math.round((Date.now() - t0) / 1000) });
  }
}

/* ---- the checks on one state ---- */
const CHECKS = {
  a: "(a) Advice or forecast words",
  b: "(b) A verdict word or a green mark at a size the investor did not ask",
  c: "(c) \" · \" meta strings (R16)",
  d: "(d) A required line is missing",
  e: "(e) Console errors",
  f: "(f) Wider than the viewport at 390 px",
};
const WHERE = { text: "visible text", input: "a form field", pseudo: "CSS-generated text", a11y: "screen-reader text" };
const inScope = (x) => x.sec === "replay" || x.sec === "dial";      // what follows the dial (R20)

function makeCtx(o) {
  const ctx = { questions: [], findings: new Map(), setup: [], errors: [], warnings: [], replays: [], states: 0, sessions: [],
    noDial: new Set(), dial: {}, shots: [], shotKeys: new Set(), browser: null, snapMs: [], notes: [] };
  async function add(check, snap, item, hit, chrome) {
    const key = [check, item.sec, item.sub || "", item.path || "", item.where || "", hit.rule, check === "f" ? "" : String(hit.match).toLowerCase()].join("|");
    let f = ctx.findings.get(key);
    if (!f) {
      f = { check, sec: item.sec, sub: item.sub || "", path: item.path || "", where: item.where || "", rule: hit.rule, match: hit.match, examples: [], states: [] };
      ctx.findings.set(key, f);
      const shotKey = `${check}|${item.sec}|${item.sub || ""}`;
      if (o.shots && ctx.shots.length < o.maxShots && chrome && !ctx.shotKeys.has(shotKey)) {
        ctx.shotKeys.add(shotKey);
        try {
          mkdirSync(o.shots, { recursive: true });
          const back = await chrome.evaluate(`(() => { const p = [scrollX, scrollY]; ${Number.isInteger(item.ref) ? `window.__gate.focusRef(${item.ref});` : ""} return p; })()`);
          await chrome.evaluate("window.__gate.raf2()"); await sleep(150);
          const file = join(o.shots, `${String(ctx.shots.length + 1).padStart(2, "0")}-${check}-${snap.investor}-${snap.depth}-${String(snap.size).replace(/[^\w.]+/g, "")}-${snap.vp}.png`);
          await chrome.shot(file);
          ctx.shots.push(file); f.shot = file;
          await chrome.evaluate(`window.scrollTo(${back[0]}, ${back[1]})`);
        } catch { /* a screenshot is evidence only */ }
      }
    }
    if (f.examples.length < 2 && hit.text && !f.examples.includes(hit.text)) f.examples.push(hit.text);
    f.states.push({ vp: snap.vp, investor: snap.investor, depth: snap.depth, index: snap.index, weight: snap.weight, asked: snap.asked, size: snap.size, step: snap.step });
  }
  ctx.check = async (snap, asked, chrome) => {
    if (o.dump) writeFileSync(o.dump, JSON.stringify({ vp: snap.vp, investor: snap.investor, depth: snap.depth, size: snap.size, asked: snap.asked, items: snap.items.map(({ sec, sub, path, where, text }) => ({ sec, sub, path, where, text })), green: snap.green.map(({ sec, path, why }) => ({ sec, path, why })) }) + "\n", { flag: "a" });
    const k = (x) => `${x.sec}|${x.path}|${x.where}|${x.text}`;
    const gk = (g) => `${g.sec}|${g.path}`;
    const askedKeys = asked ? new Set(asked.items.map(k)) : null, askedGreen = asked ? new Set(asked.green.map(gk)) : null;
    const other = !snap.asked && !!asked;
    for (const it of snap.items) {
      for (const h of adviceHits(it.text, ctx.questions)) await add("a", snap, it, { match: h.match, rule: h.label, text: h.context }, chrome);
      if (it.where === "text" || it.where === "pseudo") for (const h of metaHits(it.text)) await add("c", snap, it, { match: "·", rule: "a \" · \" string", text: h.context }, chrome);
      if (other && it.where !== "input" && (inScope(it) || !askedKeys.has(k(it)))) {
        for (const h of verdictHits(it.text)) await add("b", snap, it, { match: h.match, rule: "a verdict word", text: h.context }, chrome);
      }
    }
    if (other) for (const g of snap.green) if (inScope(g) || !askedGreen.has(gk(g))) await add("b", snap, { ...g, where: "mark" }, { match: "green", rule: "a green status mark", text: `${g.text ? `“${g.text}”: ` : ""}${g.why}` }, chrome);
    const seen = snap.items.filter((x) => x.where === "text").map((x) => norm(x.text)).join("\n");
    for (const line of REQUIRED) if (!seen.includes(norm(line))) await add("d", snap, { sec: "page", path: "", where: "text" }, { match: line, rule: "missing", text: `“${line}” is not visible anywhere on the page` }, chrome);
    if (snap.phone && snap.scrollWidth > snap.vw) {
      if (!snap.overflow.length) await add("f", snap, { sec: "page", path: "html", where: "layout" }, { match: snap.scrollWidth, rule: "wider than the viewport", text: `document scrollWidth ${snap.scrollWidth} px at a ${snap.vw} px viewport` }, chrome);
      for (const ov of snap.overflow) await add("f", snap, { ...ov, where: "layout" }, { match: snap.scrollWidth, rule: "wider than the viewport", text: `document scrollWidth ${snap.scrollWidth} px at ${snap.vw} px; this element ends at ${ov.right} px (width ${ov.width} px)${ov.text ? `: “${ov.text}”` : ""}` }, chrome);
    }
  };
  return ctx;
}

/* ---- who owns what (design doc §4 lane contract) and where a string comes from ---- */
const OWNERS = {
  bar: "web/sections/bar.js (lane U7b); the Simple / Detailed switch is web/depth.js (lane U0)",
  hero: "web/sections/hero.js, web/css/hero.css (lane U1)",
  replay: "web/sections/replay.js, web/lib/replay.js, web/css/replay.css (lane U2)",
  "replay/race chart": "web/race.js, web/lib/race.js, web/css/race.css (lane U3)",
  "replay/dial strip": "web/sections/dial.js, web/lib/dial.js, web/css/dial.css (lane U4)",
  dial: "web/sections/dial.js, web/lib/dial.js, web/css/dial.css (lane U4)",
  money: "web/sections/money.js, web/lib/money.js, web/css/money.css (lane U5)",
  checklist: "web/sections/checklist.js, web/lib/status.js (lane U5)",
  deep: "web/sections/deep.js, web/lib/deep.js, web/css/deep.css (lane U8)",
  scenario: "web/sections/scenario.js, web/css/scenario.css (lane sc-u)",
  why: "web/sections/why.js, web/lib/why.js, web/css/why.css (lane U6)",
  investors: "web/sections/investors.js, web/css/investors.css (lane U7)",
  how: "web/sections/how.js, web/lib/how.js, web/css/how.css (lane U7)",
  record: "web/sections/record.js, web/lib/record.js, web/css/record.css (lane U9)",
  footer: "web/sections/footer.js (lane U7)",
  page: "web/index.html, web/app.js, web/styles.css (lane U0)",
};
function ownerOf(sec, sub) {
  if (sub && OWNERS[`${sec}/${sub}`]) return OWNERS[`${sec}/${sub}`];
  if (OWNERS[sec]) return OWNERS[sec];
  if (/thread|drawer/i.test(sec)) return OWNERS.why + " (the thread drawer)";
  if (/tour/i.test(sec)) return "web/tour.js (lane U0)";
  if (/depth/i.test(sec)) return "web/depth.js (lane U0)";
  return OWNERS.page;
}
function ownerOfUrl(text, url) {
  const s = `${url || ""} ${text || ""}`;
  const m = s.match(/(?:sections|css|lib)\/([\w-]+)\.(?:js|css)/) || s.match(/section "([\w-]+)"/);
  if (m && OWNERS[m[1]]) return `${OWNERS[m[1]]}; the page that asks for it: web/index.html, web/app.js (lane U0)`;
  if (/race/.test(s)) return OWNERS["replay/race chart"];
  if (/globe/.test(s)) return "web/globe.js (lane U1)";
  return OWNERS.page;
}

function jsSources(dir) {
  const out = [];
  const walk = (d) => {
    let names = [];
    try { names = readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const n of names) {
      const p = join(d, n.name);
      if (n.isDirectory()) { if (!["vendor", "runs", "dev", "node_modules"].includes(n.name)) walk(p); }
      else if (/\.(m?js|html)$/.test(n.name)) out.push({ rel: relative(dir, p), text: readFileSync(p, "utf8") });
    }
  };
  walk(dir);
  return out;
}
function findInJson(value, frag, path = "") {
  if (typeof value === "string") return value.toLowerCase().includes(frag) ? path : null;
  if (Array.isArray(value)) { for (let i = 0; i < value.length; i++) { const r = findInJson(value[i], frag, `${path}[${i}]`); if (r) return r; } return null; }
  if (value && typeof value === "object") { for (const [k, v] of Object.entries(value)) { const r = findInJson(v, frag, path ? `${path}.${k}` : k); if (r) return r; } }
  return null;
}
/* the source of an offending string: a phrase of 2 to 6 words around the match (no digits) in the page's code (the owner's files
   first, comments skipped, exact case first), else in a saved Result's text */
function codeHit(src, frag, fold) {
  const hay = fold ? src.lower : src.text, needle = fold ? frag.toLowerCase() : frag;
  for (let i = hay.indexOf(needle); i >= 0; i = hay.indexOf(needle, i + 1)) {
    const lineStart = src.text.lastIndexOf("\n", i) + 1, before = src.text.slice(lineStart, i), lead = before.trimStart();
    if (lead.startsWith("//") || lead.startsWith("*") || lead.startsWith("/*") || before.includes("//") || before.includes("/*")) continue;
    return src.text.slice(0, i).split("\n").length;
  }
  return 0;
}
function sourceOf(text, match, sources, runs, owner) {
  const words = norm(text).replace(/[…“”"«»()]/g, " ").split(/\s+/).filter(Boolean);
  const m0 = String(match).toLowerCase().split(/\s+/)[0];
  const at = words.findIndex((w) => w.toLowerCase().includes(m0));
  if (at < 0) return null;
  const mine = new Set((String(owner || "").match(/web\/[\w/.-]+\.(?:js|html)/g) || []).map((x) => x.replace(/^web\//, "")));
  const ordered = [...sources.filter((x) => mine.has(x.rel)), ...sources.filter((x) => !mine.has(x.rel))];
  for (const x of ordered) if (x.lower === undefined) x.lower = x.text.toLowerCase();
  /* every phrase of 2 to 6 words within 6 words of the match: the string itself, or the fixed part of the template that builds it */
  const found = new Map();
  for (let span = 6; span >= 2; span--) {
    for (let s = Math.max(0, at - 6); s <= Math.min(words.length - span, at + 1); s++) {
      const frag = words.slice(s, s + span).join(" ").replace(/[.,;:!?]+$/, "");
      if (frag.length < 8 || /\d/.test(frag)) continue;
      const withMatch = s <= at && at < s + span;
      for (const fold of [false, true]) for (const v of [frag, frag.replace(/'/g, "’")]) for (const x of ordered) {
        const line = codeHit(x, v, fold);
        const key = `web/${x.rel}:${line}`;
        if (line && !found.has(key)) found.set(key, { key, v, span, withMatch, mine: mine.has(x.rel), fold });
      }
    }
  }
  const best = [...found.values()].sort((a, b) => b.span - a.span || Number(a.fold) - Number(b.fold) || Number(b.mine) - Number(a.mine) || Number(b.withMatch) - Number(a.withMatch));
  if (best.length) {
    const top = [best[0]], other = best.find((b) => b.withMatch !== best[0].withMatch && b.key !== best[0].key && b.span >= 3);
    if (other) top.push(other);
    return top.map((b) => `${b.key} (“${b.v}”)`).join(" or ");
  }
  for (let span = 4; span >= 2; span--) {
    for (let s = Math.max(0, at - span + 1); s <= at; s++) {
      const frag = words.slice(s, s + span).join(" ").replace(/[.,;:!?]+$/, "");
      if (frag.length < 8) continue;
      for (const [id, r] of Object.entries(runs)) { const p = findInJson(r, frag.toLowerCase()); if (p) return `the saved Result's text, ${id}'s run → ${p} (“${frag}”)`; }
    }
  }
  return null;
}
export { sourceOf, jsSources };

/* ---- the report ---- */
function whereText(states) {
  const by = new Map();
  for (const s of states) {
    if (!by.has(s.investor)) by.set(s.investor, { depths: new Set(), vps: new Set(), w: new Set(), asked: new Set(), plain: false, steps: new Set() });
    const b = by.get(s.investor);
    if (s.depth) b.depths.add(s.depth);
    b.vps.add(s.vp);
    if (s.step) b.steps.add(s.step);
    if (s.weight === null || s.weight === undefined) { if (!s.step) b.plain = true; }
    else { b.w.add(s.weight); if (s.asked) b.asked.add(s.weight); }
  }
  return [...by.entries()].map(([id, b]) => {
    const sizes = [...b.w];
    const ints = sizes.every((x) => Number.isInteger(x));
    const parts = [sizes.length ? `${ints ? ranges(sizes) : sizes.sort((x, y) => x - y).join(", ")} %${b.asked.size ? ` (asked ${[...b.asked].join(", ")} %)` : ""}` : null,
      b.plain ? "the asked answer (no dial)" : null, ...b.steps].filter(Boolean);
    const where = parts.join(", ");
    return `${NAMES[id] || id} (${[...b.depths].join(" + ") || "any depth"}; ${[...b.vps].join(", ")}): ${where}`;
  }).join("; ");
}

function report(ctx, o, site, base, sources, runs) {
  const fs = [...ctx.findings.values()];
  const errGroups = new Map();
  for (const e of ctx.errors) {
    const key = `${String(e.text).replace(/127\.0\.0\.1:\d+/g, "HOST").slice(0, 300)}|${String(e.url || "").replace(/127\.0\.0\.1:\d+/g, "HOST")}`;
    if (!errGroups.has(key)) errGroups.set(key, { text: e.text, url: e.url, source: e.source, states: [] });
    errGroups.get(key).states.push(e);
  }
  const count = { a: 0, b: 0, c: 0, d: 0, e: errGroups.size, f: 0 };
  for (const f of fs) count[f.check] += 1;
  const total = fs.length + errGroups.size;
  const setup = [...new Map(ctx.setup.map((s) => [`${s.step}|${s.text}`, s])).values()];
  const pass = total === 0 && setup.length === 0;
  const L = [];
  L.push(`# EPICENTRE release gate: ${pass ? "PASS" : "FAIL"}${pass ? "" : ` (${total} finding${total === 1 ? "" : "s"}${setup.length ? `, ${setup.length} step${setup.length === 1 ? "" : "s"} the gate could not complete` : ""})`}`);
  L.push("");
  L.push(`- Site: ${site.label}, opened at ${base}${site.commit ? `; checkout ${site.commit}` : ""}.`);
  const now = new Date(), pad = (n) => String(n).padStart(2, "0");
  L.push(`- Checked ${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())} (local) with ${ctx.browser || "Chrome"}; viewports ${o.viewports.join(", ")} (${ctx.sessions.map((s) => `${s.vp} took ${s.seconds} s`).join(", ")}).`);
  const dials = o.investors.map((id) => ctx.dial[id] ? `${NAMES[id]}: dial ${ctx.dial[id].weights[ctx.dial[id].min ?? 0]}-${ctx.dial[id].weights[ctx.dial[id].max]} %, asked ${ctx.dial[id].askedSize}` : `${NAMES[id]}: no dial on this run`);
  L.push(`- Investors: ${dials.join("; ")}. Depths: ${o.depths.join(", ")}. States read: ${ctx.states} (median ${ctx.snapMs.length ? ctx.snapMs.slice().sort((x, y) => x - y)[ctx.snapMs.length >> 1] : 0} ms each). Replays to the end frame: ${ctx.replays.filter((r) => r.ended).length} of ${ctx.replays.length}.`);
  L.push(`- Tally: ${Object.entries(count).map(([k, n]) => `(${k}) ${n}`).join(", ")}.`);
  for (const c of ["a", "b", "c", "d", "f"]) {
    const list = fs.filter((f) => f.check === c);
    L.push("", `## ${CHECKS[c]}: ${list.length}`);
    if (!list.length) { L.push("", "None."); continue; }
    list.sort((x, y) => y.states.length - x.states.length).forEach((f, i) => {
      const sec = f.sec.startsWith("overlay:") ? f.sec.replace("overlay:", "overlay ") : `#${f.sec}`;
      L.push("", `${i + 1}. **${sec}${f.sub ? ` (${f.sub})` : ""}**${f.path ? ` \`${f.path}\`` : ""}, ${WHERE[f.where] || f.where}: ${c === "f" ? "the page scrolls sideways" : f.where === "mark" ? "a green status mark (icon, colour or tone)" : `“${f.match}” (${f.rule})`}`);
      L.push(`   - Where: ${whereText(f.states)}.`);
      for (const ex of f.examples) L.push(`   - Text: “${ex}”`);
      const src = (c === "a" || c === "b" || c === "c") && f.where !== "mark" ? sourceOf(f.examples[0] || "", c === "c" ? "·" : f.match, sources, runs, ownerOf(f.sec, f.sub)) : null;
      L.push(`   - Owner: ${ownerOf(f.sec, f.sub)}${src ? `; the string: ${src}` : ""}.`);
      if (f.shot) L.push(`   - Screenshot: ${f.shot}`);
    });
  }
  L.push("", `## ${CHECKS.e}: ${errGroups.size}`);
  if (!errGroups.size) L.push("", "None.");
  [...errGroups.values()].forEach((g, i) => {
    L.push("", `${i + 1}. ${g.source}: “${String(g.text).replace(/127\.0\.0\.1:\d+/g, "HOST").slice(0, 300)}”${g.url ? ` at ${String(g.url).replace(/http:\/\/127\.0\.0\.1:\d+\//, "")}` : ""}`);
    L.push(`   - When: ${whereText(g.states)}.`);
    L.push(`   - Owner: ${ownerOfUrl(g.text, g.url)}.`);
  });
  if (ctx.notes.length) { L.push("", "## Notes", ""); for (const n of [...new Set(ctx.notes)]) L.push(`- ${n}`); }
  if (setup.length) {
    L.push("", `## Steps the gate could not complete: ${setup.length}`);
    setup.forEach((s, i) => L.push("", `${i + 1}. ${NAMES[s.investor] || s.investor || ""} ${s.depth || ""} at ${s.vp}, ${s.step}: ${s.text}`));
  }
  const warns = [...new Set(ctx.warnings.map((w) => String(w.text).replace(/127\.0\.0\.1:\d+/g, "HOST").slice(0, 200)))];
  if (warns.length) {
    L.push("", `## Console warnings (not failures): ${warns.length}`, "");
    for (const w of warns.slice(0, 10)) L.push(`- ${w}`);
  }
  L.push("", "Rules: scripts/gate_rules.mjs (node-tested by tests/web_gate_test.mjs). Exempt: an investor's question (whole or quoted), a quoted or first-person question, the disclaimers. (b) reads what follows the dial: the #replay stage, the #dial ruler, and any text or mark that changed from the asked size.");
  return { text: L.join("\n") + "\n", pass, count, setup, findings: fs, errors: [...errGroups.values()] };
}

/* ---- main ---- */
async function main() {
  let o;
  try { o = parseArgs(process.argv.slice(2)); } catch (e) { console.error(`release gate: ${e.message}`); return 2; }
  if (o.help) { console.log(readFileSync(fileURLToPath(import.meta.url), "utf8").split("*/")[0]); return 0; }
  const chromePath = findChrome();
  let site = null, problem = null;
  try { site = await resolveSite(o); } catch (e) { problem = e.message; }
  if (o.probe) {
    console.log(JSON.stringify({ chrome: chromePath, site: site ? (site.url || site.dir) : null, problem }));
    return chromePath && site ? 0 : 2;
  }
  if (!chromePath) { console.error("release gate: Chrome was not found (set CHROME_PATH)."); return 2; }
  if (!site) { console.error(`release gate: no site to check${problem ? `: ${problem}` : ""}. Build one (python scripts/publish_pages.py --dry-run [--runs DIR]) or pass --site DIR / --url URL.`); return 2; }
  if (site.kind === "build") site.commit = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT, encoding: "utf8" }).stdout.trim();
  let server = null, base = site.url;
  if (site.dir) { server = await serve(site.dir); base = server.url; }
  const runs = {};
  for (const id of o.investors) {
    for (const path of [`runs/${id}.json`, `api/demo-run?pilot=${id}`]) {
      try { const r = await fetch(new URL(path, base)); if (r.ok) { runs[id] = await r.json(); break; } } catch { /* next */ }
    }
  }
  const sources = jsSources(site.dir || join(ROOT, "web"));
  const ctx = makeCtx(o);
  try {
    for (const vp of o.viewports) await session(o, base, vp, ctx);
  } catch (e) {
    ctx.setup.push({ vp: "-", investor: "", step: "browser session", text: String(e && e.stack || e).slice(0, 500) });
  } finally {
    if (server) server.server.close();
  }
  const out = report(ctx, o, site, base, sources, runs);
  if (o.report) { mkdirSync(dirname(resolve(o.report)), { recursive: true }); writeFileSync(o.report, out.text); }
  if (o.json) writeFileSync(o.json, JSON.stringify({ pass: out.pass, count: out.count, setup: out.setup, findings: out.findings, errors: out.errors }, null, 1));
  process.stdout.write(out.text);
  return out.pass ? 0 : 1;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {      // run, not imported (a test may import it)
  main().then((code) => { dropLock(); process.exit(code); }, (e) => { console.error(e && e.stack || e); dropLock(); process.exit(2); });
}
