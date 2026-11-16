/* The classic page's globe (frozen copy of web/globe.js before the Replay; web/globe.js is lane U1's). */
// The night Earth for the hero: NASA Black Marble 2016 (public domain) on a sphere, the Result's shocks at their epicentres, each
// with a short light line as long as the trough the default run measured (no trough, no line: never invented).
// Ported from the spike (/tmp/epi_spike/globe.js). One WebGL context; the one rAF loop is app.js's; DPR <= 2; the texture tier
// follows the viewport (4096 desktop, 2048 below 768 px) and loads behind the poster; no per-frame allocation; context loss is
// handled; dispose() frees every geometry, material and texture. The camera sits at a fixed distance (CAMERA_D, shared with
// PF.globeProject in lib.js) so the poster and the SVG rings of the no-WebGL state line up with this render at any size.
import * as THREE from './vendor/three/three.module.min.js';

const D2R = Math.PI / 180;
export const CAMERA_D = 6;
const toVec = (lat, lon, r, out) => { const a = lat * D2R, b = lon * D2R;
  return out.set(r * Math.cos(a) * Math.cos(b), r * Math.sin(a), -r * Math.cos(a) * Math.sin(b)); };
const earthVert = `varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main(){ vUv = uv; vec4 wp = modelMatrix * vec4(position,1.); vP = wp.xyz; vN = normalize(mat3(modelMatrix) * normal);
  gl_Position = projectionMatrix * viewMatrix * wp; }`;
const earthFrag = `uniform sampler2D night; uniform float lights;
varying vec2 vUv; varying vec3 vN; varying vec3 vP;
void main(){
  vec3 n = normalize(vN); vec3 v = normalize(cameraPosition - vP);
  vec3 nc = texture2D(night, vUv).rgb;
  float lum = dot(nc, vec3(.299,.587,.114));
  float cm = smoothstep(.06, .38, lum);
  vec3 city = mix(nc * .42, nc * (1.0 + lights * 1.6) * vec3(1.06, .97, .84), cm);
  float f = pow(1.0 - max(dot(n, v), 0.0), 4.0);
  gl_FragColor = vec4(city + vec3(.20,.42,1.0) * f * .55, 1.0);
  #include <colorspace_fragment>
}`;
const atmoVert = `varying vec3 vN; varying vec3 vP;
void main(){ vec4 wp = modelMatrix * vec4(position,1.); vP = wp.xyz; vN = normalize(mat3(modelMatrix) * normal); gl_Position = projectionMatrix * viewMatrix * wp; }`;
const atmoFrag = `varying vec3 vN; varying vec3 vP;
void main(){ vec3 v = normalize(cameraPosition - vP); float d = -dot(normalize(vN), v);
  float i = pow(smoothstep(0.0, 0.4, d), 1.8) * (1.0 - smoothstep(0.4, 0.95, d)) * .7;
  gl_FragColor = vec4(vec3(.30,.55,1.0) * i, i); }`;
