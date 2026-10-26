# Translator (working name): a translator for robot skills

Entry for the **Meta Global AI Developer Hackathon 2026** (Cerebral Valley, virtual), **Indie track, solo**.
This file is the full project context for any Claude session working on this repo. Read it first, then keep the **Status** section up to date.

## The idea

Film a task once with a phone. Muse turns it into a **skill card** that any robot can use, translates the card into each robot's own motions, checks every translation in simulation, and then each robot trains its own policy on it.

**Core rule: translate the MEANING, never copy the MOTION.** The skill card holds the goal, the object, the grip, the steps and the success test. A small arm and a humanoid can't move the same way, but both can reach the same goal, each in its own way. Like a good human translator: the sense, not word by word.
(Motion copy / arm retargeting belongs to a different project of the user. Keep this repo separate from it in name and code.)

**Why it matters:** today every robot must be taught separately, with hours of human demos per task and per robot. Here, one phone video becomes checked training data for any robot.

**Demo video story (3 min):** "I show the skill once with my hand. Three robots that look nothing like me do it, each in its own way. Then I give it a robot it has never seen: it reads the blueprint, and that robot does it too."

## Pipeline

1. **Perceive:** phone video → SAM 3.1 (Meta Model API) tracks the objects (and the hand) → Muse Spark writes the skill card (JSON).
2. **Translate:** Muse reads the target robot's blueprint (MJCF/URDF: reach, gripper type and width, joint limits) → robot adapter (end-effector site, gripper actuator with open/close values, home pose, base placement) + grasp choice → waypoints → IK with `mink`.
3. **Check:** run in MuJoCo, success test (block inside the bowl), render a replay. On failure, Muse looks at the replay frames + the log and changes the translation (max 3 rounds).
4. **Data:** random object poses → run the checked skill → save successful episodes as a LeRobot dataset per robot.
5. **Train:** LeRobot ACT per robot (state input first, images later) → evaluate on 50 random trials.

How each Meta model is used:
- **SAM 3.1** (API): text-prompt tracking of objects/hand in the phone video.
- **Muse Spark** (API): video understanding → skill card; reads robot blueprints; reviews failed replays.
- **Muse Spark Open** (open weights via Baseten/Modal/Fireworks): the translate-check-fix loop. This makes us eligible for the open-weight bonus prize.
- Optional: Muse Wonder for the long agent loop; Muse Code for coding.

## Scope v1 (keep it small)

- Skill: 3 cm cube → bowl. One skill first; a second one only if everything works.
- Robots: SO-101 (TheRobotStudio/SO-ARM100 repo, `Simulation/SO101`), Franka Panda and UR5e + Robotiq 2F-85 (google-deepmind/mujoco_menagerie).
- Bonus: Unitree G1, one arm, pelvis fixed.
- Wow moment: a robot the code has never seen (e.g. Kinova Gen3 or xArm7) works from its blueprint alone.

## Plan (German time, CET) and kill tests

| Day | Work | Done when |
|---|---|---|
| Mon 26 Oct eve | Setup on Linux, load all robots, scene (table, cube, bowl). User films the skill video and adds a card to the Meta account | All robots load and move |
| Tue 27 | Hand-written skill card → SO-101 + Franka pick-and-place via IK | **KILL TEST: 8/10 per robot** with random cube poses |
| Wed 28 | Muse: video → skill card; blueprint → adapter for UR5e; fix-from-replay loop | UR5e works ≥ 5/10 without hand-written code |
| Thu 29 | Data generation (200+ episodes per robot) → start the training queue, which must run unattended Fri–Sun | Queue running, first eval numbers |
| Fri 30 – Sun 1 Nov | Offline, no work. Training runs alone | — |
| Mon 2 Nov | Eval the trained policies, success table | Table done |
| Tue 3 | Unseen-robot wow, G1 bonus, film the demo | Demo footage |
| Wed 4 | Edit the 3-min video, README, submit (~20:00) | Submitted. Hard deadline Thu 5 Nov 03:00 |

