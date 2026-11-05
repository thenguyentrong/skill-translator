# Upload a video, run it on Modal

The site's "Try your own video" panel talks to this API. GitHub Pages only serves the page.

```bash
modal setup               # once
bash cloud/deploy.sh      # makes ACCESS_CODE in .env on the first run, sends it and the Meta key to Modal, deploys
.venv/bin/python cloud/test_api.py   # the upload rules, no Modal needed
```

| Step | Runs in | Tested 5 Nov, lemon clip |
|---|---|---|
| `ingest` | ffmpeg on the upload, no secrets | |
| `learn` | SAM + Muse, then every robot's yes or no | 122 s, $0.08, same answers as my PC |
| `robot_try` | one robot, 8 CPUs, no GPU (MuJoCo with OSMesa) | UR5e 2 min, Panda 2 min, G1 6.5 min, all 5/5, same as my PC |

Limits are in `api.py`: access code, 15 videos and 60 robot runs a day, 3 robots per video, 60 MB, 15 s. A job's id is random, so results can only be opened with its link. Results are deleted after 24 hours and the video as soon as the card is done. Training is not on this path.
