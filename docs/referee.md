# SAM referee: measured agreement

**39 of 40 clips agree with the simulator's own success test (97.5 %).** With only 40 clips the 95 % interval is 87.1 to 99.6 %.

- False pass (said done, was not): 1. False fail: 0. Unsure: 0.
- SAM alone decided 39 clips, 39 right. Muse broke 1 tie blind, 0 right.
- Cost $0.806 for this set, $0.020 per clip. Median 5.2 s per clip, slowest 12.8 s.
- Plain box test from events.py, no margin and no Muse: 37 of 40.
- Easy part: in 8 failed clips the object never moved, all 8 right. Harder part: 12 failed clips where it moved, 11 right.

## What this does and does not show

20 clips the simulator passed and 20 it failed, clean renders with no labels, at most 50 frames, one fixed camera, seeds from 7000. Pick-and-place cards only; door and carry cards are not covered. The scene paints the object red and the container green, and the camera never moves, so this is the easy case for vision. It says nothing yet about real phone video.

One prompt changed on the dev set before the test: a flat cylinder is a "red disc", because "red cylinder" found no cookie. Thresholds stayed as first written. The test ran once and the rules did not change after it. Dev set: 10 of 10, 3 of 3 ties right.

| How the simulator scored it | Right | Clips |
|---|---|---|
| bowl | 2 | 2 |
| drop | 5 | 5 |
| grasp | 8 | 8 |
| ik | 4 | 5 |
| ok | 20 | 20 |

## Wrong cases

| Clip | Simulator | Referee | Decided by | Why | Off-centre (m) |
|---|---|---|---|---|---|
| block_to_plate__g1__s7001.mp4 | fail (ik) | pass | muse | too close to the edge to call (0.96) | 0.0635 |

## What Muse is told

Clip plus this question, with the card's shapes filled in. Never the pixels' score:

> A robot arm tries to put a red ball into a green bowl. Watch to the very end of the video. In the last second, is the red ball resting in the green bowl? Touching the rim from outside, lying beside it or lying behind it all count as not in it.
