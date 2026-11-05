// The live robot: MuJoCo physics plus a loop that reads the card 25 times a second. No DOM, so Node tests run the same code.
// In the browser the cube position comes straight from the simulator, not from cameras.

export const STEPS = ["reach", "descend", "close", "lift", "carry", "lower", "open", "retreat", "done"];

const PHYS_PER_TICK = 20;
const SHAPE = { sphere: 2, cylinder: 5, box: 6 };
const DENSITY = 900;
const GRIP_TIME = 0.4;
const MAX_JOINT_SPEED = 1.5;
const SPEED = { reach: 0.42, descend: 0.16, lift: 0.22, carry: 0.42, lower: 0.16, retreat: 0.24, done: 0.2, wait: 0.2 };

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b, s = 1) => [a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2]];
const norm = (a) => Math.hypot(a[0], a[1], a[2]);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const axis = (spec) => [spec[0] === "+" ? 1 : -1, "xyz".indexOf(spec[1])];

const matMul = (a, b) => {
  const r = new Array(9);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) r[3 * i + j] = a[3 * i] * b[j] + a[3 * i + 1] * b[3 + j] + a[3 * i + 2] * b[6 + j];
  return r;
};
const transpose = (m) => [m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]];

// rotation vector taking `cur` to `des`, world frame
function rotError(des, cur) {
  const e = matMul(des, transpose(cur));
  const v = [e[7] - e[5], e[2] - e[6], e[3] - e[1]];
  const s = 0.5 * norm(v);
  const c = Math.min(1, Math.max(-1, 0.5 * (e[0] + e[4] + e[8] - 1)));
  const angle = Math.atan2(s, c);
  if (s < 1e-6) {
    if (c > 0) return [0, 0, 0];
    const i = [e[0], e[4], e[8]].indexOf(Math.max(e[0], e[4], e[8]));
    const a = [0, 1, 2].map((k) => (k === i ? Math.sqrt(Math.max(0, (e[4 * k] + 1) / 2)) : e[3 * i + k] / (2 * Math.sqrt(Math.max(1e-9, (e[4 * i] + 1) / 2)))));
    return a.map((x) => x * Math.PI);
  }
  return v.map((x) => (x * angle) / (2 * s));
}

function rodrigues(w) {
  const a = norm(w);
  if (a < 1e-9) return [1, 0, 0, 0, 1, 0, 0, 0, 1];
  const [x, y, z] = w.map((v) => v / a);
  const c = Math.cos(a), s = Math.sin(a), t = 1 - c;
  return [t * x * x + c, t * x * y - s * z, t * x * z + s * y, t * x * y + s * z, t * y * y + c, t * y * z - s * x, t * x * z - s * y, t * y * z + s * x, t * z * z + c];
}

function solve(A, b, n) {
  const M = A.slice(), x = b.slice();
  for (let i = 0; i < n; i++) {
    let p = i;
    for (let r = i + 1; r < n; r++) if (Math.abs(M[r * n + i]) > Math.abs(M[p * n + i])) p = r;
    if (p !== i) {
      for (let c = 0; c < n; c++) [M[i * n + c], M[p * n + c]] = [M[p * n + c], M[i * n + c]];
      [x[i], x[p]] = [x[p], x[i]];
    }
    for (let r = i + 1; r < n; r++) {
      const f = M[r * n + i] / M[i * n + i];
      if (!f) continue;
      for (let c = i; c < n; c++) M[r * n + c] -= f * M[i * n + c];
      x[r] -= f * x[i];
    }
  }
  for (let i = n - 1; i >= 0; i--) {
    for (let c = i + 1; c < n; c++) x[i] -= M[i * n + c] * x[c];
    x[i] /= M[i * n + i];
  }
  return x;
}

