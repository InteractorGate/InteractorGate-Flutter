import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from calibration import GazeMapper, load_calibration, save_calibration


class CalibrationCompatibilityTests(unittest.TestCase):
    def test_old_axis_profile_is_rejected_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'calibration.json'
            original = json.dumps({'gaze': {'mean': [[0]*6]*2,
                'std': [[1]*6]*2, 'coef_x': [0]*7, 'coef_y': [0]*7}})
            target.write_text(original)
            with patch('calibration.config.CALIB_FILE', str(target)):
                self.assertIsNone(load_calibration())
            self.assertEqual(target.read_text(), original)

    def test_new_calibration_keeps_backup_and_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'calibration.json'
            target.write_text('old calibration')
            mapper = GazeMapper(np.zeros(12), np.ones(12), np.zeros(6), np.zeros(8))
            with patch('calibration.config.CALIB_FILE', str(target)):
                save_calibration(mapper)
                self.assertIsNotNone(load_calibration())
            backups = list(target.parent.glob('calibration.backup-*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'old calibration')

    def test_failed_backup_does_not_replace_original(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'calibration.json'
            target.write_text('old calibration')
            mapper = GazeMapper(np.zeros(12), np.ones(12), np.zeros(6), np.zeros(8))
            with patch('calibration.config.CALIB_FILE', str(target)), patch(
                    'calibration.shutil.copy2', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    save_calibration(mapper)
            self.assertEqual(target.read_text(), 'old calibration')
            self.assertEqual(list(target.parent.glob('*.tmp')), [])
