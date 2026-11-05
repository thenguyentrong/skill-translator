# Upload a video, run it on Modal

The site's "Try your own video" panel talks to this API. GitHub Pages only serves the page.

```bash
modal setup               # once
bash cloud/deploy.sh      # sends the Meta key to Modal, deploys
.venv/bin/python cloud/test_api.py   # the upload rules, no Modal needed
```

| Step | Runs in | Tested 5 Nov, lemon clip |
|---|---|---|
| `ingest` | ffmpeg on the upload, no secrets | |
| `learn` | SAM + Muse, then every robot's yes or no | 122 s, $0.08, same answers as my PC |
| `robot_try` | one robot, 8 CPUs, no GPU (MuJoCo with OSMesa) | UR5e 2 min, Panda 2 min, G1 6.5 min, all 5/5, same as my PC |

Anyone can use it until a budget runs out. `BUDGET_USD` in `api.py` has one per service: $140 of the Meta credit and $25 of Modal. Every video promises $0.35 Meta and $0.05 Modal, every robot $0.20 Modal, before it starts. That is the worst case, so the real bill stays below the budget. The promises are saved in `budget.json` on the volume. When the next job does not fit, it is refused, for good: to open it again, raise the number and deploy.

Other limits: 5 videos an hour per address, 3 robots per video, 60 MB, 15 s. A job's id is random, so results can only be opened with its link. Results are deleted after 24 hours and the video as soon as the card is done. Training is not on this path.

Each robot's first try saves its joint state at every tick (`<robot>_run.json`) and its practised grip. Every picked robot is interactive on the site: UR5e, Panda and xArm7 run in the browser, the others run `translator/live.py` on Modal and stream to the browser over a WebSocket (`cloud/stream.py`), 2 minutes per session, 10 sessions an hour per address. Their scored try can also be played back. Pick and place only so far.
