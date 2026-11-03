"""Local E1 instrument. --init-config FILE, then --config FILE [--output DIR]."""
import argparse
import ctypes
import importlib.metadata
import json
import math
import os
import time
import uuid
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from e1_protocol import (ENGINES, Evidence, Geometry, Dwell, cell_at, cells,
                         generic_point, make_plan, sha256, validate_config)

WINDOW = "InteractorGate - E1"
PHASE_LABELS = {"angular": "Fijacion de puntos (sin cursor)",
                "open_loop": "Celda estimada (sin cursor)",
                "closed_loop": "Seleccion confirmada (con cursor)",
                "observation": "Observacion libre (sin intentar seleccionar)"}
ENGINE_LABELS = {ENGINES[0]: "CNN generica", ENGINES[1]: "Motor calibrado"}


def template():
    return {"participant_code": "PILOTO_E1", "cohort": "pilot", "seed": 42,
            "engines": list(ENGINES),
            "screen_width_mm": None, "screen_height_mm": None,
            "eye_x_mm": 0, "eye_y_mm": 0,
            "eye_alignment_basis": "assumed_centered_record_or_replace_with_measurements",
            "repetitions": 1, "min_valid_samples": 5,
            "settle_s": 1.2, "capture_s": 1.2, "dwell_s": 1.2,
            "selection_timeout_s": 8, "observation_s": 30,
            "conditions": [{"lighting": light, "nominal_camera_distance_cm": distance,
                            "posture": posture}
                           for light in ("natural", "artificial")
                           for distance in (50, 70)
                           for posture in ("habitual", "variacion_postura_permitida")]}


def documents_folder():
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home()/"Documents"


def condition_geometry(condition, cfg, width, height):
    # Researcher confirms actual distances after positioning; nominal != measured.
    import tkinter as tk
    from tkinter import simpledialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        text = (f"{condition['lighting']} / {condition['posture']}\n"
                f"Distancia nominal: {condition['nominal_camera_distance_cm']} cm.\n"
                "Ajusta la luz y postura sin forzar movimientos.\n"
                "Mide ojos-camara (cm):")
        camera = simpledialog.askfloat("E1 - Condicion", text, parent=root,
                                       minvalue=10, maxvalue=200)
        if camera is None:
            raise InterruptedError("Condition setup cancelled")
        distance = simpledialog.askfloat("E1 - Geometria", "Mide ojos-pantalla (cm):",
                                         parent=root, minvalue=10, maxvalue=200)
        if distance is None:
            raise InterruptedError("Geometry setup cancelled")
    finally:
        root.destroy()
    return Geometry(width, height, cfg["screen_width_mm"], cfg["screen_height_mm"],
                    distance*10, cfg.get("eye_x_mm", 0), cfg.get("eye_y_mm", 0)), camera


class Camera:
    def __init__(self):
        import config
        from blink_detector import BlinkDetector
        from eye_tracker import EyeTracker
        from gaze_cnn import GazeModel
        self.cap = config.open_camera()
        self.tracker = None
        self.blink = BlinkDetector(threshold=config.BLINK_THRESHOLD)
        self.last_ms = 0
        self.deadline = time.monotonic()+45*60
        try:
            if not self.cap.isOpened():
                raise RuntimeError("Webcam unavailable; close other camera applications.")
            self.tracker = EyeTracker()
            self.cnn = GazeModel()
        except BaseException:
            self.close()
            raise

    def close(self):
        self.cap.release()
        if self.tracker is not None:
            self.tracker.close()

    def reset_blink(self):
        import config
        from blink_detector import BlinkDetector
        self.blink = BlinkDetector(threshold=config.BLINK_THRESHOLD)

    def frame(self, engine, mapper, smoother):
        import config
        from blink_detector import BlinkDetector
        from eye_tracker import feature_vector, head_angles
        if time.monotonic() >= self.deadline:
            raise InterruptedError("45 minute session limit reached")
        ok, frame = self.cap.read()
        now = time.monotonic()
        self.last_ms = max(self.last_ms+1, int(now*1000))
        face = self.tracker.process(frame, self.last_ms) if ok else None
        if face is None:
            self.blink = BlinkDetector(threshold=config.BLINK_THRESHOLD)
            return {"gaze": None, "blink": False,
                    "reason": "face_not_detected" if ok else "camera_read_failed"}
        openness = (face.right.openness+face.left.openness)/2
        blink = self.blink.detect(openness, now=now)
        if openness < config.OPEN_GAZE_THRESHOLD:
            return {"gaze": None, "blink": blink, "reason": "eyes_closed"}
        features = feature_vector(face)
        if not all(math.isfinite(f) for f in features):
            return {"gaze": None, "blink": False, "reason": "invalid_features"}
        sample = {"gaze": None, "blink": blink, "features": features,
                  "head_angles_rad": head_angles(face.pose_matrix), "reason": None}
        if engine == ENGINES[0]:
            pitch, yaw = map(float, self.cnn.predict(face.right.patch)[0])
            sample["cnn_angles_rad"] = [pitch, yaw]
            point = generic_point(pitch, yaw)
        elif engine == ENGINES[1]:
            point = mapper.transform(features)
        else:
            return sample
        if not all(math.isfinite(x) for x in point):
            sample.update(reason="invalid_prediction", gaze=None)
        else:
            sample["raw_gaze"] = list(point)
            sample["gaze"] = list(smoother.update(*point, now))
        return sample


