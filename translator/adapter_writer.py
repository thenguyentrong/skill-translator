"""Muse reads a robot's model file and writes its adapter; the translator measures and tests it; Muse fixes it.

Round 0: model file + facts -> adapter. Each later round: the adapter, the measurements (blueprint.measure), the
practice and test results and three replay frames go back to Muse, which returns a corrected adapter. At most 3 fixes.
"""
import base64
import io
import json
import time
import urllib.request

from PIL import Image

from .meta import api_key, stream_response

SPARK_IN, SPARK_OUT = 1.25e-6, 4.25e-6
OPEN = {  # Muse Spark Open, same weights on two hosts: (url, model, key in .env)
    "baseten": ("https://inference.baseten.co/v1/chat/completions", "meta-models/muse-spark-open-1026", "BASETEN_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1/chat/completions", "accounts/fireworks/models/muse-spark-open",
                  "FIREWORKS_API_KEY"),
}

AXES = ["+x", "-x", "+y", "-y", "+z", "-z"]
_num3 = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "ee_site": {"type": "string", "description": "site at the grip point between the fingertips"},
        "ee_add": {"type": ["object", "null"], "properties": {
            "body": {"type": "string"}, "pos": _num3,
            "quat": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}},
            "required": ["body", "pos", "quat"], "description": "create ee_site on this body when no such site exists"},
        "tool": {"type": ["object", "null"], "properties": {
            "attach_to": {"type": "string", "description": "a flange site, or else the wrist body"},
            "file": {"type": "string"}, "pos": _num3,
            "quat": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}},
            "required": ["attach_to", "file", "pos", "quat"],
            "description": "a gripper from the tool list, when the robot has none; pos/quat place the tool's base frame "
                           "in the site's or body's frame (the tool's fingers point along its own +z)"},
        "gripper": {"type": "array", "items": {"type": "string"}, "description": "gripper actuator name(s)"},
        "gripper_open": {"type": "array", "items": {"type": "number"}},
        "gripper_closed": {"type": "array", "items": {"type": "number"}},
        "home": {"type": ["string", "null"], "description": "keyframe name for the start pose"},
        "home_joints": {"type": "array", "items": {"type": "object", "properties": {
            "joint": {"type": "string"}, "value": {"type": "number"}}, "required": ["joint", "value"]},
            "description": "joint angles applied on top of the keyframe (or alone when there is none)"},
        "base_pos": _num3,
        "base_yaw": {"type": "number", "description": "radians"},
        "fixed_base": {"type": "boolean"},
        "active": {"type": ["array", "null"], "items": {"type": "string"},
                   "description": "actuator name prefixes of the arm used; null = every non-gripper actuator"},
        "approach_axis": {"type": "string", "enum": AXES},
        "closing_axis": {"type": "string", "enum": AXES},
        "grip_offset": _num3,
        "orientation_cost": {"type": "number", "description": "1.0 = the hand must point exactly straight down; an arm "
                             "with fewer than 6 joints cannot always do that, then 0.05-0.3 lets it tilt the hand"},
        "fixed_jaw": {"type": "boolean"},
        "notes": {"type": "string", "description": "what you read in the model and what you are unsure about"},
    },
    "required": ["name", "ee_site", "ee_add", "tool", "gripper", "gripper_open", "gripper_closed", "home", "home_joints",
                 "base_pos", "base_yaw", "fixed_base", "active", "approach_axis", "closing_axis", "grip_offset",
                 "orientation_cost",
                 "fixed_jaw", "notes"],
}

TOOLS = [{"file": "mujoco_menagerie/robotiq_2f85/2f85.xml", "what": "Robotiq 2F-85 parallel gripper",
          "grip_site": "pinch", "actuator": "fingers_actuator", "ctrl": "0 = open (85 mm), 255 = closed",
          "attach": "at the arm's flange site (pos 0 0 0, quat 1 0 0 0) or, without one, at the wrist body with the "
                    "pos/quat that makes its +z point out of the wrist; inside the robot its names get the prefix 'tool/'"}]

INSTRUCTIONS = """You write the adapter that lets a robot skill translator drive a robot it has never seen.
The translator moves the robot's grip point (a site between the fingertips) through waypoints with inverse kinematics,
opens and closes the gripper, and checks the result in MuJoCo physics. It needs from you:
- ee_site: a site at the grip point, the point that sits at the object's centre during a grasp. If the model has no
  such site, give a new name and ee_add {body, pos, quat} to create it on the hand body (pos/quat in that body's frame).
- approach_axis: the ee_site's local axis that points from the palm toward the fingertips (the hand moves along it to grasp).
- closing_axis: the ee_site's local axis along which the fingers move toward each other.
- gripper (actuator names), gripper_open and gripper_closed (one control value per actuator, inside its ctrlrange).
- home (a keyframe name, or null) and home_joints: a start pose with the hand above the table, not touching it.
- placement: the table top is the plane z = 0.75 m in the world; it spans x from -0.20 to 0.90 m and y from -0.60 to
  0.60 m, the floor is z = 0. The robot's root body frame is placed at (base_pos[0], base_pos[1], 0.75 + base_pos[2])
  and turned by base_yaw around z; any position the model gives its root body is added on top. The task objects lie
  on the table in front of the robot along +x, 0.1 to 0.6 m away. An arm stands on the table near its back edge
  (base_pos 0, 0, 0). A humanoid stands on the floor behind the back edge (x < -0.2, not touching the table) with its
  feet at z = 0, and fixed_base true so it cannot fall.
- active: for a humanoid, the actuator name prefixes of the one arm that does the task; null for an arm.
- grip_offset: usually [0, 0, 0]; fixed_jaw: true only if one jaw is fixed and the other moves.
- tool: only if the robot has no gripper; choose one from the tool list and set ee_site/gripper to its names with the prefix 'tool/'.
Read the model file carefully (body tree, joint axes, site positions, actuator ctrlranges, keyframes). In notes, say how
you decided each axis and what you are unsure about. When you get measurements and test results, fix what they show is
wrong and keep what works."""


