// The night Earth (lane U1; its light, motion and touch: lane globe-hq). NASA Black Marble 2016 (public domain) on a sphere, each
// shock of the Result at its epicentre: a 3-4 px core, a soft halo and one ring whose radius is how far the mix fell after that
// shock (the Result's trough; none, no ring). One canvas, one WebGL context, shared by the hero and the #replay stage: the canvas
// is a fixed full-viewport layer and the disc is placed by the camera (frames() gives its centre and radius in CSS px), so
// setLayout glides it without a second context. It draws only while something moves or the frames change, never while the tab is
// hidden or the host has set it inactive (hero.js does so once the hero-to-stage region has left the viewport); no per-frame
// allocation; context loss is handled; dispose() frees every geometry, material, texture and listener. The camera sits at
// CAMERA_D globe radii (PF.globeProject uses the same), so the poster and the no-WebGL rings line up with this render at any size.
// Light: the map is decoded as sRGB and lit in linear light; the city lights bloom from the texture's own mip chain (no extra
// pass); a thin atmosphere scatters one cool blue along the line of sight (e^(-tau) - e^(-tau/mu) on the disc, the same value at
// the limb falling off as e^(-h/H) above it, so the edge is one curve); a highlight shoulder rolls off only the hottest cores (identity
// below 0.6, hue kept), then sRGB out. Motion: a turn is a quintic Hermite curve that leaves at the globe's current angular speed
// and lands at rest with no jerk; in the hero the reader may drag the Earth (a damped follow, then inertia; the tilt kept within
// 60 degrees, north up; no scroll or wheel captured); hover or tap a ring for its name, place and date.
import * as THREE from './vendor/three/three.module.min.js';
import { easeInOut, easeOut, easeTurn, ringRadius, ignitionSchedule, mix, mixFrame, HOME } from './lib/u1.js';

export const CAMERA_D = 6;
const D2R = Math.PI / 180, TAN_A = 1 / Math.sqrt(CAMERA_D * CAMERA_D - 1);
const RING_MS = 600, DIM = 0.3, DIM_MS = 400, MORPH_MS = 500, PULSE_MS = 1100;
/* the air: optical depth at the zenith, its blue (linear), scale height in Earth radii; the lights' bloom */
const TAU = 0.012, AIR = new THREE.Vector3(0.30, 0.56, 1.0).multiplyScalar(0.95), SCALE_H = 0.008, BLOOM = 0.85;
/* the drag: the tilt limit, the follow and coast time constants (ms), the move that starts a drag (px), the fastest fling (rad/s) */
const LAT_MAX = 60 * D2R, FOLLOW_MS = 55, COAST_MS = 380, DRAG_PX = 4, FLING_MAX = 6;
const asset = (p) => new URL(p, import.meta.url).href;     // textures resolve from this module, whatever page loads it

const earthVert = `varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main(){ vUv = uv; vec4 wp = modelMatrix * vec4(position, 1.); vP = wp.xyz; vN = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * wp; }`;
/* c: the map in linear light (the GPU decodes sRGB). The ground and the sea keep the map's own moonlit navy (x .42); the lights
   (its bright end) are lifted and warmed; the bloom is the lights' neighbourhood read from two coarser mips (no extra pass); the
   air in-scatters blue with the air mass 1/mu beyond the zenith's own (none facing the camera, the most at the limb: a Fresnel
   rim on a physical curve) and dims the lights behind it; tone() is the highlight shoulder */
const earthFrag = `uniform sampler2D night; uniform float uFlip; uniform float uBloom; uniform vec3 uAir; uniform float uTau;
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
float lum(vec3 c){ return dot(c, vec3(.2126, .7152, .0722)); }
vec3 tone(vec3 c){ float L = max(max(c.r, c.g), c.b); if (L <= .6) return c;
  float T = .6 + .4 * (1. - exp(-(L - .6) / .4)); return mix(c * (T / L), vec3(T), smoothstep(.6, 3.2, L) * .55); }
void main(){ vec2 uv = vec2(vUv.x, uFlip > .5 ? 1. - vUv.y : vUv.y);
  vec3 n = normalize(vN), v = normalize(cameraPosition - vP); float mu = max(dot(n, v), 0.);
  vec3 c = texture2D(night, uv).rgb; float m = smoothstep(.05, .34, lum(c));
  vec3 ground = c * mix(.42, 2.5, m) * mix(vec3(1.), vec3(1.07, .95, .80), m);
  vec3 g1 = texture2D(night, uv, 2.).rgb, g2 = texture2D(night, uv, 4.).rgb;
  vec3 glow = (g1 * smoothstep(.03, .22, lum(g1)) * .55 + g2 * smoothstep(.02, .14, lum(g2)) * .45) * uBloom * vec3(1.08, .92, .74);
  float air = 1. / max(mu, .03);                           // the air mass along the line of sight (1 facing the camera)
  vec3 col = (ground + glow) * exp(-uTau * .5 * (air - 1.)) + uAir * max(0., exp(-uTau) - exp(-uTau * air));
  gl_FragColor = vec4(tone(col), 1.);
  #include <colorspace_fragment>
}`;
/* past the limb: h, the line of sight's lowest altitude above the ground (Earth radii); the limb's in-scattering falls off as
   e^(-h/H) (a sharp part and a faint wider one: a few px at the hero's size), gone before the shell's edge; drawn on the back of
   a shell 6 % above the ground */
const atmoVert = `varying vec3 vP;
void main(){ vec4 wp = modelMatrix * vec4(position, 1.); vP = wp.xyz; gl_Position = projectionMatrix * viewMatrix * wp; }`;
const atmoFrag = `uniform vec3 uAir; uniform float uTau; uniform float uH; varying vec3 vP;
void main(){ vec3 d = normalize(vP - cameraPosition); vec3 cp = cameraPosition - dot(cameraPosition, d) * d;
  float h = length(cp) - 1.; if (h < 0.) discard;
  float a = (exp(-uTau) - exp(-uTau / .03)) * (.85 * exp(-h / uH) + .15 * exp(-h / (uH * 3.))) * (1. - smoothstep(.03, .056, h));
  gl_FragColor = vec4(uAir * a, min(1., a));
  #include <colorspace_fragment>
}`;
// a ring lying on the ground at the epicentre (a tangent quad): radius uR in quad units, a ~1.3 px stroke at any zoom (fwidth)
const ringVert = `varying vec2 vUv; varying float vFace;
void main(){ vUv = uv; vec4 wp = modelMatrix * vec4(position, 1.); vec3 n = normalize(mat3(modelMatrix) * vec3(0., 0., 1.));
  vFace = dot(n, normalize(cameraPosition - wp.xyz)); gl_Position = projectionMatrix * viewMatrix * wp; }`;
