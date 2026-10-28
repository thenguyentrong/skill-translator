"""Step 3: Muse Spark watches the video (plus the SAM facts) and writes the skill card."""
import json

from .meta import data_url, stream_response

SPARK_IN, SPARK_OUT = 1.25e-6, 4.25e-6

STEP_NAMES = ["reach", "descend", "close", "lift", "carry", "lower", "open", "retreat"]

NEEDS_SCHEMA = {
    "type": "object",
    "description": "what the task needs from a body, as seen in the video; a robot that lacks it says no",
    "properties": {
        "hands": {"type": "integer", "description": "hands that hold the object while it moves (1 or 2)"},
        "move_m": {"type": "number", "description": "how far the person walks between where the object starts and "
                                                    "where it ends; 0 if they stay in place"},
        "mass_kg": {"type": "number", "description": "estimated weight of what is lifted (0 for a door)"},
        "keep_upright": {"type": "boolean", "description": "must stay level while carried (open container, liquid)"},
        "fragile": {"type": "boolean", "description": "breaks or dents if squeezed hard"},
        "guessed": {"type": "array", "items": {"type": "string"},
                    "description": "which of these values are guesses rather than seen or measured"}},
    "required": ["hands", "move_m", "mass_kg", "keep_upright", "fragile", "guessed"],
}

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "snake_case task name"},
        "goal": {"type": "string", "description": "one sentence: what must be true at the end"},
        "objects": {
            "type": "object",
            "properties": {
                "held": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "shape": {"type": "string", "enum": ["box", "sphere", "cylinder"]},
                    "size_m": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                               "description": "width, depth, height in metres (a sphere: its diameter three times)"},
                    "color": {"type": "string"}},
                    "required": ["name", "shape", "size_m", "color"]},
                "container": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "shape": {"type": "string", "enum": ["bowl", "box", "plate", "basket"]},
                    "inner_radius_m": {"type": "number"},
                    "wall_height_m": {"type": "number"},
                    "color": {"type": "string"}},
                    "required": ["name", "shape", "inner_radius_m", "wall_height_m", "color"]},
            },
            "required": ["held", "container"],
        },
        "grip": {"type": "object", "properties": {
            "approach": {"type": "string", "enum": ["top", "side"]},
            "between": {"type": "string", "enum": ["opposite faces", "around"]},
            "width_m": {"type": "number"}},
            "required": ["approach", "between", "width_m"]},
        "steps": {"type": "array", "items": {"type": "object", "properties": {
            "do": {"type": "string", "enum": STEP_NAMES},
            "height_m": {"type": "number", "description": "only for lift and retreat"}},
            "required": ["do"]}},
        "success": {"type": "object", "properties": {"test": {"type": "string", "enum": ["inside", "on_top"]}},
                    "required": ["test"]},
        "needs": NEEDS_SCHEMA,
        "evidence": {"type": "object", "properties": {
            "grab_time_s": {"type": "number"},
            "release_time_s": {"type": "number"},
            "notes": {"type": "string", "description": "what in the video supports this card, and what is uncertain"},
            "confidence": {"type": "number", "description": "0 to 1"}},
            "required": ["grab_time_s", "release_time_s", "notes", "confidence"]},
    },
    "required": ["name", "goal", "objects", "grip", "steps", "success", "needs", "evidence"],
}

INSTRUCTIONS = """You turn a short video of a person doing one tabletop task into a robot skill card.
The card holds the MEANING of the task (goal, objects, grip, steps, success test), never the human's arm motion,
because robots with very different bodies will each do it in their own way.
Rules:
- Describe only the single object that is picked up and moved ("held") and where it goes ("container").
- Give real sizes in metres. Use common knowledge of the object plus the measured width ratio below; say in notes how you estimated.
- Steps use only: reach, descend, close, lift, carry, lower, open, retreat. Typical order: reach, descend, close, lift, carry, lower, open, retreat.
- lift and retreat get a height_m. Choose a lift that clears the container wall.
- grip.width_m is the width the fingers close on.
- Be honest in evidence.notes about anything you cannot see (for example the object hidden after release).
- needs: what the task asks of a body (hands holding the object, metres walked, weight, keep level, fragile), and list
  in needs.guessed the values you estimated rather than saw."""


OPEN_STEPS = ["reach", "approach", "close", "pull", "open", "retreat"]

