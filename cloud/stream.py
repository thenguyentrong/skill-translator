"""One live robot over a WebSocket: the Python live loop runs here, the browser draws it and sends the disturbances.

Used for the robots the browser can't drive itself. A ticket from the API (one use, expires) opens a session of at most
SECONDS, so a session has a known worst-case cost. It reads true object poses (eyes=False): on 2 CPUs without a GPU the
cameras would not keep up with 25 Hz, and the page says so.
"""
import asyncio
import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.concurrency import run_in_threadpool

FPS = 25
SECONDS = 120
TICKET_SECONDS = 90
TICKET = re.compile(r"[0-9a-f]{32}")


def make_stream(store, root, reload=lambda: None):
    app = FastAPI(title="Translator live", docs_url=None, redoc_url=None, openapi_url=None)
    root = Path(root)

    def claim(token):
        key = f"live:{token}"
        ticket = store.get(key) if TICKET.fullmatch(token) else None
        if not ticket:
            return None
        store.pop(key)
        return ticket if time.time() - ticket["created"] < TICKET_SECONDS else None

    def start(ticket):
        import numpy as np
        from cloud.jobs import plain_name
        from translator.live import Live
        from translator.scene import practice_file
        reload()
        card = plain_name(store[f"job:{ticket['job']}"]["card"])
        grip = root / ticket["job"] / f"{ticket['robot']}_practice.json"
        if grip.exists():  # the depth this robot found when it practised for its scored tries
            target = practice_file(ticket["robot"], card)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(grip.read_text())
        return Live(ticket["robot"], card, seed=int(np.random.default_rng().integers(1 << 30)), eyes=False)

    def act(lv, rng, msg):
        from translator.live import free_spot
        s = lv.scene
        if msg.get("do") == "knock":
            lv.knock()
        elif msg.get("do") == "move":
            x, y = [float(v) for v in msg["xy"][:2]]
            if s.on_table((x, y), s.held_xy):
                lv.move_object((x, y))
        elif msg.get("do") == "new":
            spot = free_spot(s, rng, s.bowl_pos()[:2], 0.1, 2.0)
            if spot is not None:
                lv.move_object(spot)

    @app.websocket("/live/{token}")
    async def live(ws: WebSocket, token: str):
        await ws.accept()
        ticket = await run_in_threadpool(claim, token)
        if not ticket:
            return await ws.close(4401)
        try:
            lv = await run_in_threadpool(start, ticket)
        except Exception:
            return await ws.close(4400)
        import numpy as np
        rng = np.random.default_rng()
        inbox = asyncio.Queue()

        async def listen():
            while True:
                inbox.put_nowait(await ws.receive_json())

        ears = asyncio.create_task(listen())
        q = lv.scene.data.qpos
        await ws.send_text(json.dumps({"hello": {"bowl": [float(v) for v in lv.scene.bowl_pos()], "seconds": SECONDS, "fps": FPS}}))
        t0 = next_tick = time.time()
        try:
            while time.time() - t0 < SECONDS and not ears.done():
                while not inbox.empty():
                    try:
                        act(lv, rng, inbox.get_nowait())
                    except (KeyError, TypeError, ValueError):
                        pass
                lv.step()
                await ws.send_text(json.dumps({"q": [round(float(v), 4) for v in q], "s": lv.state()}, separators=(",", ":")))
                next_tick += 1 / FPS
                await asyncio.sleep(max(0.0, next_tick - time.time()))
            if not ears.done():
                await ws.send_text('{"end":"time"}')
                await ws.close()
        except Exception:  # the visitor left
            pass
        finally:
            ears.cancel()
            lv.close()

    return app
