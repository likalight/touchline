/* Touchline 3D broadcast view.
   three.js (MIT) + Mesh2Motion/Quaternius CC0 character and animations.
   Reads the same live state as the 2D views (S.pos, S.ball, S.ballZ, S.draws, S.prefs) and adds:
   floodlit stadium, animated players in club kits, a broadcast camera director with goal replays
   and a player cam, LED boards that carry the verified insight, and a crowd that reacts. */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/addons/libs/meshopt_decoder.module.js";
import * as SkeletonUtils from "three/addons/utils/SkeletonUtils.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { SMAAPass } from "three/addons/postprocessing/SMAAPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const S = window.S;
const L = 105, W = 68;
// pitch (x along the touchline, y across) -> world (X right, Y up, Z towards the main camera)
const wx = (x) => x - L / 2, wz = (y) => W / 2 - y;
const qs = new URLSearchParams(location.search);
const LOW = qs.get("gl") === "low" || (navigator.hardwareConcurrency || 8) <= 4;

const canvas = document.getElementById("pitch3d");
const box = document.getElementById("pitchBox");
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance", preserveDrawingBuffer: !!qs.get("capture") });
} catch (e) {
  console.warn("WebGL unavailable, keeping the 2D broadcast view", e);
}

const api = { ready: false };
window.TV3D = api;

if (renderer) init();

