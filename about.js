// The long explainer under the upload panel: the idea, how it works, the stack, the repo, how to run it.
const REPO = "https://github.com/thenguyentrong/skill-translator";
const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};
const code = (path) => {
  const a = el("a", "path", path);
  a.href = `${REPO}/${path.endsWith("/") ? "tree" : "blob"}/main/${path.replace(/\/$/, "")}`;
  return a;
};

const CARD = `{
  "name": "lemon_to_bowl",
  "goal": "A lemon is inside the wooden bowl.",
  "objects": {
    "lemon": { "shape": "sphere", "size": [0.055, 0.055, 0.055] },
    "wooden_bowl": { "shape": "bowl", "inner_radius": 0.1, "wall_height": 0.07 }
  },
  "grip": { "object": "lemon", "approach": "top", "width": 0.055 },
  "steps": ["reach", "descend", "close", "lift", "carry", "lower", "open", "retreat"],
  "success": { "test": "inside", "object": "lemon", "container": "wooden_bowl" }
}`;

const PIPE = [
  ["Film the job", "One short video of a hand doing the task. A phone is enough.", ["Your phone"], []],
  ["Meta AI reads it", "Muse Spark decides the kind of task and names the objects. SAM 3.1 follows the object, the container and the hand through every frame. From those tracks the code finds the grab and the release, then Muse writes the skill card.", ["SAM 3.1", "Muse Spark 1.3"], ["translator/card_writer.py", "translator/events.py"]],
  ["Each robot answers", "Every robot checks the card against measurements of its own model: gripper opening, reach, hands, load. It says yes, or no with the reason.", ["MuJoCo model files"], ["translator/scene.py"]],
  ["Translate to its body", "The robot practises the grip on layouts it won't be tested on, because a Robotiq closes on an arc and a lemon rolls where a cube sits. Then the card becomes hand targets, and IK turns them into joint moves at 25 Hz.", ["mink", "MuJoCo"], ["translator/practice.py", "translator/translate.py", "translator/ik.py"]],
  ["Test it in simulation", "Full physics. The robot finds the objects with its own cameras. A try counts only if the object ends up where the card says.", ["MuJoCo"], ["translator/execute.py", "translator/perceive.py"]],
  ["Check and improve", "Muse compares a failed try with the human video, says what went wrong and proposes a card change. A change is kept only if more tries pass on the same layouts. SAM can also judge a clip from pixels alone.", ["Muse Spark 1.3", "SAM 3.1"], ["translator/review.py", "translator/referee.py"]],
  ["Mess with it", "The live loop looks again 12.5 times a second, works out which card step is true now and moves one step at a time. Push the object away and the hand follows.", ["MuJoCo", "Live loop"], ["translator/live.py"]],
  ["Train a policy", "Passed runs become a dataset for each robot, and each robot trains its own policy from cameras and joints. Short runs so far, and they score below the scripted motion.", ["LeRobot", "ACT"], ["scripts/make_dataset.py", "scripts/train_job.py"]],
];

const STACK = [
  ["Meta AI", [["SAM 3.1", "follows objects and hands through a video"], ["Muse Spark 1.3", "reads video, writes cards and adapters, judges failed tries"], ["Muse Spark Open", "open weights on Baseten and Fireworks, wrote the Lite6 and FR3 adapters"], ["Muse Voice Transcribe", "turns a spoken note into text for the card"]]],
  ["Simulation and control", [["MuJoCo 3.17", "physics and the robots' cameras"], ["mink", "inverse kinematics with joint limits and self-collision"], ["MuJoCo Menagerie", "most of the robot models"]]],
  ["Learning", [["LeRobot 0.6", "datasets and training"], ["ACT", "the policy each robot trains"], ["RTX 3090", "about 40 minutes per policy, on my own PC"]]],
  ["Cloud", [["Modal", "runs the upload, the card step and the robots, costs nothing when idle"], ["FastAPI", "the upload API"], ["ffmpeg", "cleans every upload before anything reads it"]]],
  ["Website", [["MuJoCo WASM", "the live robot runs in your browser"], ["three.js", "draws it"], ["GitHub Pages", "plain HTML, CSS and JS, no build step"]]],
];

const REPO_MAP = [
  ["translator/", "The core: card writing, robot scene, IK, physics run, vision, live loop, referee"],
  ["cards/", "The skill library, one JSON file per skill"],
  ["robots/", "The robot library, one JSON adapter per robot. robots/muse/ holds the ones Muse wrote"],
  ["scripts/", "Command line tools: run a job, test every skill on every robot, write an adapter, train"],
  ["cloud/", "The upload API and its workers on Modal"],
  ["site/", "This website, plus the tools that export the robots for the browser"],
  ["web/", "The first local web app"],
  ["docs/", "README images and notes"],
];

const TILES = [
  ["611 of 760", "tries passed: 11 skills on 9 robots, in simulation"],
  ["5 of 7", "new robots passed from a Muse adapter, with no hand-written code for them"],
  ["372 of 420", "disturbed tries finished by the live loop; replay 49, a plain re-plan 398"],
  ["39 of 40", "clean simulated clips where SAM's verdict matched the simulator"],
  ["38 to 74 %", "trained policies from cameras, on 50 new layouts"],
  ["$0.08", "Meta API cost of a 3 second clip, about 2 minutes on Modal"],
];

