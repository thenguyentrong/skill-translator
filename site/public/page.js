// The static part of the page, built from data/site.json and data/facts.json (saved results only).
import { answer } from "./check.js";
import { uploadPanel } from "./upload.js";

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const KIND = { pick_place: "Pick and place", open: "Open a door", carry: "Carry" };

function video(src, label) {
  const v = el("video");
  v.dataset.src = src;
  v.muted = v.loop = v.playsInline = true;
  v.setAttribute("aria-label", label);
  v.preload = "none";
  return v;
}

function cardView(c) {
  const box = el("div", "card");
  box.append(el("span", "kind", KIND[c.kind] ?? c.kind), el("h3", "", c.goal));
  const dl = el("dl");
  const row = (k, v) => { dl.append(el("dt", "", k), el("dd", "", v)); };
  row("Objects", c.objects.join(", "));
  row("Steps", c.steps.join(", "));
  const n = c.needs ?? {};
  if (n.hands) row("Needs", `${n.hands} ${n.hands > 1 ? "hands" : "hand"}${n.move_m ? `, moves ${n.move_m} m` : ""}${n.mass_kg ? `, about ${n.mass_kg} kg` : ""}`);
  if (n.guessed?.length) row("Guessed", n.guessed.map((g) => g.replace(/_kg|_m$/g, "").replace(/_/g, " ")).join(", "));
  box.append(dl);
  return box;
}

function verdicts(list, title) {
  const wrap = el("div", "verdicts");
  wrap.append(el("h4", "", title));
  const ul = el("ul");
  for (const r of list) {
    const li = el("li", r.no ? "no" : "yes");
    li.append(el("b", "", r.robot));
    li.append(el("span", "result", r.no ?? r.score ?? "Can try"));
    if (r.why) li.append(el("small", "", r.why));
    ul.append(li);
  }
  wrap.append(ul);
  return wrap;
}

function kindPanel(k) {
  const p = el("div", "panel");
  p.id = `kind-${k.id}`;
  p.hidden = k.id !== "pick";
  const left = el("figure");
  left.append(video(k.overlay, `Source video with SAM 3.1 boxes: ${k.title}`), el("figcaption", "", `${k.title} SAM 3.1 tracks it, Muse Spark writes the card: ${k.job.seconds} s, $${k.job.usd.toFixed(2)}. ${k.credit}`));
  const top = el("div", "split");
  top.append(left, cardView(k.card));
  p.append(top);
  if (k.answers) p.append(verdicts(k.answers, k.answers_title));
  const res = el("figure", "wide");
  res.append(video(k.result, `Robots doing: ${k.tab}`));
  if (k.note) res.append(el("figcaption", "", k.note));
  p.append(res, verdicts(k.robots, k.robots_title));
  if (k.robots2) p.append(verdicts(k.robots2, k.robots2_title));
  return p;
}

function checkPanel(f) {
  const sec = el("section", "check");
  sec.id = "check";
  sec.append(el("h2", "", "Check a job"), el("p", "lede", "Set the job, or start from a saved one. Each robot answers from measurements of its own model, in simulation. A yes means worth a real test, not a promise."));
  const job = { ...f.jobs[0] };
  const grid = el("div", "check-grid");
  const form = el("div", "form");
  const picks = el("div", "picks");
  const result = el("div", "verdicts answers");
  const count = el("p", "count");
  const list = el("ul");
  result.append(count, list);
  const render = () => {
    list.innerHTML = "";
    let yes = 0;
    for (const r of f.robots) {
      const a = answer(r, job, f.table);
      yes += a.ok;
      const li = el("li", a.ok ? "yes" : "no");
      li.append(el("b", "", r.name), el("span", "result", a.title), el("small", "", a.why));
      list.append(li);
    }
    count.textContent = `${yes} of ${f.robots.length} worth a real test`;
  };
  const fields = [];
  const slider = (key, label, unit, min, max, step) => {
    const wrap = el("label", "field");
    const head = el("span", "", label), value = el("output");
    const top = el("div", "field-head");
    top.append(head, value);
    const input = el("input");
    input.type = "range";
    Object.assign(input, { min, max, step });
    const sync = () => { input.value = job[key]; value.textContent = `${job[key]} ${unit}`; };
    input.oninput = () => { job[key] = +input.value; sync(); render(); };
    wrap.append(top, input);
    form.append(wrap);
    fields.push(sync);
  };
  const choice = (key, label, options) => {
    const wrap = el("div", "field");
    wrap.append(el("span", "", label));
    const row = el("div", "seg");
    const sync = () => row.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(job[key]) === b.dataset.v));
    for (const [v, text] of options) {
      const b = el("button", "", text);
      b.type = "button";
      b.dataset.v = v;
      b.onclick = () => { job[key] = key === "hands" ? +v : v; sync(); render(); };
      row.append(b);
    }
    wrap.append(row);
    form.append(wrap);
    fields.push(sync);
  };
  slider("width_cm", "Width the fingers close on", "cm", 1, 40, 0.1);
  slider("kg", "Weight", "kg", 0.02, 8, 0.01);
  slider("move_m", "Distance between the two places", "m", 0, 3, 0.1);
  slider("container_cm", "Container width", "cm", 0, 80, 1);
  choice("hands", "Hands", [["1", "One"], ["2", "Two"]]);
  choice("handles", "Handles", [["none", "None"], ["side", "Two side"], ["top", "One top"]]);
  for (const j of f.jobs) {
    const b = el("button", "", j.title);
    b.type = "button";
    b.onclick = () => {
      Object.assign(job, j);
      picks.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
      fields.forEach((x) => x());
      render();
    };
    picks.append(b);
  }
  picks.firstChild.setAttribute("aria-pressed", "true");
  fields.forEach((x) => x());
  render();
  const left = el("div");
  left.append(picks, form);
  grid.append(left, result);
  sec.append(grid, el("p", "small", "Each check uses a measured gripper opening, reach and hand count; opening marked estimated was worked out from finger positions. Weight limits are the maker's rating where known, otherwise estimated from the model's torque limits, which is higher than a safe load. No room is approximate. The example jobs come from saved skill cards."));
  return sec;
}

