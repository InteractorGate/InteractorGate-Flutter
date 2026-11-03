import tempfile
import unittest
from unittest.mock import patch, MagicMock

from bench_precision import Camera as RealCamera, run_trial, calibrate
from blink_detector import BlinkDetector
from e1_protocol import ENGINES, Evidence, Geometry
from test_e1_protocol import config, trial


class Clock:
    def __init__(self):
        self.now = 10

    def __call__(self):
        self.now += .05
        return self.now


class Camera:
    def reset_blink(self):
        self.was_reset = True

    def frame(self, engine, mapper, smoother):
        assert self.was_reset
        return {"gaze": [.1625, .34], "blink": True, "reason": None}


class RunnerTests(unittest.TestCase):
    def test_failed_calibration_point_can_retry_without_using_invalid_samples(self):
        cfg = config()
        cfg.update(settle_s=.1, capture_s=.5, min_valid_samples=1)
        camera = MagicMock()
        camera.frame.return_value = {"reason": "eyes_closed", "gaze": None}
        def retry(*args):
            camera.frame.return_value = {"features": [1.0]*12}
            return True
        with tempfile.TemporaryDirectory() as folder:
            evidence = Evidence(folder, cfg, [])
            with patch('calibration.CALIB_POINTS', [(.92, .64)]), \
                    patch('calibration.GazeMapper') as factory, \
                    patch('bench_precision.time.monotonic', Clock()), \
                    patch('bench_precision.draw'), \
                    patch('bench_precision.retry_calibration_point', side_effect=retry) as prompt:
                mapper = factory.return_value.fit.return_value
                mapper.to_dict.return_value = {'test_model': True}
                self.assertIs(calibrate(camera, evidence, {'condition_id':'c1'}, cfg, 1920, 1080), mapper)
                self.assertEqual(prompt.call_count, 1)
                self.assertTrue(all(row == [1.0]*12 for row in factory.return_value.fit.call_args.args[0]))
            attempts = [e for e in evidence.events if e['type'] == 'calibration_attempt_end']
            self.assertEqual([e['usable'] for e in attempts], [False, True])
            self.assertGreater(attempts[0]['invalid_reasons']['eyes_closed'], 0)
            evidence.close(1)

    def test_declining_a_failed_calibration_does_not_fit_a_model(self):
        cfg = config()
        cfg.update(settle_s=.1, capture_s=.5, min_valid_samples=1)
        camera = MagicMock()
        camera.frame.return_value = {'gaze':None, 'reason':'face_not_detected'}
        with tempfile.TemporaryDirectory() as folder:
            evidence = Evidence(folder, cfg, [])
            with patch('calibration.CALIB_POINTS', [(.92, .64)]), \
                    patch('calibration.GazeMapper') as factory, \
                    patch('bench_precision.time.monotonic', Clock()), \
                    patch('bench_precision.draw'), \
                    patch('bench_precision.retry_calibration_point', return_value=False):
                self.assertIsNone(calibrate(camera, evidence, {'condition_id':'c1'}, cfg, 1920, 1080))
                factory.assert_not_called()
            self.assertEqual(evidence.events[-1]['type'], 'calibration_failed')
            evidence.close(1)

    def test_eye_closure_before_a_pause_cannot_become_a_new_trial_activation(self):
        camera = RealCamera.__new__(RealCamera)
        camera.blink = BlinkDetector()
        camera.blink.detect(.1, now=1)
        camera.blink.detect(.1, now=1.1)
        camera.reset_blink()
        self.assertFalse(camera.blink.detect(.3, now=10))

    def test_open_loop_never_displays_estimated_gaze_and_records_samples(self):
        cfg = config()
        cfg.update(settle_s=.1, capture_s=.5)
        t = trial()
        with tempfile.TemporaryDirectory() as folder:
            evidence = Evidence(folder, cfg, [t])
            with patch("bench_precision.draw") as draw, patch("bench_precision.time.monotonic", Clock()):
                run_trial(Camera(), evidence, t, cfg, Geometry(1920, 1080, 344, 195, 600), None)
            self.assertTrue(all(call.kwargs.get("gaze") is None for call in draw.call_args_list))
            self.assertTrue(any(e["type"] == "sample" for e in evidence.events))
            self.assertFalse(any(e["type"] == "selection" for e in evidence.events))
            evidence.close(1)

    def test_closed_loop_confirms_cell_zero_and_preserves_time(self):
        cfg, t = config(), trial("closed_loop")
        with tempfile.TemporaryDirectory() as folder:
            evidence = Evidence(folder, cfg, [t])
            with patch("bench_precision.draw") as draw, patch("bench_precision.time.monotonic", Clock()):
                run_trial(Camera(), evidence, t, cfg, Geometry(1920, 1080, 344, 195, 600), None)
            selection = next(e for e in evidence.events if e["type"] == "selection")
            self.assertEqual(selection["cell"], 0)
            self.assertGreater(selection["elapsed_s"], 0)
            self.assertTrue(any(call.kwargs.get("gaze") is not None for call in draw.call_args_list))
            evidence.close(1)

    def test_operator_interrupt_leaves_trial_end_and_recoverable_evidence(self):
        cfg, t = config(), trial()
        with tempfile.TemporaryDirectory() as folder:
            evidence = Evidence(folder, cfg, [t])
            with patch("bench_precision.draw", side_effect=[None, InterruptedError("ESC")]), \
                    patch("bench_precision.time.monotonic", Clock()):
                with self.assertRaises(InterruptedError):
                    run_trial(Camera(), evidence, t, cfg, Geometry(1920, 1080, 344, 195, 600), None)
            self.assertEqual(evidence.events[-1]["status"], "interrupted")
            evidence.close(1)


if __name__ == "__main__":
    unittest.main()