OPEN_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "snake_case task name"},
        "goal": {"type": "string", "description": "one sentence: what must be true at the end"},
        "cabinet": {"type": "object", "properties": {
            "name": {"type": "string"},
            "size_m": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                       "description": "width, depth, height in metres, seen from the front"},
            "color": {"type": "string"}},
            "required": ["name", "size_m", "color"]},
        "door": {"type": "object", "properties": {
            "width_m": {"type": "number"}, "height_m": {"type": "number"}, "thickness_m": {"type": "number"},
            "hinge": {"type": "string", "enum": ["left", "right"], "description": "hinge side as seen by someone facing the door"}},
            "required": ["width_m", "height_m", "thickness_m", "hinge"]},
        "handle": {"type": "object", "properties": {
            "name": {"type": "string"},
            "diameter_m": {"type": "number"}, "length_m": {"type": "number"},
            "standoff_m": {"type": "number", "description": "from the door surface to the middle of the bar"},
            "from_free_edge_m": {"type": "number", "description": "from the door's free edge to the middle of the bar"},
            "height_m": {"type": "number", "description": "middle of the bar above the bottom of the cabinet"},
            "color": {"type": "string"}},
            "required": ["name", "diameter_m", "length_m", "standoff_m", "from_free_edge_m", "height_m", "color"]},
        "steps": {"type": "array", "items": {"type": "object", "properties": {"do": {"type": "string", "enum": OPEN_STEPS}},
                                             "required": ["do"]}},
        "min_angle_deg": {"type": "number", "description": "how far the door must be open at the end"},
        "needs": NEEDS_SCHEMA,
        "evidence": SCHEMA["properties"]["evidence"],
    },
    "required": ["name", "goal", "cabinet", "door", "handle", "steps", "min_angle_deg", "needs", "evidence"],
}

OPEN_INSTRUCTIONS = """You turn a short video of a person opening a hinged door (a cupboard, cabinet or wardrobe) with one hand
into a robot skill card. The card holds the MEANING of the task, never the human's arm motion.
Rules:
- Describe the cabinet, its door (hinge side as seen by someone facing the door) and the handle the hand pulls.
- Give real sizes in metres from common knowledge and what you see; say in evidence.notes how you estimated them.
- A knob or a recessed handle: describe it as the bar the fingers close around (its thickness and length).
- Steps use only: reach, approach, close, pull, open, retreat (in that order).
- min_angle_deg: how far the door ends open in the video, rounded down to a multiple of 10, at most 90.
- needs: hands used on the door, metres walked while pulling (a person stepping back with a big door), mass_kg 0;
  list in needs.guessed what you estimated."""


CARRY_STEPS = ["reach", "close", "lift", "walk", "lower", "open", "retreat"]

CARRY_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "snake_case task name"},
        "goal": {"type": "string", "description": "one sentence: what must be true at the end"},
        "object": {"type": "object", "properties": {
            "name": {"type": "string"},
            "size_m": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                       "description": "depth (front to back as held), length (side to side, between the hands), height"},
            "mass_kg": {"type": "number"},
            "color": {"type": "string"},
            "handles": {"type": "string", "enum": ["side", "top", "none"],
                        "description": "side: one on each end (two hands); top: one bar over the top (one hand); none"},
            "handle_diameter_m": {"type": "number"},
            "handle_length_m": {"type": "number", "description": "side: how far each handle sticks out; top: the bar's length"},
            "handle_height_m": {"type": "number", "description": "middle of the bar above the object's bottom"}},
            "required": ["name", "size_m", "mass_kg", "color", "handles", "handle_diameter_m", "handle_length_m", "handle_height_m"]},
        "place": {"type": "object", "properties": {
            "name": {"type": "string"},
            "distance_m": {"type": "number", "description": "from where the object starts to where it ends, sideways"},
            "side": {"type": "string", "enum": ["left", "right"], "description": "as seen by the person carrying it"}},
            "required": ["name", "distance_m", "side"]},
        "steps": {"type": "array", "items": {"type": "object", "properties": {"do": {"type": "string", "enum": CARRY_STEPS}},
                                             "required": ["do"]}},
        "within_m": {"type": "number", "description": "how close to the spot it must end"},
        "needs": NEEDS_SCHEMA,
        "evidence": SCHEMA["properties"]["evidence"],
    },
    "required": ["name", "goal", "object", "place", "steps", "within_m", "needs", "evidence"],
}

