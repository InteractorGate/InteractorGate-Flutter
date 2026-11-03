"""E1 geometry, trial accounting and local evidence; no camera/UI dependencies."""
import hashlib
import json
import math
import random
import re
import statistics
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ENGINES = ("gazecnn_generic", "mediapipe_ridge_calibrated")
WORDS = ("Si", "No", "Gracias", "Agua", "Comida", "Ayuda", "Teclado", "Borrar")
PHASES = ("angular", "open_loop", "closed_loop", "observation")


@dataclass(frozen=True)
class Geometry:
    width_px: int
    height_px: int
    width_mm: float
    height_mm: float
    eye_screen_distance_mm: float
    eye_x_mm: float = 0
    eye_y_mm: float = 0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not math.isfinite(value) or (key not in {"eye_x_mm", "eye_y_mm"} and value <= 0):
                raise ValueError(f"Invalid geometry: {key}")

    def ray(self, point):
        x, y = point
        return ((x - .5) * self.width_mm - self.eye_x_mm,
                (y - .5) * self.height_mm - self.eye_y_mm,
                self.eye_screen_distance_mm)

    def angular_error(self, estimated, target):
        a, b = self.ray(estimated), self.ray(target)
        cosine = sum(x*y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))
        return math.degrees(math.acos(max(-1, min(1, cosine))))


def generic_point(pitch, yaw):
    """Existing backend's fixed +/-25deg mapping, without clipping outliers.

    Operational screen estimate, NOT a camera-to-screen extrinsic calibration.
    Keep the original CNN angles separately; do not report screen error as its
    native MPIIGaze angular metric.
    """
    half_fov = math.radians(25)
    return .5 + yaw / (2*half_fov), .5 - pitch / (2*half_fov)