def draw(width, height, lines, target=None, gaze=None, selected=None):
    import cv2
    import numpy as np
    canvas = np.full((height, width, 3), 20, dtype=np.uint8)
    for c in cells():
        x0, y0, x1, y1 = c["rect"]
        p0, p1 = (int(x0*width), int(y0*height)), (int(x1*width), int(y1*height))
        color = (60, 120, 60) if target and target["id"] == c["id"] else (45, 45, 45)
        if selected == c["id"]:
            color = (120, 90, 30)
        cv2.rectangle(canvas, p0, p1, color, -1)
        cv2.putText(canvas, c["label"], (p0[0]+15, (p0[1]+p1[1])//2),
                    cv2.FONT_HERSHEY_SIMPLEX, .8, (230, 230, 230), 2)
    if target and target["point"] and isinstance(target["id"], str):
        point = target["point"]
        cv2.circle(canvas, (int(point[0]*width), int(point[1]*height)), 12, (0, 0, 255), -1)
    if gaze is not None and all(abs(v) < 10 for v in gaze):
        cv2.circle(canvas, (int(gaze[0]*width), int(gaze[1]*height)), 9, (0, 180, 255), -1)
    for i, line in enumerate(lines):
        cv2.putText(canvas, line, (25, 28+i*26), cv2.FONT_HERSHEY_SIMPLEX,
                    .55, (240, 240, 240), 1)
    cv2.imshow(WINDOW, canvas)
    key = cv2.waitKey(1) & 0xff
    if key == 27 or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
        raise InterruptedError("Operator stopped the session")
    return key


def prompt(width, height, lines):
    while draw(width, height, [*lines, "ESPACIO: continuar   ESC: guardar y salir"]) != 32:
        time.sleep(.02)


def show_result(folder):
    import tkinter as tk
    from tkinter import messagebox
    report = json.loads((folder/"report.json").read_text(encoding="utf-8"))
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        messagebox.showinfo("E1 - Resultados guardados",
                            f"Estado: {report['session_status']}\n"
                            f"Detalle: {report.get('session_reason') or 'Recorrido finalizado'}\n"
                            f"Ensayos iniciados: {report['attempted']}/{report['planned']}\n"
                            f"Carpeta: {folder}\n\n"
                            "Conservar los ensayos sin seguimiento. Estos datos no demuestran eficacia.",
                            parent=root)
    finally:
        root.destroy()


def retry_calibration_point(camera, width, height, number, count, minimum, reasons):
    labels = {"eyes_closed": "apertura de ojos insuficiente",
              "face_not_detected": "rostro no detectado",
              "camera_read_failed": "sin fotograma", "invalid_features": "datos no validos"}
    detail = "; ".join(f"{labels.get(k, k)}: {v}" for k, v in reasons.items())
    while True:
        if time.monotonic() >= camera.deadline:
            raise InterruptedError("45 minute session limit reached")
        key = draw(width, height, [f"Calibracion: punto {number}, {count}/{minimum} muestras validas.",
                                   detail[:160], "Comprueba el encuadre y vuelve a mirar el punto.",
                                   "R: reintentar punto / C: omitir motor / ESC: guardar y salir"])
        if chr(key).lower() in {"r", "c"}:
            return chr(key).lower() == "r"
        time.sleep(.02)


def calibrate(camera, evidence, condition, cfg, width, height):
    from calibration import CALIB_POINTS, GazeMapper
    from smoothing import GazeSmoother2D
    features, targets = [], []
    accepted = []
    smoother = GazeSmoother2D()
    for i, point in enumerate(CALIB_POINTS):
        attempt = 0
        while True:
            attempt += 1
            captured, reasons = [], Counter()
            start = time.monotonic()
            while time.monotonic()-start < cfg["settle_s"]+cfg["capture_s"]:
                sample = camera.frame(None, None, smoother)
                draw(width, height, [f"Calibracion {i+1}/{len(CALIB_POINTS)}: mira el punto rojo"],
                     target={"id": f"cal{i}", "point": point})
                if time.monotonic()-start < cfg["settle_s"]:
                    continue
                if sample.get("features"):
                    captured.append(sample["features"])
                    evidence.append("calibration_sample", condition_id=condition["condition_id"],
                                    point=point, attempt=attempt, features=sample["features"])
                else:
                    reasons[sample.get("reason") or "unknown"] += 1
            usable = len(captured) >= cfg["min_valid_samples"]
            evidence.append("calibration_attempt_end", condition_id=condition["condition_id"],
                            point=point, attempt=attempt, valid_samples=len(captured),
                            usable=usable, invalid_reasons=dict(reasons))
            if usable:
                features.extend(captured)
                targets.extend([point]*len(captured))
                accepted.append({"point": point, "attempt": attempt})
                break
            if not retry_calibration_point(camera, width, height, i+1, len(captured),
                                           cfg["min_valid_samples"], reasons):
                evidence.append("calibration_failed", condition_id=condition["condition_id"],
                                point=point, valid_samples=len(captured), invalid_reasons=dict(reasons))
                return None
    mapper = GazeMapper().fit(features, targets)
    evidence.write_json(f"calibration_{condition['condition_id']}.json",
                        {"method": ENGINES[1], "gaze": mapper.to_dict(),
                         "points": CALIB_POINTS, "samples": len(features),
                         "accepted_attempts": accepted,
                         "condition": condition, "screen_px": [width, height]})
    return mapper


def run_trial(camera, evidence, trial, cfg, geometry, mapper):
    from smoothing import GazeSmoother2D
    camera.reset_blink()
    width, height = geometry.width_px, geometry.height_px
    phase, target = trial["phase"], trial["target"]
    visible = phase in {"closed_loop", "observation"}
    lines = [f"{ENGINE_LABELS[trial['engine']]} / {PHASE_LABELS[phase]} / objetivo {target['id']}",
             "No intentes seleccionar. Observa libremente." if phase == "observation"
             else "Selecciona con permanencia o parpadeo." if phase == "closed_loop"
             else "Mira el objetivo y manten la mirada hasta que cambie."]
    draw(width, height, lines, target=target)
    start = time.monotonic()
    evidence.append("trial_start", trial["trial_id"], geometry=asdict(geometry))
    dwell = Dwell(cfg["dwell_s"])
    smoother = GazeSmoother2D(mincutoff=.5, beta=.008)
    activations = []
    settle = cfg["settle_s"] if phase in {"angular", "open_loop"} else 0
    duration = (cfg["observation_s"] if phase == "observation" else
                cfg["selection_timeout_s"] if phase == "closed_loop" else settle+cfg["capture_s"])
    status = "completed"
    try:
        while time.monotonic()-start < duration:
            sample = camera.frame(trial["engine"], mapper, smoother)
            sample.pop("features", None)
            elapsed = time.monotonic()-start
            gaze = sample["gaze"]
            if gaze is not None and target["point"]:
                sample["angular_error_screen_deg"] = geometry.angular_error(gaze, target["point"])
            cell = cell_at(gaze)
            draw(width, height, lines, target=target, gaze=gaze if visible else None,
                 selected=cell if phase == "closed_loop" else None)
            if elapsed < settle:
                continue
            evidence.append("sample", trial["trial_id"], elapsed_s=elapsed, **sample)
            if phase == "closed_loop":
                held = dwell.update(cell, time.monotonic())
                chosen = cell if sample["blink"] and cell is not None else held
                if chosen is not None:
                    evidence.append("selection", trial["trial_id"], cell=chosen,
                                    method="blink" if sample["blink"] else "dwell", elapsed_s=elapsed)
                    break
            elif phase == "observation" and sample["blink"] and cell is not None:
                activation = {"activation_id": str(uuid.uuid4()), "cell": cell, "elapsed_s": elapsed}
                evidence.append("activation", trial["trial_id"], **activation)
                activations.append(activation)
    except BaseException:
        status = "interrupted"
        raise
    finally:
        evidence.append("trial_end", trial["trial_id"], status=status,
                        duration_s=time.monotonic()-start)
    for event in activations:
        label = None
        while label is None:
            key = draw(width, height, [f"Revision: activacion {event['elapsed_s']:.2f}s, celda {event['cell']}",
                                       "U: no intencional / I: intencional / D: dudosa"])
            label = {'u': "unintended", 'i': "intended", 'd': "uncertain"}.get(chr(key).lower())
        evidence.append("annotation", trial["trial_id"], activation_id=event["activation_id"], label=label)


def run(cfg, output=None):
    import cv2
    import config
    from gaze_cnn import DEFAULT_ONNX, DEFAULT_META
    from eye_tracker import MODEL_PATH
    validate_config(cfg)
    width, height = config.SCREEN_WIDTH, config.SCREEN_HEIGHT
    plan = make_plan(cfg)
    metadata = {**cfg, "instrument": "e1-v1", "screen_px": [width, height],
                "generic_mapping": "fixed_25deg_backend_mapping_unclipped",
                "angular_metric": "operational_screen_ray_error_not_native_cnn_error",
                "smoothing": {"mincutoff": .5, "beta": .008},
                "dwell_exit_tolerance_s": 0, "cell_count": 8,
                "cnn_sha256": sha256(DEFAULT_ONNX), "cnn_metadata_sha256": sha256(DEFAULT_META),
                "face_landmarker_sha256": sha256(MODEL_PATH),
                "versions": {name: importlib.metadata.version(name) for name in
                             ("mediapipe", "opencv-python", "onnxruntime", "numpy")}}
    evidence = Evidence(output or documents_folder()/"InteractorGate"/"E1", metadata, plan)
    camera = None
    hide_cursor = False
    try:
        camera = Camera()
        evidence.append("camera_started", index=config.CAM_INDEX,
                        width=camera.cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                        height=camera.cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                        reported_fps=camera.cap.get(cv2.CAP_PROP_FPS))
        last_pause = time.monotonic()
        for cid in dict.fromkeys(t["condition_id"] for t in plan):
            trials = [t for t in plan if t["condition_id"] == cid]
            condition = {k: trials[0][k] for k in
                         ("condition_id", "lighting", "posture", "nominal_camera_distance_cm")}
            cv2.destroyAllWindows()
            if hide_cursor:
                ctypes.windll.user32.ShowCursor(True)
                hide_cursor = False
            geometry, distance = condition_geometry(condition, cfg, width, height)
            evidence.append("condition_confirmed", condition=condition,
                            actual_camera_distance_cm=distance, geometry=asdict(geometry))
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            if os.name == "nt" and not hide_cursor:
                ctypes.windll.user32.ShowCursor(False)
                hide_cursor = True
            mapper, previous = None, None
            for trial in trials:
                if time.monotonic()-last_pause >= 600:
                    prompt(width, height, ["Pausa. Descansa y continua solo si estas comodo."])
                    last_pause = time.monotonic()
                stage = (trial["engine"], trial["phase"])
                if stage != previous:
                    prompt(width, height, [f"Condicion {cid}: {condition['lighting']} / {condition['posture']}",
                                           f"{ENGINE_LABELS[stage[0]]} / {PHASE_LABELS[stage[1]]}",
                                           "ESC interrumpe ante fatiga o malestar."])
                    viewport = cv2.getWindowImageRect(WINDOW)
                    if tuple(viewport) != (0, 0, width, height):
                        raise RuntimeError(f"E1 requires the complete primary screen; viewport={viewport}")
                    if stage == (ENGINES[1], "angular"):
                        mapper = calibrate(camera, evidence, condition, cfg, width, height)
                        if mapper is None:
                            evidence.append("engine_skipped", condition_id=cid,
                                            engine=ENGINES[1], reason="insufficient_calibration")
                            break
                    previous = stage
                run_trial(camera, evidence, trial, cfg, geometry, mapper)
        ended = {e["trial_id"] for e in evidence.events if e["type"] == "trial_end"}
        complete = len(ended) == len(plan)
        evidence.append("session_end", status="completed" if complete else "incomplete",
                        reason=None if complete else "Calibracion insuficiente: el motor calibrado no se evaluo.")
    except (InterruptedError, KeyboardInterrupt) as error:
        evidence.append("session_end", status="interrupted", reason=str(error))
    except BaseException as error:
        evidence.append("session_end", status="error", reason=str(error))
        raise
    finally:
        if camera is not None:
            camera.close()
        cv2.destroyAllWindows()
        if hide_cursor:
            ctypes.windll.user32.ShowCursor(True)
        evidence.close(cfg["min_valid_samples"])
        print(f"E1 evidence: {evidence.folder}", flush=True)
    show_result(evidence.folder)
    return evidence.folder


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-config", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.init_config:
        with args.init_config.open("x", encoding="utf-8") as f:
            json.dump(template(), f, indent=2)
        return
    if not args.config:
        parser.error("Provide --config FILE, or create a template with --init-config FILE.")
    run(json.loads(args.config.read_text(encoding="utf-8")), args.output)


if __name__ == "__main__":
    main()
