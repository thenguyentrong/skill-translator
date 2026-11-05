import * as THREE from "./vendor/three.module.min.js";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { RoomEnvironment } from "./vendor/RoomEnvironment.js";
import { RoundedBoxGeometry } from "./vendor/RoundedBoxGeometry.js";
import { toCreasedNormals } from "./vendor/BufferGeometryUtils.js";
import loadMujoco from "./vendor/mujoco.js";
import { LiveRobot, loadRobot, STEPS } from "./sim.js";

const $ = (s) => document.querySelector(s);
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

let scene, camera, renderer, controls, sun, floorMat, tableTop, ring, trail, cubeMesh, bowlMesh, cubeGroup, bowlGroup;
let robot = null, mj = null, bodies = new Map(), sceneRoot;
const trailPts = [], TRAIL = 200;
let quality = { pixelRatio: Math.min(devicePixelRatio, 2), shadows: 2048 };
const lowEnd = /Mobi|Android/i.test(navigator.userAgent) || (navigator.hardwareConcurrency ?? 8) <= 4;
if (lowEnd) quality = { pixelRatio: Math.min(devicePixelRatio, 1.25), shadows: 1024 };
let lastInteraction = -1e9, doneSince = null;
let watching = null;  // the card of an uploaded job while the engine runs it in the watch panel
let opened;
const ready = new Promise((r) => (opened = r));
const TINT = { yellow: 0xf2b705, red: 0xd8412f, orange: 0xe8862a, brown: 0x8a5a33, tan: 0xd2a56d, green: 0x3f9a5a, sage_green: 0x8fae8b, black: 0x2a2c30, white: 0xe9ecef, grey: 0x9aa3ab, gray: 0x9aa3ab, blue: 0x3f7fd0 };

const toThree = (v) => new THREE.Vector3(v[0], v[2], -v[1]);

function materialFor(rgba) {
  const [r, g, b] = rgba;
  const lum = 0.3 * r + 0.6 * g + 0.1 * b;
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color().setRGB(r, g, b, THREE.SRGBColorSpace),
    metalness: lum > 0.5 ? 0.35 : 0.15, roughness: lum > 0.5 ? 0.38 : 0.55, envMapIntensity: 1.1,
  });
}

function buildStudio() {
  const canvas = $("#stage");
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(quality.pixelRatio);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  scene = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  camera = new THREE.PerspectiveCamera(28, 1, 0.05, 40);
  camera.position.copy(toThree([2.55, -1.55, 1.95]));
  controls = new OrbitControls(camera, canvas);
  controls.target.copy(toThree([0.28, 0.0, 0.98]));
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.enablePan = false;
  controls.minDistance = 1.3;
  controls.maxDistance = 5;
  controls.maxPolarAngle = 1.48;
  controls.minPolarAngle = 0.5;
  controls.touches = { ONE: null, TWO: THREE.TOUCH.DOLLY_ROTATE };

  // a soft key light makes a pool on the table; a weak cool rim separates the arm from the backdrop
  sun = new THREE.SpotLight(0xfff1de, 95, 12, 0.5, 0.85, 2);
  sun.position.set(1.5, 4.3, 1.9);
  sun.target.position.copy(toThree([0.32, 0, 0.75]));
  scene.add(sun.target);
  sun.castShadow = true;
  sun.shadow.mapSize.set(quality.shadows, quality.shadows);
  sun.shadow.camera.near = 1.5; sun.shadow.camera.far = 8;
  sun.shadow.bias = -0.0003; sun.shadow.normalBias = 0.02; sun.shadow.radius = 9; sun.shadow.blurSamples = 16;
  scene.add(sun);
  const rim = new THREE.DirectionalLight(0xc6d4ec, 0.55);
  rim.position.set(-2.4, 2.2, -2.2);
  scene.add(rim);

  floorMat = new THREE.MeshStandardMaterial({ roughness: 0.82, metalness: 0, envMapIntensity: 0.25 });
  const floor = new THREE.Mesh(new THREE.CircleGeometry(16, 64), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  scene.fog = new THREE.Fog(0x000000, 5, 12);
  applyTheme();
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

  ring = new THREE.Mesh(new THREE.RingGeometry(0.03, 0.034, 56), new THREE.MeshBasicMaterial({ color: 0xf2b705, side: THREE.DoubleSide, transparent: true, opacity: 0.95 }));
  ring.rotation.x = -Math.PI / 2;
  scene.add(ring);
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL * 3), 3));
  trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ color: 0xf2b705, transparent: true, opacity: 0.55 }));
  trail.frustumCulled = false;
  scene.add(trail);
}