const shockVert = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`;
const shockFrag = `uniform float age; uniform float steady; uniform float vis; varying vec2 vUv;
void main(){
  float r = length(vUv - .5) * 2.0;
  float flash = exp(-age / .22);
  float p = clamp(age / 1.1, 0.0, 1.0);
  float rr = .10 + .90 * (1.0 - pow(1.0 - p, 3.0));
  float ring = smoothstep(.055, 0.0, abs(r - rr)) * (1.0 - p) * (1.0 - p);
  float core = smoothstep(.15, 0.02, r) * (steady + 1.6 * flash);
  float halo = pow(smoothstep(.8, 0.0, r), 2.2) * (.42 * steady + .6 * flash);
  vec3 col = vec3(1.0) * core + vec3(.62, .90, 1.0) * (ring * 1.1 + halo);
  float k = vis * smoothstep(1.0, .92, r);
  gl_FragColor = vec4(col * k, clamp(core + ring + halo, 0.0, 1.0) * k);
}`;

// a short light line rising from the epicentre; its length is the trough the default run measured (the Result)
const spikeVert = `varying float vH; void main(){ vH = uv.y; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`;
const spikeFrag = `uniform float vis; varying float vH;
void main(){ float a = min(1.0, pow(1.0 - vH, 1.1) * 1.35) * vis; vec3 c = mix(vec3(1.0), vec3(.62,.90,1.0), vH);
  gl_FragColor = vec4(c * a, a); }`;
const UP = new THREE.Vector3(0, 1, 0);


/* events: [{lat, lon, trough: number | null}] in date order. Returns null when WebGL is not available (the poster stays). */
export function createGlobe(canvas, events, { onReady, onLost, lon0 = -18, tierWidth = 1440, stars = true, context = undefined } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, context, antialias: true, alpha: false, powerPreference: 'default', failIfMajorPerformanceCaveat: true });
  } catch (e) { return null; }
  if (!renderer.getContext()) return null;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(30, 1, 0.05, 200);
  const tilt = new THREE.Group(), spin = new THREE.Group(); tilt.add(spin); scene.add(tilt);
  const tier = tierWidth < 768 ? 2048 : 4096;
  let dirty = true, lost = false, ready = false;
  const night = new THREE.TextureLoader().load(`vendor/nasa/black-marble-2016-${tier}.jpg`,
    () => { ready = true; dirty = true; onReady && onReady(); }, undefined, () => { onLost && onLost(true); });
  night.colorSpace = THREE.SRGBColorSpace; night.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const earthGeo = new THREE.SphereGeometry(1, 160, 80), atmoGeo = new THREE.SphereGeometry(1.07, 96, 48), plane = new THREE.PlaneGeometry(1, 1);
  const earthMat = new THREE.ShaderMaterial({ vertexShader: earthVert, fragmentShader: earthFrag, uniforms: { night: { value: night }, lights: { value: 1 } } });
  spin.add(new THREE.Mesh(earthGeo, earthMat));
  const atmoMat = new THREE.ShaderMaterial({ vertexShader: atmoVert, fragmentShader: atmoFrag, side: THREE.BackSide,
    blending: THREE.AdditiveBlending, transparent: true, depthWrite: false });
  tilt.add(new THREE.Mesh(atmoGeo, atmoMat));
  const NS = 1400, pos = new Float32Array(NS * 3); let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < NS; i++) { const u = rnd() * 2 - 1, th = rnd() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    pos.set([60 * s * Math.cos(th), 60 * u, 60 * s * Math.sin(th)], i * 3); }
  const starGeo = new THREE.BufferGeometry(); starGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const starMat = new THREE.PointsMaterial({ color: 0x8fa3c8, size: 1.2, sizeAttenuation: false, transparent: true, opacity: .42, depthWrite: false });
  if (stars) scene.add(new THREE.Points(starGeo, starMat));                  // the poster is rendered without them
  const spikeGeo = new THREE.CylinderGeometry(0.0055, 0.009, 1, 8, 1, true); spikeGeo.translate(0, 0.5, 0);
  const near = {}; for (const e of events) { const k = `${e.lat.toFixed(1)},${e.lon.toFixed(1)}`; near[k] = (near[k] || 0) + 1; }
  const mats = [earthMat, atmoMat, starMat];
  const shocks = events.map((e) => {
    const n = near[`${e.lat.toFixed(1)},${e.lon.toFixed(1)}`];
    const mat = new THREE.ShaderMaterial({ vertexShader: shockVert, fragmentShader: shockFrag, transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending, uniforms: { age: { value: 99 }, steady: { value: .95 / Math.sqrt(n) }, vis: { value: 0 } } });
    const m = new THREE.Mesh(plane, mat); m.renderOrder = 2; scene.add(m); mats.push(mat);
    const p = toVec(e.lat, e.lon, 1.0, new THREE.Vector3());
    let spike = null, smat = null, len = 0;
    if (typeof e.trough === 'number' && Number.isFinite(e.trough) && e.trough < 0) {   // a measured fall sets the line; none or a rise, no line
      smat = new THREE.ShaderMaterial({ vertexShader: spikeVert, fragmentShader: spikeFrag, transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, uniforms: { vis: { value: 0 } } });
      spike = new THREE.Mesh(spikeGeo, smat); spike.position.copy(p); spike.quaternion.setFromUnitVectors(UP, p);
      len = Math.min(0.3, 0.02 + 2.0 * Math.abs(e.trough)); spike.scale.set(1, 1e-4, 1); spin.add(spike); mats.push(smat);
    }
    return { m, mat, spike, smat, len, grow: 0, lit: false, p: p.clone().multiplyScalar(1.004), sz: 0.085 + 0.02 * Math.sqrt(n), facing: 0 };
  });
  const view = { lat: 26, cx: 0.5, cy: 0.5, r: 0.3 };
  const wp = new THREE.Vector3(), camDir = new THREE.Vector3();
  let W = 1, H = 1;
  const onLostEv = (ev) => { ev.preventDefault(); lost = true; onLost && onLost(true); };
  const onBack = () => { lost = false; dirty = true; onLost && onLost(false); };
  canvas.addEventListener('webglcontextlost', onLostEv);
  canvas.addEventListener('webglcontextrestored', onBack);
  /* frame: {cx, cy} the disc centre as a share of the canvas, r its radius in px. The camera stays at CAMERA_D; the field of view
     makes the silhouette exactly r px, so every size shows the same perspective as the poster. */
  function resize(w, h, frame) {
    W = Math.max(1, w); H = Math.max(1, h); Object.assign(view, frame);
    renderer.setSize(W, H, false); camera.aspect = W / H;
    const tanA = 1 / Math.sqrt(CAMERA_D * CAMERA_D - 1);
    camera.fov = 2 * Math.atan(tanA * H / (2 * Math.max(8, view.r))) / D2R;
    camera.position.set(0, 0, CAMERA_D);
    camera.setViewOffset(W, H, -(view.cx - 0.5) * W, -(view.cy - 0.5) * H, W, H);
    camera.updateProjectionMatrix(); dirty = true;
  }
  function draw(lon, dt, dLat = 0) {
    if (lost || !ready) return;
    tilt.rotation.x = (view.lat + dLat) * D2R; spin.rotation.y = -(Math.PI / 2 + lon * D2R);
    scene.updateMatrixWorld();
    camDir.copy(camera.position).normalize();
    for (const k of shocks) {
      wp.copy(k.p).applyMatrix4(spin.matrixWorld); k.m.position.copy(wp); k.m.quaternion.copy(camera.quaternion);
      k.facing = wp.normalize().dot(camDir);
      k.m.scale.setScalar(k.sz * (0.55 + 0.45 * Math.max(k.facing, 0)));
      k.mat.uniforms.vis.value = k.lit ? Math.min(1, Math.max(0, (k.facing - 0.06) / 0.22)) : 0;
      k.mat.uniforms.age.value = Math.min(99, k.mat.uniforms.age.value + dt);
      if (k.spike) {
        if (k.lit && k.grow < 1) k.grow = Math.min(1, k.grow + dt / 0.7);
        const g = 1 - Math.pow(1 - k.grow, 3);
        k.spike.scale.set(1, Math.max(1e-4, k.len * g), 1);
        k.smat.uniforms.vis.value = k.lit ? Math.min(1, 0.25 + Math.max(0, k.facing + 0.15)) : 0;
      }
    }
    renderer.render(scene, camera); dirty = false;
  }
  /* light shock i: with its flash and growing line, or at once (reduced motion, Pause motion, a repeat visit) */
  function ignite(i, instant = false) {
    const k = shocks[i]; if (!k) return;
    k.lit = true; if (instant) { k.grow = 1; k.mat.uniforms.age.value = 99; } else k.mat.uniforms.age.value = 0;
    dirty = true;
  }
  function dispose() {
    canvas.removeEventListener('webglcontextlost', onLostEv); canvas.removeEventListener('webglcontextrestored', onBack);
    for (const g of [earthGeo, atmoGeo, plane, starGeo, spikeGeo]) g.dispose();
    for (const m of mats) m.dispose();
    night.dispose(); renderer.dispose();
  }
  return { resize, draw, ignite, dispose, count: shocks.length, get dirty() { return dirty; }, get lost() { return lost; }, get ready() { return ready; } };
}