const ringFrag = `uniform float uR; uniform float uA; varying vec2 vUv; varying float vFace;
void main(){ float d = length(vUv - .5) * 2.; float w = max(fwidth(d), 1e-4), e = abs(d - uR);
  float line = 1. - smoothstep(.55 * w, 1.35 * w, e), glow = exp(-e * e / (w * w * 9.)) * .22;
  float a = (line + glow) * uA * smoothstep(.04, .3, vFace);
  gl_FragColor = vec4(vec3(.62, .90, 1.) * a, min(a, 1.)); }`;
// the lights: one point per shock, constant size in px (core + halo), lit by its ignition, dimmed by the focus
const coreVert = `attribute float aLit; attribute float aFlash; attribute float aDim; attribute float aW;
uniform float uSize; varying float vA; varying float vFlash;
void main(){ vec4 wp = modelMatrix * vec4(position, 1.); vec3 n = normalize(wp.xyz);
  float face = dot(n, normalize(cameraPosition - wp.xyz)); vA = aLit * aDim * aW * smoothstep(.06, .28, face); vFlash = aFlash;
  gl_PointSize = uSize; gl_Position = projectionMatrix * viewMatrix * wp; }`;
const coreFrag = `uniform float uCore; varying float vA; varying float vFlash;
void main(){ float r = length(gl_PointCoord - .5) * 2.; if (vA <= .001) discard;
  float core = 1. - smoothstep(uCore * .7, uCore, r);
  float halo = exp(-r * r * 7.) * (.62 + 1.2 * vFlash);
  vec3 c = vec3(1.) * core * (1. + vFlash) + vec3(.62, .90, 1.) * halo;                 // the core at 2x as it ignites
  float a = clamp(core + halo, 0., 1.) * vA; gl_FragColor = vec4(c * vA, a); }`;

const toVec = (lat, lon, r, out) => { const a = lat * D2R, b = lon * D2R;
  return out.set(r * Math.cos(a) * Math.cos(b), r * Math.sin(a), -r * Math.cos(a) * Math.sin(b)); };
/* the globe's turn that puts (lat, lon) at the disc centre, north up: Rx(lat) · Ry(-(90° + lon)) */
const _e = new THREE.Euler(), _q2 = new THREE.Quaternion();
function quatFor(lat, lon, out) {
  out.setFromEuler(_e.set(lat * D2R, 0, 0));
  return out.multiply(_q2.setFromEuler(_e.set(0, -(Math.PI / 2 + lon * D2R), 0)));
}
const Z = new THREE.Vector3(0, 0, 1), XA = new THREE.Vector3(1, 0, 0), YA = new THREE.Vector3(0, 1, 0);
/* a ring only for a fall (a rise or a missing trough never reads as one): its radius from the measured trough */
const fallRing = (e) => (Number.isFinite(e.trough) && e.trough < 0 ? ringRadius(e.trough) || 0 : 0);
/* the turn's curve: a quintic Hermite from speed s0 (in turns per duration) to rest, no jerk at either end; s0 = 0 is the
   quintic smootherstep (peak 1.875 x the mean speed); 0 <= s0 <= 2.5 never overshoots, s0 < 0 eases out of a turn the other way */
export function turnCurve(p, s0 = 0) {
  if (!(p > 0)) return 0;
  if (p >= 1) return 1;
  const p3 = p * p * p, p4 = p3 * p, p5 = p4 * p;
  return 10 * p3 - 15 * p4 + 6 * p5 + s0 * (p - 6 * p3 + 8 * p4 - 3 * p5);
}
/* the controls a drag must never start on, and the ground it may start on (the page under the disc, the stage's globe slot) */
const SLOT = '[data-globe-slot], .hx-globe';
const CONTROL = 'a,button,input,textarea,select,label,summary,[role="button"],[role="link"],[role="slider"],[role="tab"],[contenteditable="true"],[tabindex]:not([tabindex="-1"])';

/* createGlobe(canvas, opts) → the globe API of INTERFACES.md, or null without WebGL (the poster stays).
   opts: events [{id, lat, lon, family, trough, title, place, date}] in date order (PF.view(result).shocks.events); frames {hero(),
   stage()} → the disc {cx, cy, r} in CSS px of the viewport (null when there is no such box); view {lat, lon} the first turn;
   still() → true when motion is off (reduced motion, Pause motion, window.EPI_MOTION === false); clock() → ms (tests freeze it);
   onReady(), onLost(isLost), onLayout(name, ms) (after every setLayout), onIgnite(litCount, latestId) (from the frame loop as the
   lights come on); context (a WebGL context already asked for on this canvas); stars (default true); preserve (keep the drawing
   buffer: the poster tool); interactive (default true: drag in the hero, hover or tap a ring). */
