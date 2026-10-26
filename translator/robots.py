"""Robot adapters: what the translator needs to know to drive one robot."""
import math
from dataclasses import dataclass
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "robots"
MENAGERIE = ASSETS / "mujoco_menagerie"
SO101 = ASSETS / "SO-ARM100" / "Simulation" / "SO101"
DEX3_JOINTS = ("thumb_0", "thumb_1", "thumb_2", "index_0", "index_1", "middle_0", "middle_1")


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
    max_joint_speed: float = 1.5
    tool: tuple[str, Path] | None = None
    ee_add: tuple | None = None


ROBOTS = {
    r.name: r
    for r in [
        Robot(
            name="so101",
            xml=SO101 / "so101_new_calib.xml",
            ee_site="gripperframe",
            gripper="gripper",
            gripper_open=0.5,
            gripper_closed=-0.1,
            home={"shoulder_lift": -0.9, "elbow_flex": 0.65, "wrist_flex": 1.2},
            approach_axis="+x",
            closing_axis="+z",
            orientation_cost=0.1,
            grip_offset=(-0.006, 0.0, 0.018),
        ),
        Robot(
            name="panda",
            xml=MENAGERIE / "franka_emika_panda" / "panda.xml",
            ee_site="pinch",
            ee_add=("hand", (0.0, 0.0, 0.1034)),
            gripper="actuator8",
            gripper_open=255.0,
            gripper_closed=0.0,
            home="home",
        ),
        Robot(
            name="ur5e",
            xml=MENAGERIE / "universal_robots_ur5e" / "ur5e.xml",
            ee_site="tool/pinch",
            tool=("attachment_site", MENAGERIE / "robotiq_2f85" / "2f85.xml"),
            gripper="tool/fingers_actuator",
            gripper_open=0.0,
            gripper_closed=255.0,
            home="home",
            base_yaw=-math.pi / 2,
        ),
        Robot(
            name="g1",
            xml=MENAGERIE / "unitree_g1" / "g1_with_hands.xml",
            ee_site="right_grip",
            ee_add=("right_wrist_yaw_link", (0.1216, 0.0587, 0.0128), (0.9557, 0.0, -0.2943, 0.0)),
            approach_axis="+y",
            closing_axis="+x",
            gripper=tuple(f"right_hand_{j}_joint" for j in DEX3_JOINTS),
            gripper_open=(0.794, -0.318, -1.518, 0.216, 1.356, 0.216, 1.356),
            gripper_closed=(0.242, -0.5, -1.122, 0.692, 1.535, 0.692, 1.535),
            home="stand",
            ready={"right_shoulder_pitch_joint": 0.85, "right_shoulder_roll_joint": -0.046, "right_shoulder_yaw_joint": 0.59,
                   "right_elbow_joint": -0.871, "right_wrist_roll_joint": -1.897, "right_wrist_pitch_joint": 0.206,
                   "right_wrist_yaw_joint": 0.093},
            base_pos=(-0.28, 0.0, -0.75),
            fixed_base=True,
            active=("right_shoulder", "right_elbow", "right_wrist"),
        ),
    ]
}
