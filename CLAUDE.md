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

- 26 Oct: idea chosen. Meta Model API account created; payment method and credit claim still pending (user). Partner credits (Baseten, Modal, Fireworks) requested or pending. Repo created. No code yet.
- Linux side: MuJoCo, LeRobot and an SO-101 model may already be installed there. Check what exists and which versions before installing anything.

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

- Python 3.12 venv; `pip install mujoco mink daqp numpy imageio imageio-ffmpeg pillow`; LeRobot (`lerobot[dataset,training]`, needs Python ≥ 3.12 and ffmpeg).
- Headless rendering: `MUJOCO_GL=egl`.
- `python scripts/smoke_test.py` checks MuJoCo, mink and rendering.
- Robot models go to `assets/robots/` (gitignored; fetch with a script: sparse clone of mujoco_menagerie + SO-ARM100).
- Meta Model API key in `.env` (gitignored), never in code or chat.

## Links

- Event guide (rules, schedule, prizes): https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details
- Meta Model API quickstart: https://dev.meta.ai/docs/quickstart
- API cookbook: https://github.com/meta-models/meta-model-cookbook
- Open-weight cookbook: https://github.com/meta-models/meta-oss-cookbook
- mink (IK for MuJoCo): https://github.com/kevinzakka/mink
- MuJoCo Menagerie: https://github.com/google-deepmind/mujoco_menagerie
- SO-101 model: https://github.com/TheRobotStudio/SO-ARM100
