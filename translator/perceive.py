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


ROLE_MASKS = {"held": _red, "container": _green}


def _world_points(model, data, camera, depth, mask):
    """Pixels in `mask` -> 3D world points, using the camera's pose, its vertical field of view and metric depth."""
    cam = model.camera(camera).id
    h, w = depth.shape
    f = 0.5 * h / math.tan(math.radians(model.cam_fovy[cam]) / 2)
    v, u = np.nonzero(mask)
    z = depth[v, u]
    pts_cam = np.stack([(u + 0.5 - w / 2) / f * z, -(v + 0.5 - h / 2) / f * z, -z], axis=1)
    return data.cam_xpos[cam] + pts_cam @ data.cam_xmat[cam].reshape(3, 3).T


def _box_yaw(xy, size):
    """Yaw of a box's x side: the smallest bounding box gives the angle up to 90 degrees; for a box whose sides
    differ, the longer measured extent tells which side is x."""
    a = _square_yaw(xy)
    if abs(size[0] - size[1]) < 0.005:
        return a
    centred = xy - xy.mean(axis=0)
    e1 = np.ptp(centred @ np.array([math.cos(a), math.sin(a)]))
    e2 = np.ptp(centred @ np.array([-math.sin(a), math.cos(a)]))
    return a if (e1 > e2) == (size[0] > size[1]) else a + math.pi / 2


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

    def points(self, role, low=-0.01, high=0.08, per_camera=False):
        m, d = self.scene.model, self.scene.data
        out = {}
        for camera in LOOK_CAMERAS:
            self.rgb.update_scene(d, camera=camera)
            self.depth.update_scene(d, camera=camera)
            rgb, depth = self.rgb.render(), self.depth.render()
            pts = _world_points(m, d, camera, depth, ROLE_MASKS[role](rgb))
            out[camera] = pts[(pts[:, 2] > TABLE_TOP + low) & (pts[:, 2] < TABLE_TOP + high)]
        return out if per_camera else np.concatenate(list(out.values()))

    def _find_open(self, card):
        """Cabinet: its top face gives centre and turn (the long side tells depth from width). The red handle is a
        thin bar, often only a few pixels from above, so it only says which face is the front and which side the
        hinge is not; its position then comes from the card (where the handle sits on the door). Without any handle
        pixels: the face towards the robot is the front and the card's hinge side holds."""
        cab, handle = card["success"]["object"], card["grip"]["object"]
        c, h = card["objects"][cab], card["objects"][handle]
        w, dpt, height = c["size"]
        top = self.points("container", height - 0.004, height + 0.01)
        bar = self.points("held", h["height"] - h["length"] / 2 - 0.01, h["height"] + h["length"] / 2 + 0.01)
        if len(top) < 20:
            return {cab: None, handle: None}
        yaw = _box_yaw(top[:, :2], [dpt, w])
        axes = np.array([[math.cos(yaw), math.sin(yaw)], [-math.sin(yaw), math.cos(yaw)]])
        local = top[:, :2] @ axes.T
        centre = ((local.min(axis=0) + local.max(axis=0)) / 2) @ axes
        seen = len(bar) >= 3
        towards = bar[:, :2].mean(axis=0) - centre if seen else self.scene.origin[:2] - centre
        if np.dot(towards, axes[0]) < 0:
            yaw += math.pi
        t = np.array([-math.sin(yaw), math.cos(yaw)])
        side = math.copysign(1.0, np.dot(towards, t)) if seen else (1.0 if c["door"]["hinge"] == "left" else -1.0)
        n = np.array([math.cos(yaw), math.sin(yaw)])
        xy = (centre + n * (dpt / 2 + c["door"]["thickness"] + h["standoff"])
              + t * side * (c["door"]["width"] / 2 - h["from_free_edge"]))
        return {cab: {"pos": np.array([centre[0], centre[1], TABLE_TOP]), "yaw": yaw, "pixels": len(top)},
                handle: {"pos": np.array([xy[0], xy[1], TABLE_TOP + h["height"]]), "yaw": yaw, "pixels": len(bar),
                         "hinge": -side}}

    def _find_carry(self, card):
        """Crate: its red walls give centre and turn (the longer side tells which way the handles point). The mark
        on the other table is not in these cameras from where the robot starts: it comes from the card (how far to
        the crate's side the person took it)."""
        crate, place = card["grip"]["object"], card["success"]["place"]
        c, p = card["objects"][crate], card["objects"][place]
        w, l, h = c["size"]
        pts = self.points("held", 0.3 * h, h + 0.01)
        if len(pts) < 20:
            return {crate: None, place: None}
        yaw = _box_yaw(pts[:, :2], [w, l])
        axes = np.array([[math.cos(yaw), math.sin(yaw)], [-math.sin(yaw), math.cos(yaw)]])
        local = pts[:, :2] @ axes.T
        centre = ((local.min(axis=0) + local.max(axis=0)) / 2) @ axes
        side = -1.0 if p.get("side") == "right" else 1.0
        return {crate: {"pos": np.array([centre[0], centre[1], TABLE_TOP]), "yaw": yaw, "pixels": len(pts)},
                place: {"pos": np.array([centre[0], centre[1] + side * p["distance"], TABLE_TOP]), "from": "card"}}

    def find(self, card):
        """Pose of every object on the card, as seen by the cameras. None for an object nobody can see."""
        if card.get("kind") == "open":
            return self._find_open(card)
        if card.get("kind") == "carry":
            return self._find_carry(card)
        found = {}
        roles = {card["grip"]["object"]: "held", card["success"]["container"]: "container"}
        for name, spec in card["objects"].items():
            if name not in roles:
                continue
            pts = self.points(roles[name])
            if len(pts) < 20:
                found[name] = None
                continue
            if roles[name] == "held":
                height = spec["size"][2]
                top = pts[pts[:, 2] > TABLE_TOP + TOP_FACE * height]
                face = top if len(top) >= 20 else pts
                xy = face[:, :2].mean(axis=0)
                found[name] = {"pos": np.array([xy[0], xy[1], TABLE_TOP + height / 2]),
                               "yaw": _box_yaw(face[:, :2], spec["size"]) if spec["shape"] == "box" else 0.0, "pixels": len(pts)}
            else:
                rim = pts[pts[:, 2] > TABLE_TOP + 0.75 * spec.get("wall_height", BOWL_WALL)]
                if len(rim) < 20:
                    xy = pts[:, :2].mean(axis=0)
                elif spec["shape"] == "box":
                    xy = (rim[:, :2].min(axis=0) + rim[:, :2].max(axis=0)) / 2
                else:
                    xy = _circle_centre(rim[:, :2])
                found[name] = {"pos": np.array([xy[0], xy[1], TABLE_TOP]), "pixels": len(pts)}
        return found

    def close(self):
        self.rgb.close()
        self.depth.close()