export class LiveRobot {
  constructor(mj, model, meta) {
    this.mj = mj;
    this.m = model;
    this.meta = meta;
    this.d = new mj.MjData(model);
    this.ik = new mj.MjData(model);
    const m = model;
    this.site = m.site(meta.site).id;
    this.cube = m.body("cube").id;
    this.bowl = m.body("bowl").id;
    const cj = m.jnt("cube").id;
    this.cubeQ = m.jnt_qposadr[cj];
    this.cubeV = m.jnt_dofadr[cj];
    this.acts = meta.acts.map((a) => m.actuator(a).id);
    const joints = meta.joints.map((j) => m.jnt(j).id);
    this.qadr = joints.map((j) => m.jnt_qposadr[j]);
    this.dof = joints.map((j) => m.jnt_dofadr[j]);
    this.lim = joints.map((j) => [m.jnt_range[2 * j], m.jnt_range[2 * j + 1], m.jnt_limited[j]]);
    this.gripActs = meta.grip_acts.map((a) => m.actuator(a).id);
    this.kp = this.acts.map((a) => m.actuator_gainprm[10 * a]);
    this.homeQ = Object.entries(meta.home).map(([k, v]) => [m.jnt_qposadr[m.jnt(k).id], v]);
    this.homeArm = joints.map((j, i) => meta.home[meta.joints[i]] ?? 0);
    this.jacp = new mj.DoubleBuffer(3 * m.nv);
    this.jacr = new mj.DoubleBuffer(3 * m.nv);
    this.tiltDown = [0, 0, -1];
    this.card = meta.card;
    this.height = Object.fromEntries(this.card.steps.filter((s) => s.height).map((s) => [s.do, s.height]));
    this.word = "cube";
    this.into = "bowl";
    this.homeCard = meta.card;
    this.setDepth();
    this.resetCounters();
    this.reset();
  }

  setDepth() {
    const [sa, ia] = axis(this.meta.approach);
    const depth = Math.min(this.meta.grip_depth, this.meta.held_half - this.meta.tip_reach - 0.003);
    this.offset = this.meta.grip_offset.slice();
    this.offset[ia] -= sa * depth;
  }

  // Puts this card's objects into the compiled scene. MuJoCo reads these arrays at every step, so no new model is needed.
  // A square bin stays a ring here: the browser scene has one kind of container.
  setJob(card) {
    const { m, mj } = this;
    const name = card.grip.object, h = card.objects[name];
    const into = card.success?.container ?? Object.keys(card.objects).find((k) => k !== name), c = card.objects[into];
    const [sx, sy, sz] = h.size, b = this.cube, g = m.body_geomadr[b];
    const r = sx / 2;
    const size = h.shape === "sphere" ? [r, 0, 0] : h.shape === "cylinder" ? [r, sz / 2, 0] : [sx / 2, sy / 2, sz / 2];
    const volume = h.shape === "sphere" ? (Math.PI / 6) * sx ** 3 : h.shape === "cylinder" ? (Math.PI / 4) * sx ** 2 * sz : sx * sy * sz;
    const mass = card.needs?.mass_kg || Math.max(0.02, DENSITY * volume);
    m.geom_type[g] = SHAPE[h.shape] ?? 6;
    const reach = h.shape === "sphere" ? r : h.shape === "cylinder" ? Math.hypot(r, sz / 2) : Math.hypot(sx, sy, sz) / 2;
    size.forEach((v, i) => (m.geom_size[3 * g + i] = v));
    m.geom_rbound[g] = reach;
    const box = (i, half) => { for (let k = 0; k < 3; k++) { m.geom_aabb[6 * i + k] = 0; m.geom_aabb[6 * i + 3 + k] = half[k]; } };
    box(g, h.shape === "box" ? size : [reach, reach, reach]);
    m.body_mass[b] = mass;
    const I = h.shape === "sphere" ? [0.4 * mass * r * r, 0.4 * mass * r * r, 0.4 * mass * r * r]
      : h.shape === "cylinder" ? [mass * (3 * r * r + sz * sz) / 12, mass * (3 * r * r + sz * sz) / 12, 0.5 * mass * r * r]
        : [mass * (sy * sy + sz * sz) / 12, mass * (sx * sx + sz * sz) / 12, mass * (sx * sx + sy * sy) / 12];
    I.forEach((v, i) => (m.body_inertia[3 * b + i] = v));

    const radius = c.inner_radius, wall = c.wall_height, bowl = this.bowl, first = m.body_geomadr[bowl], n = m.body_geomnum[bowl] - 1;
    m.geom_size[3 * first] = radius + 0.005;
    m.geom_rbound[first] = radius + 0.006;
    box(first, [radius + 0.005, radius + 0.005, 0.003]);
    const half = (radius + 0.005) * Math.tan(Math.PI / n);
    for (let i = 0; i < n; i++) {
      const k = first + 1 + i, a = (2 * Math.PI * i) / n;
      m.geom_pos[3 * k] = (radius + 0.003) * Math.cos(a);
      m.geom_pos[3 * k + 1] = (radius + 0.003) * Math.sin(a);
      m.geom_pos[3 * k + 2] = wall / 2;
      m.geom_size[3 * k + 1] = half;
      m.geom_size[3 * k + 2] = wall / 2;
      m.geom_rbound[k] = Math.hypot(0.003, half, wall / 2);
      box(k, [Math.hypot(0.003, half), Math.hypot(0.003, half), wall / 2]);
    }
    for (const body of [b, bowl]) {  // bounding boxes a little too big only cost time
      const wide = body === b ? reach : radius + 0.02 + wall;
      for (let i = m.body_bvhadr[body], end = i + m.body_bvhnum[body]; i < end; i++) {
        for (let k = 0; k < 3; k++) { m.bvh_aabb[6 * i + k] = 0; m.bvh_aabb[6 * i + 3 + k] = wide; }
      }
    }
    mj.mj_setConst(m, this.d);
    this.meta = { ...this.meta, held_half: sz / 2, held_width: card.grip.width ?? sx, bowl_radius: radius, bowl_wall: wall, card };
    this.card = card;
    this.height = Object.fromEntries(card.steps.filter((x) => x.height).map((x) => [x.do, x.height]));
    this.round = h.shape !== "box";
    this.narrow = h.shape === "box" && Math.abs(sx - sy) > 0.002 ? (sx < sy ? 0 : Math.PI / 2) : null;
    this.word = name.replace(/_/g, " ");
    this.into = into.replace(/_/g, " ");
    this.setDepth();
    this.resetCounters();
    this.reset();
  }

