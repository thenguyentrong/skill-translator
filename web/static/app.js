const $ = (s) => document.querySelector(s);
const NAMES = { so101: "SO-101", panda: "Franka Panda", ur5e: "UR5e", g1: "Unitree G1", xarm7: "xArm7", lite6: "Lite6",
                tienkung3: "TienKung 3", oli: "LimX Oli", fr3: "Franka FR3" };
const NO = { "too big": "Too big for its gripper", "too thin": "Too thin for its gripper", "no room": "Out of its reach",
             "two hands": "Needs two hands", "must walk": "Would have to walk", "too heavy": "Too heavy for its arm",
             "two hand grip": "Two-hand grip not built yet", "handle too high": "Handle too high", "handle too low": "Handle too low" };
const state = { video: null, job: null, videos: [], robots: [], picked: new Set(), timer: null, last: null };

const pretty = (s) => (s || "").replace(/_/g, " ");
const name = (r) => NAMES[r] || r;
const cm = (m) => `${+(m * 100).toFixed(1)} cm`;
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

function showError(msg) {
  const e = $("#error");
  e.textContent = msg || "";
  e.hidden = !msg;
}

async function api(path, body, raw) {
  const opts = body ? { method: "POST", ...(raw ? { body } : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) } : {};
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `${r.status} ${r.statusText}`);
  return data;
}

/* video library */
async function loadVideos() {
  state.videos = await api("/api/videos");
  const box = $("#library");
  box.replaceChildren();
  for (const v of state.videos) {
    const t = el("button", "tile" + (v.name === state.video ? " on" : ""));
    t.type = "button";
    const img = el("img"); img.src = v.thumb; img.alt = ""; img.loading = "lazy";
    const label = el("span");
    label.append(el("b", null, pretty(v.name)));
    if (v.has_card) label.append(el("i", "saved", "card saved"));
    t.append(img, label);
    t.onclick = () => choose(v.name);
    box.append(t);
  }
  if (!state.videos.length) box.append(el("p", "muted", "No clips yet. Drop a video above."));
}

function choose(video) {
  state.video = video;
  const v = state.videos.find((x) => x.name === video) || {};
  document.querySelectorAll(".tile").forEach((t, i) => t.classList.toggle("on", state.videos[i]?.name === video));
  $("#make-row").hidden = false;
  $("#chosen").textContent = pretty(video);
  $("#make").textContent = v.has_card ? "Use the saved card" : "Make the card";
  $("#again").hidden = !v.has_card;
  $("#make-note").textContent = v.has_card ? "Free: Meta AI already read this video." : "About a minute, about $0.10 of Meta AI.";
}

async function upload(file) {
  if (!file) return;
  showError("");
  $(".drop-title").textContent = `Uploading ${file.name}`;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const r = await api("/api/upload", fd, true);
    await loadVideos();
    choose(r.name);
    $(".drop-title").textContent = "Drop a short video here";
    $("#s-video").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    $(".drop-title").textContent = "Drop a short video here";
    showError(`Upload failed: ${e.message}`);
  }
}

async function make(again) {
  showError("");
  try {
    const r = await api("/api/jobs", { video: state.video, again: !!again });
    state.picked.clear();
    openJob(r.job);
  } catch (e) { showError(e.message); }
}

