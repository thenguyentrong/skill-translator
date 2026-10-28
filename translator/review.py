"""Step 5: Muse Spark checks what each robot did against the human video, then improves the skill card.

judge(): Muse watches the human video and one robot clip side by side and says whether the robot did the same task,
what went wrong and whether the fix belongs in the card (shared by every robot) or in that robot's adapter.
improve(): from all robots' results and judgments, Muse proposes changes to a few card fields; apply() makes them.
"""
import copy
import json

from .card_writer import SPARK_IN, SPARK_OUT
from .meta import data_url, stream_response

CAUSES = ["grip", "approach", "lift_height", "placement", "object_size", "container_size", "robot_reach",
          "robot_hand", "perception", "none", "other"]

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "same_task": {"type": "boolean", "description": "the robot attempts the same task as the person"},
        "looks_done": {"type": "boolean", "description": "at the end of the robot clip the goal is true"},
        "what_happened": {"type": "string", "description": "one or two sentences on the robot clip"},
        "cause": {"type": "string", "enum": CAUSES},
        "fix_in": {"type": "string", "enum": ["card", "robot", "none"],
                   "description": "card: the skill card itself is wrong for most bodies; robot: only this robot's body or "
                                  "adapter; none: it worked"},
        "suggestion": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["same_task", "looks_done", "what_happened", "cause", "fix_in", "suggestion", "confidence"],
}

FIELDS = ["grip.approach", "grip.between", "grip.width", "held.size", "container.inner_radius", "container.wall_height",
          "lift.height", "retreat.height"]
FIELD_HELP = """What each field does in the translator:
- grip.approach: "top" = the hand comes straight down; "side" = it comes in level with the table.
- grip.between: "opposite faces" = the fingers close on two flat faces; "around" = on a round object.
- grip.width: the object's width between the fingers. The gripper opens a little wider than this and always closes
  until it touches, so this does NOT set how hard it squeezes.
- held.size: the object's real size [width, depth, height] in metres (the simulator builds it this size).
- container.inner_radius / container.wall_height: the container's size.
- lift.height / retreat.height: how high the hand goes after closing / after letting go.
Each robot also practises how deep to grip on its own, so grip depth is not a card field."""

IMPROVE_SCHEMA = {
    "type": "object",
    "properties": {
        "changes": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string", "enum": FIELDS},
            "value": {"type": "string", "description": "new value as JSON: a number in metres, a word, or [w, d, h]"},
            "why": {"type": "string"}},
            "required": ["field", "value", "why"]}},
        "summary": {"type": "string"},
    },
    "required": ["changes", "summary"],
}


def _ask(instructions, content, schema, name, effort="medium"):
    body = {"model": "muse-spark-1.3", "instructions": instructions,
            "input": [{"type": "message", "role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": name, "schema": schema}},
            "reasoning": {"effort": effort}, "max_output_tokens": 8000}
    deltas, usage = stream_response(body)
    cost = usage.get("input_tokens", 0) * SPARK_IN + usage.get("output_tokens", 0) * SPARK_OUT if usage else None
    return json.loads("".join(deltas)), cost


def judge(human_video, robot_clip, card, robot, result):
    text = (f"The first video shows a person doing a task. The second shows the robot '{robot}' doing it in simulation "
            f"from this skill card:\n{json.dumps(card)}\n\nThe simulator's own test over {result['n']} tries: "
            f"{result['success']} passed, failures {json.dumps(result['fails'])}. The clip is "
            f"{'a failed try' if result.get('clip_failed') else 'the first try'}.")
    return _ask("You check robot runs against a human demonstration. Judge the robot clip honestly from what you see. "
                "Say fix_in=card only if the card's grip, sizes or heights are wrong in a way that would hurt most robots; "
                "a body that is too small, too weak or out of reach is fix_in=robot.",
                [{"type": "input_text", "text": text},
                 {"type": "input_video", "video_url": data_url(human_video)},
                 {"type": "input_video", "video_url": data_url(robot_clip)}],
                JUDGE_SCHEMA, "robot_check")


def improve(human_video, card, rows, judgments, tried=()):
    table = "\n".join(f"- {r['robot']}: {r['success']}/{r['n']} passed, failures {json.dumps(r['fails'])}"
                      + (f"; check: {json.dumps(judgments[r['robot']])}" if r["robot"] in judgments else "") for r in rows)
    history = "".join(f"\nAlready tried: {json.dumps(t['changes'])} -> {t['score']} passed (before {t['before']}), not kept."
                      for t in tried)
    text = (f"Skill card:\n{json.dumps(card)}\n\nEvery robot ran it in simulation:\n{table}\n{history}\n\n"
            f"{FIELD_HELP}\n\nPropose changes to the card that would help most robots, different from what was already tried. "
            "Return no changes if the card is fine or nothing new would help.")
    return _ask("You improve a robot skill card that was written from the attached video. The card holds the meaning of "
                "the task; keep the goal and the objects' identity. Change only the listed fields, only with evidence "
                "from several robots or from the video, and keep sizes physically plausible. Problems of a single "
                "robot's body are not card problems.",
                [{"type": "input_text", "text": text}, {"type": "input_video", "video_url": data_url(human_video)}],
                IMPROVE_SCHEMA, "card_changes")


def apply(card, changes):
    """The card with Muse's changes (unknown fields or bad values are skipped and listed)."""
    new, skipped = copy.deepcopy(card), []
    held, cont = card["grip"]["object"], card["success"].get("container")
    for c in changes:
        try:
            value = json.loads(c["value"])
        except json.JSONDecodeError:
            value = c["value"]
        field = c["field"]
        if field in ("grip.approach", "grip.between", "grip.width"):
            new["grip"][field.split(".")[1]] = value
        elif field == "held.size" and isinstance(value, list) and len(value) == 3:
            new["objects"][held]["size"] = [float(v) for v in value]
        elif field.startswith("container.") and cont:
            new["objects"][cont][field.split(".")[1]] = float(value)
        elif field in ("lift.height", "retreat.height"):
            for s in new["steps"]:
                if s["do"] == field.split(".")[0]:
                    s["height"] = float(value)
        else:
            skipped.append(c)
    return new, skipped
