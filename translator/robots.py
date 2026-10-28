"""Robot adapters: what the translator needs to know to drive one robot.

One robot = one JSON file in robots/ (hand-written and checked) or robots/muse/ (written by Muse from the
robot's model file). Model paths are relative to assets/robots/. To add a robot, drop in a file.
"""
import json
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "robots"
ADAPTERS = ROOT / "robots"


@dataclass
class Robot:
    name: str
    xml: Path
    ee_site: str | None
    gripper: str | tuple[str, ...] | None = None
    gripper_open: float | tuple[float, ...] = 0.0
    gripper_closed: float | tuple[float, ...] = 0.0
    home: dict[str, float] | str | None = None
    ready: dict[str, float] | None = None
    base_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    base_yaw: float = 0.0
    fixed_base: bool = False
    active: tuple[str, ...] | None = None
    approach_axis: str = "+z"
    closing_axis: str = "+y"
    orientation_cost: float = 1.0
    grip_offset: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fixed_jaw: bool = False
    max_joint_speed: float = 1.5
    tool: tuple[str, Path] | None = None
    ee_add: tuple | None = None
    grip_force_gain: float = 1.0
    tool_replaces_hand: bool = False
    hands: int = 1
    payload_kg: float | None = None
    mobile: bool = False
    left: dict | None = None
    handle_open: tuple[float, ...] | None = None
    handle_release: tuple[float, ...] | None = None
    notes: str = ""
    source: str = ""


def _tuple(v):
    return tuple(_tuple(x) for x in v) if isinstance(v, list) else v


def from_dict(d, source=""):
    known = {f.name for f in fields(Robot)}
    d = {k: _tuple(v) for k, v in d.items() if k in known}
    d["xml"] = ASSETS / d["xml"]
    if d.get("tool"):
        d["tool"] = (d["tool"][0], ASSETS / d["tool"][1], *d["tool"][2:])
    if isinstance(d.get("gripper"), tuple) and len(d["gripper"]) == 1:
        d["gripper"] = d["gripper"][0]
    return Robot(**d, source=source)


def load(path):
    path = Path(path)
    return from_dict(json.loads(path.read_text()), source=str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path))


def library():
    robots = {}
    for path in sorted(ADAPTERS.glob("*.json")) + sorted(ADAPTERS.glob("muse/*.json")):
        r = load(path)
        robots[r.name] = r
    return robots


ROBOTS = library()


def get(name_or_path):
    """A robot by name from the library, or straight from an adapter file."""
    if name_or_path in ROBOTS:
        return ROBOTS[name_or_path]
    path = Path(name_or_path)
    if path.suffix == ".json" and path.exists():
        r = load(path)
        ROBOTS[r.name] = r
        return r
    raise KeyError(f"unknown robot {name_or_path!r}; library: {', '.join(ROBOTS)}")