  resetCounters() {
    this.tries = 0;
    this.recoveries = 0;
    this.done = 0;
    this.log = [];
  }

  // A cube and bowl spot from the same rule as the Python sampler: 35-75 % of the reach, 45 degrees to each side.
  layout(rng = Math.random) {
    const { origin, reach, footprint, bowl_radius: br, held_half: hh } = this.meta;
    const held = Math.SQRT2 * hh;
    const point = (clear) => {
      const near = Math.max(0.35 * reach, footprint + clear), far = 0.75 * reach;
      for (let i = 0; i < 400; i++) {
        const r = near + rng() * (far - near), a = (rng() - 0.5) * (Math.PI / 2);
        const xy = [origin[0] + r * Math.cos(a), origin[1] + r * Math.sin(a)];
        if (this.onTable(xy, clear)) return xy;
      }
      return [0.4, 0];
    };
    for (let t = 0; t < 200; t++) {
      const cube = point(held + 0.02), bowl = point(br + 0.026);
      if (Math.hypot(cube[0] - bowl[0], cube[1] - bowl[1]) >= Math.max(0.12, br + held + 0.025)) return { cube, bowl, yaw: rng() * (Math.PI / 2) };
    }
    return { cube: [0.35, 0.2], bowl: [0.35, -0.2], yaw: 0 };
  }

  onTable(xy, clear = 0) {
    const { table_centre: c, table_half: h } = this.meta;
    return Math.abs(xy[0] - c[0]) <= h[0] - clear && Math.abs(xy[1] - c[1]) <= h[1] - clear;
  }

  placeCube(xy, yaw) {
    const q = this.cubeQ, d = this.d;
    d.qpos[q] = xy[0];
    d.qpos[q + 1] = xy[1];
    d.qpos[q + 2] = this.meta.table_top + this.meta.held_half + 0.001;
    d.qpos[q + 3] = Math.cos(yaw / 2);
    d.qpos[q + 4] = 0;
    d.qpos[q + 5] = 0;
    d.qpos[q + 6] = Math.sin(yaw / 2);
    for (let i = 0; i < 6; i++) d.qvel[this.cubeV + i] = 0;
  }

