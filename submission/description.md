# Project description


## Short version

Film a job. See which robot can do it, before you buy one.
Mess with it and it still finishes (cube, in simulation).

SAM 3.1 tracks the hand and the objects in a short video, and Muse Spark writes a skill card. Each of 9 robots checks the card against its own body, says yes or no with a reason, and then tries the job in MuJoCo. Muse Spark and Muse Spark Open also write adapters for new robots from their model files. Everything runs in simulation.

## Long version

### What it does

Film a job. See which robot can do it, before you buy one.
Mess with it and it still finishes (cube, in simulation).

You give Translator a short video of a hand doing a job. Meta AI turns it into a skill card with the objects, the grip, the steps and a success test. The card says nothing about joints or arm paths, so a small arm and a humanoid can both use it.

Each robot checks the card against its own body. If it can't do the job, it says why: "needs two hands", "must walk", "too heavy", "too big for its gripper". The others try it in MuJoCo and find the objects in camera images. A try counts only if the object ends up where the card says.

I have no real robot, so all of this is simulation. A pass means the robot's model passed in MuJoCo.

### Who it's for

People who have a job for a robot and have not picked one yet. Also people who already have robots and don't want to teach each one from zero. Today every robot is taught every task on its own, with hours of demos per robot. Here the same card goes to all of them.

### How Meta models are used

**SAM 3.1 (Meta Model API)** tracks the object, the container and the hand in every frame. From the tracks I read which object moved, when it was grabbed and released, and whether it ended inside the container. In a 30 s clip with 13 lemons on the table, it tracked all 13 and my code found the one that moved.

**Muse Spark 1.3 (Meta Model API)** does three jobs:

- It decides the kind of task (pick and place, open a door, carry), names the objects, watches the video with the facts from SAM, and writes the card as structured JSON.
- It reads a robot's model file and writes the adapter: grip point, gripper values, start pose, where the robot stands. My code measures the adapter and tests it on two skills. If it fails, the numbers, the failures and three replay frames go back to Muse. It gets at most 3 fixes.
- It watches a failed robot try next to the human video, says what went wrong and whether the fix is in the card or in the robot, and proposes card changes. A change stays only if more tries pass on the same layouts.

**Muse Spark Open (open weights, on Baseten and Fireworks)** writes adapters through the same flow. It wrote the uFactory Lite6 adapter on Baseten in 9 s and the Franka FR3 adapter on Fireworks in 21 s. Both passed 10/10 with 0 fixes.

### What I built during the event

The whole project. The repo starts on 26 Oct, after kickoff, and the commits are public. The open-source libraries and robot models I use are listed in the README.

- Translator: card and robot model to waypoints, IK at every control step, physics run, success test
- Vision from each robot's front, top and wrist cameras
- Video to card with SAM 3.1 and Muse Spark
- Robot adapters written by Muse, with the measure, test and fix loop
- Grip practice, and a needs check where robots say no with a measured reason
- 11 skills and 9 robots as JSON files, with a test of every skill on every robot
- Door and carry skills, including two hands on the G1
- LeRobot datasets from checked runs, and one ACT policy per robot
- The loop where Muse checks failed tries against the human video
- A local web app: upload a video, see what Meta AI understood, pick robots, watch them try
- A live loop: 25 Hz, it looks through the cameras and the card decides the next step
- A public site: https://thenguyentrong.github.io/skill-translator/

### Results

- 7 clips from 6 stock videos became cards, each in 52-169 s for $0.07-0.49 of Meta API cost. Lemon, cookie, kiwi and potato went into the skill library.
- Muse wrote adapters for 8 robots from their model files. 6 passed with 9/10 or 10/10. TALOS and Booster T1 got 1/10, so they were not added.
- Every skill on every robot, 10 random layouts each: 611/760 tries passed (80 %) in the 76 cells where a robot can try.
- 7 robots each trained an ACT policy on 200 checked episodes. On 50 new layouts they scored 19/50 to 37/50.
- The check-and-improve loop has run once, on the cookie skill. It found the right problem for 4 of 5 robots, but its change passed no extra tries, so the card stayed the same.
- Live loop on 6 robots with the cube, 7 scripted disturbances, same layouts: a plan made once passed 49/420, the live loop 372/420, and a simple re-plan from the card 398/420. The card is what makes recovery possible; the live loop's difference is that it reacts during the motion. The lemon is harder: 180/420, and G1 and SO-101 fail it.
- On the site, UR5e, Panda and xArm7 run in your browser with MuJoCo. You can drag the cube or knock it out, or set a job and see what 9 robots answer. There the cube position comes from the simulator, and the video step is not on the site.
- SAM 3.1 can referee a robot's clip from video alone: on 40 clean simulated clips it agreed with the simulator 39 times.
- Check and improve: Muse watched failed tries and changed one card field; on new layouts the cookie skill went from 143 to 161 passes, and the gain is the G1 (2/30 to 17/30). I added the field by hand after physics tests, and Muse chose to use it.
- Trained policies are behind planned motion: 19/50 to 37/50. Recovery data gave no gain on UR5e (30/50 vs 33/50).

### What doesn't work yet

- All test videos are Pexels stock clips. I have not tried my own phone video yet.
- The door and carry skills in the library are hand-written. For the real door video and the box video, every robot said no.
- Humanoids move on a sliding base. Their legs don't step.
- Trained policies exist only for pick and place, and they are much weaker than the planned runs.