function init() {
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, LOW ? 1 : 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0a1520, 140, 320);
  const camera = new THREE.PerspectiveCamera(30, 16 / 9, 0.5, 600);

  /* ---------- sky: deep evening gradient */
  const sky = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: new THREE.Color(0x050b14) }, mid: { value: new THREE.Color(0x10233a) }, glow: { value: new THREE.Color(0x2a4a5e) } },
    vertexShader: "varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }",
    fragmentShader: "uniform vec3 top, mid, glow; varying vec3 vP; void main(){ float h = vP.y; vec3 c = mix(mid, top, smoothstep(0.05, 0.6, h)); c = mix(glow, c, smoothstep(-0.02, 0.12, h)); gl_FragColor = vec4(c,1.); }",
  }));
  scene.add(sky);

  /* ---------- light: four floodlight banks + sky fill */
  scene.add(new THREE.HemisphereLight(0xa9c4dc, 0x1a3324, 0.55));
  const flood = [];
  const banks = [[-70, 48, 55], [70, 48, 55], [-70, 48, -55], [70, 48, -55]];
  banks.forEach(([x, y, z], i) => {
    const d = new THREE.DirectionalLight(0xf3f6ff, i < 2 ? 1.25 : 0.95);
    d.position.set(x, y, z); d.target.position.set(0, 0, 0);
    if (i === 0 || (!LOW && i === 3)) {
      d.castShadow = true;
      d.shadow.mapSize.set(LOW ? 1024 : 2048, LOW ? 1024 : 2048);
      Object.assign(d.shadow.camera, { left: -64, right: 64, top: 44, bottom: -44, near: 10, far: 220 });
      d.shadow.bias = -0.0004; d.shadow.normalBias = 0.02;
      d.shadow.radius = 3;
    }
    scene.add(d, d.target); flood.push(d);
  });

  /* ---------- the pitch: mown stripes, chalk, wear, all in one texture */
  const RUN = 6, TW = 3072, TH = Math.round(TW * (W + 2 * RUN) / (L + 2 * RUN));
  const pc = document.createElement("canvas"); pc.width = TW; pc.height = TH;
  const g = pc.getContext("2d");
  const sx = TW / (L + 2 * RUN), px = (x) => (x + RUN) * sx, py = (y) => (y + RUN) * sx;
  g.fillStyle = "#245f3a"; g.fillRect(0, 0, TW, TH);
  const stripes = 20;
  for (let k = 0; k < stripes; k++) {
    g.fillStyle = k % 2 ? "#2c6d42" : "#25603a";
    g.fillRect(px(k * L / stripes), 0, sx * L / stripes + 1, TH);
  }
  // cross-mow, very faint
  for (let k = 0; k < 12; k++) { g.fillStyle = k % 2 ? "rgba(255,255,255,.025)" : "rgba(0,0,0,.03)"; g.fillRect(0, py(k * W / 12), TW, sx * W / 12 + 1); }
  // grain
  const img = g.getImageData(0, 0, TW, TH), dd = img.data;
  let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < dd.length; i += 4) { const n = (rnd() - 0.5) * 16; dd[i] += n * 0.6; dd[i + 1] += n; dd[i + 2] += n * 0.5; }
  g.putImageData(img, 0, 0);
  // goalmouth and centre wear
  const wear = (x, y, r, a) => { const gr = g.createRadialGradient(px(x), py(y), 0, px(x), py(y), r * sx); gr.addColorStop(0, `rgba(120,110,70,${a})`); gr.addColorStop(1, "rgba(120,110,70,0)"); g.fillStyle = gr; g.fillRect(0, 0, TW, TH); };
  wear(3, W / 2, 5, 0.28); wear(L - 3, W / 2, 5, 0.28); wear(L / 2, W / 2, 6, 0.12);
  g.strokeStyle = "rgba(244,247,240,.92)"; g.lineWidth = 0.12 * sx; g.lineCap = "round";
  const line = (pts) => { g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo(px(x), py(y)) : g.moveTo(px(x), py(y)))); g.stroke(); };
  line([[0, 0], [L, 0], [L, W], [0, W], [0, 0]]); line([[L / 2, 0], [L / 2, W]]);
  g.beginPath(); g.arc(px(L / 2), py(W / 2), 9.15 * sx, 0, Math.PI * 2); g.stroke();
  g.fillStyle = "rgba(244,247,240,.95)";
  const spot = (x, y) => { g.beginPath(); g.arc(px(x), py(y), 0.18 * sx, 0, Math.PI * 2); g.fill(); };
  spot(L / 2, W / 2);
  for (const s of [0, 1]) {
    const xe = s ? L : 0, d = s ? -1 : 1;
    line([[xe, W / 2 - 20.16], [xe + d * 16.5, W / 2 - 20.16], [xe + d * 16.5, W / 2 + 20.16], [xe, W / 2 + 20.16]]);
    line([[xe, W / 2 - 9.16], [xe + d * 5.5, W / 2 - 9.16], [xe + d * 5.5, W / 2 + 9.16], [xe, W / 2 + 9.16]]);
    spot(xe + d * 11, W / 2);
    g.beginPath(); const a0 = Math.acos(5.5 / 9.15);
    if (s) g.arc(px(L - 11), py(W / 2), 9.15 * sx, Math.PI - a0, Math.PI + a0); else g.arc(px(11), py(W / 2), 9.15 * sx, -a0, a0);
    g.stroke();
    for (const c of [0, W]) { g.beginPath(); g.arc(px(xe), py(c), 1 * sx, 0, Math.PI * 2); g.stroke(); }
  }
  const pitchTex = new THREE.CanvasTexture(pc);
  pitchTex.colorSpace = THREE.SRGBColorSpace;
  pitchTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const pitch = new THREE.Mesh(new THREE.PlaneGeometry(L + 2 * RUN, W + 2 * RUN), new THREE.MeshStandardMaterial({ map: pitchTex, roughness: 0.88, metalness: 0 }));
  pitch.rotation.x = -Math.PI / 2; pitch.receiveShadow = true;
  scene.add(pitch);
  // surround: track and concourse
  const apron = new THREE.Mesh(new THREE.PlaneGeometry(190, 140), new THREE.MeshStandardMaterial({ color: 0x15392a, roughness: 1 }));
  apron.rotation.x = -Math.PI / 2; apron.position.y = -0.02; apron.receiveShadow = true; scene.add(apron);

  /* ---------- goals with nets */
  const netC = document.createElement("canvas"); netC.width = netC.height = 64;
  const ng = netC.getContext("2d"); ng.strokeStyle = "rgba(255,255,255,.85)"; ng.lineWidth = 3;
  ng.beginPath(); ng.moveTo(0, 32); ng.lineTo(32, 0); ng.lineTo(64, 32); ng.lineTo(32, 64); ng.closePath(); ng.stroke();
  const netTex = new THREE.CanvasTexture(netC); netTex.wrapS = netTex.wrapT = THREE.RepeatWrapping;
  const postM = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.35, emissive: 0x222222 });
  for (const s of [0, 1]) {
    const gx = s ? L / 2 : -L / 2, back = s ? 2 : -2, grp = new THREE.Group();
    const cyl = (len, x, y, z, rot) => { const m = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, len, 12), postM); m.position.set(x, y, z); if (rot) m.rotation[rot[0]] = rot[1]; m.castShadow = true; grp.add(m); };
    cyl(2.44, gx, 1.22, -3.66); cyl(2.44, gx, 1.22, 3.66); cyl(7.32, gx, 2.44, 0, ["x", Math.PI / 2]);
    cyl(Math.hypot(2.44, 2), gx + back / 2, 1.22, -3.66, ["z", (s ? 1 : -1) * Math.atan2(2, 2.44)]);
    cyl(Math.hypot(2.44, 2), gx + back / 2, 1.22, 3.66, ["z", (s ? 1 : -1) * Math.atan2(2, 2.44)]);
    const nm = (w, h) => { const t = netTex.clone(); t.needsUpdate = true; t.repeat.set(w * 3, h * 3); return new THREE.MeshStandardMaterial({ map: t, transparent: true, alphaTest: 0.3, side: THREE.DoubleSide, roughness: 1, depthWrite: false }); };
    const backNet = new THREE.Mesh(new THREE.PlaneGeometry(7.32, Math.hypot(2.44, 2)), nm(7.32, 3.2));
    backNet.position.set(gx + back / 2, 1.22, 0); backNet.rotation.y = Math.PI / 2; backNet.rotation.x = (s ? -1 : 1) * Math.atan2(2, 2.44); backNet.rotation.order = "YXZ";
    grp.add(backNet);
    const top = new THREE.Mesh(new THREE.PlaneGeometry(1.0, 7.32), nm(1, 7.32)); top.rotation.x = -Math.PI / 2; top.position.set(gx + back * 0.25, 2.44, 0); grp.add(top);
    for (const z of [-3.66, 3.66]) {
      const sh = new THREE.Shape(); sh.moveTo(0, 0); sh.lineTo(back, 0); sh.lineTo(0, 2.44); sh.lineTo(0, 0);
      const side = new THREE.Mesh(new THREE.ShapeGeometry(sh), nm(2, 2.44)); side.position.set(gx, 0, z); grp.add(side);
    }
    scene.add(grp);
  }

  /* ---------- stands, crowd, roof floodlights */
  const standM = new THREE.MeshStandardMaterial({ color: 0x18242c, roughness: 0.9 });
  const seatColors = [0x2a3946, 0x31414e, 0x26323c];
  const crowdGeo = new THREE.BoxGeometry(0.42, 0.62, 0.32); crowdGeo.translate(0, 0.31, 0);
  const crowd = [];
  const homeCol = new THREE.Color(S.meta ? S.meta.home.color : "#1f6feb"), awayCol = new THREE.Color(S.meta ? S.meta.away.color : "#e5484d");
  const palette = [0xd9dccf, 0x2b2f33, 0x5a6168, 0x8c6b52, 0x3b4a5a, 0xb8b2a4];
  function stand(cx, cz, len, rot, rows, fanSide, open = false) {
    const grp = new THREE.Group(); grp.position.set(cx, 0, cz); grp.rotation.y = rot;
    const depth = 0.85, rise = 0.42, start = 6;
    for (let r = 0; r < rows; r++) {
      const step = new THREE.Mesh(new THREE.BoxGeometry(len, rise * (r + 1) + 1.2, depth), new THREE.MeshStandardMaterial({ color: seatColors[r % 3], roughness: 0.95 }));
      step.position.set(0, (rise * (r + 1) + 1.2) / 2, start + r * depth); step.receiveShadow = true; grp.add(step);
    }
    if (!open) {
    const back = new THREE.Mesh(new THREE.BoxGeometry(len + 4, rise * rows + 14, 2), standM);
    back.position.set(0, (rise * rows + 14) / 2, start + rows * depth + 1); grp.add(back);
    // roof with a floodlight strip on its lip
    const roof = new THREE.Mesh(new THREE.BoxGeometry(len + 6, 0.8, rows * depth + 10), new THREE.MeshStandardMaterial({ color: 0x0d151b, roughness: 0.8 }));
    roof.position.set(0, rise * rows + 15, start + rows * depth / 2 - 2); grp.add(roof);
    const strip = new THREE.Mesh(new THREE.BoxGeometry(len * 0.92, 0.35, 0.5), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    strip.material.color.setScalar(6); strip.position.set(0, rise * rows + 14.5, start - 6.5); grp.add(strip);
    }
    // crowd: instanced, one per seat with gaps
    const seats = [];
    for (let r = 0; r < rows; r++) for (let x = -len / 2 + 0.5; x < len / 2 - 0.5; x += 0.62) if (rnd() > (LOW ? 0.55 : 0.18)) seats.push([x + (rnd() - 0.5) * 0.12, rise * (r + 1) + 1.2, start + r * depth + 0.1]);
    const inst = new THREE.InstancedMesh(crowdGeo, new THREE.MeshStandardMaterial({ roughness: 0.85 }), seats.length);
    const m4 = new THREE.Matrix4(), c = new THREE.Color(), phase = new Float32Array(seats.length);
    seats.forEach(([x, y, z], i) => {
      m4.makeTranslation(x, y, z); inst.setMatrixAt(i, m4);
      const fan = fanSide === "home" ? homeCol : fanSide === "away" ? awayCol : (x < 0 ? homeCol : awayCol);
      c.set(rnd() < 0.55 ? fan : palette[(rnd() * palette.length) | 0]).multiplyScalar(0.55 + rnd() * 0.35);
      inst.setColorAt(i, c); phase[i] = rnd() * 6.28;
    });
    inst.geometry = crowdGeo.clone();
    inst.geometry.setAttribute("phase", new THREE.InstancedBufferAttribute(phase, 1));
    inst.material.onBeforeCompile = (sh) => {
      sh.uniforms.uT = crowdU.uT; sh.uniforms.uJump = crowdU.uJump;
      sh.vertexShader = "attribute float phase; uniform float uT; uniform float uJump;\n" + sh.vertexShader.replace("#include <begin_vertex>",
        "#include <begin_vertex>\n transformed.y += 0.04 * sin(uT * 1.7 + phase) + uJump * max(0., sin(uT * 9. + phase)) * 0.55;");
    };
    grp.add(inst); crowd.push(inst);
    scene.add(grp);
    return grp;
  }
  const crowdU = { uT: { value: 0 }, uJump: { value: 0 } };
  stand(0, -(W / 2 + 4), 128, Math.PI, LOW ? 16 : 26, "mixed"); // far main stand, faces the camera
  stand(0, W / 2 + 4, 128, 0, 6, "mixed", true); // near stand: the camera gantry sits in it
  stand(-(L / 2 + 4), 0, 84, -Math.PI / 2, LOW ? 14 : 22, "home");
  stand(L / 2 + 4, 0, 84, Math.PI / 2, LOW ? 14 : 22, "away");

  /* ---------- LED boards: the verified insight runs round the ground */
  const ledC = document.createElement("canvas"); ledC.width = 4096; ledC.height = 64;
  const lg = ledC.getContext("2d");
  const ledTex = new THREE.CanvasTexture(ledC); ledTex.colorSpace = THREE.SRGBColorSpace; ledTex.wrapS = THREE.RepeatWrapping;
  let ledText = "TOUCHLINE  ·  EVERY MOMENT EXPLAINED  ·  CHECKED AGAINST THE MATCH DATA";
  function drawLed(text, accent) {
    lg.fillStyle = "#04100b"; lg.fillRect(0, 0, 4096, 64);
    lg.font = "600 40px Barlow, 'Barlow Condensed', sans-serif"; lg.textBaseline = "middle";
    const unit = `   ${text}   `, w = Math.max(400, lg.measureText(unit).width);
    for (let x = 0, i = 0; x < 4096; x += w, i++) { lg.fillStyle = i % 2 ? "#eef0e8" : (accent || "#f2c14e"); lg.fillText(unit, x, 34); }
    ledTex.needsUpdate = true;
  }
  drawLed(ledText);
  const ledM = new THREE.MeshBasicMaterial({ map: ledTex, toneMapped: false });
  ledM.color.setScalar(1.6);
  const boards = [];
  const addBoard = (len, x, z, ry) => {
    const t = ledTex.clone(); t.needsUpdate = true; t.repeat.set(len / 60, 1);
    const m = new THREE.Mesh(new THREE.BoxGeometry(len, 0.9, 0.12), [standM, standM, standM, standM, new THREE.MeshBasicMaterial({ map: t, toneMapped: false, color: new THREE.Color(1.6, 1.6, 1.6) }), standM]);
    m.position.set(x, 0.45, z); m.rotation.y = ry; scene.add(m); boards.push(t);
  };
  addBoard(L + 6, 0, -(W / 2 + 3.2), 0);
  addBoard(W - 10, -(L / 2 + 3.5), -W / 4 - 3, Math.PI / 2); addBoard(W - 10, L / 2 + 3.5, -W / 4 - 3, -Math.PI / 2);
  addBoard(W - 10, -(L / 2 + 3.5), W / 4 + 3, Math.PI / 2); addBoard(W - 10, L / 2 + 3.5, W / 4 + 3, -Math.PI / 2);

  /* ---------- ball */
  const bc = document.createElement("canvas"); bc.width = 256; bc.height = 128;
  const bg2 = bc.getContext("2d"); bg2.fillStyle = "#f6f7f2"; bg2.fillRect(0, 0, 256, 128);
  bg2.fillStyle = "#1c2a24";
  for (let i = 0; i < 12; i++) { const x = (i % 6) * 44 + (i > 5 ? 22 : 0), y = i > 5 ? 92 : 36; bg2.beginPath(); for (let k = 0; k < 5; k++) { const a = k / 5 * Math.PI * 2; bg2.lineTo(x + 11 * Math.cos(a), y + 11 * Math.sin(a)); } bg2.fill(); }
  const ballTex = new THREE.CanvasTexture(bc); ballTex.colorSpace = THREE.SRGBColorSpace;
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.11, 24, 16), new THREE.MeshStandardMaterial({ map: ballTex, roughness: 0.45 }));
  ball.castShadow = true; scene.add(ball);
  const ballGlow = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.3, 32), new THREE.MeshBasicMaterial({ color: 0xf2c14e, transparent: true, opacity: 0, depthWrite: false }));
  ballGlow.rotation.x = -Math.PI / 2; scene.add(ballGlow);

  /* ---------- players */
  const players = {};
  const REGION = { skin: 0, shirt: 1, shorts: 2, socks: 3, boots: 4 };
  function regionOf(bone) {
    if (/foot|ball/.test(bone)) return REGION.boots;
    if (/calf/.test(bone)) return REGION.socks;
    if (/thigh|pelvis|root/.test(bone)) return REGION.shorts;
    if (/spine|clavicle|upperarm/.test(bone)) return REGION.shirt;
    return REGION.skin;
  }
  const SKIN = [0xf1c7a5, 0xd9a47e, 0xb07a55, 0x8a5a3c, 0x5e3b27, 0xe0b48e];
  function kitFor(pl) {
    const home = pl.team === "home", gk = pl.position === "GK";
    const shirt = gk ? (home ? "#3fd0a8" : "#f2a33a") : pl.color;
    return { shirt: new THREE.Color(shirt), shorts: new THREE.Color(home ? (gk ? "#14332a" : "#f2f4ef") : (gk ? "#3a2408" : "#191c20")), socks: new THREE.Color(gk ? shirt : (home ? pl.color : "#191c20")) };
  }
  function kitMaterial(kit, skin) {
    const m = new THREE.MeshStandardMaterial({ roughness: 0.62, metalness: 0 });
    const u = { uShirt: { value: kit.shirt }, uShorts: { value: kit.shorts }, uSocks: { value: kit.socks }, uSkin: { value: new THREE.Color(skin) }, uHi: { value: 0 } };
    m.userData.u = u;
    m.onBeforeCompile = (sh) => {
      Object.assign(sh.uniforms, u);
      sh.vertexShader = "attribute float region; varying float vRegion;\n" + sh.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\n vRegion = region;");
      sh.fragmentShader = "uniform vec3 uShirt, uShorts, uSocks, uSkin; uniform float uHi; varying float vRegion;\n" + sh.fragmentShader.replace("#include <color_fragment>",
        `#include <color_fragment>
         float rg = floor(vRegion + 0.5);
         vec3 kc = rg < 0.5 ? uSkin : rg < 1.5 ? uShirt : rg < 2.5 ? uShorts : rg < 3.5 ? uSocks : vec3(0.06);
         diffuseColor.rgb = kc;`).replace("#include <emissivemap_fragment>", "#include <emissivemap_fragment>\n totalEmissiveRadiance += uHi * vec3(0.35, 0.27, 0.08);");
    };
    m.customProgramCacheKey = () => "touchline-kit";
    return m;
  }

  let proto = null, clips = {};
  const loader = new GLTFLoader().setMeshoptDecoder(MeshoptDecoder);
  Promise.all([loader.loadAsync("/static/models/player.glb"), loader.loadAsync("/static/models/player-extra.glb")]).then(([a, b]) => {
    proto = a.scene;
    for (const c of [...a.animations, ...b.animations]) {
      c.tracks = c.tracks.filter((t) => !/^root\.position$/.test(t.name)); // keep players on their tracked spot
      clips[c.name] = c;
    }
    // per-vertex kit region: arms by bone (short sleeves), body by height in the bind pose (clean waistband and sock lines)
    proto.updateMatrixWorld(true);
    proto.traverse((o) => {
      if (!o.isSkinnedMesh) return;
      const gm = o.geometry, si = gm.attributes.skinIndex, sw = gm.attributes.skinWeight, pos = gm.attributes.position, n = si.count, reg = new Float32Array(n);
      const names = o.skeleton.bones.map((b) => b.name);
      const v = new THREE.Vector3(), ys = new Float32Array(n);
      let lo = Infinity, hi = -Infinity;
      for (let i = 0; i < n; i++) { v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld); ys[i] = v.y; lo = Math.min(lo, v.y); hi = Math.max(hi, v.y); }
      for (let i = 0; i < n; i++) {
        let best = 0, bw = -1;
        for (let k = 0; k < 4; k++) { const w = sw.getComponent(i, k); if (w > bw) { bw = w; best = si.getComponent(i, k); } }
        const bone = names[best] || "", h = (ys[i] - lo) / (hi - lo);
        if (/hand|index|middle|pinky|ring|thumb|lowerarm/.test(bone)) reg[i] = REGION.skin;
        else if (/upperarm|clavicle/.test(bone)) reg[i] = REGION.shirt;
        else if (h < 0.055) reg[i] = REGION.boots;
        else if (h < 0.29) reg[i] = REGION.socks;
        else if (h < 0.335) reg[i] = REGION.skin;
        else if (h < 0.52) reg[i] = REGION.shorts;
        else if (h < 0.825) reg[i] = REGION.shirt;
        else reg[i] = REGION.skin;
      }
      gm.setAttribute("region", new THREE.BufferAttribute(reg, 1));
      o.castShadow = true; o.frustumCulled = false;
    });
    const bb = new THREE.Box3().setFromObject(proto), h = bb.max.y - bb.min.y;
    proto.userData.scale = 1.82 / h; proto.userData.lift = -bb.min.y * proto.userData.scale;
    api.ready = true;
    document.getElementById("pitchBox").classList.add("gl");
  }).catch((e) => console.warn("3D players failed to load; 2D view stays on", e));

  function makePlayer(pid) {
    const pl = S.players[pid]; if (!pl || !proto) return null;
    const root = new THREE.Group();
    const body = SkeletonUtils.clone(proto);
    body.scale.setScalar(proto.userData.scale * (0.95 + ((pl.number * 37) % 10) / 100));
    body.position.y = proto.userData.lift;
    const mat = kitMaterial(kitFor(pl), SKIN[(pl.number * 7 + (pl.team === "home" ? 1 : 3)) % SKIN.length]);
    body.traverse((o) => { if (o.isSkinnedMesh) { o.material = mat; o.castShadow = true; } });
    root.add(body);
    // focus / favourite ring
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.55, 0.68, 40), new THREE.MeshBasicMaterial({ color: 0xf2c14e, transparent: true, opacity: 0, depthWrite: false, toneMapped: false }));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.03; root.add(ring);
    const mixer = new THREE.AnimationMixer(body);
    const act = {};
    for (const k of ["Idle_A", "Walk", "Jog", "Sprint"]) { if (clips[k]) { act[k] = mixer.clipAction(clips[k]); act[k].play(); act[k].setEffectiveWeight(0); act[k].time = Math.random() * clips[k].duration; } }
    scene.add(root);
    return { pid, pl, root, body, mixer, act, mat, ring, last: null, speed: 0, yaw: pl.team === "home" ? Math.PI / 2 : -Math.PI / 2, oneShot: null };
  }
  function oneShot(P, name, dur = 1.6, fade = 0.2) {
    if (!P || !clips[name]) return;
    if (P.oneShot) P.oneShot.a.fadeOut(0.1);
    const a = P.mixer.clipAction(clips[name]); a.reset(); a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true; a.setEffectiveWeight(1); a.fadeIn(fade); a.play();
    P.oneShot = { a, until: performance.now() + dur * 1000 };
  }

  /* ---------- live graphics on the grass */
  const vizGroup = new THREE.Group(); scene.add(vizGroup);
  const vizCache = new WeakMap();
  const gold = new THREE.Color(0xf2c14e).multiplyScalar(1.25), paper = new THREE.Color(0xeef0e8).multiplyScalar(1.1);
  function ribbon(x1, y1, x2, y2, color, width = 0.35, arc = 0) {
    const pts = []; for (let i = 0; i <= 24; i++) { const t = i / 24; pts.push(new THREE.Vector3(wx(x1 + (x2 - x1) * t), 0.05 + arc * 4 * t * (1 - t), wz(y1 + (y2 - y1) * t))); }
    const curve = new THREE.CatmullRomCurve3(pts);
    return new THREE.Mesh(new THREE.TubeGeometry(curve, 48, width / 2, 8, false), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, toneMapped: false, depthWrite: false }));
  }
  function vizFor(d) {
    if (vizCache.has(d)) return vizCache.get(d);
    const grp = new THREE.Group();
    if ((d.kind === "pass" || d.kind === "evidence") && d.end_x != null) grp.add(ribbon(d.x, d.y, d.end_x, d.end_y, gold, 0.16, Math.hypot(d.end_x - d.x, d.end_y - d.y) > 25 ? 2.2 : 0.1));
    if (d.kind === "shot" && d.end_x != null) {
      grp.add(ribbon(d.x, d.y, d.end_x, d.end_y, paper, 0.18, 1.2));
      const r = 0.8 + (d.xg || 0) * 5;
      const ring = new THREE.Mesh(new THREE.RingGeometry(r - 0.16, r, 64), new THREE.MeshBasicMaterial({ color: gold, transparent: true, opacity: 0.95, toneMapped: false, depthWrite: false }));
      ring.rotation.x = -Math.PI / 2; ring.position.set(wx(d.x), 0.04, wz(d.y)); grp.add(ring);
    }
    vizGroup.add(grp); vizCache.set(d, grp); grp.userData.d = d;
    return grp;
  }

  /* ---------- post-processing */
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1280, 720), 0.55, 0.5, 0.92);
  composer.addPass(bloom);
  if (!LOW) composer.addPass(new SMAAPass());
  composer.addPass(new OutputPass());

  /* ---------- camera director */
  const cam = { mode: "main", tx: 0, tz: 0, until: 0, shot: null, fov: 30 };
  camera.position.set(0, 23, W / 2 + 40);
  function aim(now, dt) {
    const bx = wx(S.ball[0]), bz = wz(S.ball[1]);
    const follow = 1 - Math.pow(0.0015, dt);
    if (cam.mode === "replay" && now > cam.until) cam.mode = "main";
    if (S.camMode === "player" && cam.mode !== "replay") cam.mode = "player";
    if (S.camMode !== "player" && cam.mode === "player") cam.mode = "main";
    if (cam.mode === "main") {
      const tx = Math.max(-L / 2 + 22, Math.min(L / 2 - 22, bx));
      cam.tx += (tx - cam.tx) * follow; cam.tz += ((bz * 0.35 - 2) - cam.tz) * follow;
      const want = 27 - (W / 2 - bz) * 0.06; cam.fov += (want - cam.fov) * follow * 0.5;
      camera.position.set(cam.tx * 0.92, 23, W / 2 + 40);
      camera.lookAt(cam.tx, 0, cam.tz);
    } else if (cam.mode === "player") {
      // isolated camera: a long lens from the gantry, locked on one player (or the ball carrier, with hysteresis)
      let P = players[S.prefs.focus];
      if (!P) {
        if (!cam.iso || now > cam.isoUntil) { const n = nearestToBall(); if (n && n !== cam.iso) { cam.iso = n; cam.isoUntil = now + 3500; } }
        P = cam.iso;
      }
      if (P) {
        const p = P.root.position, k = 1 - Math.pow(0.004, dt);
        const tgt = new THREE.Vector3(p.x, 0.95, p.z);
        cam.look = cam.look ? cam.look.lerp(tgt, k) : tgt;
        const want = new THREE.Vector3(cam.look.x * 0.85, 18, W / 2 + 34);
        camera.position.lerp(want, k);
        camera.lookAt(cam.look);
        const dist = camera.position.distanceTo(cam.look);
        const fovWant = 2 * Math.atan(7.5 / dist) * 180 / Math.PI; // ~15 m of picture height around the player
        cam.fov += (fovWant - cam.fov) * k;
      }
    } else if (cam.mode === "replay") {
      const s = cam.shot, k = Math.min(1, (now - s.t0) / (cam.until - s.t0));
      const a = s.a0 + (s.a1 - s.a0) * k, r = 13 - 3 * k;
      camera.position.set(s.cx + Math.cos(a) * r, 2.2 + 1.6 * k, s.cz + Math.sin(a) * r);
      const P = players[s.pid]; const focus = (P ? P.root.position.clone() : new THREE.Vector3(s.cx, 0, s.cz)).add(new THREE.Vector3(0, 1.0, 0));
      cam.look = cam.look ? cam.look.lerp(focus, 1 - Math.pow(0.002, dt)) : focus;
      camera.lookAt(cam.look); cam.fov += (34 - cam.fov) * 0.1;
    }
    camera.fov = cam.fov; camera.updateProjectionMatrix();
  }
  function nearestToBall() {
    let best = null, bd = 1e9; const bx = wx(S.ball[0]), bz = wz(S.ball[1]);
    for (const P of Object.values(players)) { const d = (P.root.position.x - bx) ** 2 + (P.root.position.z - bz) ** 2; if (d < bd) { bd = d; best = P; } }
    return best;
  }

  /* ---------- size */
  function resize() {
    const r = box.getBoundingClientRect();
    const w = Math.max(320, r.width), h = Math.max(180, r.height);
    renderer.setSize(w, h, false); composer.setSize(w, h);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(box); resize();

  /* ---------- per frame */
  const q = { avg: 1 / 60, at: performance.now(), level: 0 };
  let lastNow = performance.now(), ballRoll = 0, lastBall = null, excite = 0;
  api.render = (now) => {
    const dt = Math.min(0.1, (now - lastNow) / 1000); lastNow = now;
    if (!api.ready) return;
    // adaptive quality: if frames run slow for two seconds, step down resolution, then bloom
    q.avg = q.avg * 0.95 + dt * 0.05;
    if (q.avg > 0.045 && now - q.at > 2000 && q.level < 2) {
      q.level++; q.at = now;
      if (q.level === 1) { renderer.setPixelRatio(1); resize(); }
      if (q.level === 2) { bloom.enabled = false; renderer.shadowMap.enabled = false; }
    }
    crowdU.uT.value = now / 1000;
    excite = Math.max(0, excite - dt * 0.18); crowdU.uJump.value = Math.min(1, excite);
    // players
    for (const [pid, p] of Object.entries(S.pos)) {
      let P = players[pid];
      if (!P) { P = players[pid] = makePlayer(pid); if (!P) continue; P.root.position.set(wx(p[0]), 0, wz(p[1])); }
      const nx = wx(p[0]), nz = wz(p[1]), dx = nx - P.root.position.x, dz = nz - P.root.position.z;
      const inst = Math.hypot(dx, dz) / Math.max(dt, 1e-3);
      P.speed += (Math.min(inst, 9) - P.speed) * (1 - Math.pow(0.02, dt));
      P.root.position.set(nx, 0, nz);
      let yaw = P.yaw;
      if (P.speed > 0.6 && Math.hypot(dx, dz) > 1e-4) yaw = Math.atan2(dx, dz);
      else { const bx = wx(S.ball[0]) - nx, bz = wz(S.ball[1]) - nz; if (Math.hypot(bx, bz) > 0.5) yaw = Math.atan2(bx, bz); }
      let dy = yaw - P.yaw; dy = Math.atan2(Math.sin(dy), Math.cos(dy)); P.yaw += dy * (1 - Math.pow(0.002, dt));
      P.root.rotation.y = P.yaw;
      // locomotion blend
      const s = P.speed, w = { Idle_A: 0, Walk: 0, Jog: 0, Sprint: 0 };
      if (s < 0.5) w.Idle_A = 1; else if (s < 2.2) { const k = (s - 0.5) / 1.7; w.Idle_A = 1 - k; w.Walk = k; }
      else if (s < 5) { const k = (s - 2.2) / 2.8; w.Walk = 1 - k; w.Jog = k; } else { const k = Math.min(1, (s - 5) / 2.5); w.Jog = 1 - k; w.Sprint = k; }
      const shot = P.oneShot && now < P.oneShot.until;
      if (P.oneShot && !shot) { P.oneShot.a.fadeOut(0.3); P.oneShot = null; }
      for (const [k, a] of Object.entries(P.act)) {
        a.setEffectiveWeight(shot ? 0 : w[k]);
        a.timeScale = k === "Walk" ? Math.max(0.6, s / 1.4) : k === "Jog" ? Math.max(0.8, s / 3.6) : k === "Sprint" ? Math.max(0.9, Math.min(1.5, s / 7)) : 1;
      }
      P.mixer.update(dt);
      // focus and favourite rings
      const fav = window.isFav(pid);
      const focus = pid === S.prefs.focus;
      P.ring.material.opacity += ((fav ? 0.95 : 0) - P.ring.material.opacity) * 0.2;
      P.ring.material.color.copy(focus ? gold : paper);
      P.mat.userData.u.uHi.value = focus ? 0.6 : 0;
    }
    // ball
    const bxw = wx(S.ball[0]), bzw = wz(S.ball[1]), by = Math.max(0.11, S.ballZ || 0.11);
    if (lastBall) { const d = Math.hypot(bxw - lastBall[0], bzw - lastBall[1]); ballRoll += d / 0.11; ball.rotation.set(ballRoll, Math.atan2(bxw - lastBall[0], bzw - lastBall[1]), 0, "YXZ"); }
    lastBall = [bxw, bzw];
    ball.position.set(bxw, by, bzw);
    ballGlow.position.set(bxw, 0.03, bzw);
    ballGlow.material.opacity = cam.mode === "main" ? 0.0 : 0;
    // LED boards scroll
    for (const t of boards) t.offset.x = (now / 1000) * 0.02 % 1;
    // graphics
    const live = new Set();
    for (const d of S.draws || []) { const gq = vizFor(d); live.add(gq); const life = (d.until - now) / 1000; gq.traverse((o) => { if (o.material) o.material.opacity = Math.max(0, Math.min(0.8, life / 1.5)); }); }
    for (const gq of [...vizGroup.children]) if (!live.has(gq)) { vizGroup.remove(gq); gq.traverse((o) => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); }); }
    aim(now, dt);
    api.frames = (api.frames || 0) + 1; api.lastNow = Math.round(now);
    composer.render(dt);
  };

  // pitch (x, y, z metres) -> CSS pixels inside the pitch box
  const v3 = new THREE.Vector3();
  api.project = (x, y, z = 0) => {
    v3.set(wx(x), z, wz(y)).project(camera);
    const r = canvas.getBoundingClientRect();
    return [(v3.x + 1) / 2 * r.width, (1 - v3.y) / 2 * r.height, v3.z < 1];
  };

  api.onEvent = (ev) => {
    if (!api.ready) return;
    const P = players[ev.player_id];
    if (ev.etype === "tackle" && P) oneShot(P, "Slide", 1.1, 0.12);
    if (ev.etype === "save") { const gk = Object.values(players).find((q) => q.pl.team === ev.team && q.pl.position === "GK"); if (gk) oneShot(gk, (ev.end_y ?? ev.y ?? 34) > 34 ? "Dodge_left" : "Dodge_right", 1.0, 0.08); }
    if (ev.etype === "goal") {
      excite = 1.6;
      const scorer = P || nearestToBall();
      const fast = Number((document.getElementById("speed") || {}).value || 10) > 20 || S.jumping;
      if (scorer && !fast) { // no replay while fast-forwarding
        oneShot(scorer, "Victory Fist Pump", 4.5);
        for (const q of Object.values(players)) if (q !== scorer && q.pl.team === scorer.pl.team && q.root.position.distanceTo(scorer.root.position) < 22) oneShot(q, Math.random() < 0.5 ? "Victory" : "Victory Fist Pump", 3.5 + Math.random());
        // replay-style orbit around the scorer, then back to the main camera
        const now = performance.now();
        cam.mode = "replay"; cam.until = now + 5200;
        const sp = scorer.root.position, side = sp.x > 0 ? 1 : -1;
        cam.shot = { t0: now, pid: scorer.pid, cx: sp.x, cz: sp.z, a0: side > 0 ? Math.PI * 0.35 : Math.PI * 0.65, a1: side > 0 ? Math.PI * 0.75 : Math.PI * 0.25 };
        cam.look = null;
      }
    }
    if (ev.etype === "card" && P) oneShot(P, "Idle_Subtle", 2.2);
  };
  api.debug = () => ({ frames: api.frames, until: Math.round(cam.until), cam: camera.position.toArray().map((v) => +v.toFixed(1)), mode: cam.mode, look: cam.look && cam.look.toArray().map((v) => +v.toFixed(1)), fov: camera.fov, n: Object.keys(players).length, focus: S.prefs.focus, camMode: S.camMode, sample: Object.values(players).slice(0, 2).map((P) => [P.pid, P.root.position.toArray().map((v) => +v.toFixed(1)), +P.yaw.toFixed(2), +P.speed.toFixed(1)]) });
  api.board = (text, accent) => { ledText = text; drawLed(text.toUpperCase(), accent); };
  api.reset = () => { for (const P of Object.values(players)) { scene.remove(P.root); } for (const k in players) delete players[k]; excite = 0; cam.mode = "main"; };
  api.teams = (meta) => {
    homeCol.set(meta.home.color); awayCol.set(meta.away.color);
  };
}
