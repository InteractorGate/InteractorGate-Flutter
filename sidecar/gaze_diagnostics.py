"""Local visual inspection of the calibrated tracker; never controls the mouse."""
import hashlib
import json
import math
import time
import uuid
from collections import Counter
from pathlib import Path
from statistics import median

TARGETS = [(x, y) for y in (.08, .5, .92) for x in (.08, .5, .92)]
WINDOW = "InteractorGate - Diagnostico visual"
SETTLE_S = 1.2


def load_profile(path, screen):
    from calibration import GazeMapper
    data = Path(path).read_bytes()
    saved = json.loads(data)
    mapper = GazeMapper.from_dict(saved["gaze"])
    saved_screen = saved.get("screen_px", saved.get("screen"))
    if saved_screen is not None and list(saved_screen) != list(screen):
        raise ValueError(f"Resolucion distinta al perfil: {saved_screen} / {screen}")
    return mapper, hashlib.sha256(data).hexdigest()


def measure(face, mapper, smoother, now, threshold):
    from eye_tracker import feature_vector, head_angles
    sample = {"reason": "face_not_detected", "gate_open": False,
              "raw": None, "clipped": None, "smoothed": None,
              "open_gaze_threshold": threshold}
    if face is None:
        return sample
    features = feature_vector(face)
    if not all(math.isfinite(v) for v in features):
        return dict(sample, reason="invalid_features")
    openness = (face.right.openness + face.left.openness)/2
    sample.update(features=features, openness=[face.right.openness, face.left.openness],
                  mean_openness=openness, head_angles_rad=head_angles(face.pose_matrix),
                  gate_open=openness >= threshold,
                  reason=None if openness >= threshold else "low_aperture")
    # Observe the candidate even when the runtime gate would reject it.
    raw = mapper.transform_unclipped(features)
    if not all(math.isfinite(v) for v in raw):
        return dict(sample, reason="invalid_prediction", gate_open=False)
    clipped = [max(0., min(1., v)) for v in raw]
    sample.update(raw=list(raw), clipped=clipped)
    if sample["gate_open"]:
        sample["smoothed"] = list(smoother.update(*clipped, now))
    return sample


def summarize(samples, screen):
    groups = []
    for target_id in range(1, 10):
        rows = [s for s in samples if s["target_id"] == target_id and s["settled"]]
        valid = [s for s in rows if s["raw"] is not None]
        accepted = [s for s in valid if s["smoothed"] is not None]
        def errors(key, data):
            return [median((s[key][axis]-s["target"][axis])*screen[axis] for s in data)
                    for axis in range(2)] if data else None
        groups.append({"target_id": target_id, "samples_after_settle": len(rows),
                       "reasons": dict(Counter(s["reason"] or "accepted" for s in rows)),
                       "candidate_samples": len(valid), "accepted_samples": len(accepted),
                       "clipped_samples": sum(s["raw"] != s["clipped"] for s in valid),
                       "candidate_median_signed_error_px": errors("raw", valid),
                       "accepted_median_signed_error_px": errors("smoothed", accepted)})
    return groups