def cells():
    # Dedicated eight-cell benchmark; never infer geometry from Flutter chrome.
    return [{"id": i, "label": word,
             "rect": [.05 + (i % 4)*.225 + .005, .18 + (i // 4)*.32 + .005,
                      .05 + (i % 4 + 1)*.225 - .005, .18 + (i // 4 + 1)*.32 - .005]}
            for i, word in enumerate(WORDS)]


def cell_at(point):
    if point is None:
        return None
    x, y = point
    for cell in cells():
        x0, y0, x1, y1 = cell["rect"]
        if x0 <= x < x1 and y0 <= y < y1:
            return cell["id"]
    return None


def targets(phase):
    if phase == "angular":
        return [{"id": f"p{row}{col}", "point": [x, y]}
                for row, y in enumerate((.2, .5, .8))
                for col, x in enumerate((.2, .5, .8))]
    if phase in {"open_loop", "closed_loop"}:
        return [{"id": c["id"], "point": [(c["rect"][0]+c["rect"][2])/2,
                                             (c["rect"][1]+c["rect"][3])/2]}
                for c in cells()]
    return [{"id": "free", "point": None}]


def validate_config(config):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", config["participant_code"]):
        raise ValueError("Use a pseudonymous participant code (letters, digits, _ or -).")
    if config["cohort"] not in {"pilot", "target"}:
        raise ValueError("cohort must be pilot or target")
    engines = config.get("engines", list(ENGINES))
    if (not isinstance(engines, list) or not engines or len(set(engines)) != len(engines)
            or any(e not in ENGINES for e in engines)):
        raise ValueError("Choose distinct supported engines")
    if config["cohort"] == "target" and engines != list(ENGINES):
        raise ValueError("The target-population protocol requires both engines in order")
    for name in ("screen_width_mm", "screen_height_mm", "capture_s", "settle_s",
                 "selection_timeout_s", "observation_s", "dwell_s"):
        value = config.get(name)
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Provide a positive measured value for {name}")
    if not 1 <= config.get("repetitions", 0) <= 10:
        raise ValueError("repetitions must be between 1 and 10")
    if not 1 <= config.get("min_valid_samples", 0) <= 1000:
        raise ValueError("min_valid_samples must be between 1 and 1000")
    if not config.get("conditions") or len(config["conditions"]) > 16:
        raise ValueError("Provide between 1 and 16 conditions")
    for c in config["conditions"]:
        if c["lighting"] not in {"natural", "artificial"} or not c.get("posture"):
            raise ValueError("Each condition requires lighting and posture")
        distance = c.get("nominal_camera_distance_cm")
        if type(distance) not in {int, float} or not 10 <= distance <= 200:
            raise ValueError("Invalid nominal camera distance")
    for key in ("eye_x_mm", "eye_y_mm"):
        if not math.isfinite(config.get(key, 0)):
            raise ValueError(f"Invalid {key}")


def make_plan(config):
    validate_config(config)
    rng = random.Random(config["seed"])
    conditions = [{**c, "condition_id": f"c{i+1}"}
                  for i, c in enumerate(config["conditions"])]
    rng.shuffle(conditions)
    plan = []
    for condition in conditions:
        # Same target order for both engines permits pairing by target/repetition.
        orders = {}
        for phase in PHASES:
            order = [{**t, "repetition": rep+1} for rep in range(
                1 if phase == "observation" else config["repetitions"])
                for t in targets(phase)]
            rng.shuffle(order)
            orders[phase] = order
        for engine in config.get("engines", ENGINES):
            for phase in PHASES:
                for target in orders[phase]:
                    plan.append({"trial_id": str(uuid.uuid4()), **condition,
                                 "engine": engine, "phase": phase, "target": target})
    return plan


class Dwell:
    """Continuous dwell, reset by exit or tracking loss (same as DwellButton)."""
    def __init__(self, duration):
        self.duration, self.cell, self.since = duration, None, None

    def update(self, cell, now):
        if cell != self.cell or cell is None:
            self.cell, self.since = cell, now if cell is not None else None
        if self.since is not None and now - self.since >= self.duration:
            selected = self.cell
            self.cell, self.since = None, None
            return selected
        return None


def summarize_trial(trial, events, minimum):
    samples = [e for e in events if e["type"] == "sample"]
    valid = [e for e in samples if e.get("gaze") is not None]
    end = next((e for e in events if e["type"] == "trial_end"), None)
    selections = [e for e in events if e["type"] == "selection"]
    errors = [e["angular_error_screen_deg"] for e in valid
              if e.get("angular_error_screen_deg") is not None]
    if len(valid) < minimum:
        errors = []
    estimate = [statistics.median(e["gaze"][i] for e in valid) for i in (0, 1)] if len(valid) >= minimum else None
    selected = selections[0] if selections else None
    status = (end or {}).get("status", "interrupted" if events else "not_run")
    if status == "completed" and len(valid) < minimum:
        status = "insufficient_tracking"
    annotations = {e["activation_id"]: e["label"] for e in events if e["type"] == "annotation"}
    activations = [e for e in events if e["type"] == "activation"]
    labels = [annotations.get(e["activation_id"], "unreviewed") for e in activations]
    elapsed = (end or {}).get("duration_s")
    reviewed = all(label in {"intended", "unintended"} for label in labels)
    return {**trial, "status": status, "attempted": bool(events),
            "frames": len(samples), "valid_samples": len(valid),
            "tracking_ratio": len(valid)/len(samples) if samples else None,
            "angular_mean_screen_deg": statistics.mean(errors) if errors else None,
            "angular_median_screen_deg": statistics.median(errors) if errors else None,
            "open_loop_cell": cell_at(estimate),
            "open_loop_correct": cell_at(estimate) == trial["target"]["id"] if estimate else False,
            "confirmed_cell": selected["cell"] if selected else None,
            "confirmed_correct": selected["cell"] == trial["target"]["id"] if selected else None,
            "selection_s": selected["elapsed_s"] if selected else None,
            "selection_method": selected["method"] if selected else None,
            "observation_s": elapsed, "blink_events": sum(e.get("blink", False) for e in samples),
            "activations": len(activations), "activation_labels": labels,
            "unintended_per_min": labels.count("unintended")*60/elapsed
            if trial["phase"] == "observation" and status == "completed" and reviewed
            and len(valid) >= minimum and elapsed else None}


def summarize(plan, events, minimum):
    grouped = {}
    for e in events:
        grouped.setdefault(e.get("trial_id"), []).append(e)
    trials = [summarize_trial(t, grouped.get(t["trial_id"], []), minimum) for t in plan]
    conditions = []
    for key in dict.fromkeys((t["condition_id"], t["engine"]) for t in trials):
        group = [t for t in trials if (t["condition_id"], t["engine"]) == key and t["attempted"]]
        opened = [t for t in group if t["phase"] == "open_loop"]
        closed = [t for t in group if t["phase"] == "closed_loop"]
        confirmed = [t for t in closed if t["confirmed_cell"] is not None]
        angles = [t["angular_mean_screen_deg"] for t in group if t["phase"] == "angular"
                  and t["status"] == "completed" and t["angular_mean_screen_deg"] is not None]
        observation = next((t for t in group if t["phase"] == "observation"), None)
        measured = next((e for e in events if e["type"] == "condition_confirmed"
                         and e["condition"]["condition_id"] == key[0]), None)
        times = [t["selection_s"] for t in confirmed]
        conditions.append({"condition_id": key[0], "engine": key[1],
                           "measured_condition": measured,
                           "angular_mean_of_targets_deg": statistics.mean(angles) if angles else None,
                           "angular_median_of_target_means_deg": statistics.median(angles) if angles else None,
                           "angular_targets_measured": len(angles),
                           "i2_correct": sum(t["open_loop_correct"] for t in opened),
                           "i2_attempted": len(opened),
                           "i2_ratio": sum(t["open_loop_correct"] for t in opened)/len(opened) if opened else None,
                           "i3_wrong_confirmed": sum(not t["confirmed_correct"] for t in confirmed),
                           "i3_confirmed": len(confirmed),
                           "i3_ratio": sum(not t["confirmed_correct"] for t in confirmed)/len(confirmed) if confirmed else None,
                           "closed_without_selection": len(closed)-len(confirmed),
                           "selection_mean_s": statistics.mean(times) if times else None,
                           "selection_median_s": statistics.median(times) if times else None,
                           "unintended_activations_per_min": observation["unintended_per_min"] if observation else None})
    ending = next((e for e in reversed(events) if e["type"] == "session_end"), {})
    return {"schema_version": 1, "session_status": ending.get("status", "unfinished"),
            "session_reason": ending.get("reason"), "trials": trials, "conditions": conditions,
            "planned": len(plan), "attempted": sum(t["attempted"] for t in trials),
            "not_run": sum(t["status"] == "not_run" for t in trials)}


class Evidence:
    def __init__(self, root, metadata, plan):
        self.session_id = str(uuid.uuid4())
        self.folder = Path(root)/metadata["participant_code"]/self.session_id
        self.folder.mkdir(parents=True, exist_ok=False)
        self.events = []
        self.plan = plan
        metadata = {**metadata, "session_id": self.session_id,
                    "created_at": datetime.now(timezone.utc).isoformat(), "plan": plan}
        self.write_json("session.json", metadata)
        self.stream = (self.folder/"events.jsonl").open("x", encoding="utf-8")

    def write_json(self, name, value):
        with (self.folder/name).open("x", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)

    def append(self, kind, trial_id=None, **fields):
        event = {"type": kind, "trial_id": trial_id, **fields}
        self.stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False)+"\n")
        self.stream.flush()
        self.events.append(event)

    def close(self, minimum):
        self.stream.close()
        self.write_json("report.json", summarize(self.plan, self.events, minimum))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
