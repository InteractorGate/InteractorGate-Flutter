import unittest
from unittest.mock import MagicMock, patch

import numpy as np

import positioning
from eye_tracker import FaceGeometry, FaceResult
from positioning import assess, estimate_distance_cm, run_positioning


def geometry(ipd_px=60.0, mid=(0.5, 0.45), roll=0.0, yaw=0.0, light=120.0):
    return FaceGeometry(eye_mid=mid, ipd_px=ipd_px, roll_deg=roll,
                        yaw_ratio=yaw, brightness=light, frame_size=(640, 480))


def px_for(cm):
    focal = 320 / np.tan(np.radians(positioning.CAMERA_HFOV_DEG / 2))
    return positioning.IPD_MM * focal / (cm * 10)


def by_key(checks):
    return {c.key: c for c in checks}


class DistanceTests(unittest.TestCase):
    def test_distance_follows_pinhole_model(self):
        self.assertAlmostEqual(estimate_distance_cm(px_for(60), 640), 60, places=3)
        self.assertGreater(estimate_distance_cm(40, 640), estimate_distance_cm(80, 640))
        self.assertIsNone(estimate_distance_cm(0, 640))


class AssessTests(unittest.TestCase):
    def test_good_position_passes_all_five_checks(self):
        checks = assess(geometry(ipd_px=px_for(60)))
        self.assertEqual(len(checks), 5)
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks])

    def test_missing_face_is_a_single_failed_check(self):
        checks = assess(None)
        self.assertEqual([c.key for c in checks], ["face"])
        self.assertFalse(checks[0].ok)

    def test_distance_hints(self):
        near = by_key(assess(geometry(ipd_px=px_for(40))))["distance"]
        far = by_key(assess(geometry(ipd_px=px_for(85))))["distance"]
        self.assertFalse(near.ok)
        self.assertIn("aléjese", near.detail)
        self.assertFalse(far.ok)
        self.assertIn("acérquese", far.detail)

    def test_centering_hints_are_mirrored(self):
        # En la imagen cruda el rostro a la izquierda (x=0.2) se ve a la
        # derecha en el espejo: la persona debe moverse hacia su izquierda.
        left_raw = by_key(assess(geometry(ipd_px=px_for(60), mid=(0.2, 0.45))))["center"]
        self.assertFalse(left_raw.ok)
        self.assertIn("izquierda", left_raw.detail)
        right_raw = by_key(assess(geometry(ipd_px=px_for(60), mid=(0.8, 0.45))))["center"]
        self.assertIn("derecha", right_raw.detail)
        high = by_key(assess(geometry(ipd_px=px_for(60), mid=(0.5, 0.1))))["center"]
        self.assertIn("arriba", high.detail)

    def test_head_and_light_hints(self):
        tilted = by_key(assess(geometry(ipd_px=px_for(60), roll=20)))["head"]
        turned = by_key(assess(geometry(ipd_px=px_for(60), yaw=0.4)))["head"]
        dark = by_key(assess(geometry(ipd_px=px_for(60), light=20)))["light"]
        bright = by_key(assess(geometry(ipd_px=px_for(60), light=240)))["light"]
        self.assertFalse(tilted.ok)
        self.assertFalse(turned.ok)
        self.assertIn("Poca luz", dark.detail)
        self.assertIn("Demasiada luz", bright.detail)


class LoopTests(unittest.TestCase):
    def _run(self, keys, faces):
        cap = MagicMock()
        cap.read.return_value = (True, np.zeros((480, 640, 3), np.uint8))
        tracker = MagicMock()
        tracker.process.side_effect = faces
        clock = iter(np.arange(0, 100, 0.5))
        with patch("positioning.cv2.imshow"), \
                patch("positioning.cv2.waitKey", side_effect=keys), \
                patch("positioning.cv2.getWindowProperty", return_value=1), \
                patch("positioning.time.time", side_effect=lambda: next(clock)):
            return run_positioning(cap, tracker, 100, "w")

    def _good(self):
        g = geometry(ipd_px=px_for(60))
        return FaceResult(right=None, left=None, pose_matrix=None, geometry=g)

    def test_continues_after_holding_a_good_position(self):
        summary, ts = self._run([-1] * 20, [self._good()] * 20)
        self.assertTrue(summary["all_checks_ok"])
        self.assertFalse(summary["forced_by_companion"])
        self.assertAlmostEqual(summary["distance_cm"], 60, delta=0.5)
        self.assertGreater(ts, 100)

    def test_enter_continues_and_records_failed_checks(self):
        summary, _ = self._run([-1, 13], [None, None])
        self.assertTrue(summary["forced_by_companion"])
        self.assertEqual(summary["failed_checks"], ["face"])

    def test_escape_cancels(self):
        with self.assertRaises(InterruptedError):
            self._run([27], [None])


if __name__ == "__main__":
    unittest.main()