  placeBowl(xy) {
    this.m.body_pos[3 * this.bowl] = xy[0];
    this.m.body_pos[3 * this.bowl + 1] = xy[1];
    this.m.body_pos[3 * this.bowl + 2] = this.meta.table_top;
  }

  reset(l = this.layout()) {
    const { mj, m, d } = this;
    mj.mj_resetData(m, d);
    for (const [adr, v] of this.homeQ) d.qpos[adr] = v;
    this.placeBowl(l.bowl);
    this.placeCube(l.cube, l.yaw);
    this.qt = this.qadr.map((a) => d.qpos[a]);
    this.acts.forEach((a, i) => (d.ctrl[a] = this.qt[i]));
    this.grip = 0;
    this.setGrip(0);
    mj.mj_forward(m, d);
    this.pt = this.handPos();
    this.Rt = this.handRot();
    this.vel = [0, 0, 0];
    this.step = "reach";
    this.timer = 0;
    this.ticks = 0;
    this.lastAim = null;
    this.drag = null;
    this.hit = 0;
    this.note = "";
    this.disturbed = false;
    this.startTime = d.time;
    this.taskTime = null;
    this.goal = this.pt;
    this.yaw = null;
    this.lostAt = -10;
  }

  newLayout() {
    const l = this.layout();
    this.placeBowl(l.bowl);
    this.placeCube(l.cube, l.yaw);
    this.mj.mj_forward(this.m, this.d);
    this.goStep("reach");
    this.startTime = this.d.time;
    this.taskTime = null;
    this.note = "";
  }

  setGrip(f) {
    const { open, closed } = this.meta;
    this.gripActs.forEach((a, i) => (this.d.ctrl[a] = open[i] + f * (closed[i] - open[i])));
  }

  handPos() {
    const v = this.d.site_xpos, s = 3 * this.site;
    return [v[s], v[s + 1], v[s + 2]];
  }

  handRot() {
    const v = this.d.site_xmat, s = 9 * this.site;
    return Array.from(v.slice(s, s + 9));
  }

  cubePos() {
    const v = this.d.xpos, s = 3 * this.cube;
    return [v[s], v[s + 1], v[s + 2]];
  }

  cubeSpeed() {
    const v = this.d.qvel, s = this.cubeV;
    return Math.hypot(v[s], v[s + 1], v[s + 2]);
  }

  // the cube's turn about the vertical, from whichever face ended up on top
  cubeYaw() {
    if (this.round) return 0;
    const x = this.d.xmat, s = 9 * this.cube;
    const R = [0, 1, 2].map((c) => [x[s + c], x[s + 3 + c], x[s + 6 + c]]);
    const up = R.reduce((b, a, i) => (Math.abs(a[2]) > Math.abs(R[b][2]) ? i : b), 0);
    const side = R[(up + 1) % 3];
    return Math.atan2(side[1], side[0]);
  }

  bowlPos() {
    const v = this.m.body_pos, s = 3 * this.bowl;
    return [v[s], v[s + 1], v[s + 2]];
  }

  // the card's success test, the same one the Python side uses
  cubeInBowl() {
    const c = this.cubePos(), b = this.bowlPos(), { bowl_radius: r, bowl_wall: w, held_half: hh, held_width, table_top: top } = this.meta;
    const inner = r - held_width / 2;
    const off = Math.hypot(c[0] - b[0], c[1] - b[1]);
    return off < inner + 0.005 && c[2] < top + Math.max(w, 0.021 + hh) && this.cubeSpeed() < 0.05;
  }