Every evening ends with a demo that works. If the Tuesday kill test fails, stop and rethink the scope before going on.

Numbers to show: success of the translated skill and of the trained policy per robot (50 trials each); for the unseen robot, how many fix rounds it needed.

## Status (update this section)

**26 Oct 2026 (evening)**
- Idea chosen: Translator. Repo created (this file = the brief). No code yet.
- Accounts created by the user: Meta Model API (dev.meta.ai), Modal, Fireworks.
- Credit requests **submitted** by the user: Meta, Baseten, Fireworks, Modal.
- **Open:** dev.meta.ai still has **no payment method** (checked 26 Oct ~18:15). Until the user adds a card, every Meta Model API call fails. Tuesday's kill test needs no API (hand-written skill card); Wednesday's video → skill card step does.
- Credit details:
  - Meta Model API $150: arrives within ~2 business days → check dev.meta.ai → Billing. The API only works with a payment method on file; set a spend alert at $150.
  - Baseten $100 + 2M TPM, Modal $100, Fireworks $25: reviewed by the partners; if selected, the redemption details come by email. Not guaranteed, so plan without them.
- Free extra: Fireworks offers free fine-tuning (SFT) of Muse Glimmer 30B until 30 Nov. Possible path to the open-weight bonus prize later; not in scope v1.

**26 Oct 2026 (night): setup done, "all robots load and move" passed**
- Machine before setup: RTX 3090, driver 590.48, CUDA 13.1 (driver only, no nvcc, not needed). No MuJoCo/LeRobot/SO-101 model for this project (an old `~/venvs/mujoco` with Python 3.13 exists; not used). System Python 3.12 has no `ensurepip` (fix needs sudo), so `.venv` is a **conda-forge env** (Python 3.12 + ffmpeg 7.1.1).
- `scripts/smoke_test.py` passes (MuJoCo 3.17.0, mink 1.3.0, EGL render).
- LeRobot 0.6.1 + torch 2.11.0+cu130 installed, CUDA sees the 3090; LeRobotDataset and ACT import; torchcodec decodes AV1 with the env's ffmpeg; `pip check` clean.
- `scripts/fetch_robots.sh`: menagerie @ f3b6013, SO-ARM100 @ a758567.
- `translator/robots.py` = hand-written adapters (SO-101, Panda, UR5e + 2F-85, G1). `translator/scene.py` = table (top 0.75 m), 3 cm cube, bowl (r 6 cm, wall 4 cm), robot; reach measured from the model, cube/bowl placed inside it.
- `scripts/check_robots.py` → all 4 OK (joint tracking < 0.05 rad, gripper moves). Contact sheet: `outputs/check/robots.png`. Reach at table height: SO-101 0.40 m, Panda 0.79, UR5e 0.80, G1 right arm 0.38.
- Facts found: SO-101 gripper opens with larger values (open 1.0, closed −0.1), approach axis = `gripperframe` +x. UR5e home faces +y → base yaw −90°. G1 `g1.xml` hand is a visual rubber mesh (no grasp); the G1 bonus needs `g1_with_hands.xml`. G1 stands on the floor, pelvis welded, only the right arm is active.
- Kinova Gen3 and xArm7 are fetched but **deliberately not in the code** (unseen-robot demo). Gen3 has no gripper; xArm7 has one built in, so xArm7 is the cleaner unseen robot.
- The UR5e adapter is hand-written for tonight's load test only. Wednesday's goal needs Muse's adapter to replace it (keep the hand-written one only as a reference to compare against).