export function createGlobe(canvas, opts = {}) {
  const o = { events: [], frames: {}, view: HOME, still: () => false, clock: () => performance.now(), stars: true, interactive: true, ...opts };
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, context: o.context, antialias: true, alpha: true, premultipliedAlpha: true,
      powerPreference: 'default', failIfMajorPerformanceCaveat: true, preserveDrawingBuffer: !!o.preserve });
  } catch (e) { return null; }
  if (!renderer.getContext()) return null;
  const DPR = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(DPR); renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.NoToneMapping;   // the Earth's shader has its own shoulder; the rings keep their exact cyan
  const gl = renderer.getContext(), maxPt = (gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE) || [1, 64])[1];
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(20, 1, 0.05, 200);
  camera.position.set(0, 0, CAMERA_D);
  const globe = new THREE.Group(); scene.add(globe);
  const geos = [], mats = [];
  const keep = (g, m) => { if (g) geos.push(g); if (m) mats.push(m); return [g, m]; };
  let ready = false, lost = false, disposed = false, active = true, raf = 0, W = 0, H = 0;
  const tier = (o.tierWidth || innerWidth) < 768 ? 2048 : 4096;
  /* the map: fetched and decoded off the main thread (createImageBitmap; the bitmap is not flipped, the shader flips v), uploaded
     with its mips in a task of its own before the first frame; an <img> where that path is missing (file://, older browsers) */
  const night = new THREE.Texture();
  night.colorSpace = THREE.SRGBColorSpace; night.anisotropy = renderer.capabilities.getMaxAnisotropy();
  night.wrapS = THREE.RepeatWrapping; night.minFilter = THREE.LinearMipmapLinearFilter; night.magFilter = THREE.LinearFilter;
  const earthU = { night: { value: night }, uFlip: { value: 0 }, uBloom: { value: BLOOM }, uAir: { value: AIR }, uTau: { value: TAU } };
  const url = asset(`./vendor/nasa/black-marble-2016-${tier}.jpg`);
  const failed = () => { if (!disposed) o.onLost && o.onLost(true); };
  const go = () => { if (disposed) return; ready = true; kick(); o.onReady && o.onReady(); };
  const loaded = (img, flip) => {
    if (disposed) { if (img && img.close) img.close(); return; }
    if (flip && strips(img)) return;
    night.image = img; night.flipY = !flip; earthU.uFlip.value = flip ? 1 : 0; night.needsUpdate = true;
    setTimeout(() => {
      if (disposed) return;
      try { renderer.initTexture(night); } catch (e) { /* uploaded with the first frame instead */ }
      go();
    }, 0);
  };
  /* the bitmap goes up in strips of 256 rows, one per task (about 20 ms each instead of one 150 ms upload), into immutable sRGB
     storage, then its mips and sampler state; three binds it for the map (the texture's version stays 0, so three never uploads
     one itself). After a lost context three uploads the kept bitmap the usual way. */
  let glTex = null, bitmap = null;
  function strips(bm) {
    const g2 = renderer.getContext();
    if (typeof WebGL2RenderingContext === 'undefined' || !(g2 instanceof WebGL2RenderingContext)) return false;
    const w = bm.width, h = bm.height, STRIP = 256, tex = g2.createTexture();
    bitmap = bm; glTex = tex; earthU.uFlip.value = 1;
    renderer.state.bindTexture(g2.TEXTURE_2D, tex);
    g2.texStorage2D(g2.TEXTURE_2D, Math.floor(Math.log2(Math.max(w, h))) + 1, g2.SRGB8_ALPHA8, w, h);
    let y = 0;
    const fail = () => { if (disposed) return; glTex = null; g2.deleteTexture(tex); night.image = bm; night.flipY = false; night.needsUpdate = true; setTimeout(go, 0); };
    const finish = () => {
      if (disposed) return;
      renderer.state.bindTexture(g2.TEXTURE_2D, tex);
      g2.generateMipmap(g2.TEXTURE_2D);
      g2.texParameteri(g2.TEXTURE_2D, g2.TEXTURE_MIN_FILTER, g2.LINEAR_MIPMAP_LINEAR); g2.texParameteri(g2.TEXTURE_2D, g2.TEXTURE_MAG_FILTER, g2.LINEAR);
      g2.texParameteri(g2.TEXTURE_2D, g2.TEXTURE_WRAP_S, g2.REPEAT); g2.texParameteri(g2.TEXTURE_2D, g2.TEXTURE_WRAP_T, g2.CLAMP_TO_EDGE);
      const an = renderer.extensions.get('EXT_texture_filter_anisotropic');
      if (an) g2.texParameterf(g2.TEXTURE_2D, an.TEXTURE_MAX_ANISOTROPY_EXT, Math.max(1, renderer.capabilities.getMaxAnisotropy()));
      renderer.properties.get(night).__webglTexture = tex;
      go();
    };
    const next = () => {
      if (disposed) return;
      const sh = Math.min(STRIP, h - y);
      createImageBitmap(bm, 0, y, w, sh, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' }).then((part) => {
        if (disposed) { part.close(); return; }
        renderer.state.bindTexture(g2.TEXTURE_2D, tex);
        g2.pixelStorei(g2.UNPACK_FLIP_Y_WEBGL, false); g2.pixelStorei(g2.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
        g2.pixelStorei(g2.UNPACK_COLORSPACE_CONVERSION_WEBGL, g2.NONE); g2.pixelStorei(g2.UNPACK_ALIGNMENT, 4);
        g2.texSubImage2D(g2.TEXTURE_2D, 0, 0, y, w, sh, g2.RGBA, g2.UNSIGNED_BYTE, part);
        part.close(); y += sh;
        setTimeout(y < h ? next : finish, 0);
      }, fail);
    };
    next();
    return true;
  }
  const viaImg = () => new THREE.ImageLoader().load(url, (img) => loaded(img, false), undefined, failed);
  if (typeof createImageBitmap === 'function' && typeof fetch === 'function' && location.protocol !== 'file:') {
    fetch(url).then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
      .then((b) => createImageBitmap(b, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' }))
      .then((bm) => loaded(bm, true), () => { if (!disposed) viaImg(); });
  } else viaImg();
  const [earthGeo, earthMat] = keep(new THREE.SphereGeometry(1, 192, 96), new THREE.ShaderMaterial({ vertexShader: earthVert, fragmentShader: earthFrag, uniforms: earthU }));
  globe.add(new THREE.Mesh(earthGeo, earthMat));
  const [atmoGeo, atmoMat] = keep(new THREE.SphereGeometry(1.06, 128, 64), new THREE.ShaderMaterial({ vertexShader: atmoVert, fragmentShader: atmoFrag,
    uniforms: { uAir: { value: AIR }, uTau: { value: TAU }, uH: { value: SCALE_H } },
    side: THREE.BackSide, blending: THREE.AdditiveBlending, premultipliedAlpha: true, transparent: true, depthWrite: false }));
  scene.add(new THREE.Mesh(atmoGeo, atmoMat));
  const NS = 1100, sp = new Float32Array(NS * 3); let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < NS; i++) { const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2, s = Math.sqrt(1 - u * u); sp.set([60 * s * Math.cos(th), 60 * u, 60 * s * Math.sin(th)], i * 3); }
  const [starGeo, starMat] = keep(new THREE.BufferGeometry(), new THREE.PointsMaterial({ color: 0x8fa3c8, size: 1.1, sizeAttenuation: false, transparent: true, opacity: .36, depthWrite: false }));
  starGeo.setAttribute('position', new THREE.BufferAttribute(sp, 3));
  if (o.stars) scene.add(new THREE.Points(starGeo, starMat));
  const quad = keep(new THREE.PlaneGeometry(1, 1))[0];

  /* ---- the shocks: state per shock; meshes rebuilt only when the set of ids changes ---- */
  let shocks = [], coreGeo = null, coreMat = null, corePts = null, focus = null, layoutName = 'hero';
  const pos = new THREE.Vector3();
  const same = {};
  function buildShocks(events) {
    for (const k of shocks) { globe.remove(k.ring); k.mat.dispose(); }
    if (corePts) { globe.remove(corePts); coreGeo.dispose(); coreMat.dispose(); }
    const list = (events || []).filter((e) => e && Number.isFinite(e.lat) && Number.isFinite(e.lon));
    for (const key of Object.keys(same)) delete same[key];
    for (const e of list) { const key = `${e.lat.toFixed(1)},${e.lon.toFixed(1)}`; same[key] = (same[key] || 0) + 1; }
    shocks = list.map((e) => {
      const mat = new THREE.ShaderMaterial({ vertexShader: ringVert, fragmentShader: ringFrag, transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, uniforms: { uR: { value: 0 }, uA: { value: 0 } } });
      const ring = new THREE.Mesh(quad, mat); ring.renderOrder = 2;
      toVec(e.lat, e.lon, 1.0015, pos); ring.position.copy(pos); ring.quaternion.setFromUnitVectors(Z, pos.clone().normalize());
      globe.add(ring);
      const rr = fallRing(e), key = `${e.lat.toFixed(1)},${e.lon.toFixed(1)}`;
      return { id: e.id, family: e.family || null, lat: e.lat, lon: e.lon, ring, mat, w: 0.95 / Math.sqrt(same[key]), key,
        title: e.title || null, place: e.place || null, date: e.date || null,
        at: null, rr, rrFrom: rr, rrT0: -1e9, dim: 1, dimFrom: 1, dimTo: 1, dimT0: -1e9 };
    });
    const n = shocks.length, P = new Float32Array(n * 3);
    shocks.forEach((k, i) => { toVec(k.lat, k.lon, 1.002, pos); P.set([pos.x, pos.y, pos.z], i * 3); });
    coreGeo = new THREE.BufferGeometry(); coreGeo.setAttribute('position', new THREE.BufferAttribute(P, 3));
    for (const a of ['aLit', 'aFlash', 'aDim', 'aW']) coreGeo.setAttribute(a, new THREE.BufferAttribute(new Float32Array(n), 1));
    shocks.forEach((k, i) => { coreGeo.attributes.aW.array[i] = k.w; });
    coreMat = new THREE.ShaderMaterial({ vertexShader: coreVert, fragmentShader: coreFrag, transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending, uniforms: { uSize: { value: Math.min(maxPt, 28 * DPR) }, uCore: { value: 3.8 / 28 } } });
    corePts = new THREE.Points(coreGeo, coreMat); corePts.renderOrder = 3; corePts.frustumCulled = false; globe.add(corePts);
  }
  buildShocks(o.events);
  /* the flyTo arrival: one ring that fires at the epicentre and fades */
  const [, pulseMat] = keep(null, new THREE.ShaderMaterial({ vertexShader: ringVert, fragmentShader: ringFrag, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, uniforms: { uR: { value: 0 }, uA: { value: 0 } } }));
  const pulse = new THREE.Mesh(quad, pulseMat); pulse.renderOrder = 2; pulse.visible = false; globe.add(pulse);
  let pulseT0 = -1e9;
  /* the programs compile in parallel while the map downloads (KHR_parallel_shader_compile where there is one): no long task later */
  if (typeof renderer.compileAsync === 'function') renderer.compileAsync(scene, camera).catch(() => { /* compiled with the first frame */ });

  /* ---- motion state: the turn (a quaternion), the zoom of the hero layout, the hero↔stage blend, the reader's drag ---- */
  const orient = quatFor(o.view.lat, o.view.lon, new THREE.Quaternion());
  let fly = null, zoom = 1, pulseAt = null, litCount = -1, hot = null;
  const lay = { k: 0, from: 0, to: 0, t0: -1e9, ms: 1 }, zm = { from: 1, to: 1, t0: -1e9, ms: 1 };   // zm: the hero layout's zoom
  const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
  const done = (ms, value) => new Promise((res) => setTimeout(() => { kick(); res(value); }, Math.max(0, ms)));
  /* the angular velocity (rad/s, world axes), measured frame to frame, so a new turn leaves at the speed the Earth already has */
  const omega = new THREE.Vector3(), prevQ = orient.clone(), _w = new THREE.Vector3(), _dq = new THREE.Quaternion(), _iq = new THREE.Quaternion();
  const _rq = new THREE.Quaternion(), _c = new THREE.Vector3();
  let lastT = -1e9;
  function trackSpin(now) {
    const dt = (now - lastT) / 1000;
    if (dt > 0 && dt < 0.1) {
      _dq.copy(orient).multiply(_iq.copy(prevQ).invert()); if (_dq.w < 0) _dq.set(-_dq.x, -_dq.y, -_dq.z, -_dq.w);
      const s = Math.hypot(_dq.x, _dq.y, _dq.z), k = s > 1e-9 ? 2 * Math.atan2(s, _dq.w) / s / dt : 0;
      omega.lerp(_w.set(_dq.x * k, _dq.y * k, _dq.z * k), 1 - Math.exp(-dt / 0.03));
    } else if (dt >= 0.1) omega.set(0, 0, 0);
    if (dt !== 0) { prevQ.copy(orient); lastT = now; }
  }
  function launchSpeed(q1, ms) {           // the current speed along the new turn, in turns per duration (0: at rest)
    if (o.clock() - lastT > 100 || o.still()) return 0;
    _dq.copy(q1).multiply(_iq.copy(orient).invert()); if (_dq.w < 0) _dq.set(-_dq.x, -_dq.y, -_dq.z, -_dq.w);
    const s = Math.hypot(_dq.x, _dq.y, _dq.z), th = 2 * Math.atan2(s, _dq.w);
    if (th < 1e-3) return 0;
    const along = (omega.x * _dq.x + omega.y * _dq.y + omega.z * _dq.z) / s;
    return Math.max(-1, Math.min(2.5, along * (ms / 1000) / th));
  }
  const centreLat = () => { _c.set(0, 0, 1).applyQuaternion(_iq.copy(orient).invert()); return Math.asin(Math.max(-1, Math.min(1, _c.y))); };
  /* the reader's drag, in radians: tilt about the screen's horizontal axis (from the pointer's y), turn about the Earth's own axis
     (from x); the Earth follows the pointer through a short damping, then coasts and slows after release */
  const drag = { id: null, on: false, coast: false, moved: false, x0: 0, y0: 0, py: 0, r: 1, el: null, hist: [],
    tt: 0, at: 0, tn: 0, an: 0, vt: 0, vn: 0, t: 0 };
  function endDrag() { drag.on = drag.coast = false; drag.id = null; drag.vt = drag.vn = 0; }
  function stepDrag(now) {
    const dt = Math.min(0.05, Math.max(0, (now - drag.t) / 1000)); drag.t = now;
    if (drag.coast) { drag.tt += drag.vt * dt; drag.tn += drag.vn * dt; const d = Math.exp(-dt * 1000 / COAST_MS); drag.vt *= d; drag.vn *= d; }
    const a = o.still() ? 1 : 1 - Math.exp(-dt * 1000 / FOLLOW_MS);
    let dT = (drag.tt - drag.at) * a; const dN = (drag.tn - drag.an) * a;
    const lat = centreLat(), want = Math.max(-LAT_MAX, Math.min(LAT_MAX, lat + dT));
    if (want !== lat + dT) {                    // the tilt limit: the Earth rests there, and answers the moment the pointer turns back
      dT = want - lat; drag.tt = drag.at + dT; drag.vt = 0; if (drag.on) drag.y0 = drag.py - drag.tt * drag.r;
    }
    drag.at += dT; drag.an += dN;
    if (dT) orient.premultiply(_rq.setFromAxisAngle(XA, dT));
    if (dN) orient.multiply(_rq.setFromAxisAngle(YA, dN));
    orient.normalize();
    const settled = Math.abs(drag.tt - drag.at) + Math.abs(drag.tn - drag.an) < 2e-4;
    if (drag.coast && settled && Math.abs(drag.vt) + Math.abs(drag.vn) < 0.05) drag.coast = false;
    return drag.coast || (drag.on && !settled);           // a pointer held still draws nothing; its next move kicks the loop
  }
  function step(now) {
    let busy = false;
    if (fly) {
      const p = clamp01((now - fly.t0) / fly.ms);
      if (fly.sweep) { const e = easeTurn(p); quatFor(mix(fly.sweep[0], fly.sweep[2], e), mix(fly.sweep[1], fly.sweep[3], e), orient); }
      else orient.slerpQuaternions(fly.q0, fly.q1, turnCurve(p, fly.s0));
      if (p >= 1) { if (fly.ring && !o.still()) { pulseAt = fly.to; pulseT0 = now; } fly = null; } else busy = true;
    } else if (drag.on || drag.coast) busy = stepDrag(now) || busy;
    trackSpin(now);
    if (zoom !== zm.to) { const p = clamp01((now - zm.t0) / zm.ms); zoom = p >= 1 ? zm.to : mix(zm.from, zm.to, easeInOut(p)); busy = busy || p < 1; }
    if (lay.k !== lay.to) {
      const p = clamp01((now - lay.t0) / lay.ms);
      lay.k = p >= 1 ? lay.to : mix(lay.from, lay.to, easeInOut(p)); busy = busy || p < 1;
    }
    const A = coreGeo.attributes;
    let lit_n = 0, litAt = -Infinity, litId = null;
    shocks.forEach((k, i) => {
      let lit = 0, flash = 0, grow = 1, ringA = 0;
      if (k.at !== null) {
        const age = now - k.at;
        if (age < 0) busy = true;
        else {
          lit = clamp01(age / 120); flash = Math.exp(-age / 220);
          const p = clamp01(age / RING_MS); grow = 0.6 + 0.4 * easeOut(p);           // the bloom: 0.6 r to r in 600 ms, bright, then settle
          ringA = mix(1.7, 0.58, easeOut(p)); if (p < 1 || flash > 0.01) busy = true;
          lit_n += 1; if (k.at > litAt) { litAt = k.at; litId = k.id; }
        }
      }
      const pd = clamp01((now - k.dimT0) / DIM_MS); k.dim = mix(k.dimFrom, k.dimTo, easeOut(pd)); if (pd < 1) busy = true;
      const pm = clamp01((now - k.rrT0) / MORPH_MS), rr = mix(k.rrFrom, k.rr, easeInOut(pm)); if (pm < 1) busy = true;
      const cur = rr * grow, s = 2 * (Math.max(rr, k.rr) + 0.01), hl = k.id === hot ? 1.9 : 1;   // the ring under the pointer, brighter
      k.ring.scale.setScalar(s); k.mat.uniforms.uR.value = cur / (s / 2);
      k.mat.uniforms.uA.value = cur > 0 ? ringA * k.dim * hl : 0; k.ring.visible = cur > 0 && ringA * k.dim > 0.002;
      A.aLit.array[i] = lit; A.aFlash.array[i] = k.id === hot ? Math.max(flash, 0.45) : flash; A.aDim.array[i] = k.id === hot ? 1 : k.dim;
    });
    A.aLit.needsUpdate = A.aFlash.needsUpdate = A.aDim.needsUpdate = true;
    if (lit_n !== litCount) { litCount = lit_n; try { o.onIgnite && o.onIgnite(lit_n, litId); } catch (e) { console.error('[globe] onIgnite failed', e); } }
    const pa = (now - pulseT0) / PULSE_MS;
    if (pulseAt && pa < 1) {
      toVec(pulseAt.lat, pulseAt.lon, 1.0015, pos); pulse.position.copy(pos); pulse.quaternion.setFromUnitVectors(Z, pos.normalize());
      pulse.scale.setScalar(0.36); pulseMat.uniforms.uR.value = 0.12 + 0.86 * easeOut(clamp01(pa));
      pulseMat.uniforms.uA.value = 0.9 * (1 - clamp01(pa)) ** 1.5; pulse.visible = true; busy = true;
    } else pulse.visible = false;
    starMat.opacity = 0.36 * (1 - lay.k);
    return busy;
  }
  /* the DOM reads (the two boxes) apart from the math, so a frame reads them before step() lets the hero write its counter */
  const boxes = () => [o.frames.hero ? o.frames.hero() : null, o.frames.stage ? o.frames.stage() : null];
  function frameOf([fh, fs]) {
    const base = mixFrame(fh || fs, fs || fh, lay.k);
    return base ? { cx: base.cx, cy: base.cy, r: base.r * mix(zoom, 1, lay.k) } : null;
  }
  const frameNow = () => frameOf(boxes());
  function applyCamera(f, cw = canvas.clientWidth, ch = canvas.clientHeight) {
    const w = Math.max(1, cw), h = Math.max(1, ch);
    if (w !== W || h !== H) { W = w; H = h; renderer.setSize(W, H, false); }
    camera.aspect = W / H; camera.fov = 2 * Math.atan(TAN_A * H / (2 * Math.max(4, f.r))) / D2R;
    camera.setViewOffset(W, H, W / 2 - f.cx, H / 2 - f.cy, W, H); camera.updateProjectionMatrix(); camera.updateMatrixWorld();
    globe.quaternion.copy(orient); globe.updateMatrixWorld(true);
  }
  let frames = 0;
  function render(f, cw, ch) {
    if (lost || !ready || disposed || !f) return;
    applyCamera(f, cw, ch); renderer.render(scene, camera); frames += 1;
  }
  function kick() { if (!raf && active && !lost && !disposed && ready && !document.hidden) raf = requestAnimationFrame(tick); }
  function tick() {
    raf = 0;
    const cw = canvas.clientWidth, ch = canvas.clientHeight, b = boxes();       // every read first, then the writes
    const busy = step(o.clock()); render(frameOf(b), cw, ch); if (busy) kick();
  }
  const onLostEv = (ev) => { ev.preventDefault(); lost = true; if (raf) { cancelAnimationFrame(raf); raf = 0; } o.onLost && o.onLost(true); };
  const onBack = () => { lost = false;
    if (glTex && bitmap) { glTex = null; night.image = bitmap; night.flipY = false; night.needsUpdate = true; }   // the strips died with the old context
    o.onLost && o.onLost(false); kick(); };
  canvas.addEventListener('webglcontextlost', onLostEv);
  canvas.addEventListener('webglcontextrestored', onBack);
  /* a hidden tab draws nothing (the frame loop stops; time-based motion is where it should be on return) */
  const onVis = () => { if (document.hidden) { if (raf) { cancelAnimationFrame(raf); raf = 0; } drag.coast = false; tipHide(true); } else kick(); };
  document.addEventListener('visibilitychange', onVis);

  /* ---- the reader's hand: drag the hero's Earth; hover (or tap) a ring for its name, place and date ---- */
  const v3 = new THREE.Vector3();
  const heroStill = () => layoutName === 'hero' && lay.k === 0 && lay.to === 0;   // the stage keeps its choreography (the thread to the chart)
  const usable = () => ready && !lost && !disposed && active && !document.hidden && canvas.style.visibility !== 'hidden';
  const inDisc = (x, y, f) => Math.hypot(x - f.cx, y - f.cy) <= f.r;
  /* the ground: the page under the disc (an element that holds the canvas or a globe slot, or sits in one), never a control */
  const ground = (t) => t instanceof Element && !t.closest(CONTROL) &&
    (t === canvas || t.contains(canvas) || !!t.closest(SLOT) || !!t.querySelector(SLOT));
  /* the lit ring nearest the pointer: on its stroke (concentric rings at one city each answer on their own circle) or its core */
  function pick(x, y, f, slop) {
    applyCamera(f);
    const b = canvas.getBoundingClientRect(), now = o.clock();
    let best = null, bestS = Infinity, bx = 0, by = 0;
    for (const k of shocks) {
      if (k.at === null || now < k.at) continue;
      toVec(k.lat, k.lon, 1, v3).applyQuaternion(orient);
      if (v3.z < 1 / CAMERA_D + 0.06) continue;                          // the near side, clear of the limb
      v3.project(camera);
      const sx = b.left + (v3.x + 1) / 2 * W, sy = b.top + (1 - v3.y) / 2 * H, d = Math.hypot(x - sx, y - sy), rp = k.rr * f.r;
      if (d > Math.max(rp + 5, 10) + slop) continue;
      const sc = rp > 0 ? Math.min(Math.abs(d - rp), d) : d;
      if (sc < bestS - 0.01 || (Math.abs(sc - bestS) <= 0.01 && best && (k.date || '') > (best.date || ''))) { best = k; bestS = sc; bx = sx; by = sy; }
    }
    return best ? { k: best, x: bx, y: by } : null;
  }
  /* the tooltip: one small panel by the ring (textContent only), above the page, never in the way of the pointer */
  let tip = null, tipK = null, tipT = 0, tipOn = false, curEl = null, hoverRaf = 0, pend = null, tap = null;
  function tipBox() {
    if (tip) return tip;
    tip = document.createElement('div'); tip.setAttribute('role', 'tooltip'); tip.className = 'globe-tip';
    Object.assign(tip.style, { position: 'fixed', left: '0', top: '0', zIndex: '35', pointerEvents: 'none', maxWidth: '18rem',
      padding: '8px 12px', background: 'rgba(0, 0, 0, .86)', border: '1px solid var(--rule, rgba(255, 255, 255, .14))', borderRadius: '4px',
      color: 'var(--ink-2, #A9B2BF)', font: '400 var(--t-small, 14px)/1.4 var(--font-text, system-ui, sans-serif)', opacity: '0',
      visibility: 'hidden', transition: 'opacity 120ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1))' });
    for (const cls of ['globe-tip-t', 'globe-tip-p', 'globe-tip-d', 'globe-tip-n']) {
      const p = document.createElement('p'); p.className = cls; p.style.margin = '0'; tip.append(p);
    }
    Object.assign(tip.children[0].style, { color: 'var(--starlight, #FFFFFF)', fontWeight: '600' });
    tip.children[2].style.fontVariantNumeric = 'tabular-nums';
    document.body.append(tip);
    return tip;
  }
  function tipShow(hit) {
    clearTimeout(tipT);
    const el = tipBox(), k = hit.k;
    if (tipK !== k) {
      const fmt = globalThis.PF && globalThis.PF.fmt, n = same[k.key] || 1;
      el.children[0].textContent = k.title || 'A shock on record';
      el.children[1].textContent = k.place || '';
      el.children[2].textContent = k.date ? (fmt && fmt.date ? fmt.date(k.date) : k.date) : '';
      el.children[3].textContent = n > 1 ? `One of ${n} shocks on record here` : '';
      for (const c of el.children) c.hidden = !c.textContent;
      tipK = k;
    }
    const w = el.offsetWidth, h = el.offsetHeight, gap = 14;
    let x = hit.x + gap, y = hit.y - gap - h;
    if (x + w > innerWidth - 8) x = hit.x - gap - w;
    if (y < 8) y = hit.y + gap;
    el.style.transform = `translate3d(${Math.round(Math.max(8, x))}px, ${Math.round(Math.min(innerHeight - h - 8, y))}px, 0)`;
    el.style.transition = o.still() ? 'none' : 'opacity 120ms var(--ease-out, cubic-bezier(0.23, 1, 0.32, 1))';
    el.style.visibility = 'visible'; el.style.opacity = '1'; tipOn = true;
  }
  function tipHide(now) {
    clearTimeout(tipT);
    const go = () => { if (!tip) return; tip.style.opacity = '0'; tipOn = false; tipK = null;
      tipT = setTimeout(() => { if (tip && !tipOn) tip.style.visibility = 'hidden'; }, 140); };
    if (now) go(); else if (tipOn) tipT = setTimeout(go, 90);       // a short grace: crossing between rings never flickers
    if (hot !== null) { hot = null; kick(); }
  }
  function setHot(hit) {
    const id = hit ? hit.k.id : null;
    if (id !== hot) { hot = id; kick(); }
    if (hit) tipShow(hit); else if (tipOn) tipHide(false);
  }
  function setCursor(c, el) {
    const t = c ? el : null;
    if (curEl && curEl !== t) curEl.style.cursor = '';
    if (t && t.style.cursor !== c) t.style.cursor = c;
    curEl = t;
  }
  function hoverNow() {
    hoverRaf = 0; const p = pend; pend = null;
    if (!p || drag.on) return;
    const f = usable() ? frameNow() : null;
    if (!f || !inDisc(p.x, p.y, f) || !ground(p.t)) { setCursor(''); setHot(null); return; }
    setCursor(heroStill() ? 'grab' : '', p.t);
    setHot(pick(p.x, p.y, f, 0));
  }
  function onDown(ev) {
    if (!ev.isPrimary || ev.button !== 0) return;
    const f = usable() ? frameNow() : null, onIt = !!f && inDisc(ev.clientX, ev.clientY, f) && ground(ev.target);
    if (!onIt) { tap = null; if (tipOn && ev.pointerType !== 'mouse') tipHide(true); return; }
    tap = ev.pointerType === 'mouse' ? null : { id: ev.pointerId, x: ev.clientX, y: ev.clientY };
    drag.on = false; drag.coast = false; drag.moved = false;
    if (!heroStill()) { drag.id = null; return; }
    Object.assign(drag, { id: ev.pointerId, x0: ev.clientX, y0: ev.clientY, py: ev.clientY, r: Math.max(40, f.r), el: ev.target, hist: [[ev.timeStamp, ev.clientX, ev.clientY]] });
  }
  function onMove(ev) {
    if (tap && ev.pointerId === tap.id && Math.hypot(ev.clientX - tap.x, ev.clientY - tap.y) >= DRAG_PX) tap = null;
    if (drag.id !== null && ev.pointerId === drag.id) {
      const dx = ev.clientX - drag.x0, dy = ev.clientY - drag.y0;
      if (!drag.moved) {
        if (Math.hypot(dx, dy) < DRAG_PX) return;
        drag.moved = drag.on = true; fly = null; Object.assign(drag, { tt: 0, at: 0, tn: 0, an: 0, vt: 0, vn: 0, t: o.clock() });
        tipHide(true); setCursor('grabbing', drag.el);
        try { drag.el.setPointerCapture(ev.pointerId); } catch (e) { /* the window still hears it */ }
      }
      drag.tt = dy / drag.r; drag.tn = dx / drag.r; drag.py = ev.clientY;
      const h = drag.hist; h.push([ev.timeStamp, ev.clientX, ev.clientY]); while (h.length > 2 && ev.timeStamp - h[0][0] > 100) h.shift();
      kick(); return;
    }
    if (ev.pointerType !== 'mouse') return;                               // touch: a tap, never a hover
    pend = { x: ev.clientX, y: ev.clientY, t: ev.target };
    if (!hoverRaf) hoverRaf = requestAnimationFrame(hoverNow);
  }
  function onUp(ev) {
    const t = tap; tap = null;
    if (t && t.id === ev.pointerId && ev.type === 'pointerup') {         // a tap (touch, pen): the ring under it, if any
      const f = usable() ? frameNow() : null, hit = f && pick(ev.clientX, ev.clientY, f, 10);
      if (hit) { hot = hit.k.id; kick(); tipShow(hit); } else tipHide(true);
    }
    if (drag.id === null || ev.pointerId !== drag.id) return;
    drag.id = null;
    if (!drag.moved) return;
    const h = drag.hist, a = h[0], b = h[h.length - 1], dt = (b[0] - a[0]) / 1000, fresh = ev.timeStamp - b[0] < 60;
    drag.vn = dt > 0.008 && fresh && ev.type === 'pointerup' ? Math.max(-FLING_MAX, Math.min(FLING_MAX, (b[1] - a[1]) / dt / drag.r)) : 0;
    drag.vt = dt > 0.008 && fresh && ev.type === 'pointerup' ? Math.max(-FLING_MAX, Math.min(FLING_MAX, (b[2] - a[2]) / dt / drag.r)) : 0;
    drag.on = false; drag.coast = !o.still(); drag.t = o.clock();
    if (o.still()) { drag.vt = drag.vn = 0; stepDrag(o.clock()); }
    setCursor('grab', drag.el); kick();
  }
  const noSelect = (ev) => { if (drag.on) ev.preventDefault(); };
  const onScroll = () => { if (tipOn || hot !== null) tipHide(true); };
  const onKey = (ev) => { if (ev.key === 'Escape' && tipOn) tipHide(true); };
  const onOut = (ev) => { if (!ev.relatedTarget) { setCursor(''); if (tipOn) tipHide(false); } };
  const listen = [[window, 'pointerdown', onDown], [window, 'pointermove', onMove], [window, 'pointerup', onUp], [window, 'pointercancel', onUp],
    [window, 'scroll', onScroll], [window, 'keydown', onKey], [document, 'selectstart', noSelect], [document, 'pointerout', onOut]];
  if (o.interactive) for (const [t, n, f] of listen) t.addEventListener(n, f, { passive: n !== 'selectstart' });

  /* ---- the API (INTERFACES.md), plus setEvents / setActive / requestRender / turnTo / sweep for the hero ---- */
  const api = {
    /* turn the globe so (lat, lon) faces the camera: a slerp of the rotation along turnCurve (leaving at the Earth's current speed,
       landing at rest); with the hero layout it also zooms (zoom × the disc radius); on arrival one ring fires there. A turn takes
       the Earth from the reader's hand. Reduced motion: the end state at once, no ring. */
    flyTo(lat, lon, ms = 900, { zoom: z = 1.6, ring = true } = {}) {
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return Promise.resolve(false);
      const q1 = quatFor(lat, lon, new THREE.Quaternion());
      endDrag();
      if (o.still() || !(ms > 0)) { fly = null; orient.copy(q1); zoom = zm.from = zm.to = z; kick(); return Promise.resolve(true); }
      const t0 = o.clock();
      fly = { q0: orient.clone(), q1, t0, ms, ring, to: { lat, lon }, s0: launchSpeed(q1, ms) };
      Object.assign(zm, { from: zoom, to: z, t0, ms });
      kick(); return done(ms, true);
    },
    turnTo(lat, lon, ms = 900) { return api.flyTo(lat, lon, ms, { zoom: 1, ring: false }); },
    /* a turntable turn, north up, along the literal longitudes (from.lon 195 east of to.lon sweeps west past half the world) */
    sweep(from, to, ms = 4600) {
      if (!from || !to || ![from.lat, from.lon, to.lat, to.lon].every(Number.isFinite)) return Promise.resolve(false);
      endDrag();
      if (o.still() || !(ms > 0)) { fly = null; quatFor(to.lat, to.lon, orient); kick(); return Promise.resolve(true); }
      quatFor(from.lat, from.lon, orient);
      fly = { sweep: [from.lat, from.lon, to.lat, to.lon], t0: o.clock(), ms, ring: false, to: { lat: to.lat, lon: to.lon } };
      kick(); return done(ms, true);
    },
    /* the asked family's epicentres stay bright, the others dim to 30 % (null: all bright) */
    focusFamily(family, ms = DIM_MS) {
      focus = family || null; const t0 = o.still() || !(ms > 0) ? -1e9 : o.clock();
      for (const k of shocks) { k.dimFrom = k.dim; k.dimTo = !focus || k.family === focus ? 1 : DIM; k.dimT0 = t0; }
      kick(); return done(t0 < 0 ? 0 : ms, true);
    },
    /* light the shocks in this order, evenly over totalMs (each ring expands for 600 ms, then settles at its trough's radius);
       shocks not in the list stay dark. Reduced motion: all lit at rest at once. */
    igniteAll(orderIds, totalMs = 4000) {
      const ids = Array.isArray(orderIds) ? orderIds : shocks.map((k) => k.id), byId = new Map(shocks.map((k) => [k.id, k]));
      for (const k of shocks) k.at = null;
      if (o.still() || !(totalMs > 0)) { for (const id of ids) if (byId.has(id)) byId.get(id).at = -1e9; kick(); return Promise.resolve(true); }
      const t0 = o.clock();
      for (const { id, at } of ignitionSchedule(ids, totalMs, RING_MS)) if (byId.has(id)) byId.get(id).at = t0 + at;
      kick(); return done(totalMs, true);
    },
    /* the same canvas: "hero" (large, right of centre) or "stage" (small, the left third of #replay); ease-in-out */
    setLayout(name, ms = 700) {
      layoutName = name === 'stage' ? 'stage' : 'hero';
      const to = layoutName === 'stage' ? 1 : 0, instant = o.still() || !(ms > 0);
      if (to === 1) { endDrag(); setCursor(''); }
      tipHide(true);
      if (to === 0 && zm.to !== 1) Object.assign(zm, { from: zoom, to: 1, t0: instant ? -1e9 : o.clock(), ms: ms || 1 });   // the zoom was the stage's beat
      if (instant) { lay.k = lay.from = lay.to = to; } else Object.assign(lay, { from: lay.k, to, t0: o.clock(), ms });
      try { o.onLayout && o.onLayout(layoutName, instant ? 0 : ms); } catch (e) { console.error('[globe] onLayout failed', e); }
      kick(); return instant ? Promise.resolve(true) : done(ms, true);
    },
    /* where (lat, lon) is now, in CSS px of the viewport; visible: on the near side and inside the viewport */
    project(lat, lon) {
      if (!disposed && step(o.clock())) kick();               // the state now, not the last frame's (a leader drawn mid-glide)
      const f = frameNow(); if (!f || !Number.isFinite(lat) || !Number.isFinite(lon)) return { x: 0, y: 0, visible: false };
      applyCamera(f);
      toVec(lat, lon, 1, v3).applyQuaternion(orient);
      const front = v3.z > 1 / CAMERA_D; v3.project(camera);
      const b = canvas.getBoundingClientRect(), x = b.left + (v3.x + 1) / 2 * W, y = b.top + (1 - v3.y) / 2 * H;
      return { x, y, visible: front && x >= 0 && y >= 0 && x <= innerWidth && y <= innerHeight };
    },
    /* a new Result: the rings morph to the new troughs (same shocks), or the shocks are rebuilt (another set) */
    setEvents(events) {
      const list = (events || []).filter((e) => e && Number.isFinite(e.lat) && Number.isFinite(e.lon));
      const sameSet = list.length === shocks.length && list.every((e, i) => shocks[i] && shocks[i].id === e.id);
      tipHide(true);
      if (!sameSet) { const lit = shocks.some((k) => k.at !== null); buildShocks(list); if (lit) for (const k of shocks) k.at = -1e9; api.focusFamily(focus, 0); kick(); return; }
      const t0 = o.still() ? -1e9 : o.clock();
      list.forEach((e, i) => { const k = shocks[i]; const rr = fallRing(e); k.family = e.family || null;
        k.title = e.title || null; k.place = e.place || null; k.date = e.date || null;
        if (rr !== k.rr) { k.rrFrom = k.rr; k.rr = rr; k.rrT0 = t0; } });
      api.focusFamily(focus); kick();
    },
    setActive(on) {
      active = !!on;
      if (active) kick();
      else { if (raf) { cancelAnimationFrame(raf); raf = 0; } drag.coast = false; tipHide(true); setCursor(''); }
    },
    requestRender() { kick(); },
    get layout() { return layoutName; },
    get frames() { return frames; },                      // renders so far (the harness checks the globe sleeps when still)
    get ready() { return ready; },
    get lost() { return lost; },
    dispose() {
      disposed = true; if (raf) cancelAnimationFrame(raf); raf = 0; if (hoverRaf) cancelAnimationFrame(hoverRaf); hoverRaf = 0;
      canvas.removeEventListener('webglcontextlost', onLostEv); canvas.removeEventListener('webglcontextrestored', onBack);
      document.removeEventListener('visibilitychange', onVis);
      if (o.interactive) for (const [t, n, f] of listen) t.removeEventListener(n, f, { passive: n !== 'selectstart' });
      clearTimeout(tipT); if (tip) tip.remove(); tip = null; setCursor('');
      for (const k of shocks) k.mat.dispose();
      if (coreGeo) coreGeo.dispose(); if (coreMat) coreMat.dispose();
      for (const g of geos) g.dispose(); for (const m of mats) m.dispose();
      const img = night.image || bitmap; night.dispose(); if (img && typeof img.close === 'function') img.close();
      if (glTex) { try { renderer.getContext().deleteTexture(glTex); } catch (e) { /* the context is gone */ } glTex = null; }
      renderer.dispose();
    },
  };
  return api;
}