  rotation(closingYaw) {
    const [sa, ia] = axis(this.meta.approach), [sc, ic] = axis(this.meta.closing);
    const a = this.tiltDown.map((v) => sa * v);
    const c = [Math.cos(closingYaw) * sc, Math.sin(closingYaw) * sc, 0];
    const cols = [null, null, null];
    cols[ia] = a;
    cols[ic] = c;
    const k = 3 - ia - ic;
    cols[k] = cross(cols[(k + 1) % 3], cols[(k + 2) % 3]);
    return [cols[0][0], cols[1][0], cols[2][0], cols[0][1], cols[1][1], cols[2][1], cols[0][2], cols[1][2], cols[2][2]];
  }

  // of the four grips on a cube, the one that needs the least wrist turn
  gripRotation(yaw) {
    let best = null, bestT = -9;
    const base = yaw + (this.narrow ?? 0), step = this.narrow === null || this.narrow === undefined ? 1 : 2;
    for (let k = 0; k < 4; k += step) {
      const r = this.rotation(base + (k * Math.PI) / 2);
      const t = r.reduce((sum, v, i) => sum + v * this.Rt[i], 0);
      if (t > bestT) (best = r), (bestT = t);
    }
    return best;
  }

  toSite(p, R) {
    const o = this.offset;
    return [p[0] - (R[0] * o[0] + R[1] * o[1] + R[2] * o[2]), p[1] - (R[3] * o[0] + R[4] * o[1] + R[5] * o[2]), p[2] - (R[6] * o[0] + R[7] * o[1] + R[8] * o[2])];
  }

  goStep(s) {
    if (s !== this.step) {
      this.log.push({ t: this.d.time, step: s });
      if (this.log.length > 40) this.log.shift();
    }
    this.step = s;
    this.timer = 0;
  }

  recover(why) {
    this.recoveries++;
    this.note = why;
    this.lostAt = this.d.time;
    this.goStep("reach");
  }

  reachable(c) {
    const { origin, reach, footprint } = this.meta;
    const r = Math.hypot(c[0] - origin[0], c[1] - origin[1]);
    return r < 0.84 * reach && r > Math.max(0.2, footprint + 0.02);
  }