def _image_part(rgb, api):
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=85)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"type": "input_image", "image_url": url} if api == "meta" else {"type": "image_url", "image_url": {"url": url}}


def ask(messages, model="meta", effort="medium", images=(), tries=3):
    """Like _ask, but asks again when the answer is cut off or not valid JSON."""
    for i in range(tries):
        try:
            return _ask(messages, model, effort, images)
        except (json.JSONDecodeError, ValueError, KeyError, RuntimeError):
            if i == tries - 1:
                raise


def _ask(messages, model="meta", effort="medium", images=()):
    """messages: list of (role, text). Images go with the last user message. Returns (adapter dict, cost, seconds)."""
    t0 = time.time()
    if model == "meta":
        inp = []
        for i, (role, text) in enumerate(messages):
            content = [{"type": "input_text" if role == "user" else "output_text", "text": text}]
            if i == len(messages) - 1:
                content += [_image_part(im, "meta") for im in images]
            inp.append({"type": "message", "role": role, "content": content})
        body = {"model": "muse-spark-1.3", "instructions": INSTRUCTIONS, "input": inp,
                "text": {"format": {"type": "json_schema", "name": "robot_adapter", "schema": SCHEMA}},
                "reasoning": {"effort": effort}, "max_output_tokens": 24000}
        deltas, usage = stream_response(body)
        cost = usage.get("input_tokens", 0) * SPARK_IN + usage.get("output_tokens", 0) * SPARK_OUT if usage else None
        return json.loads("".join(deltas)), cost, round(time.time() - t0, 1)
    msgs = [{"role": "system", "content": INSTRUCTIONS}]
    for i, (role, text) in enumerate(messages):
        if i == len(messages) - 1 and images:
            msgs.append({"role": role, "content": [{"type": "text", "text": text}] + [_image_part(im, "openai") for im in images]})
        else:
            msgs.append({"role": role, "content": text})
    url, name, key = OPEN[model]
    body = {"model": name, "messages": msgs, "max_tokens": 16000, "reasoning_effort": effort,
            "response_format": {"type": "json_schema", "json_schema": {"name": "robot_adapter", "schema": SCHEMA}}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {api_key(key)}", "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=900).read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:400]}") from None
    text = r["choices"][0]["message"]["content"]
    return json.loads(text[text.index("{"):text.rindex("}") + 1]), None, round(time.time() - t0, 1)


def first_message(xml_text, facts):
    return (f"Robot model file ({facts['file']}):\n```xml\n{xml_text}\n```\n\nFacts read from it:\n"
            f"{json.dumps(facts)}\n\nTool list (grippers you may attach):\n{json.dumps(TOOLS)}\n\n"
            "Write the adapter for this robot.")


def feedback_message(adapter, measurements, results):
    return ("The translator measured your adapter and ran it.\n"
            f"Adapter:\n{json.dumps(adapter)}\n\nMeasurements (in the ee_site's own axes unless said otherwise):\n"
            f"{json.dumps(measurements, indent=1)}\n\nPractice and test on 'cube_to_bowl' (3 cm cube into a bowl) and "
            "'block_to_plate' (a 6 x 2.5 x 3 cm block gripped across its 2.5 cm side, onto a plate):\n"
            f"{json.dumps(results, indent=1)}\n\nThe images are the front camera at the end of descend, close and lift "
            "in the first failed trial (none if all passed). Return the corrected full adapter.")


def to_adapter(a, xml):
    """Muse's answer -> the adapter format of robots/*.json."""
    out = {"name": a["name"], "xml": xml, "ee_site": a["ee_site"],
           "gripper": a["gripper"][0] if len(a["gripper"]) == 1 else a["gripper"],
           "gripper_open": a["gripper_open"][0] if len(a["gripper_open"]) == 1 else a["gripper_open"],
           "gripper_closed": a["gripper_closed"][0] if len(a["gripper_closed"]) == 1 else a["gripper_closed"],
           "base_pos": a["base_pos"], "base_yaw": a["base_yaw"], "fixed_base": a["fixed_base"],
           "approach_axis": a["approach_axis"], "closing_axis": a["closing_axis"], "grip_offset": a["grip_offset"],
           "fixed_jaw": a["fixed_jaw"], "orientation_cost": a.get("orientation_cost", 1.0), "notes": a["notes"]}
    if a.get("ee_add"):
        out["ee_add"] = [a["ee_add"]["body"], a["ee_add"]["pos"], a["ee_add"]["quat"]]
    tool = a.get("tool") or {}
    where = tool.get("attach_to") or tool.get("attach_site")
    if where and tool.get("file"):
        out["tool"] = [where, tool["file"], tool.get("pos") or [0, 0, 0], tool.get("quat") or [1, 0, 0, 0]]
    if a.get("active"):
        out["active"] = a["active"]
    joints = {j["joint"]: j["value"] for j in a.get("home_joints") or []}
    if a.get("home"):
        out["home"] = a["home"]
        if joints:
            out["ready"] = joints
    else:
        out["home"] = joints
    return out
