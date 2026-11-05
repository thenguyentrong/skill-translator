// "Try your own video": the panel under the hero. Talks to the Modal API in cloud/. No keys here.
import { engine } from "./app.js";
import { watchPanel } from "./watch.js";

const API = "https://gokuvietsub1--translator-api.us-east.modal.run";
const NAMES = { ur5e: "UR5e", panda: "Franka Panda", fr3: "Franka FR3", xarm7: "xArm7", lite6: "Lite6", so101: "SO-101", g1: "Unitree G1", tienkung3: "TienKung 3", oli: "LimX Oli" };
const MAX_ROBOTS = 3;
const MAX_MB = 60;
const FLOW = ["Upload", "Meta AI reads it", "Robots answer", "Up to 3 try it"];
const WORDS = { queued: "Preparing your video", reading: "Meta AI is reading your video, about a minute", checking: "Each robot is checking the job" };
const SAYS = {
  403: "This demo has used up its budget and is closed.", 413: "This video is over 60 MB. Try a shorter clip.",
  429: "Five videos an hour at most. Try again later.",
};

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const title = (s) => s.charAt(0).toUpperCase() + s.slice(1);

async function call(path, options) {
  let r;
  try {
    r = await fetch(API + path, options);
  } catch {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
  if (r.ok) return r.json();
  const body = await r.json().catch(() => ({}));
  throw new Error(SAYS[r.status] ?? (typeof body.detail === "string" ? title(body.detail) + "." : "Something went wrong."));
}

export function uploadPanel(cardView) {
  const sec = el("section", "yours");
  sec.id = "yours";
  const band = el("div", "yours-band");
  const head = el("div", "yours-head");
  const flow = el("ol", "flow");
  flow.append(...FLOW.map((x) => el("li", "", x)));
  head.append(el("h2", "", "Try your own video"), el("p", "", "Film one hand moving one object into something. We use the first 15 seconds."), flow);

  const form = el("form", "drop-form");
  const drop = el("label", "drop");
  const file = el("input", "sr");
  Object.assign(file, { type: "file", accept: "video/*" });
  const hint = el("span", "drop-hint");
  const name = el("strong", "", "Choose a video");
  const touch = matchMedia("(hover: none)").matches;
  const sub = el("span", "", touch ? `From your phone, up to ${MAX_MB} MB` : `or drop it here, up to ${MAX_MB} MB`);
  if (touch) document.querySelector("#hero-hint").textContent = "From your phone, 15 seconds is plenty";
  hint.append(name, sub);
  drop.append(file, hint);
  const send = el("button", "go", "Read this video");
  send.type = "submit";
  send.hidden = true;
  const said = el("p", "said");
  said.setAttribute("aria-live", "polite");
  form.append(drop, send, said, el("p", "small yours-fine", "Your video goes to Modal and to Meta's API to make the card, so keep faces and private things out of it. Our copy of the video is deleted when the card is done, and the results within 24 hours. Everything runs in simulation. This demo closes for good when its budget is used up."));
  band.append(head, form);
  const out = el("div", "yours-out");
  sec.append(band, out);

  let timer = 0, job = null, misses = 0, picked = null, built = "", url = "";
  const shown = {};
  const stop = () => { clearTimeout(timer); timer = 0; };
  const busy = (on) => { send.disabled = on; };
  const step = (n) => [...flow.children].forEach((li, i) => {
    li.classList.toggle("past", i < n);
    li.classList.toggle("now", i === n);
  });

  function choose(f) {
    if (!f) return;
    if (!f.type.startsWith("video/") && !/\.(mp4|mov|webm|mkv|m4v|3gp)$/i.test(f.name)) {
      said.textContent = "This is not a video file. Try an mp4 or mov.";
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      said.textContent = SAYS[413];
      return;
    }
    picked = f;
    said.textContent = "";
    if (url) URL.revokeObjectURL(url);
    url = URL.createObjectURL(f);
    drop.querySelector("video")?.remove();
    const v = el("video");
    Object.assign(v, { src: url, muted: true, loop: true, autoplay: true, playsInline: true });
    v.setAttribute("aria-label", "Preview of your video");
    v.onerror = () => v.remove();
    drop.prepend(v);
    drop.classList.add("has-file");
    name.textContent = f.name;
    sub.textContent = "Choose another";
    send.hidden = false;
    send.disabled = false;
    step(0);
    sec.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function showVideo(parent, key, src, label) {
    if (shown[key]) return;
    shown[key] = true;
    const v = el("video");
    Object.assign(v, { src: API + src, controls: true, muted: true, loop: true, playsInline: true });
    v.setAttribute("aria-label", label);
    parent.append(v);
  }

  function robots(state, box) {
    box.replaceChildren();
    const rows = Object.entries(state.check);
    const yes = rows.filter(([, a]) => a === "can try");
    box.append(el("p", "count", `${yes.length} of ${rows.length} robots can try`));
    const ul = el("ul");
    const pick = [];
    const go = el("button", "go", "Try these robots");
    const started = Object.keys(state.runs);
    const free = MAX_ROBOTS - started.length;
    const sync = () => {
      const n = pick.filter((c) => c.checked).length;
      go.disabled = !n;
      go.textContent = n > 1 ? `Try these ${n} robots` : n ? "Try this robot" : "Pick up to 3 robots";
      pick.forEach((c) => { c.disabled = !c.checked && n >= free; });
    };
    for (const [robot, answer] of [...yes, ...rows.filter(([, a]) => a !== "can try")]) {
      const ok = answer === "can try";
      const li = el("li", ok ? "yes" : "no");
      const [why0, ...why] = answer.split(": ");
      if (ok && free > 0 && !started.includes(robot)) {
        const lab = el("label", "robot-pick");
        const c = el("input");
        Object.assign(c, { type: "checkbox", value: robot, onchange: sync });
        pick.push(c);
        lab.append(c, el("b", "", NAMES[robot] ?? robot));
        li.append(lab);
      } else {
        li.append(el("b", "", NAMES[robot] ?? robot));
      }
      li.append(el("span", "result", title(why0)));
      if (why.length) li.append(el("small", "", why.join(": ")));
      ul.append(li);
    }
    box.append(ul);
    if (pick.length) {
      go.type = "button";
      go.onclick = async () => {
        const names = pick.filter((c) => c.checked).map((c) => c.value);
        go.disabled = true;
        said.textContent = "Starting the robots";
        try {
          await call(`/jobs/${job}/run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ robots: names }) });
          said.textContent = "";
          built = "";
          poll();
        } catch (e) {
          said.textContent = e.message;
          go.disabled = false;
        }
      };
      sync();
      box.append(go);
    }
  }

  function render(s) {
    const key = `${s.state}|${Object.keys(s.runs).join()}`;
    if (key !== built) {
      built = key;
      const film = out.querySelector(".yours-film") ?? el("div", "yours-film");
      const left = el("div", "yours-left");
      const card = el("div", "yours-card");
      left.append(film, card);
      const tries = out.querySelector(".yours-tries") ?? el("div", "yours-tries");
      const watch = out.querySelector(".yours-watch") ?? (s.check && s.state === "ready" ? watchPanel(s.card, s.check, NAMES, API) : null);
      out.replaceChildren(left, el("div", "verdicts answers yours-robots"), tries, ...(watch ? [watch] : []));
      if (s.card) card.append(cardView({ goal: s.card.goal, kind: s.card.kind ?? "pick_place", objects: Object.keys(s.card.objects ?? {}), steps: (s.card.steps ?? []).map((x) => x.do), needs: s.card.needs }));
      if (s.check) robots(s, out.querySelector(".yours-robots"));
    }
    out.querySelector(".yours-watch")?.setRuns(s.runs);
    if (s.overlay_url) showVideo(out.querySelector(".yours-film"), "film", s.overlay_url, "Your video with SAM 3.1's boxes around the objects and the hand.");
    const tries = out.querySelector(".yours-tries");
    for (const [robot, run] of Object.entries(s.runs)) {
      let fig = tries.querySelector(`[data-robot="${robot}"]`);
      if (!fig) {
        fig = el("figure");
        fig.dataset.robot = robot;
        fig.append(el("figcaption"));
        tries.append(fig);
      }
      const text = run.state === "done" ? (/^\d+\/\d+$/.test(run.result) ? `${run.result} tries passed` : title(run.result)) : run.state === "failed" ? (run.error ?? "This try failed.") : run.state === "running" ? "Practising, then 5 tries" : "Waiting for a machine";
      fig.querySelector("figcaption").replaceChildren(el("b", "", NAMES[robot] ?? robot), el("span", "", text));
      if (run.clip_url) showVideo(fig, `clip-${robot}`, run.clip_url, `${NAMES[robot] ?? robot} trying the job in simulation.`);
    }
  }

  async function poll() {
    stop();
    try {
      const s = await call(`/jobs/${job}`);
      misses = 0;
      render(s);
      const runs = Object.values(s.runs);
      const running = runs.some((r) => r.state === "waiting" || r.state === "running");
      if (s.state === "failed") {
        said.textContent = s.error ?? "Something went wrong.";
        busy(false);
      } else if (s.state === "ready") {
        const cost = s.stages.reduce((a, x) => a + (x.cost_usd ?? 0), 0);
        const time = s.stages.reduce((a, x) => a + x.seconds, 0);
        said.textContent = running ? "The robots are trying it, a few minutes" : runs.length ? "Done. Scroll down for the tries and the live view." : `Meta AI took ${Math.round(time)} s and $${cost.toFixed(2)}. Pick your robots below.`;
        step(runs.length ? (running ? 3 : 4) : 2);
        busy(false);
      } else {
        said.textContent = WORDS[s.state] ?? "Working";
        step(s.state === "checking" ? 2 : 1);
      }
      if (running || !["failed", "ready"].includes(s.state)) timer = setTimeout(poll, 2500);
    } catch (e) {
      if (e.message === "No such job.") {
        said.textContent = "This job is gone. Results are kept for 24 hours.";
        busy(false);
      } else if (++misses > 5) {
        said.textContent = e.message;
        busy(false);
      } else {
        timer = setTimeout(poll, 4000);
      }
    }
  }

  file.onchange = () => choose(file.files[0]);
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (!picked) return;
    stop();
    busy(true);
    built = "";
    Object.keys(shown).forEach((k) => delete shown[k]);
    out.querySelector(".yours-watch")?.stop?.();
    engine.close();
    out.replaceChildren();
    step(0);
    said.textContent = "Uploading";
    try {
      ({ job } = await call("/jobs", { method: "POST", body: picked }));
      history.replaceState(null, "", `#job=${job}`);
      poll();
    } catch (err) {
      said.textContent = err.message;
      busy(false);
    }
  };

  document.querySelector("#hero-file").onchange = (e) => choose(e.target.files[0]);
  const hasFile = (e) => e.dataTransfer?.types?.includes("Files");
  addEventListener("dragover", (e) => {
    if (!hasFile(e)) return;
    e.preventDefault();
    document.body.classList.add("dropping");
  });
  addEventListener("dragleave", (e) => { if (!e.relatedTarget) document.body.classList.remove("dropping"); });
  addEventListener("drop", (e) => {
    if (!hasFile(e)) return;
    e.preventDefault();
    document.body.classList.remove("dropping");
    choose(e.dataTransfer.files[0]);
  });

  const up = el("a", "float-up", "Upload a video");
  up.href = "#yours";
  up.onclick = (e) => { e.preventDefault(); sec.scrollIntoView({ behavior: "smooth" }); };
  document.body.append(up);
  const inView = new Set();
  const watch = new IntersectionObserver((items) => {
    for (const it of items) it.isIntersecting ? inView.add(it.target) : inView.delete(it.target);
    up.classList.toggle("on", !inView.size);
  });
  watch.observe(band);
  watch.observe(document.querySelector(".hero"));

  const open = location.hash.match(/^#job=([0-9a-f]{32})$/);
  if (open) {
    job = open[1];
    busy(true);
    poll();
    setTimeout(() => sec.scrollIntoView(), 300);
  }
  return sec;
}
