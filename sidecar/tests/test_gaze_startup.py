import runpy
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from calibration import _check_cancel, run_calibration


class GazeStartupTests(unittest.TestCase):
    def test_escape_and_window_close_cancel_calibration(self):
        for key, visible in ((27, 1), (-1, 0)):
            with patch('calibration.cv2.waitKey', return_value=key), \
                    patch('calibration.cv2.getWindowProperty', return_value=visible):
                with self.assertRaises(InterruptedError):
                    _check_cancel()

    def test_cancel_releases_camera_and_does_not_replace_profile(self):
        cap, tracker = MagicMock(), MagicMock()
        with patch('calibration.config.open_camera', return_value=cap), \
                patch('calibration.EyeTracker', return_value=tracker), \
                patch('calibration._fullscreen_window'), \
                patch('calibration._collect', side_effect=InterruptedError), \
                patch('calibration.cv2.destroyAllWindows'), \
                patch('calibration.save_calibration') as save:
            self.assertIsNone(run_calibration())
        cap.release.assert_called_once()
        tracker.close.assert_called_once()
        save.assert_not_called()

    def test_calibration_exit_code_distinguishes_failure_from_success(self):
        entry = Path(__file__).resolve().parents[1]/'main.py'
        for result, code in ((None, 1), (object(), 0)):
            with patch('sys.argv', ['main.py', '--calibrate']), \
                    patch('calibration.run_calibration', return_value=result):
                with self.assertRaises(SystemExit) as exit:
                    runpy.run_path(str(entry), run_name='__main__')
                self.assertEqual(exit.exception.code, code)

    def test_tracking_without_profile_does_not_start_calibration(self):
        entry = Path(__file__).resolve().parents[1]/'main.py'
        with patch('sys.argv', ['main.py', '--track']), \
                patch('calibration.load_calibration', return_value=None), \
                patch('calibration.run_calibration') as calibrate, \
                patch('config.open_camera') as camera:
            with self.assertRaises(SystemExit) as exit:
                runpy.run_path(str(entry), run_name='__main__')
            self.assertEqual(exit.exception.code, 1)
            calibrate.assert_not_called()
            camera.assert_not_called()


if __name__ == '__main__':
    unittest.main()