function lazyVideos() {
  const seen = new IntersectionObserver((items) => {
    for (const it of items) {
      const v = it.target;
      if (it.isIntersecting) {
        if (!v.src) v.src = v.dataset.src;
        if (!matchMedia("(prefers-reduced-motion: reduce)").matches) v.play().catch(() => {});
        else v.controls = true;
      } else if (v.src) v.pause();
    }
  }, { rootMargin: "120px" });
  document.querySelectorAll("video[data-src]").forEach((v) => seen.observe(v));
}

async function build() {
  const [d, facts, live] = await Promise.all(["data/site.json", "data/facts.json", "data/live_test.json"].map(async (u) => (await fetch(u)).json()));
  const main = document.querySelector("#content");
  const jobs = el("section", "jobs");
  jobs.append(el("h2", "", "One short video. A clear answer per robot."));
  jobs.append(el("p", "lede", "The card holds what the job means: objects, grip, steps and how to know it worked. It holds no arm motion, so a small arm and a humanoid can both use it, or say why they can't."));
  const tabs = el("div", "tabs");
  tabs.setAttribute("role", "tablist");
  for (const k of d.kinds) {
    const b = el("button", "", k.tab);
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", k.id === "pick");
    b.onclick = () => {
      tabs.querySelectorAll("button").forEach((x) => x.setAttribute("aria-selected", x === b));
      jobs.querySelectorAll(".panel").forEach((x) => (x.hidden = x.id !== `kind-${k.id}`));
    };
    tabs.append(b);
  }
  jobs.append(tabs, ...d.kinds.map(kindPanel));

  const mx = el("section", "matrix");
  const head = el("div", "big");
  head.append(el("strong", "", `${d.matrix.ok} of ${d.matrix.n}`), el("p", "", `tries passed in simulation: ${d.matrix.skills} skills on ${d.matrix.robots} robots, ${d.matrix.cells} pairs that could try, 10 tries each with the robot's own cameras. Where a robot can't do a job, it says so instead of trying.`));
  const img = el("img");
  img.src = "media/matrix.webp";
  img.loading = "lazy";
  img.width = 2000;
  img.height = 1257;
  img.alt = "A grid of eleven skills by nine robots with a picture of each robot doing the skill and its score out of ten.";
  mx.append(head, img);

  const pol = el("section", "policies");
  const fig = el("figure");
  fig.append(video(d.policy_clip, "The G1 humanoid driven only by its trained policy picks a cube and puts it in a bowl. On the right, the three camera views the policy sees."), el("figcaption", "", "G1 on a layout it never saw. No planner, no IK: cameras and joints in, motor commands out."));
  const side = el("div");
  side.append(el("h2", "", "Then each robot learns its own policy."), el("p", "lede", "200 checked runs per robot become training data. ACT, 40k steps, about 40 minutes each on one RTX 3090. Tested on 50 new layouts."));
  const t = el("table");
  t.innerHTML = "<thead><tr><th>Robot</th><th>Skill</th><th>Passed</th></tr></thead>";
  const body = el("tbody");
  for (const r of d.policies) {
    const tr = el("tr");
    tr.append(el("td", "", r.robot), el("td", "", r.skill), el("td", "num", `${r.ok}/${r.n}${r.smoothed > r.ok ? ` (${r.smoothed} smoothed)` : ""}`));
    body.append(tr);
  }
  t.append(body);
  side.append(t, el("p", "small", "This is a short training run, and trained policies still score below the scripted teacher. Smoothed = temporal ensembling."));
  pol.append(fig, side);

  const how = el("section", "how");
  how.append(el("h2", "", "Where Meta AI does the work"));
  const rows = [["SAM 3.1", "Follows the objects and the hand through every frame of the video."],
    ["Muse Spark 1.3", "Decides the kind of task, writes the skill card, writes a robot adapter from its model file, and judges failed tries against the video."],
    ["Muse Spark Open", "Open weights on Baseten and Fireworks. Wrote the Lite6 and Franka FR3 adapters."]];
  const list = el("div", "rows");
  for (const [a, b] of rows) {
    const r = el("div");
    r.append(el("h3", "", a), el("p", "", b));
    list.append(r);
  }
  how.append(list);

  const lim = el("section", "limits");
  lim.append(el("h2", "", "What this is not, yet"));
  const ul = el("ul");
  for (const s of ["Everything runs in simulation. No real robot has done any of this.",
    "Each new kind of task (pick, open, carry) is hand-written code once. Only the card and the adapters are written by Meta AI.",
    "Vision in the Python runs works by colour and depth; the browser robot reads the simulator directly, with no cameras and no training.",
    "Moving between tables is a sliding base. The legs do not step.",
    "No buyer has tested this yet."]) ul.append(el("li", "", s));
  lim.append(ul);

  const foot = el("footer");
  foot.innerHTML = `<p class="built">Built with Muse Spark Open.</p>
  <p>Made for the Meta Global AI Developer Hackathon 2026. <a href="https://github.com/thenguyentrong/skill-translator">Code on GitHub</a>.</p>
  <p class="small">Simulation: <a href="https://github.com/google-deepmind/mujoco">MuJoCo</a> (<a href="licenses/mujoco-LICENSE.txt">licence</a>, <a href="licenses/mujoco-LICENSES_THIRD_PARTY.md">third party</a>), drawn with <a href="licenses/three-LICENSE.txt">three.js</a>. Live robots from <a href="https://github.com/google-deepmind/mujoco_menagerie">MuJoCo Menagerie</a>, meshes reduced for the web: <a href="licenses/ur5e-LICENSE.txt">UR5e</a>, <a href="licenses/robotiq-2f85-LICENSE.txt">Robotiq 2F-85</a>, <a href="licenses/panda-LICENSE.txt">Franka Panda</a>, <a href="licenses/xarm7-LICENSE.txt">xArm7</a>. Fonts: <a href="licenses/archivo-OFL.txt">Archivo</a>, <a href="licenses/martian-mono-OFL.txt">Martian Mono</a>.</p>
  <p class="small">The source videos are stock clips under the Pexels License, not my own footage: <a href="https://www.pexels.com/video/person-putting-orange-in-bowl-7198787/">SHVETS production</a>, <a href="https://www.pexels.com/video/young-woman-taking-mug-out-of-cupboard-5515109/">Ivan S</a>, <a href="https://www.pexels.com/video/a-woman-taking-her-packages-inside-8927178/">Kampus Production</a>.</p>
  <p class="small">Robot names and logos belong to their makers. No robot maker supports or is connected with this project.</p>`;
  const tally = Object.values(live).flatMap((r) => Object.entries(r).filter(([k]) => k !== "undisturbed").map(([, v]) => v));
  const mess = el("section", "mess");
  const ok = tally.reduce((a, v) => a + v[0], 0), all = tally.reduce((a, v) => a + v[1], 0);
  mess.append(el("h2", "", "It knows the goal, so you can mess with it."));
  mess.append(el("p", "lede", `The robot at the top reads the card 25 times a second. In scripted tests on ${Object.keys(live).length} arms, with the same card and the same code, it finished ${ok} of ${all} runs after the cube was moved mid-reach, taken away mid-descent, knocked out of the gripper, or pulled out of the bowl. A replayed motion cannot do that.`));
  main.append(checkPanel(facts), uploadPanel(cardView), mess, jobs, mx, pol, how, lim, foot);
  lazyVideos();
}
build();