function applyTheme() {
  const bg = new THREE.Color(css("--bg"));
  scene.background = bg;
  scene.fog.color = bg;
  floorMat.color = new THREE.Color(css("--floor"));
  renderer.toneMappingExposure = dark() ? 0.95 : 0.8;
  scene.environmentIntensity = dark() ? 0.32 : 0.6;
  if (tableTop) tableTop.color = new THREE.Color(css("--table"));
}

function buildWorld(model, meta) {
  const m = model;
  sceneRoot = new THREE.Group();
  sceneRoot.rotation.x = -Math.PI / 2;
  scene.add(sceneRoot);
  bodies = new Map();
  const groupFor = (id) => {
    if (!bodies.has(id)) {
      const g = new THREE.Group();
      g.matrixAutoUpdate = true;
      sceneRoot.add(g);
      bodies.set(id, g);
    }
    return bodies.get(id);
  };
  // table
  const tbl = m.body("table").id, top = meta.table_top;
  const metal = new THREE.MeshStandardMaterial({ color: 0x8b9199, metalness: 0.85, roughness: 0.35 });
  tableTop = new THREE.MeshStandardMaterial({ color: css("--table"), roughness: 0.72, metalness: 0, envMapIntensity: 0.5 });
  for (let g = 0; g < m.ngeom; g++) {
    if (m.geom_bodyid[g] !== tbl) continue;
    const s = [m.geom_size[3 * g], m.geom_size[3 * g + 1], m.geom_size[3 * g + 2]];
    const isTop = s[0] > 0.2;
    const geo = isTop ? new RoundedBoxGeometry(2 * s[0], 2 * s[1], 2 * s[2], 3, 0.006) : new THREE.CylinderGeometry(0.018, 0.018, 2 * s[2], 20).rotateX(Math.PI / 2);
    const mesh = new THREE.Mesh(geo, isTop ? tableTop : metal);
    mesh.position.set(m.geom_pos[3 * g], m.geom_pos[3 * g + 1], m.geom_pos[3 * g + 2]);
    mesh.castShadow = mesh.receiveShadow = true;
    groupFor(tbl).add(mesh);
  }
  bowlGroup = groupFor(m.body("bowl").id);
  cubeGroup = groupFor(m.body("cube").id);
  drawObjects(meta);
}

// the bowl is one smooth shell over the physics ring of boxes
function drawObjects(meta) {
  for (const old of [cubeMesh, bowlMesh]) {
    old?.parent?.remove(old);
    old?.geometry.dispose();
    old?.material.dispose();
  }
  const held = meta.card.objects[meta.card.grip.object];
  const into = meta.card.objects[meta.card.success?.container] ?? {};
  const r = meta.bowl_radius + 0.005, w = meta.bowl_wall, lip = Math.min(0.004, w / 3);
  const pts = [[0, 0], [r - lip, 0], [r, lip], [r, w - lip / 2], [r - lip / 2, w], [r - 0.006, w - lip / 2], [r - 0.006, Math.min(0.008, w)], [r - 0.01, Math.min(0.006, w)], [0, Math.min(0.006, w)]].map(([x, y]) => new THREE.Vector2(x, y));
  bowlMesh = new THREE.Mesh(new THREE.LatheGeometry(pts, 72).rotateX(Math.PI / 2), new THREE.MeshStandardMaterial({ color: TINT[into.color] ?? 0xe9ecef, roughness: 0.28, metalness: 0.02 }));
  bowlMesh.castShadow = bowlMesh.receiveShadow = true;
  bowlGroup.add(bowlMesh);
  const [x, y, z] = held.size;
  const geo = held.shape === "sphere" ? new THREE.SphereGeometry(x / 2, 32, 24)
    : held.shape === "cylinder" ? new THREE.CylinderGeometry(x / 2, x / 2, z, 40).rotateX(Math.PI / 2)
      : new RoundedBoxGeometry(x, y, z, 3, 0.09 * Math.min(x, y, z));
  cubeMesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: TINT[held.color] ?? 0xf2b705, roughness: 0.34, metalness: 0.05, emissive: 0x3a2a00, emissiveIntensity: 0.35 }));
  cubeMesh.castShadow = true;
  cubeGroup.add(cubeMesh);
}

