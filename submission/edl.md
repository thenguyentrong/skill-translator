# Edit list

All clips: 1920x1080, 25 fps, H.264 mp4, no sound. Drag them into your editor in number order.

Import `captions.srt` for timed captions, or use it as a reading guide. Times match this list.

| Time | Clip | Clip length | Use | Spoken line |
|---|---|---|---|---|
| 0:00 | 01_problem_nine_robots | 10.0 s | 10 s | Can this robot do my job? Today you often find out after you buy it, and then you teach it from zero. |
| 0:10 | 02_film_a_job_lemon_sam_boxes | 3.1 s | 3 s | So I built Translator. You film a job once. This stock video shows a hand and a lemon. SAM 3.1 tracks the objects and the hand. |
|  | 03_sam_tracks_lemon_bowl_hand | 10.0 s | 9 s |  |
| 0:22 | 04_muse_writes_the_card_web_app | 13.0 s | 13 s | Muse Spark watches the video and writes a skill card: the goal, the objects, the grip, the steps, the success test. The meaning, not the motion. 56 seconds, 7 cents. |
| 0:35 | 05_second_video_box_two_hands | 4.9 s | 5 s | Here is another stock video: a box, moved with two hands. Each robot checks the card against its own body. The box is 146 millimetres wide, this gripper opens 85. So it says no, with a measured reason. |
|  | 06_robots_say_no_with_a_reason | 11.0 s | 11 s |  |
| 0:51 | 07_robots_say_can_try_lemon | 7.0 s | 2 s | For the lemon, most robots say yes. Same card, each in its own way. |
|  | 14_lemon_eight_robots_grid | 9.0 s | 5 s |  |
| 0:58 | 15_door_cabinet_fr3 | 12.7 s | 4 s | They also open a door, and the G1 carries a crate with two hands; here the base slides, the legs do not step. Nine robots, eleven skills, 80 percent of 760 tries passed. |
|  | 18_carry_g1_two_hands_2x | 21.8 s | 5 s |  |
|  | 20_all_skills_all_robots_matrix | 10.0 s | 5 s |  |
| 1:12 | 21_live_vs_replay_stick | 11.2 s | 11 s | Because the card holds the goal, not a path, you can mess with it. Here a stick knocks the cube away. A replay carries on with nothing. This robot looks again and goes back for it. Across six robots and scripted moves and hits on the cube, it passed 372 of 420 tries; replay passed 49. A simple re-plan from the card does a little better, 398, because the card is what makes recovery possible. Try it in your browser, the link is below. |
|  | 21c_live_vs_replay_hit_in_gripper | 19.5 s | 6 s |  |
|  | 21b_live_six_robots_hit_3x | 16.5 s | 13 s |  |
|  | 22_PLACEHOLDER_browser_site | 6.0 s | 5 s |  |
| 1:47 | 23_adapter_written_by_muse | 7.0 s | 6 s | Muse reads the model file and writes the adapter. If a test fails, Muse gets the numbers and frames and fixes it. The Franka FR3 took 21 seconds on Muse Spark Open, and passed 10 out of 10 first try. Of seven new robots, five passed. |
|  | 24_new_robot_fr3_does_it | 9.9 s | 6 s |  |
|  | 10_lemon_xarm7 | 6.8 s | 4 s |  |
|  | 11_lemon_tienkung3 | 9.8 s | 4 s |  |
| 2:07 | 24b_sam_referee_caught_miss | 10.0 s | 10 s | SAM 3.1 can also referee a robot's clip from video alone. On 40 clean simulated clips it agreed with the simulator 39 times. |
| 2:17 | 25_trained_policy_ur5e_cameras_only | 13.6 s | 5 s | Everything here is simulation, no real robot yet. When a robot trains its own policy from cameras, it passes 38 to 74 percent, behind the planned motion. Watch the UR5e learn: on the same 20 layouts, 6, 6, 13, then 15. |
|  | 25b_watch_it_learn | 15.6 s | 13 s |  |
| 2:35 | 14_lemon_eight_robots_grid | 9.0 s | 6 s | Everything here was built during this hackathon, with SAM 3.1, Muse Spark and Muse Spark Open. Show a task once. See which robots can do it. |
|  | 26_end_card | 6.0 s | 5 s |  |

Spare clips, not in the plan: 08_lemon_ur5e, 09_lemon_g1, 12_lemon_panda, 13_lemon_so101, 16_door_cabinet_tienkung3, 17_door_four_robots_grid, 19_carry_basket_tienkung3_2x, rough_cut_guide

## Steps

1. Record the voice from `script.md`, one take per beat, in a quiet room.
2. Lay the voice down, then move the clips to fit it. The voice sets the timing, not this list.
3. Replace clip 22 with your screen recording of the site.
4. Add your music under the voice, about 12 dB quieter, and a soft sound on the main cuts.
5. Use clip 26 as the end card, and add the site link. Keep the line "Built with Muse Spark Open": the model licence requires it.
6. Export 1080p H.264 under 3:00. Upload it, then open the link in a private window to check that it plays.

`stills/` has the full-size web app screens, the matrix, the adapter panel and the end card. `rough_cut_guide.mp4` shows the planned order and timing; it is only a guide.

## Stock clip rules (Pexels)

- These are stock videos, not filmed by us. Never say "I filmed" or "my hand" over them.
- Only show them with the SAM boxes, never alone. Keep the small credit that is already in clips 02, 03, 04 and 05.
- Beat 7 numbers are for the cube only. Don't use them for the lemon, and don't say all robots did equally well.
- Clip 05 is cropped so no face shows. Don't use the uncropped video, and don't let a stock person look like they support the project.
- Put the lines from `credits.md` into the video description.

## Added: 8c (optional)

clips/24c_muse_improves_card_g1_cookie.mp4, 12 s, goes after 24b. Real run, same layout, before and after.
