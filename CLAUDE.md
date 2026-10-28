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

**Vision from the robot's own cameras (26 Oct night)**
- `translator/perceive.py` (`Eyes`): front + top camera, colour mask (red cube, green bowl) + metric depth → 3D points → cube centre (top face), cube yaw (smallest bounding box), bowl centre (circle fit on the rim). Colour step = stand-in for SAM 3.1 text prompts. Accuracy on 150 layouts: cube ~2.5 mm, yaw ~1–2° (max 8°), bowl ~2 mm; top camera is usually blocked by the arm at home, the front camera always sees.
- Kill test now uses camera vision by default (`--eyes sim` = old perfect knowledge). Official seeds 0–9: **SO-101 10/10, Panda 10/10**. Unseen 1000–1049: SO-101 48/50, Panda 44/50, UR5e 48/50.
- Also changed: gripper closes over 0.4 s (Robotiq no longer shoves the cube), grip direction chosen by IK reachability (the translator tries all 4 face pairs), arm origin = first arm joint axis (SO-101 pan axis is 3.9 cm in front of its base frame), robot parts split into turning footprint + fixed obstacles, home pose clipped to joint limits, `ready` pose in the adapter.

**G1 humanoid: WORKS (27 Oct ~01:00)** - kill test **9/10** (seeds 0-9, camera vision), unseen 1000-1049 **47/50** (2 ik = target across its body, 1 grasp).
- `g1_with_hands.xml` (Dex3), pelvis welded, right arm + hand active, `ready` pose with the hand above the table. Hand = 7-motor "gripper" with open/closed poses (adapter tuples).
- Why the old grasp failed: Dex3's two fingers are ~39 mm apart (a 30 mm cube fits between them) and palm-down the short thumb lies flat. Fix = thumb-index pinch with the hand turned 34° (grip site quat in the adapter) so the thumb-index line runs through the cube; poses from `scripts/grasp_design/search.py` (geometric: opposite faces, same moment, flat pads, no table/cube touch before) + physics check in `scripts/grasp_design/rig.py`.
- Lesson: a mocap-teleported hand cannot lift anything in MuJoCo (friction is velocity-based); the rig drives the hand on an x-y-z gantry with motors. All earlier rig results were invalid because of this.
- IK now keeps forearm+hand (from the 4th arm joint) 1 cm away from the robot's other parts (mink CollisionAvoidanceLimit); arms' numbers unchanged (SO-101 10/10 48/50, Panda 10/10 44/50, UR5e 48/50).

**Pitch idea (user, 26 Oct night, saved for the pitch/video)**
- Two stages: (1) **learning** = video → skill (Muse analyses, tests, builds the skill file); (2) **repeating / imitation** = skill → every other robot.
- Teacher metaphor (his mother is a teacher): you teach the whole class the same material once, but every student *understands* it differently; that is the hard, expensive part (video → skill). But people are very good at *repeating* a physical task once it is shown and checked (work stations). So: learn and test the skill once, then each robot only repeats it on its own body.
- Cost story: price of making a skill once vs price of each repeat on a new robot vs what is saved because nobody re-learns the skill per robot. Put real numbers on it (GPU minutes, API cost, demo hours).
- Honest contrast with RL: you must hand-write goal, reward and task; if lucky you get a good policy, if unlucky you burn compute for nothing. Real-world video + a checked skill gives a direct, cheaper path. Avoid buzzwords ("agentic physical AI").

**Product idea (user, 26 Oct)**: a web tool: upload a 5–10 s phone video of one task → skill card → pick robots from a library or upload your own model (MJCF/URDF) → it translates, runs the sim (cloud GPU, e.g. Modal credits) and shows each robot doing it, so one demo scales to many robots. Fits the judging: Impact 30 % ("could become something people use"), Demo 25 % ("holds up live"). Plan shown, waiting for "go".

**Day 1 end (26 Oct, ~21:00): pushed** `translator`, `readme`, `cleanup`, `status` to main. **27 Oct ~01:30: pushed** `g1` (G1 grasp, self-collision IK, 4-robot README video). README has hero.gif/mp4 + vision/robots images (`scripts/make_media.py` re-makes them).

