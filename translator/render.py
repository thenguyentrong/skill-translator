"""The robot's camera images (front, top, wrist), labelled, for videos and the live viewer."""
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .scene import CAMERAS, PREFIX


class Cameras:
    def __init__(self, model, width=240, height=180):
        self.renderer = mujoco.Renderer(model, height, width)
        self.font = ImageFont.load_default(size=max(12, height // 12))

    def views(self, data):
        out = {}
        for cam in CAMERAS:
            self.renderer.update_scene(data, camera=cam)
            im = Image.fromarray(self.renderer.render())
            ImageDraw.Draw(im).text((6, 4), cam.removeprefix(PREFIX), fill=(255, 255, 255), font=self.font,
                                    stroke_width=2, stroke_fill=(0, 0, 0))
            out[cam] = np.asarray(im)
        return out

    def column(self, data):
        return np.concatenate(list(self.views(data).values()), axis=0)

    def close(self):
        self.renderer.close()
