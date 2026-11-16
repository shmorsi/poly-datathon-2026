// Minimal Chrome DevTools Protocol driver for ONE headless Chrome at a time (vendored from the team's capture driver for the
// release gate, scripts/release_gate.mjs). Node 22 (global fetch and WebSocket), no dependencies.
//   launch({port, W, H, dsf, mobile, maxMs}) -> { send, evaluate, waitFor, goto, shot, viewport, logs, close }
//   findChrome() -> the Chrome binary (env CHROME_PATH or CHROME, the macOS app, or google-chrome / chromium on the PATH), or null
// `logs` collects every console error / assert, uncaught exception and browser log entry of level "error" (a failed request, a
// CSP refusal) as {kind, text, url}; console warnings are kept as kind "warn" so a report can show them without failing on them.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { writeFileSync } from 'node:fs';
import { tmpdir, platform } from 'node:os';
import { join } from 'node:path';

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function findChrome() {
  for (const env of [process.env.CHROME_PATH, process.env.CHROME]) if (env && existsSync(env)) return env;
  const mac = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium'];
  for (const p of mac) if (existsSync(p)) return p;
  for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome']) {
    const r = spawnSync('which', [name], { encoding: 'utf8' });
    const p = (r.stdout || '').trim();
    if (r.status === 0 && p && existsSync(p)) return p;
  }
  return null;
}

const argText = (a) => (a.value !== undefined ? (typeof a.value === 'string' ? a.value : JSON.stringify(a.value)) : (a.description || a.type || ''));

export async function launch({ port = 9560, W = 1440, H = 900, dsf = 1, mobile = false, maxMs = 6 * 60000 } = {}) {
  const CHROME = findChrome();
  if (!CHROME) throw new Error('Chrome was not found (set CHROME_PATH)');
  const prof = join(tmpdir(), `epi-gate-chrome-${port}`);
  const flags = ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, `--window-size=${W},${H}`,
    '--hide-scrollbars', `--force-device-scale-factor=${dsf}`, '--mute-audio', '--no-first-run', '--no-default-browser-check',
    '--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows', '--force-color-profile=srgb', '--disable-extensions', '--disable-component-update'];
  if (platform() === 'darwin') flags.push('--use-angle=metal');
  const chrome = spawn(CHROME, [...flags, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = ''; chrome.stderr.on('data', (d) => { stderr = (stderr + d).slice(-4000); });
  const kill = () => { try { chrome.kill('SIGKILL'); } catch { /* gone */ } };
  process.on('exit', kill);
  const watchdog = setTimeout(() => { console.error('cdp watchdog: the browser session took too long; Chrome killed'); kill(); process.exit(3); }, maxMs);
  watchdog.unref();
  let wsUrl = null;
  for (let i = 0; i < 150 && !wsUrl; i++) {
    try { const l = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); const p = l.find((t) => t.type === 'page'); if (p) wsUrl = p.webSocketDebuggerUrl; }
    catch { /* not up yet */ }
    if (!wsUrl) await sleep(100);
  }
  if (!wsUrl) { kill(); throw new Error('Chrome did not start: ' + stderr.slice(-600)); }
  const ws = new WebSocket(wsUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let seq = 0; const pending = new Map(); const logs = []; const handlers = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { const { res, rej } = pending.get(msg.id); pending.delete(msg.id); msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result); return; }
    const p = msg.params || {};
    if (msg.method === 'Runtime.consoleAPICalled') {
      const kind = p.type === 'error' || p.type === 'assert' ? 'error' : p.type === 'warning' ? 'warn' : null;
      const top = p.stackTrace && p.stackTrace.callFrames && p.stackTrace.callFrames[0];
      if (kind) logs.push({ kind, source: 'console', text: (p.args || []).map(argText).join(' ').slice(0, 600), url: top ? `${top.url}:${top.lineNumber + 1}` : '' });
    } else if (msg.method === 'Runtime.exceptionThrown') {
      const d = p.exceptionDetails || {};
      logs.push({ kind: 'error', source: 'exception', text: ((d.exception && d.exception.description) || d.text || 'exception').slice(0, 600), url: d.url ? `${d.url}:${(d.lineNumber || 0) + 1}` : '' });
    } else if (msg.method === 'Log.entryAdded') {
      const e = p.entry || {};
      if (e.level === 'error') logs.push({ kind: 'error', source: e.source || 'log', text: String(e.text || '').slice(0, 600), url: e.url || '' });
    }
    const h = handlers.get(msg.method); if (h) h(p);
  };
  const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
  const evaluate = async (expression) => {
    const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error('eval: ' + JSON.stringify(r.exceptionDetails).slice(0, 500));
    return r.result.value;
  };
  await send('Runtime.enable'); await send('Page.enable'); await send('Log.enable');
  const api = {
    send, evaluate, logs, on: (m, f) => handlers.set(m, f),
    async viewport(w, h, scale = 1, phone = false) {
      await send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: scale, mobile: phone });
      await send('Emulation.setTouchEmulationEnabled', { enabled: phone, maxTouchPoints: phone ? 5 : 1 });
    },
    async goto(url, readyExpr = 'document.readyState === "complete"', timeout = 30000) {
      await send('Page.navigate', { url });
      return api.waitFor(readyExpr, timeout);
    },
    async waitFor(expr, timeout = 30000, every = 120) {
      const t0 = Date.now();
      while (Date.now() - t0 < timeout) { try { if (await evaluate(`!!(${expr})`)) return true; } catch { /* loading */ } await sleep(every); }
      throw new Error('timeout waiting for: ' + expr);
    },
    async shot(path) {
      const r = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
      writeFileSync(path, Buffer.from(r.data, 'base64'));
    },
    async close() {
      clearTimeout(watchdog);
      try { ws.close(); } catch { /* gone */ }
      chrome.kill('SIGTERM');
      await new Promise((r) => { const t = setTimeout(() => { kill(); r(); }, 4000); chrome.on('exit', () => { clearTimeout(t); r(); }); });
      try { rmSync(prof, { recursive: true, force: true }); } catch { /* ok */ }
    },
  };
  await api.viewport(W, H, dsf, mobile);
  return api;
}