function openJob(job) {
  state.job = job;
  history.replaceState(null, "", `#job=${encodeURIComponent(job)}`);
  $("#s-card").hidden = false;
  poll();
  $("#s-card").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* polling */
async function poll() {
  clearTimeout(state.timer);
  if (!state.job) return;
  let busy = false;
  try {
    const j = await api(`/api/jobs/${encodeURIComponent(state.job)}`);
    state.last = j;
    busy = render(j);
  } catch (e) { showError(e.message); }
  state.timer = setTimeout(poll, busy ? 1500 : 8000);
}

function alive(j, step) { const s = j.steps[step]; return !!(s && s.alive && s.state === "running"); }

function render(j) {
  const learning = alive(j, "learn");
  const checking = alive(j, "check");
  const trying = alive(j, "try");
  const learnFailed = j.steps.learn && j.steps.learn.state === "failed";
  $("#gpu").hidden = !j.gpu_busy;
  $("#gpu").textContent = j.gpu_busy ? "GPU busy: a policy is training" : "";
  if (learnFailed) showError(`Meta AI could not make a card: ${j.steps.learn.error}`);

  renderStages(j, learning);
  const ov = $("#overlay");
  if (j.overlay_url && ov.dataset.src !== j.overlay_url) { ov.src = j.overlay_url; ov.dataset.src = j.overlay_url; ov.play().catch(() => {}); }
  renderCard(j.card, j.evidence, learning);
  for (const s of ["#s-video", "#s-card", "#s-check", "#s-runs"]) $(s).classList.remove("now");
  $(learning ? "#s-card" : j.card && !Object.keys(j.runs).length ? "#s-check" : "#s-runs")?.classList.add("now");

  $("#s-check").hidden = !j.card;
  if (j.card) renderCheck(j.check, checking);
  $("#s-runs").hidden = !Object.keys(j.runs).length;
  renderRuns(j);
  const training = Object.values(j.training?.robots || {}).some((r) => !r.eval || r.eval.running);
  return learning || checking || trying || training || j.gpu_busy;
}

function renderStages(j, learning) {
  const ol = $("#stages");
  ol.replaceChildren();
  for (const s of j.stages) {
    const li = el("li", "done", s.stage.replace(/'([^']+)'/, "“$1”"));
    li.append(el("span", "num", `${s.seconds} s`));
    ol.append(li);
  }
  if (learning) ol.append(el("li", "run pulse", "Meta AI is working"));
  const cost = j.stages.reduce((a, s) => a + (s.cost_usd || 0), 0);
  const secs = j.stages.reduce((a, s) => a + (s.seconds || 0), 0);
  if (j.card && j.stages.length) ol.append(el("li", "done", `${Math.round(secs)} s and $${cost.toFixed(2)} in total`));
}

function fact(dl, label, value) {
  if (value == null || value === "") return;
  const d = el("div");
  d.append(el("dt", null, label));
  const dd = el("dd");
  if (value instanceof Node) dd.append(value); else dd.textContent = value;
  d.append(dd);
  dl.append(d);
}

function stepsLine(card) {
  const box = el("div", "steps-line");
  for (const s of card.steps || []) {
    const what = s.object || s.into || s.to || (s.height ? cm(s.height) : "");
    box.append(el("span", null, `${s.do}${what ? " " + pretty(what) : ""}`));
  }
  return box;
}

function renderCard(card, evidence, learning) {
  const box = $("#card");
  box.replaceChildren();
  if (!card) {
    if (learning) { box.append(el("div", "skeleton", "")); box.firstChild.style.minHeight = "220px"; }
    return;
  }
  const kind = card.kind || "pick_place";
  box.append(el("span", "kind", { pick_place: "Pick and place", open: "Open a door", carry: "Carry" }[kind] || pretty(kind)));
  box.append(el("p", "goal", card.goal));
  const dl = el("dl", "facts");
  const o = card.objects || {};
  const g = card.grip || {};
  if (kind === "open") {
    const cab = card.success.object, h = o[g.object] || {}, c = o[cab] || {};
    fact(dl, "Cabinet", `${pretty(cab)}, ${(c.size || []).map((v) => Math.round(v * 100)).join(" x ")} cm, hinge on the ${c.door?.hinge}`);
    fact(dl, "Handle", `${pretty(g.object)}, ${Math.round((h.diameter || 0) * 1000)} mm thick`);
    fact(dl, "Done when", `the door is open at least ${card.success.min_angle_deg} degrees`);
  } else if (kind === "carry") {
    const c = o[g.object] || {}, place = card.success.place, p = o[place] || {};
    fact(dl, "Object", `${pretty(g.object)}, ${(c.size || []).map((v) => Math.round(v * 100)).join(" x ")} cm, ${c.mass} kg`);
    fact(dl, "Take it to", `${pretty(place)}, ${p.distance} m away`);
    fact(dl, "Done when", `it rests on ${pretty(place)}, upright`);
  } else {
    const held = g.object, cont = card.success?.container, h = o[held] || {}, c = o[cont] || {};
    fact(dl, "Object", `${pretty(held)}, ${pretty(h.shape)}, ${(h.size || []).map((v) => +(v * 100).toFixed(1)).join(" x ")} cm`);
    fact(dl, card.success?.test === "on_top" ? "Onto" : "Into", `${pretty(cont)}, ${pretty(c.shape)}, ${Math.round((c.inner_radius || 0) * 200)} cm across`);
    fact(dl, "Grip", `from the ${g.approach}, ${g.between}, ${cm(g.width || 0)} wide`);
    fact(dl, "Done when", `the ${pretty(held)} is ${card.success?.test === "on_top" ? "on top of" : "inside"} the ${pretty(cont)}`);
  }
  fact(dl, "Steps", stepsLine(card));
  const n = card.needs;
  if (n) {
    const parts = [`${n.hands || 1} hand${(n.hands || 1) > 1 ? "s" : ""}`];
    if (n.move_m) parts.push(`moves ${n.move_m} m`);
    if (n.mass_kg) parts.push(`about ${n.mass_kg} kg`);
    if (n.keep_upright) parts.push("keep it level");
    fact(dl, "Needs", parts.join(", "));
  }
  box.append(dl);
  if (evidence?.notes) {
    const p = el("p", "notes", evidence.notes);
    box.append(p);
  }
}

/* robots */
async function loadRobots() {
  if (!state.robots.length) state.robots = await api("/api/robots");
  return state.robots;
}

function robotCard(r, body) {
  const c = el("article", "robot");
  const img = el("img"); img.src = r.thumb; img.alt = `${name(r.name)} in simulation`; img.loading = "lazy";
  img.onerror = () => img.remove();
  const b = el("div", "body");
  b.append(...body);
  c.append(img, b);
  return c;
}

async function renderCheck(check, checking) {
  const robots = await loadRobots();
  const box = $("#check");
  box.replaceChildren();
  for (const r of robots) {
    const answer = check ? check[r.name] : null;
    const head = el("div", "name");
    head.append(el("h3", null, name(r.name)));
    let card;
    if (!answer) {
      head.append(el("span", "chip no pulse", checking ? "Checking" : "Waiting"));
      card = robotCard(r, [head]);
    } else if (answer === "can try") {
      const box2 = el("input"); box2.type = "checkbox"; box2.checked = state.picked.has(r.name);
      box2.setAttribute("aria-label", `Pick ${name(r.name)}`);
      head.append(box2);
      card = robotCard(r, [head, el("span", "chip yes", "Can try"), el("span", "meta", r.written_by === "Muse" ? "Adapter by Muse" : "Adapter by hand")]);
      card.classList.add("can");
      card.classList.toggle("picked", box2.checked);
      const toggle = (on) => { on ? state.picked.add(r.name) : state.picked.delete(r.name); box2.checked = on; card.classList.toggle("picked", on); $("#run").disabled = !state.picked.size; };
      card.onclick = (e) => { if (e.target !== box2) toggle(!box2.checked); };
      box2.onchange = () => toggle(box2.checked);
    } else {
      const [label, ...rest] = answer.split(": ");
      const why = rest.join(": ");
      card = robotCard(r, [head, el("span", "chip no", NO[label] || label), el("p", "why", why.charAt(0).toUpperCase() + why.slice(1) + ".")]);
      card.classList.add("cannot");
    }
    box.append(card);
  }
  $("#run").disabled = !state.picked.size || alive(state.last || { steps: {} }, "try");
}

async function run() {
  showError("");
  try {
    await api(`/api/jobs/${encodeURIComponent(state.job)}/run`, { robots: [...state.picked], trials: +$("#trials").value || 5 });
    $("#s-runs").hidden = false;
    poll();
    $("#s-runs").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { showError(e.message); }
}

function trainLine(j, robot, result) {
  const line = el("div", "train");
  const t = j.training?.robots?.[robot];
  const pickPlace = (j.card?.kind || "pick_place") === "pick_place";
  if (t) {
    const ds = t.dataset || {}, tr = t.train || {}, ev = t.eval || {};
    let text = "Making 200 practice runs for its own policy";
    if (ds.error || tr.error || ev.error) text = `Training stopped: ${ds.error || tr.error || ev.error}`;
    else if (ev.success != null) text = `Its own policy: ${ev.success} of ${ev.trials} new layouts`;
    else if (ev.running) text = "Testing its policy on 50 new layouts";
    else if (tr.running) text = `Training its policy: ${tr.step_k}k of ${j.training.steps / 1000}k steps`;
    else if (tr.steps) text = "Trained, waiting for the test";
    line.append(el("span", ev.success == null && !text.startsWith("Training stopped") ? "pulse" : null, text));
    return line;
  }
  const ok = /^(\d+)\//.exec(result || "");
  if (!pickPlace || !ok || +ok[1] === 0) return null;
  const b = el("button", "ghost", "Train its own policy");
  b.disabled = j.gpu_busy;
  b.onclick = async () => {
    try { await api(`/api/jobs/${encodeURIComponent(state.job)}/train`, { robots: [robot] }); poll(); }
    catch (e) { showError(e.message); }
  };
  line.append(b, el("span", null, j.gpu_busy ? "GPU busy, try later" : "About an hour on the GPU"));
  return line;
}

function renderRuns(j) {
  const box = $("#runs");
  const keep = new Map([...box.children].map((c) => [c.dataset.robot, c]));
  const order = Object.keys(j.runs);
  for (const robot of order) {
    const r = j.runs[robot];
    let card = keep.get(robot);
    if (!card) { card = el("article", "run"); card.dataset.robot = robot; box.append(card); }
    const key = `${r.state}|${r.result}|${r.clip_url}|${JSON.stringify(j.training?.robots?.[robot] || {})}|${j.gpu_busy}`;
    if (card.dataset.key === key) continue;
    card.dataset.key = key;
    card.replaceChildren();
    const shot = el("div", "shot");
    if (r.clip_url) {
      const v = el("video"); v.src = r.clip_url; v.muted = true; v.loop = true; v.playsInline = true; v.controls = true; v.autoplay = true;
      shot.append(v);
    } else {
      shot.append(el("span", r.state === "running" ? "pulse" : null,
        { waiting: "Waiting for its turn", running: "Practising, then trying", failed: "Stopped" }[r.state] || r.state));
    }
    const body = el("div", "body");
    const head = el("div", "name");
    head.append(el("h3", null, name(robot)));
    const m = /^(\d+)\/(\d+)$/.exec(r.result || "");
    if (m) {
      const rate = m[1] / m[2];
      head.append(el("span", "score " + (rate >= 0.8 ? "good" : rate < 0.5 ? "low" : ""), `${m[1]}/${m[2]}`));
    }
    body.append(head);
    if (r.result && !m) body.append(el("p", "why", r.result));
    if (r.error) body.append(el("p", "why", r.error));
    if (m) body.append(el("p", "meta", `${m[1]} of ${m[2]} tries ended with the goal true`));
    const t = r.state === "done" ? trainLine(j, robot, r.result) : null;
    if (t) body.append(t);
    card.append(shot, body);
  }
}

/* robots view */
async function showRobots() {
  const robots = await loadRobots();
  const box = $("#robot-list");
  box.replaceChildren();
  for (const r of robots) {
    const head = el("div", "name");
    head.append(el("h3", null, name(r.name)));
    head.append(el("span", "chip " + (r.written_by === "Muse" ? "yes" : "no"), r.written_by === "Muse" ? "By Muse" : "By hand"));
    const facts = [`Gripper: ${r.gripper}`, `${r.hands} hand${r.hands > 1 ? "s" : ""}${r.moves ? ", moves between tables" : ""}`];
    if (r.payload_kg) facts.push(`Rated load: ${r.payload_kg} kg`);
    box.append(robotCard(r, [head, ...facts.map((f) => el("span", "meta", f))]));
  }
}

function view(v) {
  document.querySelectorAll(".tab").forEach((t) => { const on = t.dataset.view === v; t.classList.toggle("on", on); t.setAttribute("aria-pressed", on); });
  $("#view-skill").hidden = v !== "skill";
  $("#view-robots").hidden = v !== "robots";
  if (v === "robots") showRobots().catch((e) => showError(e.message));
}

/* wiring */
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => view(t.dataset.view)));
$("#file").onchange = (e) => upload(e.target.files[0]);
const drop = $("#drop");
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files[0]); };
$("#make").onclick = () => make(false);
$("#again").onclick = () => make(true);
$("#run").onclick = run;
$("#pick-all").onclick = () => {
  const check = state.last?.check || {};
  for (const [r, a] of Object.entries(check)) if (a === "can try") state.picked.add(r);
  renderCheck(check, false);
};

function fromHash() {
  const m = /job=([^&]+)/.exec(location.hash);
  if (!m) return;
  const job = decodeURIComponent(m[1]);
  if (job === state.job) return;
  if (state.videos.some((v) => v.name === job)) choose(job);
  openJob(job);
}
window.addEventListener("hashchange", fromHash);
loadVideos().then(fromHash).catch((e) => showError(`Cannot reach the server: ${e.message}`));