**Tuesday kill test: PASSED (done early, night of 26 Oct; user said "go")**
- Code: `cards/cube_to_bowl.json` (hand-written card) → `translator/translate.py` (card + adapter → gripper waypoints; heights from object sizes) → `translator/ik.py` (mink: FrameTask + posture 0.01 + DampingTask 0.1, DofFreezing for non-arm joints, joint limits, 1.5 rad/s speed limit) → `translator/execute.py` (IK every tick at 25 Hz, min-jerk Cartesian paths, 0.3 s settle at pre-grasp and above-bowl, full physics, failure reason) → `scripts/kill_test.py`.
- **Official result (seeds 0–9, final code): SO-101 9/10, Panda 10/10.** SO-101 seed 3: the jaws pushed the cube 1.5 cm on closing, the tilted carry put it 6 cm off the bowl centre, it hit the rim (logged as "drop").
- Extra, unseen seeds 1000–1049: **SO-101 50/50, Panda 46/50 (3 drop, 1 grasp), UR5e 48/50** (UR5e with the hand-written adapter, reference only). Results JSON + failure videos in `outputs/kill_test/<robot>/`.
- Fixes found on the way (all general, none robot-specific):
  - SO-101 `gripperframe` sits on the fixed jaw's inner face → adapter `grip_offset` (−6 mm along approach, +18 mm toward the moving jaw). Panda/Robotiq pinch sites are already the pad centre.
  - SO-101 has 5 joints: straight-down works at cube height but not at 10 cm → `orientation_cost` 0.1 (tilts up high, exact at grasp/release; grasp/release IK error ≤ 5.5 mm).
  - Layout sampler ignored the robot's own body: SO-101 shoulder hit the bowl (all 5 early SO-101 failures). Now cube/bowl stay outside the base footprint, measured from the model (SO-101 0.115 m, Panda 0.219, UR5e 0.085).
  - Panda drops: near the singularity where joints 1 and 3 line up, the posture term swung them at 1.2 rad/s → hand shook → cube slid out. DampingTask + speed limit cut it; the rest is the menagerie Panda gripper's weak squeeze (~1.5 N on a 3 cm cube). Tested and NOT the cause: gravity compensation, no-slip solver, cube friction 1.5 (each tried on 50 seeds).
- Open: Panda ~8 % drops (fine for data generation, which keeps only successful episodes; matters for the "translated skill success" number on 50 trials).

**Vision + live view (26 Oct night)**
- Every robot has 3 cameras: `front` (45°, like the phone on a stand), `top` (straight down) and `robot/wrist` (10 cm behind the grip point, 5 cm to the side, looking at the fingers). Placed from the adapter (grip site + approach/closing axes) and the measured reach, so an unseen robot gets them too. Cameras do not change physics (kill test still SO-101 9/10, Panda 10/10).
- `translator/render.py` (`Cameras`): labelled front/top/wrist images. Used by kill-test videos (main view + camera column, 960×540), `check_robots.py` (`outputs/check/cameras.png`) and the live viewer.
- `scripts/watch.py`: real-time MuJoCo viewer with the 3 camera views inside the window; cycles SO-101 → Panda → UR5e. Close the window to stop.
- Not yet: the robot still gets cube/bowl positions from the simulator. Next vision step = find them from the front/top camera (colour + depth now, SAM 3.1 once the Meta API works). G1 with Dex3 hands is planned and waiting for "go".

**Vision from the robot's own cameras (26 Oct night)**
- `translator/perceive.py` (`Eyes`): front + top camera, colour mask (red cube, green bowl) + metric depth → 3D points → cube centre (top face), cube yaw (smallest bounding box), bowl centre (circle fit on the rim). Colour step = stand-in for SAM 3.1 text prompts. Accuracy on 150 layouts: cube ~2.5 mm, yaw ~1–2° (max 8°), bowl ~2 mm; top camera is usually blocked by the arm at home, the front camera always sees.
- Kill test now uses camera vision by default (`--eyes sim` = old perfect knowledge). Official seeds 0–9: **SO-101 10/10, Panda 10/10**. Unseen 1000–1049: SO-101 48/50, Panda 44/50, UR5e 48/50.
- Also changed: gripper closes over 0.4 s (Robotiq no longer shoves the cube), grip direction chosen by IK reachability (the translator tries all 4 face pairs), arm origin = first arm joint axis (SO-101 pan axis is 3.9 cm in front of its base frame), robot parts split into turning footprint + fixed obstacles, home pose clipped to joint limits, `ready` pose in the adapter.

