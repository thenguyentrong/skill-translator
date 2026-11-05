# Submission checklist

Deadline: Wed 4 Nov 21:00 ET = Thu 5 Nov 03:00 CET. Late means not judged. You submit on the Cerebral Valley platform.

## Enter in the form

| Item | Enter |
|---|---|
| Project name | Translator |
| Track | Indie developer |
| Team | Solo. Representative: The Vinh Nguyen Trong. No other members. |
| Theme | Push the Frontier |
| Public repo | https://github.com/thenguyentrong/skill-translator |
| Demo video | [VIDEO LINK] (3 min, only work from the event) |
| Live site | https://thenguyentrong.github.io/skill-translator/ (leave empty if the test fails) |
| X post | [X POST LINK] |
| Short description | description.md, Short version |
| Long description | description.md, Long version |
| Meta models | SAM 3.1, Muse Spark 1.3 (Meta Model API), Muse Spark Open (Baseten and Fireworks) |

## Before you submit

- [ ] Open the form and match this list to its real fields. I could not see the form, so the fields above come from CLAUDE.md and the event page.
- [ ] Make and upload the 3-minute video. I found no finished demo video in the repo.
- [ ] Fill every slot: [VIDEO LINK], https://thenguyentrong.github.io/skill-translator/, [X POST LINK].
- [ ] Apply readme_patch.md.
- [ ] Add `site/node_modules/` to `.gitignore`. It is not ignored now, and `site/` is 73 MB with it.
- [ ] Commit and push tonight's work. `translator/live.py`, `scripts/live.py` and `site/` are untracked, and the last commit is from 28 Oct.
- [ ] Change the GitHub repo description. It still says "any robot can learn it".
- [ ] Check the robot model licenses (open item in CLAUDE.md), including the UR5e model in `site/public/models/`.
- [ ] Open the repo link and the video link in a private window.

## Bonus prizes

The event page names only a community vote and a most viral award. The other categories below come from CLAUDE.md, so check in Discord how to enter them.

| Prize | Enter? | Why |
|---|---|---|
| Most viral | Yes | x_post.md. Engagement counts until 8 Nov. |
| Best build on Meta open-weight models | Yes | Muse Spark Open wrote the Lite6 adapter on Baseten and the FR3 adapter on Fireworks, both 10/10 with 0 fixes. It is a smaller part of the project: cards and the other adapters use hosted Muse Spark 1.3. |
| Best agentic use case | Yes | Muse writes an adapter, my code measures and tests it, and the failures and replay frames go back for up to 3 fixes. The second loop, check and improve, has one run with no gain, so lead with the adapter loop. |
| Community vote | Yes, if it needs no extra entry | A public site gives people something to try. |
| Best creative build (Muse Image / Muse Wonder) | No | The code calls neither model. |
