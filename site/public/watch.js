// The two views after a job: left what the robot understood and is doing, right the same engine as the header, running this card.
import { engine } from "./app.js";

const LIVE = ["ur5e", "panda", "xarm7"];  // the arms with a browser model

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const word = (s) => s.replace(/_/g, " ");
const cm = (m) => `${+(m * 100).toFixed(1)} cm`;

function shapeText(o) {
  const [x, y, z] = o.size;
  if (o.shape === "sphere") return `round, ${cm(x)} across`;
  if (o.shape === "cylinder") return `cylinder, ${cm(x)} across, ${cm(z)} tall`;
  return `box, ${+(x * 100).toFixed(1)} x ${+(y * 100).toFixed(1)} x ${cm(z)}`;
}

export function watchPanel(card, check, names) {
  const box = el("div", "yours-watch");
  const robots = LIVE.filter((r) => check[r] === "can try");
  if ((card.kind ?? "pick_place") !== "pick_place" || !robots.length || !card.objects?.[card.grip?.object]?.size) {
    box.append(el("h3", "", "Watch it run"), el("p", "small", "The live view covers pick and place on UR5e, Panda and xArm7. For this job, the recorded tries are the view."));
    return box;
  }
  const held = card.grip.object, into = card.success?.container ?? Object.keys(card.objects).find((k) => k !== held);
  const o = word(held), c = word(into), cont = card.objects[into];
  const SAY = {
    reach: `Moving above the ${o}`, descend: `Going down to the ${o}`, close: `Closing the fingers on the ${o}`, lift: `Lifting the ${o}`,
    carry: `Carrying it above the ${c}`, lower: `Lowering it into the ${c}`, open: "Letting go", retreat: "Moving the hand away", done: "Job done",
  };

  const top = el("div", "watch-top");
  const seg = el("span", "seg");
  top.append(el("h3", "", "Watch it run"), seg);
  const grid = el("div", "watch-grid");

  const think = el("div", "think");
  const facts = el("dl");
  const row = (k, v) => facts.append(el("dt", "", k), el("dd", "", v));
  row("Goal", card.goal);
  row("Holds", `${o}: ${shapeText(card.objects[held])}`);
  row("Into", `${c}: ${cm(2 * cont.inner_radius)} across, ${cm(cont.wall_height)} deep`);
  row("Passes if", `the ${o} ends ${word(card.success?.test ?? "inside")} the ${c}`);
  const part = (name, ...kids) => {
    const s = el("div");
    s.append(el("h4", "", name), ...kids);
    return s;
  };
  const doing = el("p", "doing", "Press start");
  const why = el("p", "why");
  why.setAttribute("aria-live", "polite");
  const gauges = el("div", "gauges");
  const gauge = (label) => {
    const v = el("span", "", "0"), d = el("div");
    d.append(v, el("small", "", label));
    gauges.append(d);
    return v;
  };
  const dist = gauge("cm, hand to object"), grip = gauge("% grip closed"), tries = gauge("grasp tries"), rec = gauge("recoveries");
  const plan = el("ol", "plan");
  const steps = card.steps.map((s) => s.do);
  const items = steps.map((s) => {
    const li = el("li");
    li.append(el("span", "", s), el("i", "", ""));
    plan.append(li);
    return li;
  });
  const tell = el("ol", "tell");
  const verdict = el("p", "verdict", "The test has not passed yet.");
  think.append(part("What it understood from the video", facts), part("What it is doing now", doing, why, gauges), part("Its steps, from the card", plan), part("What it decided", tell), verdict);

  const side = el("div", "stage-side");
  const host = el("div", "stage-host");
  const start = el("button", "go start", "Start the live run");
  host.append(start);
  const buttons = el("div", "watch-buttons");
  const knock = el("button", "hit", "Knock it out"), again = el("button", "", "New layout"), close = el("button", "", "Stop");
  [knock, again, close].forEach((b) => { b.type = "button"; b.disabled = true; });
  buttons.append(knock, again, close);
  side.append(host, buttons, el("p", "small", `Drag the ${o} or knock it out and watch the left side react. This runs in your browser with the sizes from the card. The object's position comes from the simulator here, not cameras, so it is a separate run from the scored tries.${cont.shape === "box" ? " A square container is drawn round here." : ""}`));
  grid.append(think, side);
  box.append(top, grid);

  let timer = 0, now = "reach", note = "", seen = 0, since = 0;
  const line = (t, text, alert) => {
    const li = el("li", alert ? "alert" : "");
    li.append(el("time", "", `${t.toFixed(1)} s`), el("span", "", text));
    tell.append(li);
    tell.scrollTop = tell.scrollHeight;
  };
  const clear = () => {
    tell.replaceChildren();
    items.forEach((li) => { li.className = ""; li.querySelector("i").textContent = ""; });
    now = "";
    note = "";
    seen = 0;
  };
  const update = () => {
    const s = engine.state();
    if (!s) return;
    const t = s.time - since;
    if (s.step !== now) {
      now = s.step;
      line(t, SAY[now] ?? now);
    }
    if (s.note && s.note !== note) line(t, s.note, true);
    note = s.note;
    const at = steps.indexOf(s.step), all = s.step === "done";
    items.forEach((li, i) => {
      li.classList.toggle("now", i === at);
      li.classList.toggle("past", all || (at >= 0 && i < at));
    });
    const log = engine.log();
    for (; seen < log.length - 1; seen++) {
      const i = steps.indexOf(log[seen].step);
      if (i >= 0) items[i].querySelector("i").textContent = `${(log[seen + 1].t - log[seen].t).toFixed(1)} s`;
    }
    doing.textContent = SAY[s.step] ?? s.step;
    why.textContent = s.note || (s.step === "reach" ? `It sees the ${o} ${cm(s.distance)} from the hand.` : s.step === "carry" ? `The ${c} is ${cm(Math.hypot(s.hand[0] - s.bowl[0], s.hand[1] - s.bowl[1]))} away.` : "");
    dist.textContent = (s.distance * 100).toFixed(1);
    grip.textContent = Math.round(s.grip * 100);
    tries.textContent = s.tries;
    rec.textContent = s.recoveries;
    const off = Math.hypot(s.cube[0] - s.bowl[0], s.cube[1] - s.bowl[1]);
    verdict.classList.toggle("pass", s.inBowl && all);
    verdict.textContent = s.inBowl && all ? `Passed: the ${o} is in the ${c}${off < 0.005 ? "" : `, ${cm(off)} from its centre`}${s.taskTime ? `, after ${s.taskTime.toFixed(1)} s` : ""}.` : "The test has not passed yet.";
  };
  const go = async (robot) => {
    seg.querySelectorAll("button").forEach((b) => { b.disabled = true; b.setAttribute("aria-pressed", b.dataset.robot === robot); });
    start.remove();
    doing.textContent = "Loading the robot";
    clearInterval(timer);
    await engine.open(host, robot, card);
    since = engine.state().time;
    clear();
    timer = setInterval(update, 120);
    seg.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    [knock, again, close].forEach((b) => { b.disabled = false; });
  };
  box.stop = () => {
    clearInterval(timer);
    timer = 0;
  };
  for (const r of robots) {
    const b = el("button", "", names[r] ?? r);
    b.type = "button";
    b.dataset.robot = r;
    b.setAttribute("aria-pressed", String(r === robots[0]));
    b.onclick = () => go(r);
    seg.append(b);
  }
  start.type = "button";
  start.onclick = () => go(robots[0]);
  knock.onclick = () => engine.knock();
  again.onclick = () => {
    engine.again();
    since = engine.state().time;
    clear();
  };
  close.onclick = () => {
    box.stop();
    engine.close();
    host.append(start);
    doing.textContent = "Press start";
    why.textContent = "";
    [knock, again, close].forEach((b) => { b.disabled = true; });
  };
  return box;
}