  // One control tick: read the state, decide which card step is true, move the hand's target.
  tick() {
    const dt = (PHYS_PER_TICK * this.m.opt.timestep);
    const c = this.cubePos(), h = this.handPos(), meta = this.meta;
    const top = meta.table_top, hh = meta.held_half;
    const onCube = norm(sub(c, this.toSiteCenter(h))) < Math.max(0.032, 0.75 * hh + 0.02);
    this.timer += dt;
    const graspZ = Math.max(c[2], top + hh, top + meta.tip_reach + 0.003);
    const hover = top + hh + 0.1;
    const moved = this.lastAim ? Math.hypot(c[0] - this.lastAim[0], c[1] - this.lastAim[1]) : 0;
    let goal = this.goal, R = this.Rt, speed = SPEED[this.step] ?? 0.3;

    if (c[2] < top - 0.04) {
      this.note = `The ${this.word} fell off the table. A new one is placed.`;
      const l = this.layout();
      this.placeCube(l.cube, l.yaw);
      this.goStep("reach");
      return this.track(goal, R, speed, dt);
    }

    switch (this.step) {
      case "reach": {
        this.grip = Math.max(0, this.grip - dt / GRIP_TIME);
        if (this.cubeInBowl() && !this.drag) {
          this.goStep("done");
          break;
        }
        const can = this.reachable(c);
        this.note = can ? (this.d.time - this.lostAt < 1.5 ? this.note : "") : `The ${this.word} is out of my reach.`;
        this.outFor = can || this.drag ? 0 : (this.outFor ?? 0) + dt;
        if (this.outFor > 3.5) {
          const l = this.layout();
          this.placeCube(l.cube, l.yaw);
          this.outFor = 0;
          this.note = `Out of reach for too long. A new ${this.word} is placed.`;
          this.lostAt = this.d.time;
        }
        R = this.gripRotation(this.cubeYaw());
        const above = can ? [c[0], c[1], hover] : [h[0], h[1], hover];
        const far = Math.hypot(above[0] - this.pt[0], above[1] - this.pt[1]);
        goal = this.pt[2] < hover - 0.02 && far > 0.03 ? [this.pt[0], this.pt[1], hover] : above;
        goal = this.toSite(goal, R);
        const near = norm(sub(goal, this.pt)) < 0.004 && norm(sub(goal, h)) < 0.012 && norm(rotError(R, this.handRot())) < 0.06;
        if (can && near && !this.drag && this.cubeSpeed() < 0.04 && this.grip === 0) {
          if (this.timer > 0.2) {
            this.tries++;
            this.lastAim = c;
            this.goStep("descend");
          }
        } else {
          this.timer = 0;
        }
        break;
      }
      case "descend": {
        R = this.gripRotation(this.cubeYaw());
        goal = this.toSite([c[0], c[1], graspZ], R);
        if (moved > 0.015 || this.drag || this.cubeSpeed() > 0.1) {
          this.recover(`The ${this.word} moved. Aiming again.`);
          break;
        }
        if (this.timer > 3) {
          this.recover("That spot is hard to reach. Trying again.");
          break;
        }
        if (norm(sub(goal, this.pt)) < 0.002 && norm(sub(goal, h)) < 0.006) this.goStep("close");
        break;
      }
      case "close": {
        goal = this.pt;
        this.grip = Math.min(1, this.grip + dt / GRIP_TIME);
        if (moved > 0.02 && this.grip < 0.5) {
          this.recover(`The ${this.word} moved. Aiming again.`);
          break;
        }
        if (this.grip >= 1 && this.timer > GRIP_TIME + 0.3) {
          if (onCube) this.goStep("lift");
          else this.recover(`Missed the ${this.word}. Trying again.`);
        }
        break;
      }
      case "lift":
      case "carry":
      case "lower": {
        if (!onCube) {
          this.recover(`I lost the ${this.word}. Going back for it.`);
          break;
        }
        const b = this.bowlPos();
        if (this.step === "lift") {
          const z = graspZ + (this.height.lift ?? 0.1);
          this.liftZ = this.liftZ && this.timer > 0.04 ? this.liftZ : Math.max(z, h[2] + 0.1);
          goal = this.toSite([this.pt[0], this.pt[1], this.liftZ], R);
          goal = [this.pt[0], this.pt[1], goal[2]];
          if (Math.abs(goal[2] - h[2]) < 0.01) this.goStep("carry");
        } else if (this.step === "carry") {
          const z = Math.max(this.liftZ ?? 0, top + meta.bowl_wall + hh + 0.04);
          goal = this.toSite([b[0], b[1], z], R);
          this.carryTime = this.timer > 0.05 ? (this.carryTime ?? 0) + dt : 0;
          if (this.carryTime > 7) {
            this.grip = 0;
            this.recover(`I could not get above the ${this.into}. Trying again.`);
            break;
          }
          if (norm(sub(goal, this.pt)) > 0.004 || norm(sub(goal, h)) > 0.012) this.settled = 0;
          else this.settled = (this.settled ?? 0) + dt;
          if (this.settled > 0.25) (this.settled = 0), this.goStep("lower");
        } else {
          goal = this.toSite([b[0], b[1], top + meta.bowl_wall + hh + 0.02], R);
          if (norm(sub(goal, this.pt)) < 0.002 && norm(sub(goal, h)) < 0.01) this.goStep("open");
        }
        break;
      }
      case "open": {
        goal = this.pt;
        this.grip = Math.max(0, this.grip - dt / GRIP_TIME);
        if (this.grip <= 0 && this.timer > GRIP_TIME + 0.25) {
          this.retreatZ = this.pt[2] + (this.height.retreat ?? 0.08);
          this.goStep("retreat");
        }
        break;
      }
      case "retreat": {
        goal = [this.pt[0], this.pt[1], this.retreatZ];
        if (Math.abs(goal[2] - h[2]) < 0.012) {
          if (this.cubeInBowl()) {
            this.done++;
            this.taskTime = this.d.time - this.startTime;
            this.goStep("done");
          } else if (this.timer > 1.2) {
            this.recover(`The ${this.word} is not in the ${this.into} yet.`);
          }
        }
        break;
      }
      case "done": {
        goal = this.pt;
        if (!this.cubeInBowl() && this.timer > 0.2) {
          if (this.drag || this.cubeSpeed() < 0.3) this.recover(`The ${this.word} left the ${this.into}. Going back for it.`);
        } else if (this.cubeInBowl()) {
          this.timer = 0.21;
        }
        break;
      }
    }
    this.goal = goal;
    return this.track(goal, R, speed, dt);
  }