const RUN = `# Setup on Linux
conda create -p .venv -c conda-forge --override-channels python=3.12 ffmpeg=7.1.1
.venv/bin/pip install mujoco mink daqp numpy imageio imageio-ffmpeg pillow "lerobot[dataset,training]"
bash scripts/fetch_robots.sh          # downloads the robot models

# No API key needed
.venv/bin/python scripts/kill_test.py so101 panda --n 10
.venv/bin/python scripts/live.py ur5e --skill cube_to_bowl   # double-click the object, Ctrl + right-drag it

# Needs MODEL_API_KEY in .env
.venv/bin/python scripts/run_job.py path/to/video.mp4

# The upload API on Modal
bash cloud/deploy.sh`;

export function aboutPanel() {
  const sec = el("section", "about");
  sec.id = "about";
  const body = el("div", "about-body");
  const part = (id, title, ...kids) => {
    const s = el("article", "about-part");
    s.id = id;
    s.append(el("h2", "", title), ...kids);
    body.append(s);
  };

  const twoStages = el("ol", "stages");
  for (const [a, b] of [["Learn once, the hard part", "Video to skill card. Done once per task."], ["Repeat on every robot, the cheap part", "Card to each robot's own motion, checked in simulation. Done once per robot, with no new demos."]]) {
    const li = el("li");
    li.append(el("b", "", a), el("span", "", b));
    twoStages.append(li);
  }
  const fig = el("figure", "code-fig");
  fig.append(el("pre", "", CARD), el("figcaption", "", "A real card, written by Muse Spark from a 3 second video. Shortened here. It has no joints and no arm paths."));
  part("idea", "The idea",
    el("p", "lede", "Can this robot do my job? Today you often find out after you buy it, and then you teach it from zero, with hours of demos per robot and per task."),
    el("p", "", "Translator copies the meaning of a task, never the motion. A small arm and a humanoid can't move the same way, but both can reach the same goal, each in its own way. Like a good human translator: the sense, not word for word."),
    el("p", "", "The meaning lives in a skill card: the objects, the grip, the steps and how to check success. Each robot reads the card with its own body in mind."),
    twoStages, fig);

  const pipe = el("ol", "pipe");
  PIPE.forEach(([title, text, tools, paths]) => {
    const li = el("li");
    const main = el("div");
    main.append(el("h3", "", title), el("p", "", text));
    const side = el("div", "pipe-side");
    side.append(...tools.map((t) => el("span", "tag", t)), ...paths.map(code));
    li.append(main, side);
    pipe.append(li);
  });
  const fresh = el("p");
  fresh.append("A robot the code has never seen goes through the same path. Muse reads its model file and writes the adapter, the code measures and tests it, and failures go back to Muse, three times at most. The Franka FR3 took 21 seconds on Muse Spark Open and passed 10 of 10 on the first try. See ", code("scripts/write_adapter.py"), ".");
  part("how", "How it works", el("p", "lede", "Eight steps from a video to a robot that can do the job. Each one links to its code."), pipe, fresh);

  const stack = el("div", "stack");
  for (const [group, rows] of STACK) {
    const box = el("div");
    box.append(el("h3", "", group));
    const dl = el("dl");
    for (const [k, v] of rows) dl.append(el("dt", "", k), el("dd", "", v));
    box.append(dl);
    stack.append(box);
  }
  part("stack", "The stack", stack);

  const tiles = el("div", "tiles");
  for (const [big, small] of TILES) {
    const t = el("div");
    t.append(el("strong", "", big), el("span", "", small));
    tiles.append(t);
  }
  part("numbers", "The numbers so far", tiles, el("p", "small", "Everything here is simulation. The robots are not equal: on the live test the UR5e finished 69 of 70 and TienKung 3 finished 44 of 70."));

  const map = el("div", "repo");
  for (const [path, text] of REPO_MAP) map.append(code(path), el("p", "", text));
  part("repo", "What's in the repo", map);

  part("run", "Run it yourself", el("pre", "run", RUN));

  const side = el("aside", "about-side");
  const links = el("nav");
  links.setAttribute("aria-label", "On this page");
  links.append(el("h3", "", "On this page"));
  for (const [id, t] of [["idea", "The idea"], ["how", "How it works"], ["stack", "The stack"], ["numbers", "The numbers"], ["repo", "The repo"], ["run", "Run it yourself"]]) {
    const a = el("a", "", t);
    a.href = `#${id}`;
    links.append(a);
  }
  const info = el("div", "about-info");
  const repo = el("a", "", "thenguyentrong/skill-translator");
  repo.href = REPO;
  info.append(el("h3", "", "About"), repo,
    el("p", "", "Built by The Vinh Nguyen Trong, solo, for the Meta Global AI Developer Hackathon 2026, Indie track, 26 Oct to 4 Nov."),
    el("p", "small", "The upload panel, the Modal backend and the live view were added after the deadline."));
  side.append(info, links);
  sec.append(body, side);
  return sec;
}