async function buildRobot(meta, buffer) {
  const cache = new Map();
  const geos = meta.mesh_table.map((t) => {
    const pos = new Float32Array(buffer.slice(t.v[0], t.v[0] + t.v[1] * 12));
    const idx = new Uint32Array(buffer.slice(t.i[0], t.i[0] + t.i[1] * 4));
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setIndex(new THREE.BufferAttribute(idx, 1));
    return toCreasedNormals(g, 0.75);
  });
  for (const item of meta.geoms) {
    const id = robot.m.body(item.body).id;
    if (!bodies.has(id)) {
      const g = new THREE.Group();
      sceneRoot.add(g);
      bodies.set(id, g);
    }
    let geo;
    if (item.mesh !== undefined) geo = geos[item.mesh];
    else if (item.type === 6) geo = new THREE.BoxGeometry(2 * item.size[0], 2 * item.size[1], 2 * item.size[2]);
    else if (item.type === 5) geo = new THREE.CylinderGeometry(item.size[0], item.size[0], 2 * item.size[1], 24).rotateX(Math.PI / 2);
    else if (item.type === 3) geo = new THREE.CapsuleGeometry(item.size[0], 2 * item.size[1], 6, 16).rotateX(Math.PI / 2);
    else if (item.type === 2) geo = new THREE.SphereGeometry(item.size[0], 20, 14);
    else continue;
    const key = item.rgba.join();
    if (!cache.has(key)) cache.set(key, materialFor(item.rgba));
    const mesh = new THREE.Mesh(geo, cache.get(key));
    mesh.position.fromArray(item.pos);
    mesh.quaternion.set(item.quat[1], item.quat[2], item.quat[3], item.quat[0]);
    mesh.castShadow = mesh.receiveShadow = true;
    bodies.get(id).add(mesh);
  }
}

function syncBodies() {
  const d = robot.d;
  for (const [id, g] of bodies) {
    g.position.set(d.xpos[3 * id], d.xpos[3 * id + 1], d.xpos[3 * id + 2]);
    g.quaternion.set(d.xquat[4 * id + 1], d.xquat[4 * id + 2], d.xquat[4 * id + 3], d.xquat[4 * id]);
  }
}

function syncMarkers() {
  const st = robot.state(), meta = robot.meta;
  const target = ["carry", "lower"].includes(st.step) ? st.bowl : st.cube;
  const visible = st.step !== "done" && st.step !== "open" && st.step !== "retreat";
  ring.visible = visible;
  const p = toThree([target[0], target[1], meta.table_top + 0.0015]);
  ring.position.lerp(p, ring.userData.ready ? 0.35 : 1);
  ring.userData.ready = true;
  ring.scale.setScalar(["carry", "lower"].includes(st.step) ? (meta.bowl_radius + 0.012) / 0.034 : 1);
  trailPts.push(toThree(st.hand));
  if (trailPts.length > TRAIL) trailPts.shift();
  const a = trail.geometry.attributes.position;
  trailPts.forEach((v, i) => a.setXYZ(i, v.x, v.y, v.z));
  a.needsUpdate = true;
  trail.geometry.setDrawRange(0, trailPts.length);
}

const hud = {};
function buildHud() {
  const row = $("#steps");
  row.innerHTML = "";
  for (const s of STEPS) {
    const li = document.createElement("li");
    li.textContent = s;
    li.dataset.step = s;
    row.append(li);
    hud[s] = li;
  }
}

let lastHud = 0;
function syncHud(now) {
  if (now - lastHud < 80) return;
  lastHud = now;
  const st = robot.state();
  const at = STEPS.indexOf(st.step);
  STEPS.forEach((s, i) => {
    hud[s].classList.toggle("now", i === at);
    hud[s].classList.toggle("past", i < at);
  });
  $("#m-dist").textContent = (st.distance * 100).toFixed(1);
  $("#m-grip").textContent = Math.round(st.grip * 100);
  $("#m-speed").textContent = st.speed.toFixed(2);
  $("#m-tries").textContent = st.tries;
  $("#m-rec").textContent = st.recoveries;
  $("#m-done").textContent = st.done;
  const note = st.note || (st.step === "done" ? "The card's test holds: the cube is inside the bowl." : "Drag the cube anywhere. The robot keeps going.");
  $("#note").textContent = note;
  $("#stage-wrap").dataset.step = st.step;
  window.__live = st;
}

