// The same yes-or-no rules as translator/scene.py (fit_gripper, check_needs, sample_layout), run on measured robot facts.
// One change: gripper openings are the corrected measurements, because the Python caliper misreads some wide-open grippers.

const mm = (m) => `${Math.round(m * 1000)} mm`;

export function payload(r) {
  return r.rated_kg ? { kg: r.rated_kg, source: "maker rated" } : { kg: r.model_kg, source: "estimated from the model, above a safe load" };
}

function hasRoom(r, width, containerM, table) {
  // a seeded copy of the layout sampler: is there a free spot for the object and the container inside this robot's reach?
  let seed = 7;
  const rnd = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const held = (width / 2) * Math.SQRT2, cont = containerM / 2;
  const on = (xy, c) => Math.abs(xy[0] - table.centre[0]) <= table.half[0] - c && Math.abs(xy[1] - table.centre[1]) <= table.half[1] - c;
  const point = (clear) => {
    const near = Math.max(0.35 * r.reach, r.footprint + clear), far = 0.75 * r.reach;
    if (near >= far) return null;
    for (let i = 0; i < 300; i++) {
      const d = near + rnd() * (far - near), a = (rnd() - 0.5) * (Math.PI / 2);
      const xy = [r.origin[0] + d * Math.cos(a), r.origin[1] + d * Math.sin(a)];
      if (on(xy, clear)) return xy;
    }
    return null;
  };
  for (let i = 0; i < 80; i++) {
    const c = point(held + 0.02);
    if (!c) return false;
    for (let k = 0; k < 40; k++) {
      const b = point(cont + 0.026);
      if (!b) return false;
      if (Math.hypot(c[0] - b[0], c[1] - b[1]) >= Math.max(0.12, cont + held + 0.025)) return true;
    }
  }
  return false;
}

// job: width_cm (what the fingers close on), kg, hands, move_m, handles ("none", "side", "top"), container_cm, kind
export function answer(r, job, table) {
  const no = (label, title, why) => ({ ok: false, label, title, why });
  const width = job.width_cm / 100, est = r.gap_estimated ? " (estimated)" : "";
  if (width > r.widest) return no("too_big", "Too big for its gripper", `It opens ${mm(r.widest)}${est}, this is ${mm(width)} wide.`);
  if (width < r.tightest) return no("too_thin", "Too thin for its gripper", `It closes only to ${mm(r.tightest)}, this is ${mm(width)} thick.`);
  const carry = job.kind === "carry" || job.handles !== "none";
  if (carry && job.handles === "none") return no("two_hand_grip", "No grip for this yet", "No handles: holding a box between two hands is not built yet.");
  if (carry && job.handles === "side" && r.hands < 2) return no("two_hands", "Needs two hands", `Two side handles, it has ${r.hands} usable hand.`);
  if (!carry && job.hands > r.hands) return no("two_hands", "Needs two hands", `This needs ${job.hands}, it has ${r.hands} usable hand.`);
  if (!carry && job.hands > 1) return no("two_hand_grip", "No grip for this yet", "It has two hands, but holds with both only by handles so far.");
  const span = 2 * 0.85 * r.reach;
  if (job.move_m > span && !r.mobile) return no("must_walk", "Must walk, cannot", `The places are ${job.move_m.toFixed(1)} m apart, it spans ${span.toFixed(2)} m from where it stands.`);
  const p = payload(r), limit = (p.kg ?? Infinity) * (carry && job.handles === "side" ? 2 : 1);
  if (job.kg > limit) return no("too_heavy", "Too heavy", `${job.kg} kg, it lifts ${limit} kg (${p.source}).`);
  if (!carry && !hasRoom(r, width, job.container_cm / 100, table)) return no("no_room", "No room (approximate)", `The object and the container do not both fit inside its ${r.reach.toFixed(2)} m reach.`);
  return { ok: true, label: null, title: "Worth a real test", why: `Opens ${mm(r.widest)}${est}, reaches ${r.reach.toFixed(2)} m, lifts ${p.kg} kg (${p.source}).` };
}
