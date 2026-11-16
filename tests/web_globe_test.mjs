/* Lane globe-hq: the night Earth's light, motion and touch (web/globe.js). Run: node tests/web_globe_test.mjs (also run by
   tests/test_web_lib.py). The curve is tested as numbers; the renderer's settings and the hand's rules are read from the source. */
import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { turnCurve, CAMERA_D } from "../web/globe.js";

const SRC = readFileSync(new URL("../web/globe.js", import.meta.url), "utf8");
let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed += 1; console.log(`ok   ${name}`); } catch (e) { failed += 1; console.log(`FAIL ${name}\n     ${e.message}`); }
}
const speed = (s0, p, h = 1e-5) => (turnCurve(Math.min(1, p + h), s0) - turnCurve(Math.max(0, p - h), s0)) / (Math.min(1, p + h) - Math.max(0, p - h));

test("a turn from rest is the quintic smootherstep: 0 to 1, symmetric, peak 1.875 x the mean speed, no jerk at the ends", () => {
  assert.equal(turnCurve(0), 0); assert.equal(turnCurve(1), 1); assert.equal(turnCurve(-1), 0); assert.equal(turnCurve(2), 1);
  assert.ok(Math.abs(turnCurve(0.5) - 0.5) < 1e-12);
  for (const p of [0.1, 0.3, 0.45]) assert.ok(Math.abs(turnCurve(p) + turnCurve(1 - p) - 1) < 1e-12);
  assert.ok(Math.abs(speed(0, 0.5) - 1.875) < 1e-4);
  assert.ok(speed(0, 0.001) < 1e-4 && speed(0, 0.999) < 1e-4);                  // it leaves and lands at rest
  const acc = (p, h = 1e-4) => (speed(0, p + h) - speed(0, p - h)) / (2 * h);
  assert.ok(Math.abs(acc(0.002)) < 0.2 && Math.abs(acc(0.998)) < 0.2);            // and with no step in acceleration (C2)
});

test("a turn that interrupts motion leaves at the Earth's own speed, lands at rest, and never overshoots for 0 <= s0 <= 2.5", () => {
  for (const s0 of [0.4, 1, 2.5]) {
    assert.ok(Math.abs(speed(s0, 1e-4) - s0) < 1e-2, `s0 ${s0}`);
    assert.ok(speed(s0, 1 - 1e-4) < 1e-3);
    let prev = 0;
    for (let i = 1; i <= 200; i++) { const e = turnCurve(i / 200, s0); assert.ok(e >= prev - 1e-12 && e <= 1 + 1e-12, `s0 ${s0} p ${i / 200}`); prev = e; }
  }
  assert.ok(turnCurve(0.1, -1) < 0 && turnCurve(1, -1) === 1);                    // moving the other way: it eases out, then turns
});

test("the renderer: antialias, the pixel ratio capped at 2, sRGB out, the map decoded as sRGB, anisotropy at the GPU's maximum", () => {
  assert.match(SRC, /antialias: true/);
  assert.match(SRC, /Math\.min\(window\.devicePixelRatio \|\| 1, 2\)/);
  assert.match(SRC, /outputColorSpace = THREE\.SRGBColorSpace/);
  assert.match(SRC, /night\.colorSpace = THREE\.SRGBColorSpace/);
  assert.match(SRC, /night\.anisotropy = renderer\.capabilities\.getMaxAnisotropy\(\)/);
  assert.match(SRC, /LinearMipmapLinearFilter/);
  assert.match(SRC, /vec3 tone\(vec3 c\)/);                                      // the highlight shoulder
  assert.match(SRC, /#include <colorspace_fragment>/);
  assert.equal(CAMERA_D, 6);                                                     // PF.globeProject and the posters share it
});

test("the map: 4096 and 2048 px progressive JPEGs from NASA's Black Marble 2016, each at most 750 KB, decoded off the main thread", () => {
  for (const [f, w] of [["black-marble-2016-4096.jpg", 4096], ["black-marble-2016-2048.jpg", 2048]]) {
    const u = new URL(`../web/vendor/nasa/${f}`, import.meta.url), b = readFileSync(u);
    assert.ok(statSync(u).size <= 750 * 1024, f);
    assert.equal(b[0], 0xff); assert.equal(b[1], 0xd8);
    const i = b.indexOf(Buffer.from([0xff, 0xc2]));                                // SOF2: progressive
    assert.ok(i > 0, `${f} is progressive`);
    assert.equal(b.readUInt16BE(i + 7), w); assert.equal(b.readUInt16BE(i + 5), w / 2);
  }
  assert.match(SRC, /createImageBitmap\(b, \{ premultiplyAlpha: 'none', colorSpaceConversion: 'none' \}\)/);
  assert.match(SRC, /renderer\.initTexture\(night\)/);                         // the <img> path
  assert.match(SRC, /texStorage2D\(g2\.TEXTURE_2D, .*g2\.SRGB8_ALPHA8/);         // the bitmap path: strips into sRGB storage, then mips
  assert.match(SRC, /STRIP = 256/); assert.match(SRC, /g2\.generateMipmap\(g2\.TEXTURE_2D\)/);
  assert.match(SRC, /compileAsync/);
  const lic = readFileSync(new URL("../web/vendor/LICENSES.md", import.meta.url), "utf8");
  assert.match(lic, /BlackMarble_2016_3km\.jpg, 13,500 x 6,750/);
  assert.match(lic, /04b209c090eb3bf5ea4de2904ceb3eac18a4851219c3d0f26d74df561bbf2b4a/);
});

test("the hand: no scroll or wheel captured, passive pointer listeners, drags only in the hero, words by textContent, a hidden tab draws nothing", () => {
  assert.ok(!/['"]wheel['"]/.test(SRC) && !/touch-action/.test(SRC));
  assert.match(SRC, /\{ passive: n !== 'selectstart' \}/);
  assert.match(SRC, /if \(!heroStill\(\)\) \{ drag\.id = null; return; \}/);
  assert.ok(!/innerHTML|insertAdjacentHTML/.test(SRC));
  assert.match(SRC, /addEventListener\('visibilitychange', onVis\)/);
  assert.match(SRC, /!document\.hidden\) raf = requestAnimationFrame\(tick\)/);
  assert.match(SRC, /LAT_MAX = 60 \* D2R/);
  assert.ok(!/tabindex=/.test(SRC.replace(/\[tabindex[^\]]*\]/g, "")));           // it adds no tab stop
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