  toSiteCenter(h) {
    return h;
  }

  // Move the hand's target towards the goal with a speed and an acceleration limit, then one IK step.
  track(goal, R, speed, dt) {
    const e = sub(goal, this.pt), dist = norm(e);
    const v = Math.min(speed, Math.sqrt(2 * 1.6 * dist));
    const want = dist > 1e-6 ? e.map((x) => (x / dist) * v) : [0, 0, 0];
    const dv = sub(want, this.vel), lim = 2.2 * dt, n = norm(dv);
    this.vel = n > lim ? add(this.vel, dv, lim / n) : want;
    const stepLen = norm(this.vel) * dt;
    this.pt = stepLen >= dist ? goal.slice() : add(this.pt, this.vel, dt);
    const w = rotError(R, this.Rt), a = norm(w), maxA = 1.6 * dt;
    if (a > 1e-6) this.Rt = matMul(rodrigues(w.map((x) => x * Math.min(1, maxA / a))), this.Rt);
    this.solveIK(dt);
    this.setGrip(this.grip);
    // gravity feed-forward, like a real arm controller: without it the servos sag about 7 mm
    const bias = this.d.qfrc_bias;
    this.acts.forEach((act, i) => (this.d.ctrl[act] = this.qt[i] + bias[this.dof[i]] / this.kp[i]));
    this.ticks++;
  }

  // Damped least squares from MuJoCo's own Jacobian, on a copy of the arm that follows the targets (not the measured arm).
  solveIK(dt) {
    const { mj, m, ik } = this;
    const n = this.dof.length, nv = m.nv;
    for (let iter = 0; iter < 3; iter++) {
      const q = ik.qpos;
      for (let i = 0; i < n; i++) q[this.qadr[i]] = this.qt[i];
      mj.mj_kinematics(m, ik);
      mj.mj_comPos(m, ik);
      const s = 3 * this.site, xp = ik.site_xpos, Rm = Array.from(ik.site_xmat.slice(9 * this.site, 9 * this.site + 9));
      const ep = [this.pt[0] - xp[s], this.pt[1] - xp[s + 1], this.pt[2] - xp[s + 2]];
      const er = rotError(this.Rt, Rm);
      const e = [...ep, ...er];
      if (norm(ep) < 3e-4 && norm(er) < 2e-3) break;
      mj.mj_jacSite(m, ik, this.jacp, this.jacr, this.site);
      const Jp = this.jacp.GetView(), Jr = this.jacr.GetView();
      const J = new Float64Array(6 * n);
      for (let c = 0; c < n; c++) {
        const d = this.dof[c];
        for (let r = 0; r < 3; r++) {
          J[r * n + c] = Jp[r * nv + d];
          J[(r + 3) * n + c] = Jr[r * nv + d];
        }
      }
      const A = new Array(36).fill(0);
      for (let a = 0; a < 6; a++) for (let b = 0; b < 6; b++) {
        let v = 0;
        for (let c = 0; c < n; c++) v += J[a * n + c] * J[b * n + c];
        A[a * 6 + b] = v + (a === b ? 2.5e-3 : 0);
      }
      const y = solve(A, e, 6);
      const dq = new Array(n).fill(0);
      for (let c = 0; c < n; c++) for (let r = 0; r < 6; r++) dq[c] += J[r * n + c] * y[r];
      if (n > 6) {
        const z = this.homeArm.map((h, i) => 0.05 * (h - this.qt[i]));
        const Jz = new Array(6).fill(0);
        for (let r = 0; r < 6; r++) for (let c = 0; c < n; c++) Jz[r] += J[r * n + c] * z[c];
        const yz = solve(A, Jz, 6);
        for (let c = 0; c < n; c++) {
          let back = 0;
          for (let r = 0; r < 6; r++) back += J[r * n + c] * yz[r];
          dq[c] += z[c] - back;
        }
      }
      const big = Math.max(...dq.map(Math.abs)), lim = (MAX_JOINT_SPEED * dt) / 3;
      const f = big > lim ? lim / big : 1;
      for (let c = 0; c < n; c++) {
        let v = this.qt[c] + f * dq[c];
        const [lo, hi, limited] = this.lim[c];
        if (limited) v = Math.min(hi, Math.max(lo, v));
        this.qt[c] = v;
      }
    }
  }

