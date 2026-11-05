// "Try your own video": talks to the Modal API in cloud/. No keys here.
const API = "https://gokuvietsub1--translator-api.us-east.modal.run";
const NAMES = { ur5e: "UR5e", panda: "Franka Panda", fr3: "Franka FR3", xarm7: "xArm7", lite6: "Lite6", so101: "SO-101", g1: "Unitree G1", tienkung3: "TienKung 3", oli: "LimX Oli" };
const MAX_ROBOTS = 3;
const WORDS = { queued: "Preparing the video", reading: "Meta AI is reading the video", checking: "Each robot is checking the job" };
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
  sec.append(el("h2", "", "Try your own video"), el("p", "lede", "Film one hand moving one object into something, 15 seconds at most. Meta AI reads it, each robot answers, and up to three of them try it in simulation."));

  const grid = el("div", "check-grid");
  const form = el("form", "form");
  const fileBox = el("label", "field");
  const file = el("input");
  Object.assign(file, { type: "file", accept: "video/*", required: true });
  fileBox.append(el("span", "", "Video, up to 60 MB"), file);
  const send = el("button", "primary", "Read my video");
  send.type = "submit";
  const said = el("p", "said");
  said.setAttribute("aria-live", "polite");
  form.append(fileBox, send, said, el("p", "small", "Your video goes to Modal and to Meta's API to make the card, so keep faces and private things out of it. Our copy of the video is deleted when the card is done, and the results within 24 hours. It only runs in simulation. This demo closes for good when its budget is used up."));

  const out = el("div", "yours-out");
  out.append(el("p", "small", "The card, the robots' answers and their tries will show up here."));
  grid.append(form, out);
  sec.append(grid);

  let timer = 0, job = null, misses = 0;
  const shown = {};

  const stop = () => { clearTimeout(timer); timer = 0; };
  const busy = (on) => { send.disabled = on; };

  function showVideo(parent, key, url, label) {
    if (shown[key]) return;
    shown[key] = true;
    const v = el("video");
    Object.assign(v, { src: API + url, controls: true, muted: true, loop: true, playsInline: true });
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
    const go = el("button", "primary", "Try these robots");
    const started = Object.keys(state.runs);
    const free = MAX_ROBOTS - started.length;
    const sync = () => {
      const n = pick.filter((c) => c.checked).length;
      go.disabled = !n;
      go.textContent = n > 1 ? `Try these ${n} robots` : "Try this robot";
      pick.forEach((c) => { c.disabled = !c.checked && n >= free; });
    };
    for (const [name, answer] of [...yes, ...rows.filter(([, a]) => a !== "can try")]) {
      const ok = answer === "can try";
      const li = el("li", ok ? "yes" : "no");
      const [head, ...why] = answer.split(": ");
      if (ok && free > 0 && !started.includes(name)) {
        const lab = el("label", "robot-pick");
        const c = el("input");
        Object.assign(c, { type: "checkbox", value: name, onchange: sync });
        pick.push(c);
        lab.append(c, el("b", "", NAMES[name] ?? name));
        li.append(lab);
      } else {
        li.append(el("b", "", NAMES[name] ?? name));
      }
      li.append(el("span", "result", title(head)));
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

  let built = "";
  function render(s) {
    const key = `${s.state}|${Object.keys(s.runs).join()}`;
    if (key !== built) {
      built = key;
      const keep = out.querySelector(".yours-film");
      out.replaceChildren(el("div", "yours-film"), el("div", "yours-card"), el("div", "verdicts answers yours-robots"), el("div", "yours-tries"));
      if (keep) { out.querySelector(".yours-film").replaceWith(keep); }
      if (s.card) out.querySelector(".yours-card").append(cardView({ goal: s.card.goal, kind: s.card.kind ?? "pick_place", objects: Object.keys(s.card.objects ?? {}), steps: (s.card.steps ?? []).map((x) => x.do), needs: s.card.needs }));
      if (s.check) robots(s, out.querySelector(".yours-robots"));
    }
    if (s.overlay_url) showVideo(out.querySelector(".yours-film"), "film", s.overlay_url, "Your video with SAM 3.1's boxes around the objects and the hand.");
    const tries = out.querySelector(".yours-tries");
    for (const [name, run] of Object.entries(s.runs)) {
      let fig = tries.querySelector(`[data-robot="${name}"]`);
      if (!fig) {
        fig = el("figure");
        fig.dataset.robot = name;
        fig.append(el("figcaption"));
        tries.append(fig);
      }
      const text = run.state === "done" ? (/^\d+\/\d+$/.test(run.result) ? `${run.result} tries passed` : title(run.result)) : run.state === "failed" ? (run.error ?? "This try failed.") : run.state === "running" ? "Practising the grip, then 5 tries" : "Waiting for a free machine";
      fig.querySelector("figcaption").replaceChildren(el("b", "", NAMES[name] ?? name), el("span", "", text));
      if (run.clip_url) showVideo(fig, `clip-${name}`, run.clip_url, `${NAMES[name] ?? name} trying the job in simulation.`);
    }
  }

  async function poll() {
    stop();
    try {
      const s = await call(`/jobs/${job}`);
      misses = 0;
      render(s);
      const running = Object.values(s.runs).some((r) => r.state === "waiting" || r.state === "running");
      if (s.state === "failed") {
        said.textContent = s.error ?? "Something went wrong.";
        busy(false);
      } else if (s.state === "ready") {
        const cost = s.stages.reduce((a, x) => a + (x.cost_usd ?? 0), 0);
        const time = s.stages.reduce((a, x) => a + x.seconds, 0);
        said.textContent = `Meta AI took ${Math.round(time)} s and $${cost.toFixed(2)}.`;
        busy(false);
      } else {
        said.textContent = WORDS[s.state] ?? "Working";
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

  form.onsubmit = async (e) => {
    e.preventDefault();
    const f = file.files[0];
    if (!f) return;
    stop();
    busy(true);
    built = "";
    Object.keys(shown).forEach((k) => delete shown[k]);
    out.replaceChildren();
    said.textContent = "Uploading";
    try {
      ({ job } = await call("/jobs", { method: "POST", body: f }));
      history.replaceState(null, "", `#job=${job}`);
      poll();
    } catch (err) {
      said.textContent = err.message;
      busy(false);
    }
  };

  const open = location.hash.match(/^#job=([0-9a-f]{32})$/);
  if (open) {
    job = open[1];
    busy(true);
    poll();
    setTimeout(() => sec.scrollIntoView(), 300);
  }
  return sec;
}