CARRY_INSTRUCTIONS = """You turn a short video of a person carrying a box, crate or basket to another place into a robot skill
card. The card holds the MEANING of the task, never the human's arm or leg motion.
Rules:
- Describe the carried object, its handles (one on each end, one bar over the top, or none) and where it ends up.
- Give real sizes and weight from common knowledge and what you see; say in evidence.notes how you estimated them.
- distance_m: how far the object travels sideways between its start and its end; 0 if it is only lifted and set down.
- Steps use only: reach, close, lift, walk, lower, open, retreat (in that order; leave out walk if nobody walks).
- needs: hands holding it while it moves, metres walked, weight, keep upright (open top with things inside), fragile;
  list in needs.guessed what you estimated rather than saw."""


def facts_text(events):
    e = events
    return (f"Measured from SAM 3.1 tracks of this video: the moving object is a '{e['moved_object']['prompt']}' "
            f"({e['other_objects_of_same_kind']} others of the same kind stay put). Grab at {e['grab']['time_s']} s "
            f"(hand touching: {e['grab']['hand_touching']}), release at {e['release']['time_s']} s, ends inside the "
            f"'{e['container']['prompt']}': {e['ends_inside_container']}. Object width / container width in the image: "
            f"{e['size_ratio_object_to_container']}.")


def write_card(video_path, events, effort="medium", kind="pick_place"):
    """`kind` from name_objects: "open" uses the door schema; the SAM facts are about a moved object, so only
    pick-and-place cards get them."""
    opening = kind == "open"
    text = ("" if opening else facts_text(events) + "\n") + "Write the skill card for the task in this video."
    instructions, schema = {"open": (OPEN_INSTRUCTIONS, OPEN_SCHEMA), "carry": (CARRY_INSTRUCTIONS, CARRY_SCHEMA)}.get(
        kind, (INSTRUCTIONS, SCHEMA))
    body = {
        "model": "muse-spark-1.3",
        "instructions": instructions,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_video", "video_url": data_url(video_path)}]}],
        "text": {"format": {"type": "json_schema", "name": "skill_card", "schema": schema}},
        "reasoning": {"effort": effort},
        "max_output_tokens": 8000,
    }
    deltas, usage = stream_response(body)
    card = json.loads("".join(deltas))
    cost = None
    if usage:
        cost = usage.get("input_tokens", 0) * SPARK_IN + usage.get("output_tokens", 0) * SPARK_OUT
    return card, usage, cost


def _open_card(card):
    c, d, h = card["cabinet"], card["door"], card["handle"]
    cab, bar = c["name"].replace(" ", "_"), h["name"].replace(" ", "_")
    steps = []
    for s in card["steps"]:
        step = {"do": s["do"]}
        if s["do"] in ("reach", "approach"):
            step["object"] = bar
        elif s["do"] == "pull":
            step["object"] = cab
        elif s["do"] == "retreat":
            step["distance"] = 0.08
        steps.append(step)
    return {
        "name": card["name"], "kind": "open", "goal": card["goal"],
        "objects": {
            cab: {"shape": "cabinet", "size": c["size_m"], "color": c["color"],
                  "door": {"width": d["width_m"], "height": d["height_m"], "thickness": d["thickness_m"], "hinge": d["hinge"]}},
            bar: {"shape": "bar", "on": cab, "diameter": h["diameter_m"], "length": h["length_m"], "standoff": h["standoff_m"],
                  "from_free_edge": h["from_free_edge_m"], "height": h["height_m"], "color": h["color"]},
        },
        "grip": {"object": bar, "approach": "front", "between": "around", "width": h["diameter_m"]},
        "steps": steps,
        "success": {"test": "open_angle", "object": cab, "min_angle_deg": card["min_angle_deg"]},
        **_needs(card),
    }


def _needs(card):
    n = card.get("needs")
    if not n:
        return {}
    out = {k: n[k] for k in ("hands", "move_m", "keep_upright", "fragile", "guessed") if k in n}
    if n.get("mass_kg"):
        out["mass_kg"] = n["mass_kg"]
    return {"needs": out}