  // Forces from the mouse or the knock button, set before every physics step.
  applyForces() {
    const d = this.d, b = 6 * this.cube, f = d.xfrc_applied;
    for (let i = 0; i < 6; i++) f[b + i] = 0;
    const mass = this.m.body_mass[this.cube], c = this.cubePos(), v = d.qvel, s = this.cubeV;
    if (this.drag) {
      const w = 42, t = this.drag;
      for (let i = 0; i < 3; i++) {
        const force = mass * (w * w * (t[i] - c[i]) - 2 * w * v[s + i]) + (i === 2 ? mass * 9.81 : 0);
        f[b + i] = Math.max(-40, Math.min(40, force));
      }
      for (let i = 3; i < 6; i++) f[b + i] = -2e-4 * v[s + i];
    }
    if (this.hit > 0) {
      this.hit -= this.m.opt.timestep;
      const held = norm(sub(c, this.handPos())) < 0.05;
      this.hitForce = Math.min(420, (this.hitForce ?? 40) + 14);  // grows until the cube is out, however firm the grip
      const k = held ? this.hitForce : 3;
      f[b] = k * this.hitDir[0];
      f[b + 1] = k * this.hitDir[1];
      f[b + 2] = held ? 0.45 * this.hitForce : 1.5;
      if (norm(sub(c, this.handPos())) > 0.07) (this.hit = 0), (this.hitForce = 40);
    }
    const sp = this.cubeSpeed();
    if (sp > 1.6) for (let i = 0; i < 3; i++) v[s + i] *= 1.6 / sp;
  }

  stepPhysics(n) {
    for (let i = 0; i < n; i++) {
      if (this.phys === undefined) this.phys = 0;
      if (this.phys % PHYS_PER_TICK === 0) this.tick();
      this.applyForces();
      this.mj.mj_step(this.m, this.d);
      this.phys++;
    }
  }

  // advance to `seconds` more of simulated time
  advance(seconds) {
    this.stepPhysics(Math.round(seconds / this.m.opt.timestep));
  }

  startDrag(xyz) {
    this.drag = xyz;
    this.userDrag = true;
    if (this.step === "done") this.recoverOnLeave = true;
  }

  moveDrag(xyz) {
    this.drag = xyz;
  }

  endDrag() {
    this.drag = null;
    this.userDrag = false;
  }

  knock() {
    const a = Math.random() * 2 * Math.PI;
    this.hitDir = [Math.cos(a), Math.sin(a)];
    this.hit = 0.25;
    this.hitForce = 40;
  }

  state() {
    const c = this.cubePos(), h = this.handPos();
    return {
      step: this.step, tries: this.tries, recoveries: this.recoveries, done: this.done, note: this.note,
      distance: Math.hypot(c[0] - h[0], c[1] - h[1], c[2] - h[2]), grip: this.grip,
      inBowl: this.cubeInBowl(), taskTime: this.taskTime, time: this.d.time, speed: norm(this.vel),
      cube: c, hand: h, bowl: this.bowlPos(),
    };
  }
}

export async function loadRobot(mj, name, fetchBytes, fetchJson) {
  const [bytes, meta] = await Promise.all([fetchBytes(`models/${name}.mjb`), fetchJson(`models/${name}.json`)]);
  const vfs = new mj.MjVFS();
  vfs.addBuffer(`${name}.mjb`, new Uint8Array(bytes));
  const model = mj.MjModel.from_binary_path(`${name}.mjb`, vfs);
  return { model, meta };
}
