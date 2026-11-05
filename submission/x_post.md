# X post

You post these yourself. Lines tagged depend on tonight's tests: delete them if a test fails, delete only the tag if it passes. Limits: every post stays under 280 characters.

Check the event rules or Discord for a required tag or hashtag. CLAUDE.md does not name one.

## One post

Film a job. See which robot can do it, before you buy one.
Mess with it and it still finishes (cube, in simulation).

One short video, 9 simulated robots. Each one checks its own body, says yes or no, then tries it.

Solo build for the Meta Global AI Developer Hackathon.
[VIDEO LINK]

Media: the demo video. `docs/media/matrix.png` also works. `docs/media/reel.mp4` is older and shows 7 robots, so don't use it with "9 robots".

## Thread

Post 1: the post above.

Post 2:
A 3 s clip of a hand putting a lemon in a bowl. SAM 3.1 tracks the hand and the objects. Muse Spark writes a skill card with the objects, the grip, the steps and a success test.

Meta API cost: $0.07.

Post 3:
Each robot checks the card against its body. Some say no and give the reason: "needs two hands", "must walk", "too heavy".

The rest try it in MuJoCo. 611 of 760 tries passed, over 11 skills and 9 robots.

Post 4:
For a new robot, Muse reads the model file and writes the adapter. I tried 8 and 6 passed. TALOS and Booster T1 failed, so they're not in the library.

Two adapters came from Muse Spark Open, on Baseten and Fireworks.

Post 5:
Then I messed with it. Moved the cube, took it away, knocked it out of the gripper, took it out of the bowl.
A plan made once mostly failed: 49/420. Going back to the card passed 372/420 on the cube.
[CLIP: replay and live side by side, 2 or more robots]

Post 6:
All of this is simulation, I have no real robot. The trained policies still score 19/50 to 37/50 on new layouts, so there's work left.

Code: https://github.com/thenguyentrong/skill-translator
Try it in your browser: https://thenguyentrong.github.io/skill-translator/
