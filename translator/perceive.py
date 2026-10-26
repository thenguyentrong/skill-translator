"""Find the card's objects in the robot's own camera images (colour + depth) instead of reading them from the simulator.

The colour step stands in for SAM 3.1 (text prompt -> mask) until the Meta API works; everything after the mask stays.
"""
import math

import mujoco
import numpy as np

from .scene import BOWL_WALL, TABLE_TOP, Scene

LOOK_CAMERAS = ("top", "front")
TOP_FACE = 0.9


def _red(rgb):
    r, g, b = (rgb[..., i].astype(float) for i in range(3))
    return (r > 110) & (r > 2.0 * g) & (r > 2.0 * b)


def _green(rgb):
    r, g, b = (rgb[..., i].astype(float) for i in range(3))
    return (g > 60) & (g > 1.4 * r) & (g > 1.3 * b)


COLOUR_MASKS = {"cube": _red, "bowl": _green}


def _world_points(model, data, camera, depth, mask):
    """Pixels in `mask` -> 3D world points, using the camera's pose, its vertical field of view and metric depth."""
    cam = model.camera(camera).id
    h, w = depth.shape
    f = 0.5 * h / math.tan(math.radians(model.cam_fovy[cam]) / 2)
    v, u = np.nonzero(mask)
    z = depth[v, u]
    pts_cam = np.stack([(u + 0.5 - w / 2) / f * z, -(v + 0.5 - h / 2) / f * z, -z], axis=1)
    return data.cam_xpos[cam] + pts_cam @ data.cam_xmat[cam].reshape(3, 3).T


def _square_yaw(xy):
    """Yaw of a square from points on its top face: the rotation with the smallest bounding box."""
    best, best_area = 0.0, np.inf
    centred = xy - xy.mean(axis=0)
    for deg in np.arange(0.0, 90.0, 0.5):
        a = math.radians(deg)
        rot = centred @ np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        area = np.ptp(rot[:, 0]) * np.ptp(rot[:, 1])
        if area < best_area:
            best, best_area = a, area
    return best


def _circle_centre(xy):
    a = np.column_stack([2 * xy, np.ones(len(xy))])
    sol, *_ = np.linalg.lstsq(a, (xy**2).sum(axis=1), rcond=None)
    return sol[:2]


class Eyes:
    def __init__(self, scene: Scene, width=480, height=360):
        self.scene = scene
        self.rgb = mujoco.Renderer(scene.model, height, width)
        self.depth = mujoco.Renderer(scene.model, height, width)
        self.depth.enable_depth_rendering()

    def points(self, name):
        m, d = self.scene.model, self.scene.data
        out = []
        for camera in LOOK_CAMERAS:
            self.rgb.update_scene(d, camera=camera)
            self.depth.update_scene(d, camera=camera)
            rgb, depth = self.rgb.render(), self.depth.render()
            pts = _world_points(m, d, camera, depth, COLOUR_MASKS[name](rgb))
            out.append(pts[(pts[:, 2] > TABLE_TOP - 0.01) & (pts[:, 2] < TABLE_TOP + 0.08)])
        return np.concatenate(out)

    def find(self, card):
        """Pose of every object on the card, as seen by the cameras. None for an object nobody can see."""
        found = {}
        for name, spec in card["objects"].items():
            pts = self.points(name)
            if len(pts) < 20:
                found[name] = None
                continue
            if spec["shape"] == "box":
                height = spec["size"][2]
                top = pts[pts[:, 2] > TABLE_TOP + TOP_FACE * height]
                face = top if len(top) >= 20 else pts
                xy = face[:, :2].mean(axis=0)
                found[name] = {"pos": np.array([xy[0], xy[1], TABLE_TOP + height / 2]),
                               "yaw": _square_yaw(face[:, :2]), "pixels": len(pts)}
            else:
                rim = pts[pts[:, 2] > TABLE_TOP + 0.75 * spec.get("wall_height", BOWL_WALL)]
                xy = _circle_centre(rim[:, :2]) if len(rim) >= 20 else pts[:, :2].mean(axis=0)
                found[name] = {"pos": np.array([xy[0], xy[1], TABLE_TOP]), "pixels": len(pts)}
        return found

    def close(self):
        self.rgb.close()
        self.depth.close()