def draw(screen, frame, face, sample, target_id, paused, panels):
    import cv2
    import numpy as np
    width, height = screen
    target = TARGETS[target_id-1]
    canvas = np.full((height, width, 3), 22, np.uint8)
    for x in (.25, .5, .75):
        cv2.line(canvas, (int(x*width), 0), (int(x*width), height), (45, 45, 45))
    for y in (.25, .5, .75):
        cv2.line(canvas, (0, int(y*height)), (width, int(y*height)), (45, 45, 45))
    def point(p):
        return int(max(0, min(1, p[0]))*(width-1)), int(max(0, min(1, p[1]))*(height-1))
    cv2.circle(canvas, point(target), 19, (255, 255, 255), 3)
    cv2.circle(canvas, point(target), 4, (255, 255, 255), -1)
    if not paused:
        if sample["clipped"] is not None:
            cv2.drawMarker(canvas, point(sample["clipped"]), (255, 100, 255),
                           cv2.MARKER_CROSS, 24, 2)
        if sample["smoothed"] is not None:
            cv2.circle(canvas, point(sample["smoothed"]), 10, (0, 220, 255), 2)
    pw, ph = min(610, width//2), min(470, height//2)
    # Keep the panel away from the selected target, including the bottom row.
    ox = width-pw if target[0] < .5 else 0
    oy = height-ph if target[1] < .5 else 0
    if panels:
        panel = np.full((470, 610, 3), 38, np.uint8)
        lines = [f"Objetivo {target_id}/9  {'PAUSA' if paused else 'ACTIVO'}",
                 "Blanco: objetivo / cruz rosa: recortada",
                 "Amarillo: suavizada (solo apertura valida)",
                 "BLOQUEO: " + (sample["reason"] or "no")]
        if "openness" in sample:
            r, l = sample["openness"]
            lines += [f"Apertura R {r:.3f} / L {l:.3f} / media {sample['mean_openness']:.3f}",
                      f"Umbral de apertura: {sample['open_gaze_threshold']:.3f}",
                      "Pose yaw/pitch (rad): " + " / ".join(f"{v:+.3f}" for v in sample["head_angles_rad"])]
        for key, label in (("raw", "Antes de recorte"), ("clipped", "Recortada"), ("smoothed", "Suavizada")):
            if sample[key] is not None:
                x, y = sample[key]
                dx, dy = (x-target[0])*width, (y-target[1])*height
                lines.append(f"{label}: {x:+.3f}, {y:+.3f}  err {dx:+.0f}/{dy:+.0f}px")
        for i, line in enumerate(lines):
            cv2.putText(panel, line, (10, 22+i*23), cv2.FONT_HERSHEY_SIMPLEX, .49, (235, 235, 235), 1)
        if frame is not None:
            # Live image only: neither camera frames nor eye patches are saved.
            thumb = cv2.resize(frame, (224, 168))
            panel[285:453, 10:234] = thumb
        if face is not None:
            for i, eye in enumerate((face.right, face.left)):
                patch = cv2.cvtColor(cv2.resize(eye.patch, (150, 90)), cv2.COLOR_GRAY2BGR)
                panel[300:390, 250+i*170:400+i*170] = patch
            cv2.putText(panel, "Parches R / L (L volteado)", (250, 415), cv2.FONT_HERSHEY_SIMPLEX, .5, (235, 235, 235), 1)
        canvas[oy:oy+ph, ox:ox+pw] = cv2.resize(panel, (pw, ph))
    cv2.putText(canvas, "1-9: objetivo | ESPACIO: siguiente | P: pausa | V: panel | ESC: guardar/salir",
                (15, height-15), cv2.FONT_HERSHEY_SIMPLEX, .6, (235, 235, 235), 1)
    cv2.imshow(WINDOW, canvas)
    return cv2.waitKey(1) & 0xff


def run(profile, output=None):
    import cv2
    import config
    from bench_precision import documents_folder
    from eye_tracker import EyeTracker
    from smoothing import GazeSmoother2D
    screen = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    mapper, digest = load_profile(profile, screen)
    folder = Path(output) if output else documents_folder()/"InteractorGate"/"Diagnostico"
    folder = folder/str(uuid.uuid4())
    folder.mkdir(parents=True, exist_ok=False)
    metadata = {"schema": 1, "purpose": "visual_diagnostic_not_validation",
                "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "profile_sha256": digest, "profile_path": str(Path(profile).resolve()),
                "screen_px": screen, "camera_index": config.CAM_INDEX,
                "open_gaze_threshold": config.OPEN_GAZE_THRESHOLD,
                "smoothing": {"mincutoff": .5, "beta": .008},
                "settle_s": SETTLE_S, "targets": TARGETS,
                "images_saved": False, "os_cursor_control": False,
                "error_units": "signed_pixels_estimate_minus_target"}
    (folder/"session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    cap, tracker = None, None
    status, detail = "stopped", None
    samples, target_id, paused, panels = [], 5, False, True
    started = changed = time.monotonic()
    last_ms = 0
    smoother = GazeSmoother2D(mincutoff=.5, beta=.008)
    try:
        with (folder/"samples.jsonl").open("x", encoding="utf-8", buffering=1) as log:
            cap = config.open_camera()
            if not cap.isOpened():
                raise RuntimeError("Webcam no disponible. Cierra otras aplicaciones de camara.")
            metadata["capture_px"] = [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))]
            tracker = EyeTracker()
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            while time.monotonic()-started < 600:
                ok, frame = cap.read()
                now = time.monotonic()
                last_ms = max(last_ms+1, int(now*1000))
                face = tracker.process(frame, last_ms) if ok else None
                sample = measure(face, mapper, smoother, now, config.OPEN_GAZE_THRESHOLD) if not paused else {
                    "reason": "paused", "gate_open": False, "raw": None, "clipped": None, "smoothed": None}
                if not ok and not paused:
                    sample["reason"] = "camera_read_failed"
                sample.update(elapsed_s=now-started, target_id=target_id, target=TARGETS[target_id-1],
                              settled=not paused and now-changed >= SETTLE_S)
                log.write(json.dumps(sample, allow_nan=False)+"\n")
                samples.append(sample)
                key = draw(screen, frame if ok else None, face, sample, target_id, paused, panels)
                if key in (27, ord('q')) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key == ord('p'):
                    paused = not paused
                    changed = now
                    smoother = GazeSmoother2D(mincutoff=.5, beta=.008)
                elif key == ord('v'):
                    panels = not panels
                elif key == 32 or ord('1') <= key <= ord('9'):
                    target_id = target_id % 9+1 if key == 32 else key-ord('0')
                    changed = now
            else:
                status = "time_limit"
    except (Exception, KeyboardInterrupt) as exc:
        status, detail = "error", str(exc) or type(exc).__name__
    finally:
        if cap is not None:
            cap.release()
        if tracker is not None:
            tracker.close()
        cv2.destroyAllWindows()
        (folder/"session.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        report = {"status": status, "detail": detail, "sample_count": len(samples),
                  "targets": summarize(samples, screen),
                  "limitations": "Exploratorio con cursor visible. No demuestra precision ni eficacia. "
                                  "Baja apertura no demuestra ojos cerrados. Error candidato incluye bloqueos."}
        (folder/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        messagebox.showinfo("Diagnostico - Registros guardados",
                            f"Estado: {status}\n{detail or 'Inspeccion finalizada'}\n"
                            f"Muestras: {len(samples)}\nCarpeta: {folder}", parent=root)
    finally:
        root.destroy()
    return folder