function resize() {
  const wrap = $("#stage-wrap"), w = wrap.clientWidth, h = wrap.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  const wide = w > 900 && !watching;
  camera.fov = wide ? 25 : 30;
  if (wide) camera.setViewOffset(w, h, -w * 0.17, -h * 0.02, w, h);
  else camera.clearViewOffset();
  camera.updateProjectionMatrix();
}

// Pointer: grab near the cube to drag it across the table, anywhere else orbits the camera.
function setupPointer() {
  const canvas = renderer.domElement, ray = new THREE.Raycaster(), pointer = new THREE.Vector2();
  const hit = (e, height) => {
    const b = canvas.getBoundingClientRect();
    pointer.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
    ray.setFromCamera(pointer, camera);
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -height), v = new THREE.Vector3();
    return ray.ray.intersectPlane(plane, v) ? [v.x, -v.z, v.y] : null;
  };
  const nearCube = (e) => {
    const m = robot.meta, p = hit(e, m.table_top + m.held_half), c = robot.state().cube;
    return p && Math.hypot(p[0] - c[0], p[1] - c[1]) < 0.075;
  };
  const dragPoint = (e) => {
    const m = robot.meta, z = m.table_top + 0.06, p = hit(e, z);
    if (!p) return null;
    const { table_centre: tc, table_half: th } = m;
    return [Math.min(tc[0] + th[0] - 0.03, Math.max(tc[0] - th[0] + 0.03, p[0])), Math.min(tc[1] + th[1] - 0.03, Math.max(tc[1] - th[1] + 0.03, p[1])), z];
  };
  canvas.addEventListener("pointerdown", (e) => {
    if (!robot || !nearCube(e)) return;
    const p = dragPoint(e);
    if (!p) return;
    e.stopImmediatePropagation();
    controls.enabled = false;
    canvas.setPointerCapture(e.pointerId);
    robot.startDrag(p);
    lastInteraction = performance.now();
    $("#stage-wrap").classList.add("dragging");
  }, { capture: true });
  canvas.addEventListener("pointermove", (e) => {
    if (!robot) return;
    if (robot.drag) {
      const p = dragPoint(e);
      if (p) robot.moveDrag(p);
      lastInteraction = performance.now();
    } else if (e.pointerType === "mouse") {
      $("#stage-wrap").classList.toggle("can-grab", !!nearCube(e));
    }
  });
  const end = () => {
    if (robot?.drag) robot.endDrag();
    controls.enabled = true;
    $("#stage-wrap").classList.remove("dragging");
  };
  // a finger on the cube drags it; anywhere else the page scrolls as usual
  canvas.addEventListener("touchstart", (e) => { if (robot && nearCube(e.touches[0])) e.preventDefault(); }, { passive: false });
  canvas.addEventListener("pointerup", end);
  canvas.addEventListener("pointercancel", end);
  controls.addEventListener("start", () => (lastInteraction = performance.now()));
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); $("#note").textContent = "The graphics context was lost. Reload the page to see the robot again."; });
  window.__cubeScreen = () => {
    const v = toThree(robot.state().cube).project(camera), b = canvas.getBoundingClientRect();
    return [b.left + ((v.x + 1) / 2) * b.width, b.top + ((1 - v.y) / 2) * b.height];
  };
  window.__tableScreen = (x, y) => {
    const v = toThree([x, y, robot.meta.table_top]).project(camera), b = canvas.getBoundingClientRect();
    return [b.left + ((v.x + 1) / 2) * b.width, b.top + ((1 - v.y) / 2) * b.height];
  };
}

// The frame budget decides quality: slow machines lose shadows and resolution, not the robot.
const perf = { t: 0, n: 0, level: 0 };
function watchFrames(ms) {
  perf.t += ms; perf.n++;
  if (perf.n < 90) return;
  const avg = perf.t / perf.n;
  perf.t = perf.n = 0;
  if (avg > 30 && perf.level < 2) {
    perf.level++;
    if (perf.level === 1) { renderer.setPixelRatio(1); sun.shadow.mapSize.set(1024, 1024); sun.shadow.radius = 4; sun.shadow.map?.dispose(); sun.shadow.map = null; }
    if (perf.level === 2) { renderer.shadowMap.enabled = false; renderer.setPixelRatio(0.8); scene.traverse((o) => o.material && (o.material.needsUpdate = true)); }
    resize();
  }
}