def _carry_card(card):
    o, p = card["object"], card["place"]
    obj, place = o["name"].replace(" ", "_"), p["name"].replace(" ", "_")
    steps = []
    for s in card["steps"]:
        step = {"do": s["do"]}
        if s["do"] == "reach":
            step["object"] = obj
        elif s["do"] == "walk":
            step["to"] = place
        elif s["do"] == "lift":
            step["height"] = 0.13
        steps.append(step)
    needs = _needs(card)
    needs.setdefault("needs", {})["mass_kg"] = o["mass_kg"]
    return {
        "name": card["name"], "kind": "carry", "goal": card["goal"],
        "objects": {
            obj: {"shape": "crate", "size": o["size_m"], "mass": o["mass_kg"], "color": o["color"], "handles": o["handles"],
                  "handle": {"diameter": o["handle_diameter_m"], "length": o["handle_length_m"], "height": o["handle_height_m"]}},
            place: {"shape": "place", "distance": p["distance_m"], "side": p["side"]},
        },
        "grip": {"object": obj, "approach": "top", "between": "around", "width": o["handle_diameter_m"]},
        "steps": steps,
        "success": {"test": "on_place", "object": obj, "place": place, "within": card["within_m"], "max_tilt_deg": 10},
        **needs,
    }


def to_translator_card(card):
    """The general card -> the format translate.py runs (objects keyed by name, steps pointing at them)."""
    if "cabinet" in card:
        return _open_card(card)
    if "place" in card:
        return _carry_card(card)
    held, cont = card["objects"]["held"], card["objects"]["container"]
    h, c = held["name"], cont["name"]
    steps = []
    for s in card["steps"]:
        do = s["do"]
        step = {"do": do}
        if do == "reach":
            step.update(to="above", object=h)
        elif do == "descend":
            step.update(object=h)
        elif do == "carry":
            step.update(to="above", object=c)
        elif do == "lower":
            step.update(into=c)
        elif do in ("lift", "retreat"):
            step.update(height=s.get("height_m", 0.10 if do == "lift" else 0.08))
        steps.append(step)
    return {
        "name": card["name"],
        "goal": card["goal"],
        "objects": {
            h: {"shape": held["shape"], "size": held["size_m"], "color": held["color"]},
            c: {"shape": cont["shape"], "inner_radius": cont["inner_radius_m"], "wall_height": cont["wall_height_m"],
                "color": cont["color"]},
        },
        "grip": {"object": h, "approach": card["grip"]["approach"], "between": card["grip"]["between"],
                 "width": card["grip"]["width_m"]},
        "steps": steps,
        "success": {"test": card["success"]["test"], "object": h, "container": c},
        **_needs(card),
    }


NAMES_SCHEMA = {
    "type": "object",
    "properties": {
        "moved_object": {"type": "string", "description": "short noun phrase for the one object that is picked up and moved, e.g. 'lemon'"},
        "container": {"type": "string", "description": "short noun phrase for where it is put, e.g. 'bowl'"},
        "hand": {"type": "string", "description": "short noun phrase for what moves it, usually 'hand'"},
        "kind": {"type": "string", "enum": ["pick_place", "open", "carry"],
                 "description": "pick_place: an object is picked up and put somewhere; open: a hinged door is pulled open "
                                "(then moved_object = the handle, container = the cabinet); carry: a box, crate or basket is "
                                "lifted with both hands or by its handle and taken to another place (then container = where "
                                "it ends up)"},
    },
    "required": ["moved_object", "container", "hand", "kind"],
}


def name_objects(video_path):
    """Muse Spark names the moved object and the container as short noun phrases that SAM 3.1 can track."""
    body = {
        "model": "muse-spark-1.3",
        "instructions": "Watch the video of a short task. First decide its kind from the FIRST complete action: if a hand "
                        "pulls a hinged door (cupboard, cabinet, wardrobe) open, the kind is open, even if the person then "
                        "does something else; if the person lifts a box, crate or basket with both hands or by its handle "
                        "and takes it to another place, the kind is carry; otherwise pick_place. For pick_place name the single object that is picked up "
                        "and moved and the container it is put into; for open name the knob or handle the hand pulls and "
                        "the cabinet. Also name what moves it. Use short concrete noun phrases (one to two words), the kind "
                        "an object detector can search for.",
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Decide the kind, then name the objects and the mover."},
            {"type": "input_video", "video_url": data_url(video_path)}]}],
        "text": {"format": {"type": "json_schema", "name": "task_objects", "schema": NAMES_SCHEMA}},
        "reasoning": {"effort": "low"},
        "max_output_tokens": 4000,
    }
    deltas, usage = stream_response(body)
    cost = usage.get("input_tokens", 0) * SPARK_IN + usage.get("output_tokens", 0) * SPARK_OUT if usage else None
    return json.loads("".join(deltas)), usage, cost