**27 Oct night (user asleep, said "do all steps, run e2e, add a skill library, test more robots, simple swap"): NOT pushed, all local**
- **E2E works (video → robots):** `scripts/run_job.py <video>`: Muse Spark names the objects → SAM 3.1 tracks object/container/hand → `translator/events.py` (moved object, grab, release, ends inside) → Muse Spark writes the card (Responses API, `text.format` json_schema) → each robot practises + runs. Short clip (Pexels 7198787, 3 s): $0.07, 71 s. Full 30 s clip: SAM tracked 13 lemons, picked the one that moved, same card; $0.49 (mostly SAM), 169 s; UR5e 3/3, Panda 3/3.
- **Robot library = one JSON per robot:** `robots/*.json` (hand-written: so101, panda, ur5e, g1) and `robots/muse/*.json` (written by Muse). `translator/robots.py` loads them; `build("<name>")` or `build("path/to/adapter.json")`. Paths relative to `assets/robots/`. `scripts/fetch_robots.sh` now also fetches lite6, TALOS, Booster T1, RB-Y1, FR3, Sawyer, UR10e (menagerie), LimX Oli (`limx_humanoid`), TienKung 3 (`tienkung_xsim`).
- **Skill library = one JSON per skill in `cards/`:** cube_to_bowl, lemon_to_bowl (Muse-written from the video), ball_to_cup, can_to_bin (square bin), block_to_plate (6x2.5x3 cm block gripped across its narrow side). `scripts/matrix.py` = every skill x every robot (practice + N camera-vision trials, one clip per cell) → `outputs/matrix/`. `scripts/make_reel.py` = run recording (video+SAM boxes → card → robot grid) and `--poster` (skills x robots image).
- **Practice step (new, general):** `translator/practice.py` tries grip depths (-10..+20 mm past the object's centre) on 12 practice layouts (seeds 90000+, never test seeds), keeps the best; cached in `outputs/practice/<robot>__<card>.json`. Why: lemon slipped because Robotiq pads close on an arc / SO-101 jaw is long. Fingertips never go below table+3 mm (`Scene.tip_reach`, measured from the model).
- **Muse writes adapters for unseen robots:** `scripts/write_adapter.py <model file> --name X [--model meta|baseten] [--fix-model meta|baseten] [--pass N]`. Muse gets the XML (+ included files) + `blueprint.facts`; the translator measures the adapter (`blueprint.measure`: hand direction, finger travel, gripper gap, robot height in the world, what the hand bumps into, parts touching the table) and tests it (practice + 5 camera trials each on cube_to_bowl and block_to_plate; a robot cutting into the table counts 0); failures + 3 replay frames go back; max 3 fixes; only passing adapters go into `robots/muse/`. Reports: `outputs/adapters/<name>/report.json`.
  - **Results:** xArm7 10/10, 0 fixes, $0.02 · UR5e (Muse picked the Robotiq from the tool list; same axes as my hand-written one) 10/10, 0 fixes, $0.02, and 50/50 on all 5 skills like the hand-written one · Lite6 10/10, 0 fixes, 9 s on **Baseten Muse Spark Open** · TienKung 3 + Robotiq on wrist 10/10, 0 fixes, $0.05 · LimX Oli + Robotiq 8/10 after 2 fixes, $0.17 (fix 1: pads touched the wrist → tool moved out; fix 2: hand started below the table) · TALOS 1/10 after 3 fixes (gripper closes only to ~37 mm at the chosen grip point), Booster T1 1/10 after 3 fixes (4-joint arm, no wrist) → not added. An `oli_v2` retry with `--pass 10` reached only 6/10 (round 1), so the first Oli adapter stays: Muse results vary between runs on hard humanoids.
- **Other general fixes:** torque motors → position servos at load (`scene._position_servos`, kp = 5 x torque limit; gripper motors kept); Panda gripper gain x10 (`grip_force_gain`, menagerie hand squeezes ~1.5 N vs real 70 N); objects have rolling + torsional friction (condim 6); success test allows 5 mm (an object resting on the bowl wall failed before); layout sampler can no longer loop forever and explains why when there is no room; failure labels scale with the card's heights; box yaw resolves long vs short side; grip chooses the face pair that matches the card's grip width; footprint ignores the arm from its 3rd joint on; "too big": if a gripper cannot open as wide as the object (measured), the robot says no instead of trying.
- **Matrix with the first 5 skills (27 Oct ~23:50, 10 camera trials per cell):** 304/380 = 80 %. UR5e 50/50, xArm7 50/50, TienKung 3 48/50, Lite6 29/30 + "too big" for can/lemon (opens 41 mm), Panda 40/50, G1 36/50, SO-101 33/50 (ball 2/10, lemon 5/10: round things near its jaw limit), Oli 18/50 (IK: reach limits from where it stands; vision is fine, 1-2 mm).
- **3 more videos → 3 more skills (28 Oct ~00:30):** a helper agent found Pexels clips (cookie onto plate 4110527, kiwi onto fruit bowl 6989169, potato into wire basket 7876937; `data/videos/SOURCES.md`). `run_job` on each: $0.07-0.09, 52-85 s; Muse wrote sensible cards (kiwi test = "on top"). Added as `cards/cookie_to_plate`, `kiwi_to_bowl`, `potato_to_basket`. **Matrix now 8 skills x 8 robots: 423/560 = 76 %** in the 56 cells a robot can try; "too big" (Lite6, 41 mm gripper) and "no room" (40 cm basket outside SO-101/G1/TienKung reach) are reported instead of tried. run_job/matrix no longer crash on a robot that cannot place the objects; `run_job --robots-only` re-runs only the robots of an earlier job.
- **UR5e policy on the video skill (lemon_to_bowl): 35/50 (70 %)** on new layouts (temporal ensemble 32/50) = the whole chain video → card → translated runs → policy works.
- **G1 humanoid policy (cube): 37/50 (74 %)** (temporal ensemble also 37/50). **Panda policy (cube): 19/50 (38 %)** (temporal ensemble 8/50; misses = not lifted 26, dropped 4). All four: 200 eps, ACT 40k steps, ~40 min each on the 3090; evals in `outputs/eval/<robot>_<skill>_040000*.json` + clips.
- **First trained policy:** SO-101 ACT, 200 eps, 40k steps (~45 min): **24/50 (48 %) on 50 new layouts** (seed 5000+), 5/20 at 10k steps. Temporal ensemble 15/50, 25-step chunks 14/50 → default (100-step chunks) is best. Misses are mostly "not lifted" (closes next to the cube). LeRobot's default recipe is 100k steps; more steps/data is the obvious next try.
- **Media:** `scripts/make_reel.py` (video + SAM boxes → card → robot grid, 1920x1080; `--poster` = skills x robots image). README now leads with `docs/media/reel.gif` (+ reel.mp4, matrix.png). `scripts/run_job.py <video>` now practises grips, runs every library robot and writes `outputs/jobs/<video>/reel.mp4`. `scripts/watch.py <robots> --skill <skills>` (+ `--list`) = live viewer for any pair.
- **LeRobot data + training:** `scripts/make_dataset.py` (helper agent; SO-101 cube 200 eps in ~6 min alone, 98 % kept) and `scripts/eval_policy.py` (closed-loop ACT eval, same observation code as the dataset; replaying recorded actions passes 5/5). 200-episode sets: so101 cube, ur5e lemon (the video skill), panda cube, g1 cube. ACT 40k steps per robot, run one after another (all done 02:43), outputs in `outputs/train/act_<robot>_<skill>`, 50-trial evals in `outputs/eval/`.
- **Artifact** https://claude.ai/artifact/V2EM27tcDwmzKAUVz6z4yg updated (version 5, 28 Oct 02:50) with all results incl. the 4 policies + 2 policy clips.
- **Meta API spent tonight:** about $3 (estimate from the logs; reports were overwritten by reruns). Baseten: a few calls.
- **Fireworks (28 Oct ~03:15):** $100 hackathon credits; `FIREWORKS_API_KEY` in `.env`. Fireworks hosts Muse Spark Open (`accounts/fireworks/models/muse-spark-open`: images + json_schema work, ~11 s). `adapter_writer.OPEN` now has two hosts (baseten, fireworks); `write_adapter.py --model fireworks --fix-model fireworks`. **Franka FR3 (no hand in its model; Muse picked the Robotiq) 10/10 first try, 21 s** → `robots/muse/fr3.json`. Matrix row: **FR3 80/80** on all 8 skills → **matrix now 9 robots: 503/640 = 79 %** (64 triable cells); README, poster (`docs/media/matrix.png`) and artifact v6 updated.
- **Second skill kind: open a hinged door (28 Oct ~03:50):** cards now have `kind` ("pick_place" default, "open"); `cards/open_cabinet.json` (20x16x30 cm cabinet, door hinged left, 14 mm bar handle at 17 cm, success = door >= 60 deg). Scene: fixed cabinet + door on a damped hinge with friction + bar handle (`scene._add_cabinet`, `cabinet_frame`, `handle_path`; `_sample_cabinet` puts it facing the robot +-20 deg with the whole handle arc inside 25-85 % of the reach, else "no room"). Eyes: cabinet pose from its top face (~1 mm, <0.3 deg); the red handle is only a few pixels from above, so it only says which face is the front and which side the hinge is not, its position comes from the card (`Eyes._find_open`). Translate (`_open_waypoints`): joint-space move to above the pre-grasp (IK from 12 start poses, `IK.reach`), down in front of the handle, approach, close, pull along the hinge circle in 10 deg steps with the hand turning with the door; only if that misses by > 1 cm, a plan where the hand may turn about the bar (`free_turn`, cheap rotation about the hand's third axis). Open cards only: IK keeps the arm (not the hand) off the table and cabinet body. Labels: not_reached, missed_handle, slipped_off_handle, door_not_open; new measured check **too_thin** (closed gripper wider than the handle; else the gripper closes further than the adapter's value). Muse side ready, not called: `card_writer.OPEN_SCHEMA`, `name_objects` returns `kind`, `run_job` passes it. Bugs found: MjSpec reads joint ranges in degrees (door stopped at 1.75 deg); door/cabinet contact excluded.
  - **Matrix row, 10 camera trials each after practice:** Panda 9/10, xArm7 9/10, UR5e 8/10, FR3 8/10, TienKung 3 8/10, SO-101 4/10, Oli 3/10, G1 1/10, Lite6 too thin (closes only to 23 mm) = **50/80 in the 8 cells that can try**. Misses: humanoids mostly not_reached (G1 9, Oli 7: the pre-grasp/arc is outside their arm's reach with the hand level; G1 reach 0.35 m), SO-101 (5 joints) cannot turn its hand with the door (door stops ~30-55 deg). Matrix now 9 skills x 9 robots (old 72 cells unchanged); clips `outputs/matrix/open_cabinet__*.mp4`, poster `outputs/reel/matrix.png` regenerated (docs/media not updated). Pick-and-place unchanged: kill test so101 5/5, panda 5/5; cube_to_bowl x so101 10/10; smoke test ok.

- **Third skill kind: carry (28 Oct ~05:00).** `cards/carry_crate.json` (two side handles, 1 kg, 1.7 m to table B) and `cards/carry_basket.json` (one top handle, 0.5 kg). Code: `translator/carry.py` (objects, crate builder with red walls + grey handles + green mark + table B, layout, plan + run, success = on the mark within 10 cm, tilt < 10 deg), `translator/mobile.py` (root welded to a mocap target; back off / turn / go / turn / step in; moves < 30 cm slide straight; base lifted by the measured weld sag; robot-floor contacts off), `ik.HandsIK` (one or two hand targets, per-arm self-collision, start pose clipped into joint limits; the old clip compared ints to pybind enums and never ran). Scene: `kind == "carry"` branches, noslip 5 only for carry, `_robot_spec(keep_free=...)`, second-hand site from `left` in the adapter. Adapters: G1 `hands: 2`, `mobile: true`, `left` block (mirrored site/fingers), `handle_open` (middle finger straight) / `handle_release` (thumb straight); TienKung 3 + Oli `mobile: true`. Per-robot decision: side handles need 2 hands ("two_hands"), no handles = "two_hand_grip" (not built), fixed base + places out of reach = "must_walk", no base pose where the hand gets palm-down onto the handle = "handle_too_high/low" (measured by a work-pose IK search, cached per scene). Perception: crate centre/turn from its red walls in the robot cameras (1-3 mm); the mark on table B comes from the card (not in the start cameras). Muse: `CARRY_SCHEMA` / `CARRY_INSTRUCTIONS` / `_carry_card`, name prompt kind enum now pick_place / open / carry. Practice for carry: depths 0/10/20 mm below the bar, 6 tries. **Matrix (10 camera trials): G1 crate (two hands) 10/10, G1 basket (one hand) 10/10, TienKung 3 basket 10/10, Oli basket "handle too high" (8 cm short at best from every base pose; it once "succeeded" by catching the basket crooked, so it now says no), every arm: crate "two hands", basket "must walk"; TienKung/Oli crate "two hands".** ~6 s wall per G1 trial. Box video re-run (old pick-and-place card, no handles): G1 now "has 2 hands, but two-hand holding only by handles so far"; others unchanged; a fresh Muse run with the carry kind is needed for a carry card. Clips show "base slides, legs do not step"; humanoid door clips now from the right side (door visible); poster rebuilt (`outputs/reel/matrix.png`, docs/media not updated). Regression: smoke ok, kill test so101 5/5 panda 5/5, cube so101/panda 10/10, g1 9/10, door unchanged.

**OPEN (start here tomorrow)**

**Tomorrow (29 Oct), in order** — status end of 28 Oct 06:00, pushed:
1. **Policies (imitation learning):** train UR5e lemon on the recovery dataset (`outputs/datasets/ur5e_lemon_to_bowl_push_200`, 200 eps, done) 40k steps + eval; resume the old UR5e run to 100k + eval; fine-tune SmolVLA (`lerobot/smolvla_base` + SmolVLM2 downloaded; check input_features / rename_map for our 3 cameras + 7-dim state). Commands ready in `scratchpad/queue/train_queue2.sh` (stopped before training). Compare all with UR5e 35/50 (seeds 5000+). Then pick the best recipe for every robot. RL only as an optional final polish (user to decide: pitch is "learn once, repeat cheaply").
2. **Web app polish:** dark header padding, robot reasons with raw names ("small_cardboard_box", "the so101"), phone headline orphan, thumbnails per skill; test one fresh upload end to end (~$0.10) and the train button; then plan the cloud (Vercel page + Modal GPU worker; Modal prices noted below).
3. **Check-and-improve loop:** rerun on cookie with FIELD_HELP + tried-changes history; consider a grip-height / edge-pinch card field.
4. **Next kinds:** two hands without handles (palm squeeze), humanoid stepping back to open a full-size door, door/carry datasets.
5. **Hand-in:** 3-min video (user's voice + music), licence check of every robot model, final README, submit by Wed 4 Nov (user submits).
6. **Known bugs:** SO-101 `gripper_gap` reports 341 mm wide open (one-jaw gripper, a ray misses) -> "too big" texts show a wrong number; the web app's check did not start after a fresh card (fixed 28 Oct, worker chains learn -> check).


- **One command card → trained policies:** `scripts/train_job.py <card.json | run_job folder> [--robots ...] [--episodes 200 --steps 40000 --trials 50]`: datasets in parallel (CPU), ACT one at a time (GPU), each 50-trial test runs while the next robot trains; skips finished steps; writes `outputs/train_jobs/<card>/report.{json,md}` + logs. Smoke test (xarm7, 12 eps, 200 steps, 3 trials) ran the whole chain. Real run started 28 Oct 03:45: lemon_to_bowl on xarm7, fr3, tienkung3 (the Muse-written adapters). TODO: `run_job --train` calling it (wait until the door work stops editing run_job/scene).
- **Needs check (28 Oct ~04:30):** cards may carry `needs` {hands, move_m, mass_kg, keep_upright, fragile, guessed}; Muse's card schemas ask for them (`card_writer.NEEDS_SCHEMA`). `scene.check_needs` + `Scene.refusal` (too_big / too_thin / two_hands / must_walk / too_heavy) run before "no room" in matrix/run_job/execute. Payload = `payload_kg` in the adapter (maker rating: panda 3, fr3 3, ur5e 5, xarm7 3.5, lite6 0.6, g1 2) else `Scene.measure_payload` (static limit from torque limits at the ready pose; higher than a safe load). Robot fields `hands`, `mobile` (all 1/False until the G1 two-hand + walk work lands). Name prompt now decides the kind first. **Door video** → Muse open card of the real 1.9 m hutch (55 cm door) → every robot "no room" (arc out of reach). **Box video** → needs 2 hands / 2 kg / 0.8 m → every robot refuses with a reason (too big for 5, two hands for xarm7/so101/g1). Oli: see-through collision geoms (group 0, alpha < 1) now hidden in `build` (only Oli had them; matrix row unchanged). Artifact v7: door section, needs section, "How it works, step by step" table, "Still open" list. README not yet updated for door/needs.
- **Oli with LimX's own gripper (28 Oct ~05:40):** `scripts/limx_gripper.py` (called by fetch_robots.sh) builds `HU_D04_01_gripper.xml`: official MJCF + LimX short wrist + gripper subtree from their URDF (mimic pairs -> joint equalities, one position actuator per side, effort 1 Nm, `{side}_pinch` sites). Muse wrote the adapter: 9/10 after 3 fixes, $0.27. `gripper_closed` 0.7 (fingertips meet; 1.0 = past contact, practice dropped). Old Robotiq Oli -> `outputs/adapters/oli/oli_robotiq.json` (26/80 pick-place); new Oli 40/80 pick-place, door 5/10, carry_basket 10/10. Also: `tool_replaces_hand` adapter flag (deletes the tool body's geoms, adds a flange); see-through group-0 collision geoms hidden; `gripper_gap` falls back to finger-to-finger distance when rays start inside crossed fingertips (two-finger grippers only; only Oli's numbers changed). Matrix now 11 skills x 9 robots: **611/760 = 80 %**. `make_reel.py --robot <name>` = one robot, every skill.
- **Meta AI check-and-improve loop:** `translator/review.py` (judge: Muse watches human video + robot clip -> same_task / looks_done / cause / fix_in card|robot; improve: Muse proposes changes to a fixed field list; apply) + `scripts/review_job.py <job> [--rounds 2]` (keeps a change only if more tries pass on the same layouts and no robot loses >1). matrix.cell with video="fail" saves `<skill>__<robot>_fail.mp4`. First run (cookie): diagnosis right ("closes but never holds; the person pinches the edge"), change = grip.width 0.06->0.04, 50->50, not kept, $0.17. Since then Muse gets FIELD_HELP (grip.width only sets the opening) and the list of tried changes. Next: rerun, maybe add an edge-pinch/grip-height field.
- **Policies:** lemon via train_job on Muse-written adapters: xArm7 33/50 (66 %), TienKung 3 29/50 (58 %), FR3 26/50 (52 %); 2 h 17 min for all three. Artifact v8 (Oli video, carry section + video, loop section, new diagram with META AI tags and the loop).
- **User picks robots (28 Oct):** `run_job.py <video> --check` = card + every robot's yes/no with the measured reason, no tries (seconds, only the ~$0.10 card); then `--robots-only --robots X Y --train` runs and trains only those. Cost estimate given to user (Modal prices 28 Oct: L4 $0.80/h, A10 $1.10/h, H100 $3.95/h, CPU $0.047/core-h): ~$1 to test a skill on every robot, ~$2 per robot for a trained policy (cloud GPU times scaled from the 3090, not measured).
- **Training fixes (28 Oct ~06:00), all imitation learning:** (1) recovery data: `make_dataset.py --push R` adds a smooth random push (OU, ~0.5 s, up to R rad, calm during close/lift) to the executed arm command while the clean planned command is recorded (`scene.push(label)` hook in `execute.run`, `scene.command`); UR5e lemon with --push 0.1: 86 % of runs pass. (2) the 40k UR5e run resumed to 100k. (3) SmolVLA (lerobot/smolvla_base) fine-tune next. Queue: `scratchpad/queue/train_queue2.sh`, logs `diag/queue2.log`, compare against UR5e 35/50 on seeds 5000+. User asked about RL: today pure IL + grip practice; proposed RL only as a final polish in sim with the card's success test as reward (asked user).
- **Local web app (28 Oct ~06:00, first version, runs):** `scripts/web.sh` -> http://127.0.0.1:8000 (FastAPI + uvicorn + python-multipart installed in .venv). `web/app.py` = JSON API that only starts processes and reads files; `web/worker.py` runs each step in its own process (learn = card stage, check = every robot's yes/no, try = practice + N tries per picked robot) and writes `outputs/jobs/<video>/web/<step>.json`; train starts `scripts/train_job.py <job> --robots X` (refused while any lerobot-train/train_job runs: one GPU). `web/static/` = index.html + app.js + style.css, no build step (could move to static hosting; workers to Modal later). Page flow: drop/upload (cut to 15 s, 1280 px, no sound) or pick a library clip (thumbnails) -> "What Meta AI understood" (Meta stages with s and $, SAM overlay, card in plain words, Muse's notes) -> robot cards with "Can try" or the measured reason -> pick -> "Watch them try" (clip + score per robot, "Train its own policy" button) ; Robots tab = library cards. `run_job.py` refactored into `learn()`, `check()`, `try_robot()` (CLI unchanged). Tested by clicking through with headless Playwright: cookie card reused, UR5e 2/2 run from the page, box video answers, light/dark/phone (no sideways scroll); screenshots `outputs/preview/web_*.png`. Not tested yet: a fresh upload end to end (costs ~$0.10), Train from the page (GPU was busy), door/carry cards in the card view (renderer has branches, unseen). Rough edges: thumbnails come from the cube_to_bowl matrix clips (robots without one show no picture); tries run one robot after another; no cancel button.
- **28 Oct decisions (user):** do the full plan: door (1 hand), card says what a task needs (hands, move, mass, keep upright) + per-robot yes/no with reason, two hands (G1), walking = **option A: base slides, legs do not step, said plainly** (real stepping = later stretch on G1 only), one command video → trained policies, "how it works" process section in the artifact. Make it work locally first (cheaper); later everything runs in the cloud, nothing local. Card v2 fields proposed: kind, needs, object mass/fragile, keep_upright, success as a measurable test, what is free vs fixed, per-field confidence.
1. ~~Keys~~ **done 27 Oct:** `MODEL_API_KEY` + `BASETEN_API_KEY` in `.env`, both tested OK (paid calls go through). Still for the user: film the skill video; check the credit balance on the dev.meta.ai dashboard (I can't log in there).
2. ~~G1 grasp~~ done (9/10). Possible later: let G1 use its waist or left arm for targets across its body.
3. **Tested 27 Oct:** Meta `/v1/models` lists muse-wonder-1.0, muse-spark-1.3 (+1.2, 1.1, -contributor), sam-3.1, muse-image-1.0, muse-voice-transcribe-1.0. Muse Spark thinks a lot by default: set `reasoning_effort` ("minimal" = 46 tokens out, $0.0002; "low" = 370 out) and give `max_tokens` room, else `content` is empty. Baseten: OpenAI-compatible `https://inference.baseten.co/v1`, Bearer key, models `meta-models/muse-spark-open` and `meta-models/muse-spark-open-1026` (works). Prices: Spark $1.25/M in, $4.25/M out; SAM video $0.20 per 1,000 frames (min 50 per request).
   **Meta API facts** (official quickstart, read 26 Oct): OpenAI-compatible, base URL `https://api.meta.ai/v1`, model `muse-spark-1.3`, input text/image/pdf/**video**, Responses API `POST /v1/responses`, `Authorization: Bearer $MODEL_API_KEY`, `pip install openai`. Still to check: SAM 3.1 endpoint + video/text-prompt format, video size limits, structured JSON output, open-weight Muse Spark Open on Baseten/Modal.
4. **Modal:** has an official MuJoCo (mjlab) example; check it for headless EGL on GPU before planning the cloud worker.
5. **Web tool (user's idea):** plan in the product idea above; waiting for "go" after items 3–4.
6. **Panda drops ~10 % on unseen layouts** (weak menagerie gripper, ~1.5 N); fine for data generation, hurts the 50-trial number.
7. **UR5e adapter** is hand-written; Wednesday's goal needs Muse to write it from the model file.
8. Robot model licenses: check before the demo goes out (menagerie: Apache-2.0 / BSD; SO-ARM100: Apache-2.0).
9. **Wrist camera is virtual** (no body; 10 cm behind the grip point, 5 cm to the side). On SO-101/G1 it floats next to the hand, on Panda it is partly inside the hand. For realism: SO-101 has an official camera mount model (`so101_new_calib_camera.xml`, 32x32 UVC module); give Panda/UR5e a typical wrist-cam mount position.

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
