# Third-party code, models and media

**Built with Muse Spark Open.**

This file lists everything in Translator that I did not make, the licence for each one, and the credit it needs. State of the repo and site on 4 Nov 2026. Licence names and paths are read from the files. This is a working list, not legal advice.

Paths under `assets/robots/` are downloaded by `scripts/fetch_robots.sh` and are not in this repo. Versions: mujoco_menagerie `f3b6013`, SO-ARM100 `a758567`, humanoid-description `0dd8454`, xSIM_MUJOCO `942469c`.

## Robot models

Only one robot's meshes are published: the UR5e with the Robotiq 2F-85, in `site/public/models/` (reduced from the Menagerie files, and used only for the live page). All other robots appear only as rendered pictures and video in `docs/media/`, the site and the demo video.

Rule for the Menagerie: "XML and asset files in each individual model directory of this repository are subject to different license terms." (`assets/robots/mujoco_menagerie/README.md`). So each model's own `LICENSE` counts, not the top-level file.

| Asset | Source | Licence (file) | What we do with it | Share meshes / show in public? | Required credit |
|---|---|---|---|---|---|
| UR5e | [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) | BSD-3-Clause (`mujoco_menagerie/universal_robots_ur5e/LICENSE`) | Simulated, shown in media, **meshes on the public site** | Yes / Yes | Keep the licence text with the files (done: `site/public/licenses/ur5e-LICENSE.txt`). "Copyright 2018 ROS Industrial Consortium". No use of the names to promote our work. |
| Robotiq 2F-85 | MuJoCo Menagerie | BSD-2-Clause (`mujoco_menagerie/robotiq_2f85/LICENSE`) | Fitted to UR5e, FR3, TienKung 3. **Meshes on the public site** | Yes / Yes | Keep the licence text with the files (done: `site/public/licenses/robotiq-2f85-LICENSE.txt`). "Copyright (c) 2013, ROS-Industrial". |
| SO-101 | [TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) | Apache-2.0 (`SO-ARM100/LICENSE`) | Simulated, shown in media | Yes / Yes | Credit the repo. If meshes are shared: copy of the licence, and say what was changed. |
| Franka Panda | MuJoCo Menagerie | Apache-2.0 (`mujoco_menagerie/franka_emika_panda/LICENSE`) | Simulated, shown in media | Yes / Yes | Credit Menagerie. If meshes are shared: copy of the licence, say what was changed, and add "Copyright 2023 Franka Robotics GmbH" (the upstream `NOTICE` in franka_ros). |
| Franka FR3 | MuJoCo Menagerie | Apache-2.0 plus a BSD text, both in one file (`mujoco_menagerie/franka_fr3/LICENSE`) | Simulated with the Robotiq, shown in media | Yes / Yes | Same as Panda (upstream `NOTICE` in franka_description). If meshes are shared, copy the **whole** file, because the BSD part must stay too. |
| Unitree G1 (with hands) | MuJoCo Menagerie | BSD-3-Clause (`mujoco_menagerie/unitree_g1/LICENSE`) | Simulated, shown in media. The UNITREE logo on its chest is part of the model and can be seen in renders | Yes / Yes | "Copyright (c) 2016-2023 HangZhou YuShu TECHNOLOGY CO.,LTD." Keep the licence text if meshes are shared. Never suggest Unitree supports this project. |
| uFactory xArm7 | MuJoCo Menagerie | BSD-3-Clause (`mujoco_menagerie/ufactory_xarm7/LICENSE`) | Simulated, shown in media | Yes / Yes | "Copyright (c) 2018, UFACTORY Inc." Keep the licence text if meshes are shared. |
| uFactory Lite6 | MuJoCo Menagerie | BSD-3-Clause (`mujoco_menagerie/ufactory_lite6/LICENSE`) | Simulated, shown in media | Yes / Yes | "Copyright (c) 2018, UFACTORY Inc." Keep the licence text if meshes are shared. |
| TienKung 3 | [Open-X-Humanoid/xSIM_MUJOCO](https://github.com/Open-X-Humanoid/xSIM_MUJOCO) | Apache-2.0 (`tienkung_xsim/LICENSE`) | Simulated with the Robotiq, shown in media | Yes / Yes | Credit X-Humanoid and the repo. If meshes are shared: copy of the licence, and say what was changed. The licence is at repo level; the README has no licence section and no copyright holder is named. |
| LimX Oli and its gripper | [limxdynamics/humanoid-description](https://github.com/limxdynamics/humanoid-description) | Apache-2.0 (`limx_humanoid/LICENSE`, README "License" section) | Simulated, shown in media. `scripts/limx_gripper.py` adds their gripper to their MJCF on your machine, so the combined file is not published | Yes / Yes | Credit LimX Dynamics and the repo. If meshes are shared: copy of the licence, and say what was changed. Their `package.xml` still says `<license>TODO</license>`, but the LICENSE file and README are clear. Their files say HU_D04, never "Oli". |
| PAL TALOS | MuJoCo Menagerie | Apache-2.0 (`mujoco_menagerie/pal_talos/LICENSE`) | Tried, named in the README, not added. No images | Yes / Yes | Credit Menagerie. |
| Booster T1 | MuJoCo Menagerie | Apache-2.0 (`mujoco_menagerie/booster_t1/LICENSE`) | Tried, named in the README, not added. No images | Yes / Yes | Credit Menagerie. |
| Kinova Gen3, UR10e, Sawyer, RB-Y1 | MuJoCo Menagerie | Gen3, UR10e: BSD-3-Clause. Sawyer, RB-Y1: Apache-2.0 (each model's `LICENSE`) | Downloaded only, not used and not shown | Not needed | None. |

To add another robot to the live page: copy its `LICENSE` to `site/public/licenses/` first, and for Apache models add a line saying the meshes were reduced.

## Videos (Pexels)

All 8 clips are stock videos, not filmed by me. Details and my edits are in `data/videos/SOURCES.md` (not in this repo; `data/` is gitignored). Raw files stay private.

Licence: Pexels License, section 5 of the [Pexels Terms](https://www.pexels.com/terms-of-service/) (last updated 20 Oct 2026). Free to use and change, credit not needed but welcome (section 6). Not allowed: sharing a clip on its own with only filter, resize or crop, giving the impression I made it, or suggesting a person in it supports this project. Identifiable people may also need their own consent for promotion, which is on the user of the clip to judge.

| Asset | Source | Licence | What we do with it | Credit (optional, but given) |
|---|---|---|---|---|
| Person Putting Orange in Bowl (hand only) | [Pexels 7198787](https://www.pexels.com/video/person-putting-orange-in-bowl-7198787/) | Pexels License | Input to the lemon skill. With SAM boxes in `docs/media/reel.*` and on the site (`lemon_sam.mp4`). In the demo video | SHVETS production via Pexels |
| Young Woman Taking Mug out of Cupboard (seen from behind) | [Pexels 5515109](https://www.pexels.com/video/young-woman-taking-mug-out-of-cupboard-5515109/) | Pexels License | Input to the door card test. With SAM boxes on the site (`door_sam.mp4`) | Ivan S via Pexels |
| A Woman Taking Her Packages Inside (face mostly hidden) | [Pexels 8927178](https://www.pexels.com/video/a-woman-taking-her-packages-inside-8927178/) | Pexels License | Input to the card test for carrying. With SAM boxes on the site (`carry_sam.mp4`) | Kampus Production via Pexels |
| A woman is moving boxes in a room (face visible) | [Pexels 4554453](https://www.pexels.com/video/a-woman-is-moving-boxes-in-a-room-4554453/) | Pexels License | Input to the check that says no. With SAM boxes in the demo video | cottonbro studio via Pexels |
| A Person Transferring Cookies on the Plate (hand only) | [Pexels 4110527](https://www.pexels.com/video/a-person-transferring-cookies-on-the-plate-4110527/) | Pexels License | Input to the cookie skill. Clip not published | Polina Tankilevitch via Pexels |
| Person Putting a Kiwi on Bowl of Fruits (hand only) | [Pexels 6989169](https://www.pexels.com/video/person-putting-a-kiwi-on-bowl-of-fruits-6989169/) | Pexels License | Input to the kiwi skill. Clip not published | Kaboompics via Pexels |
| A Person Putting Potato in a Basket (hand only) | [Pexels 7876937](https://www.pexels.com/video/a-person-putting-potato-in-a-basket-7876937/) | Pexels License | Input to the potato skill. Clip not published | Tima Miroshnichenko via Pexels |
| A Man Opening and Closing Drawers from a Cabinet (no face) | [Pexels 8987274](https://www.pexels.com/video/a-man-opening-and-closing-drawers-from-a-cabinet-8987274/) | Pexels License | Downloaded, never run. Not published | Artem Podrez via Pexels |

## AI models

| Asset | Source | Licence | What we do with it | Required credit |
|---|---|---|---|---|
| Muse Spark Open | [Meta, Hugging Face](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B/blob/main/LICENSE.md) | Muse Model License (LICENSE.md in that repo), with its Usage Policy | Called on Baseten and Fireworks (`translator/adapter_writer.py`). Wrote the Lite6 and FR3 adapters in `robots/muse/`. No weights in this repo | **"Built with Muse Spark Open"**, shown prominently in the UI, docs or website (section 2). Meta claims no ownership of outputs (section 4). The licence also covers models trained using outputs, so publishing the FR3 policy weights would need the licence and Usage Policy with them |
| Muse Spark 1.3, SAM 3.1 | Meta Model API | API terms. I could not find them to read, so this is **not confirmed** | Called over the API. Their output is in `cards/` and `robots/muse/`. No weights here | Named in the README |
| SmolVLA (`lerobot/smolvla_base`) and SmolVLM2 | Hugging Face | Apache-2.0 (`license:` line in each cached model `README.md`) | **Not used.** Downloaded on 28 Oct. No code uses it and `outputs/train/` has no run. Only named as a future idea | None while unused |
| ACT policies (mine) | Trained with LeRobot on my own simulated data | Backbone: `ResNet18_Weights.IMAGENET1K_V1`. Licence of those weights **not checked** | Only videos of the policies are published. No weights in this repo or on the site | Check before publishing any weights |

## Libraries

| Asset | Source | Licence (file) | What we do with it | Required credit |
|---|---|---|---|---|
| MuJoCo 3.17 (Python) | [google-deepmind/mujoco](https://github.com/google-deepmind/mujoco) | Apache-2.0 (`.venv/.../mujoco-3.17.0.dist-info/licenses/LICENSE`, plus `LICENSES_THIRD_PARTY.md`) | Simulation. Installed, not shipped | Named in the README |
| @mujoco/mujoco 3.17 (browser) | npm, same repo | Apache-2.0 (`license` field in `site/node_modules/@mujoco/mujoco/package.json`; the package has no LICENSE file) | **Shipped** as `site/public/vendor/mujoco.js` and `mujoco.wasm` | Copy of Apache-2.0 and the third-party list must go with the files |
| three.js 0.170 | [mrdoob/three.js](https://github.com/mrdoob/three.js) | MIT (`site/node_modules/three/LICENSE`) | **Shipped** in `site/public/vendor/`, including OrbitControls and other add-ons | Copyright and licence text must go with the files |
| mink 1.3.0 | [kevinzakka/mink](https://github.com/kevinzakka/mink) | Apache-2.0 (`.venv/.../mink-1.3.0.dist-info/licenses/LICENSE`) | Inverse kinematics. Installed, not shipped | Named in the README |
| LeRobot 0.6.1 | [huggingface/lerobot](https://github.com/huggingface/lerobot) | Apache-2.0 (`.venv/.../lerobot-0.6.1.dist-info/licenses/LICENSE`) | Datasets and ACT training. Installed, not shipped | Named in the README |
| Archivo, Martian Mono fonts | Fontsource npm packages | SIL OFL 1.1 (`site/public/licenses/archivo-OFL.txt`, `martian-mono-OFL.txt`) | **Shipped** in `site/public/fonts/` | Licence files are already published with the site |
| Torch, torchvision, numpy, Pillow, imageio, FastAPI, uvicorn, PyAV | PyPI | BSD or MIT family (package metadata in `.venv`) | Installed, not shipped | None |
| qpsolvers | PyPI | LGPL (package metadata) | Installed, not shipped or changed | None |
| ffmpeg (GPL build, with x264) | conda-forge | GPL (`.venv/conda-meta/ffmpeg-7.1.1-gpl_*.json`) | Used on my machine to cut video. The program is not shipped, and GPL does not reach the videos it makes | None |

## Not checked

- Music and voice for the demo video: no files exist yet.
- Google Fonts in the local web app (`web/static/index.html`): loaded at run time, nothing stored, app not public.
- Meta Model API terms: see above.
- pexels.com/license itself: it blocks automated reading. The terms above come from an archive copy of the Terms page dated 27 Oct 2026.
- The event rules page did not load for me, so the rule on rights is taken from the brief.
- This repo has no licence of its own yet, so others have no right to reuse my code.
