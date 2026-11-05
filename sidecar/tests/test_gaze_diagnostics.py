import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from calibration import GazeMapper
from gaze_diagnostics import load_profile, measure, run, summarize
from smoothing import GazeSmoother2D


def mapper():
    return GazeMapper(np.zeros(12), np.ones(12), [0]*5+[1.4], [0]*7+[-.2])


def face(aperture=.2):
    eye = SimpleNamespace(openness=aperture, h_ratio=.5, v_ratio=.5, iris=(.5, .5))
    return SimpleNamespace(right=eye, left=eye, pose_matrix=None)


class DiagnosticTests(unittest.TestCase):
    def test_unclipped_prediction_preserves_runtime_clipping(self):
        self.assertEqual(mapper().transform_unclipped([0]*12), (1.4, -.2))
        self.assertEqual(mapper().transform([0]*12), (1., 0.))

    def test_gate_blocks_smoothing_but_keeps_candidate_and_features(self):
        smoother = MagicMock()
        sample = measure(face(.1), mapper(), smoother, 1, .15)
        self.assertEqual(sample['reason'], 'low_aperture')
        self.assertEqual(sample['raw'], [1.4, -.2])
        self.assertEqual(sample['clipped'], [1., 0.])
        self.assertEqual(len(sample['features']), 12)
        self.assertFalse(sample['gate_open'])
        smoother.update.assert_not_called()

    def test_valid_aperture_updates_smoother_and_invalid_data_does_not(self):
        smoother = MagicMock()
        smoother.update.return_value = (.9, .1)
        sample = measure(face(.15), mapper(), smoother, 1, .15)
        self.assertEqual(sample['smoothed'], [.9, .1])
        smoother.update.assert_called_once_with(1., 0., 1)
        smoother.reset_mock()
        self.assertEqual(measure(None, mapper(), smoother, 2, .15)['reason'], 'face_not_detected')
        self.assertEqual(measure(face(float('nan')), mapper(), smoother, 3, .15)['reason'], 'invalid_features')
        smoother.update.assert_not_called()

    def test_profile_rejects_invalid_arrays_and_incompatible_resolution(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'profile.json'
            data = {'gaze': mapper().to_dict(), 'screen_px': [1920, 1080]}
            path.write_text(json.dumps(data))
            self.assertEqual(load_profile(path, (1920, 1080))[0].transform([0]*12), (1., 0.))
            with self.assertRaises(ValueError):
                load_profile(path, (1280, 720))
            data['gaze']['std'][0] = 0
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                load_profile(path, (1920, 1080))

    def test_report_separates_blocked_candidates_and_excludes_settling(self):
        smoother = GazeSmoother2D()
        rows = []
        for aperture, settled in ((.1, True), (.2, True), (.2, False)):
            s = measure(face(aperture), mapper(), smoother, len(rows)+1, .15)
            rows.append(dict(s, target_id=5, target=[.5, .5], settled=settled))
        rows.append(dict(measure(None, mapper(), smoother, 4, .15), target_id=5,
                         target=[.5, .5], settled=True))
        report = summarize(rows, (1000, 500))[4]
        self.assertEqual(report['samples_after_settle'], 3)
        self.assertEqual(report['candidate_samples'], 2)
        self.assertEqual(report['accepted_samples'], 1)
        self.assertEqual(report['clipped_samples'], 2)
        np.testing.assert_allclose(report['candidate_median_signed_error_px'], [900, -350])
        self.assertEqual(report['accepted_median_signed_error_px'], [500, -250])
        self.assertEqual(report['reasons'], {'low_aperture': 1, 'accepted': 1, 'face_not_detected': 1})

    def test_camera_failure_saves_report_and_closes_resources_without_overwriting_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'profile.json'
            original = json.dumps({'gaze': mapper().to_dict()})
            path.write_text(original)
            cap = MagicMock()
            cap.isOpened.return_value = False
            with patch('config.open_camera', return_value=cap), \
                    patch('cv2.destroyAllWindows'), patch('tkinter.Tk'), \
                    patch('tkinter.messagebox.showinfo'):
                first = run(path, folder)
                second = run(path, folder)
            self.assertNotEqual(first, second)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(json.loads((first/'report.json').read_text())['status'], 'error')
            self.assertEqual(cap.release.call_count, 2)

    def test_exit_and_pause_preserve_numeric_samples_and_release_tracker(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'profile.json'
            path.write_text(json.dumps({'gaze': mapper().to_dict()}))
            cap, tracker = MagicMock(), MagicMock()
            cap.read.return_value = (True, np.zeros((480, 640, 3), np.uint8))
            tracker.process.return_value = face()
            with patch('config.open_camera', return_value=cap), \
                    patch('eye_tracker.EyeTracker', return_value=tracker), \
                    patch('cv2.namedWindow'), patch('cv2.setWindowProperty'), \
                    patch('cv2.getWindowProperty', return_value=1), \
                    patch('cv2.destroyAllWindows'), patch('tkinter.Tk'), \
                    patch('tkinter.messagebox.showinfo'), \
                    patch('gaze_diagnostics.draw', side_effect=[ord('p'), ord('p'), ord('9'), 27]):
                result = run(path, folder)
            rows = [json.loads(line) for line in (result/'samples.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[1]['reason'], 'paused')
            self.assertFalse(rows[1]['settled'])
            self.assertEqual(rows[-1]['target_id'], 9)
            self.assertEqual(rows[0]['raw'], [1.4, -.2])
            self.assertEqual(json.loads((result/'report.json').read_text())['status'], 'stopped')
            self.assertEqual(sorted(p.name for p in result.iterdir()), ['report.json', 'samples.jsonl', 'session.json'])
            tracker.close.assert_called_once()
            cap.release.assert_called_once()


if __name__ == '__main__':
    unittest.main()