let prev = 0, theta = 0, baseAzimuth = null;
function frame(now) {
  requestAnimationFrame(frame);
  const ms = Math.min(50, now - prev || 16);
  prev = now;
  watchFrames(ms);
  if (!robot) return;
  robot.stepPhysics(Math.round((ms / 1000) / robot.m.opt.timestep));
  const st = robot.step;
  if (st === "done" && !robot.drag) {
    doneSince ??= now;
    if (!watching && !reduced && now - doneSince > 3200 && now - lastInteraction > 6000) {
      robot.newLayout();
      trailPts.length = 0;
      doneSince = null;
    }
  } else doneSince = null;
  syncBodies();
  syncMarkers();
  syncHud(now);
  if (!reduced && now - lastInteraction > 5000 && !robot.drag) {
    theta += ms * 0.00008;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.12 * Math.sin(theta * 3);
  } else controls.autoRotate = false;
  controls.update();
  renderer.render(scene, camera);
}

async function loadInto(name) {
  $("#stage-wrap").classList.add("loading");
  const fetchBytes = async (p) => {
    const r = await fetch(p);
    if (!r.ok) throw new Error(`${p}: ${r.status}`);
    return r.arrayBuffer();
  };
  const fetchJson = async (p) => (await fetch(p)).json();
  const { model, meta } = await loadRobot(mj, name, fetchBytes, fetchJson);
  const buffer = await fetchBytes(`models/${name}.bin`);
  robot = null;
  if (sceneRoot) { scene.remove(sceneRoot); sceneRoot.traverse((o) => o.geometry?.dispose?.()); }
  trailPts.length = 0;
  ring.userData.ready = false;
  buildWorld(model, meta);
  const r = new LiveRobot(mj, model, meta);
  robot = r;
  await buildRobot(meta, buffer);
  window.__robot = r;
  if (watching) showJob(watching);
  buildHud();
  resize();
  $("#stage-wrap").classList.remove("loading");
}

function showJob(card) {
  robot.setJob(card);
  drawObjects(robot.meta);
  trailPts.length = 0;
  ring.userData.ready = false;
  doneSince = null;
}

// The one engine on the page: it leaves the header to run an uploaded job in the watch panel, and comes back.
export const engine = {
  ready,
  async open(host, name, card) {
    await ready;
    watching = card;
    host.append($("#stage-wrap"));
    if (robot.meta.name === name) showJob(card);
    else await loadInto(name);
    resize();
  },
  close() {
    if (!watching) return;
    watching = null;
    $(".hero").insertBefore($("#stage-wrap"), $(".hud"));
    showJob(robot.homeCard);
    resize();
  },
  state: () => robot?.state(),
  log: () => robot?.log ?? [],
  knock() { robot.knock(); lastInteraction = performance.now(); },
  again() { robot.newLayout(); trailPts.length = 0; lastInteraction = performance.now(); },
};

async function start() {
  try {
    buildStudio();
    setupPointer();
    new ResizeObserver(resize).observe($("#stage-wrap"));
    resize();
    requestAnimationFrame(frame);
    mj = await loadMujoco({ locateFile: (f) => `vendor/${f}` });
    await loadInto(document.body.dataset.robot || "ur5e");
    opened();
    $("#knock").onclick = () => { robot.knock(); lastInteraction = performance.now(); };
    $("#layout").onclick = () => { robot.newLayout(); trailPts.length = 0; lastInteraction = performance.now(); };
    document.querySelectorAll("[data-load]").forEach((b) => (b.onclick = async () => {
      if (b.getAttribute("aria-pressed") === "true") return;
      document.querySelectorAll("[data-load]").forEach((x) => { x.setAttribute("aria-pressed", x === b); x.disabled = true; });
      await loadInto(b.dataset.load);
      document.querySelectorAll("[data-load]").forEach((x) => (x.disabled = false));
    }));
  } catch (e) {
    console.error(e);
    $("#stage-wrap").classList.add("failed");
    $("#note").textContent = "This browser could not start the simulation. The recorded runs below still work.";
  }
}
start();
