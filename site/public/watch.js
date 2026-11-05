// The two views after a job: left what the robot understood and is doing, right the same engine as the header.
// The robots you picked: the three arms run live in the browser, the others replay their real run from the cloud.
import { engine } from "./app.js";

const LIVE = ["ur5e", "panda", "xarm7"];

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const word = (s) => s.replace(/_/g, " ");
const cm = (m) => `${+(m * 100).toFixed(1)} cm`;
const FAILS = { grasp: "the fingers never held it", drop: "it slipped out on the way", bowl: "it landed outside", ik: "the arm could not reach", reach: "the arm could not reach", no_view: "its cameras could not find it" };
const place = (test) => (test === "on_top" ? "on top of" : word(test ?? "inside"));

function shapeText(o) {
  const [x, y, z] = o.size;
  if (o.shape === "sphere") return `round, ${cm(x)} across`;
  if (o.shape === "cylinder") return `cylinder, ${cm(x)} across, ${cm(z)} tall`;
  return `box, ${+(x * 100).toFixed(1)} x ${+(y * 100).toFixed(1)} x ${cm(z)}`;
}

export function watchPanel(card, check, names, api) {
  const box = el("div", "yours-watch");
  if ((card.kind ?? "pick_place") !== "pick_place" || !card.objects?.[card.grip?.object]?.size) {
    box.append(el("h3", "", "Watch it run"), el("p", "small", "The 3D view covers pick and place so far. For this job, the recorded tries are the view."));
    box.setRuns = () => {};
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
  row("Passes if", `the ${o} ends ${place(card.success?.test)} the ${c}`);
  const part = (name, ...kids) => {
    const s = el("div");
    s.append(el("h4", "", name), ...kids);
    return s;
  };
  const doing = el("p", "doing", "Pick a robot, then watch it here");
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
  const start = el("button", "go start", "Pick a robot above");
  start.disabled = true;
  host.append(start);
  const buttons = el("div", "watch-buttons");
  const knock = el("button", "hit", "Knock it out"), again = el("button", "", "New layout");
  const play = el("button", "hit", "Pause"), close = el("button", "", "Stop");
  const scrub = el("input", "scrub");
  Object.assign(scrub, { type: "range", min: 0, max: 1, step: 0.01, value: 0 });
  scrub.setAttribute("aria-label", "Move through the run");
  [knock, again, play, close].forEach((b) => { b.type = "button"; });
  buttons.append(play, scrub, knock, again, close);
  const small = el("p", "small");
  side.append(host, buttons, small);
  const shown = (on) => {
    [play, scrub].forEach((e) => { e.hidden = !recorded || !on; });
    [knock, again].forEach((e) => { e.hidden = recorded || !on; });
    close.hidden = !on;
  };
  const LIVE_NOTE = `Live in your browser with the sizes from the card. Drag the ${o} or knock it out and watch the left side react. The object's position comes from the simulator here, not cameras, so this is a separate run from the scored tries.`;
  const RUN_NOTE = "This is the robot's real first try from the cloud, played back in the engine: its own cameras, full physics and the IK that keeps the arm off its body. Move the slider to go through it.";
  const ROUND = cont.shape === "box" ? " A square container is drawn round here." : "";
  grid.append(think, side);
  box.append(top, grid);

  let timer = 0, now = "reach", note = "", seen = 0, since = 0, recorded = false, current = null, last = -1, verdictText = "";
  let runs = {};
  shown(false);
  const line = (t, text, alert) => {
    const li = el("li", alert ? "alert" : "");
    li.append(el("time", "", `${t.toFixed(1)} s`), el("span", "", text));
    tell.append(li);
    tell.scrollTop = tell.scrollHeight;
  };
  const clear = () => {
    tell.replaceChildren();
    items.forEach((li) => { li.className = ""; if (!recorded) li.querySelector("i").textContent = ""; });
    now = "";
    note = "";
    seen = 0;
  };
  const update = () => {
    const s = engine.state();
    if (!s) return;
    const pb = engine.playback();
    if (pb) {
      if (pb.t < last) clear();
      last = pb.t;
      if (document.activeElement !== scrub) scrub.value = pb.t;
      scrub.max = pb.end;
      play.textContent = pb.playing ? "Pause" : pb.t >= pb.end ? "Play again" : "Play";
    }
    const t = pb ? pb.t : s.time - since;
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
    tries.textContent = recorded ? 1 : s.tries;
    rec.textContent = s.recoveries;
    const off = Math.hypot(s.cube[0] - s.bowl[0], s.cube[1] - s.bowl[1]);
    if (recorded) {
      const finished = pb && pb.t >= pb.end;
      verdict.classList.toggle("pass", !!(finished && verdictText.startsWith("Passed")));
      verdict.textContent = finished ? verdictText : "The test has not passed yet.";
      return;
    }
    verdict.classList.toggle("pass", s.inBowl && all);
    verdict.textContent = s.inBowl && all ? `Passed: the ${o} is in the ${c}${off < 0.005 ? "" : `, ${cm(off)} from its centre`}${s.taskTime ? `, after ${s.taskTime.toFixed(1)} s` : ""}.` : "The test has not passed yet.";
  };
  const stop = () => {
    clearInterval(timer);
    timer = 0;
  };
  const go = async (robot) => {
    const run = runs[robot], live = LIVE.includes(robot);
    if (!live && !run?.log_url) return;
    current = robot;
    seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.robot === robot));
    start.remove();
    stop();
    doing.textContent = "Loading the robot";
    recorded = !live;
    let log = null;
    if (recorded) {
      try {
        log = await (await fetch(api + run.log_url)).json();
      } catch {
        doing.textContent = "Could not load this run.";
        return;
      }
      verdictText = log.success ? `Passed: the ${o} ended ${place(card.success?.test)} the ${c}.` : `Failed this try: ${FAILS[log.reason] ?? word(log.reason)}.`;
    }
    await engine.open(host, robot, card, log);
    since = engine.state().time;
    clear();
    last = -1;
    if (log) steps.forEach((step, i) => {
      const n = log.labels.filter((l) => l === step).length;
      if (n) items[i].querySelector("i").textContent = `${(n / log.fps).toFixed(1)} s`;
    });
    if (log?.seen?.[held]) line(0, `Its cameras found the ${o} at x ${log.seen[held][0]}, y ${log.seen[held][1]} m`);
    if (log?.seen?.[into]) line(0, `Its cameras found the ${c} at x ${log.seen[into][0]}, y ${log.seen[into][1]} m`);
    small.textContent = (recorded ? RUN_NOTE : LIVE_NOTE) + ROUND;
    shown(true);
    timer = setInterval(update, 120);
  };
  box.setRuns = (next) => {
    runs = next;
    const picked = Object.keys(next);
    if (!picked.length) return;
    for (const r of picked) {
      let b = seg.querySelector(`[data-robot="${r}"]`);
      if (!b) {
        b = el("button", "", names[r] ?? r);
        b.type = "button";
        b.dataset.robot = r;
        b.setAttribute("aria-pressed", "false");
        b.onclick = () => go(r);
        seg.append(b);
      }
      const wait = !LIVE.includes(r) && !next[r].log_url;
      const failed = next[r].state === "failed";
      b.disabled = wait;
      b.textContent = `${names[r] ?? r}${wait && !failed ? ", running" : ""}`;
    }
    if (!current) {
      const first = picked.find((r) => LIVE.includes(r) || next[r].log_url);
      start.disabled = !first;
      start.textContent = first ? `Watch ${names[first] ?? first}` : "Waiting for its run in the cloud";
      start.onclick = () => go(first);
    }
  };
  box.stop = stop;
  knock.onclick = () => engine.knock();
  again.onclick = () => {
    engine.again();
    since = engine.state().time;
    clear();
  };
  play.onclick = () => engine.toggle();
  scrub.oninput = () => engine.seek(+scrub.value);
  close.onclick = async () => {
    stop();
    current = null;
    await engine.close();
    host.append(start);
    doing.textContent = "Press start";
    why.textContent = "";
    shown(false);
    box.setRuns(runs);
  };
  return box;
}
