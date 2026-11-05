# Translator: 3-minute demo script

One sentence: **Film a job. See which robots can do it.**

About 383 spoken words, 2:46 at a calm pace. The hard limit is 3:00.

Hard limit 3:00. If you read slowly, cut in beat 7 or beat 8 first. Clip 22 is a slot for your screen recording of the site.

## 0:00  1 Problem (10 s)

> Can this robot do my job? Today you often find out after you buy it, and then you teach it from zero.

On screen: 01_problem_nine_robots

## 0:10  2 Film a job (12 s)

> So I built Translator. You film a job once. This stock video shows a hand and a lemon. SAM 3.1 tracks the objects and the hand.

On screen: 02_film_a_job_lemon_sam_boxes, 03_sam_tracks_lemon_bowl_hand

## 0:22  3 Meta AI understands (13 s)

> Muse Spark watches the video and writes a skill card: the goal, the objects, the grip, the steps, the success test. The meaning, not the motion. 56 seconds, 7 cents.

On screen: 04_muse_writes_the_card_web_app

## 0:35  4 Robots answer (16 s)

> Here is another stock video: a box, moved with two hands. Each robot checks the card against its own body. The box is 146 millimetres wide, this gripper opens 85. So it says no, with a measured reason.

On screen: 05_second_video_box_two_hands, 06_robots_say_no_with_a_reason

## 0:51  5 Robots do it (7 s)

> For the lemon, most robots say yes. Same card, each in its own way.

On screen: 07_robots_say_can_try_lemon, 14_lemon_eight_robots_grid

## 0:58  6 More kinds (14 s)

> They also open a door, and the G1 carries a crate with two hands; here the base slides, the legs do not step. Nine robots, eleven skills, 80 percent of 760 tries passed.

On screen: 15_door_cabinet_fr3, 18_carry_g1_two_hands_2x, 20_all_skills_all_robots_matrix

## 1:12  7 Mess with it (35 s)

> Because the card holds the goal, not a path, you can mess with it. Here a stick knocks the cube away. A replay carries on with nothing. This robot looks again and goes back for it. Across six robots and scripted moves and hits on the cube, it passed 372 of 420 tries; replay passed 49. A simple re-plan from the card does a little better, 398, because the card is what makes recovery possible. Try it in your browser, the link is below.

On screen: 21_live_vs_replay_stick, 21c_live_vs_replay_hit_in_gripper, 21b_live_six_robots_hit_3x, 22_PLACEHOLDER_browser_site

## 1:47  8 New robots (20 s)

> Muse reads the model file and writes the adapter. If a test fails, Muse gets the numbers and frames and fixes it. The Franka FR3 took 21 seconds on Muse Spark Open, and passed 10 out of 10 first try. Of seven new robots, five passed.

On screen: 23_adapter_written_by_muse, 24_new_robot_fr3_does_it, 10_lemon_xarm7, 11_lemon_tienkung3

## 2:07  8b SAM referee (10 s)

> SAM 3.1 can also referee a robot's clip from video alone. On 40 clean simulated clips it agreed with the simulator 39 times.

On screen: 24b_sam_referee_caught_miss

## 2:17  8c Muse improves the card (10 s, optional)

> When a robot fails, Muse checks the clip and changes the card. Here the fingers go a little lower. On new layouts, the G1 went from 2 of 30 to 17 of 30.

On screen: 24c_muse_improves_card_g1_cookie

If the video goes over 3:00, cut 8b or 8c. Say this line only for the G1: the other robots stayed about the same, and SO-101 still fails.

## 2:17  9 Honest limits (18 s)

> Everything here is simulation, no real robot yet. When a robot trains its own policy from cameras, it passes 38 to 74 percent, behind the planned motion. Watch the UR5e learn: on the same 20 layouts, 6, 6, 13, then 15.

On screen: 25_trained_policy_ur5e_cameras_only, 25b_watch_it_learn

## 2:35  10 Close (11 s)

> Everything here was built during this hackathon, with SAM 3.1, Muse Spark and Muse Spark Open. Show a task once. See which robots can do it.

On screen: 14_lemon_eight_robots_grid, 26_end_card

## Where each number comes from

- 2 of 30 to 17 of 30: G1 on the cookie, unseen seeds 2000-2029, card change grip.table_gap 1 mm kept by the same-layouts rule. All robots: 143 to 161.

- 56 s and $0.07: the lemon job report, also shown on screen in clip 04.
- 146 mm box, 85 mm gripper: the robots' answers for the box video, on screen in clip 06.
- 9 robots, 11 skills, 611 of 760 tries (80 %): the matrix, counting only cells a robot can try; clip 20.
- FR3 adapter: 20.8 s of model time on Fireworks, test 10/10, no fixes.
- Seven new robots, five passed: xArm7, Lite6, TienKung 3, Oli, FR3 passed; TALOS and Booster T1 did not. UR5e is not counted because it already had a hand-written adapter.
- Live loop, cube only: 372 of 420 disturbed tries, replay 49, re-plan after each run 398, on six robots, 7 disturbed cases, 10 tries each. 4 cases move the cube, 3 hit it with a stick. Per robot: UR5e 69/70, xArm7 68, FR3 67, G1 64, SO-101 60, TienKung 3 44, so the robots are not equal. Lemon results are much lower and are not in this video.
- SAM referee: 39 of 40 clean simulated clips agree with the simulator. SAM alone decided 39, all right; Muse broke one tie and was wrong. Pick and place only.
- 38 to 74 percent: trained policies on 50 new layouts, Panda 19/50 to G1 37/50.
- 6, 6, 13, 15 of 20: UR5e lemon policy at 10k, 20k, 30k, 40k training steps, on the same 20 layouts.
- Stock clips: lemon by SHVETS production, box by cottonbro studio, both via Pexels. They are not our own footage.
- Clip 25 is one passing try of the UR5e policy. UR5e scored 32/50 with default settings and 35/50 with temporal ensembling.