**G1 humanoid (in progress)**
- `g1_with_hands.xml` (Dex3, 7 hand motors, BSD-3), pelvis welded, right arm + hand active, ready pose with the hand above the table. Hand open/close poses found by a kinematic search (thumb meets index+middle 156 mm along the hand, 60 mm off the palm).
- Arm reaches the grasp within 1–2 mm, but 0/5 grasps hold: the curling middle finger lands on the cube's top edge while the thumb pushes the side → cube squeezed out. Shifting the grip point alone: best 1/4. Next: redesign the close motion so the fingertips come down beside the cube (no part of the hand inside the cube volume before side contact).

**Product idea (user, 26 Oct)**: a web tool: upload a 5–10 s phone video of one task → skill card → pick robots from a library or upload your own model (MJCF/URDF) → it translates, runs the sim (cloud GPU, e.g. Modal credits) and shows each robot doing it, so one demo scales to many robots. Fits the judging: Impact 30 % ("could become something people use"), Demo 25 % ("holds up live"). Plan shown, waiting for "go".

**Day 1 end (26 Oct, ~21:00): pushed** `translator`, `readme`, `cleanup`, `status` to main. README has hero.gif/mp4 + vision/robots images (`scripts/make_media.py` re-makes them).

**OPEN (start here tomorrow)**
1. **User:** add a payment method on dev.meta.ai (every API call fails until then), put the key in `.env` as `MODEL_API_KEY`, film the skill video (spec in "Next" below).
2. **G1 grasp:** best so far 3/10 (an agent's experiment with new hand poses, not saved as code). Problem: curling middle finger lands on the cube's top edge, thumb pushes the side, cube squeezes out. Redo the Dex3 open/close search with a "no hand vertex inside the cube before side contact" check; maybe a smaller close target past contact (hand motors kp 500, no force limit). Search script idea: scratchpad `dex3.py` (lost with the session; easy to redo).
3. **Meta API facts** (official quickstart, read 26 Oct): OpenAI-compatible, base URL `https://api.meta.ai/v1`, model `muse-spark-1.3`, input text/image/pdf/**video**, Responses API `POST /v1/responses`, `Authorization: Bearer $MODEL_API_KEY`, `pip install openai`. Still to check: SAM 3.1 endpoint + video/text-prompt format, video size limits, structured JSON output, open-weight Muse Spark Open on Baseten/Modal.
4. **Modal:** has an official MuJoCo (mjlab) example; check it for headless EGL on GPU before planning the cloud worker.
5. **Web tool (user's idea):** plan in the product idea above; waiting for "go" after items 3–4.
6. **Panda drops ~10 % on unseen layouts** (weak menagerie gripper, ~1.5 N); fine for data generation, hurts the 50-trial number.
7. **UR5e adapter** is hand-written; Wednesday's goal needs Muse to write it from the model file.
8. Robot model licenses: check before the demo goes out (menagerie: Apache-2.0 / BSD; SO-ARM100: Apache-2.0).

**Next**
1. User: film the skill video (hand puts a 3 cm cube into a bowl; phone on a stand ~45°, good light, plain table; 3 normal takes + 1 fumble; one photo from straight above) and put the Meta API key into `.env`.
2. Wednesday: Muse video → skill card (needs the Meta payment method), Muse blueprint → adapter for UR5e (must reproduce: approach/closing axes, grip offset, gripper open/close values, base yaw), fix-from-replay loop.

## Hackathon facts

- Submit on the Cerebral Valley platform by **Wed 4 Nov 21:00 ET = Thu 5 Nov 03:00 CET**. Late = not judged.
- Submission needs: **public repo**, a **3-minute demo video** showing only what was built during the event, all team members listed.
- **New work only:** everything presented must be built during the event (kickoff Mon 26 Oct 12:00 ET). Copy no code from older projects. Open-source libraries and models are fine if their licenses are followed.
- Must use Meta models: Muse Spark series / Muse Wonder / Muse Image / Muse Voice Transcribe / SAM 3.1 via the Meta Model API, or open weights Muse Glimmer / Muse Spark Open. Baseten model id for the hackathon: `meta-models/muse-spark-open-1026`.
- Themes: "Build for Your World" or **"Push the Frontier"** (ours: robotics, "give a machine a new capability").
- Judging: stage 1 pass/fail (fits a theme, uses Meta models); stage 2 scores 0–10 on **Impact 30%, Use of Meta AI tooling 25%, Technical depth 20%, Demo 25%**; stage 3: top 5 per track, finalists' videos are watched live. Indie track looks for "creativity, technical ambition, and whether it works".
- Bonus prizes: most viral (X post engagement until 8 Nov), best build on Meta open-weight models, community vote, best agentic use case, best creative build (Muse Image/Wonder).
- Avoid anything that looks like: medical advice, basic RAG, simple image analyzer, education chatbot, sports coach.
- Never claim "first". Related work: π0 (Physical Intelligence), NVIDIA GR00T, Open X-Embodiment, Mirage, Shadow, MimicGen. Our claim: it reads each robot's blueprint, translates, and proves every translation in simulation.
- Check the license of every robot model before the demo goes out.
- Schedule (CET): live sessions Tue 27 and Wed 28 Oct at 17:00 (Agents 101/102); Meta office hours in Discord #office-hours on weekdays 15:00–16:00 (16:00–17:00 from 2 Nov); closing ceremony Mon 9 Nov 18:00.

## Hardware

- One PC with Windows and Linux on separate SSDs (dual boot): i9-14900K, RTX 3090 24 GB. All robot work (MuJoCo, IK, training) runs on **Linux**.
- Phone: Galaxy S23 Ultra (filming).
- No physical robot. Everything robot-side is simulation.

## Working rules

- Explain in short, simple English (B1–B2): meaning → why → formula.
- Show the plan before building anything new; wait for the user's "go".
- Commit messages: 1–2 words, no trailers (no Co-Authored-By or similar).
- No AI labels in deliverables (README, slides, video).
- Never submit, send or post anything for the user; the user submits the hackathon form.
- Videos: the user's own voice + music the user chooses; licensed assets only.
- Report results honestly, including failed kill tests.
- Keep secrets out of the repo: API keys only in `.env` (gitignored).

## Setup (Linux)

- `conda create -p .venv -c conda-forge --override-channels python=3.12 ffmpeg=7.1.1`, then `.venv/bin/pip install mujoco mink daqp numpy imageio imageio-ffmpeg pillow "lerobot[dataset,training]"`.
- Headless rendering: `MUJOCO_GL=egl`.
- `.venv/bin/python scripts/smoke_test.py` checks MuJoCo, mink and rendering.
- Robot models go to `assets/robots/` (gitignored): `scripts/fetch_robots.sh` (sparse clone of mujoco_menagerie + SO-ARM100).
- `.venv/bin/python scripts/check_robots.py [robot ...]` loads each robot into the scene, moves it, writes `outputs/check/robots.png`.
- `.venv/bin/python scripts/kill_test.py so101 panda --n 10 --seed 0 [--videos none|fail|first+fail|all]` runs the skill card on random layouts; results + videos in `outputs/kill_test/<robot>/`.
- Meta Model API key in `.env` (gitignored), never in code or chat.

## Links

- Event guide (rules, schedule, prizes): https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details
- Meta Model API quickstart: https://dev.meta.ai/docs/quickstart
- API cookbook: https://github.com/meta-models/meta-model-cookbook
- Open-weight cookbook: https://github.com/meta-models/meta-oss-cookbook
- mink (IK for MuJoCo): https://github.com/kevinzakka/mink
- MuJoCo Menagerie: https://github.com/google-deepmind/mujoco_menagerie
- SO-101 model: https://github.com/TheRobotStudio/SO-ARM100
