import json
import math
import tempfile
import unittest
from pathlib import Path

from bench_precision import template
from blink_detector import BlinkDetector
from e1_protocol import (ENGINES, Dwell, Evidence, Geometry, cell_at, generic_point,
                         make_plan, summarize, summarize_trial, targets, validate_config)


def config():
    cfg = template()
    cfg.update(screen_width_mm=355, screen_height_mm=225)
    return cfg


def trial(phase="open_loop"):
    return {"trial_id": "one", "condition_id": "c1", "engine": ENGINES[0],
            "phase": phase, "target": targets(phase)[0]}


def event(kind, **data):
    return {"type": kind, "trial_id": "one", **data}


class GeometryTests(unittest.TestCase):
    def test_screen_ray_error_is_zero_and_matches_known_angle(self):
        g = Geometry(1920, 1080, 400, 200, 600)
        self.assertAlmostEqual(g.angular_error((.5, .5), (.5, .5)), 0)
        self.assertAlmostEqual(g.angular_error((1, .5), (.5, .5)), math.degrees(math.atan(200/600)))
        self.assertAlmostEqual(g.angular_error((.5, 1), (.5, .5)), math.degrees(math.atan(100/600)))

    def test_physical_geometry_affects_error_and_rejects_unknown_or_nan(self):
        a = Geometry(1920, 1080, 355, 225, 500)
        b = Geometry(1920, 1080, 355, 225, 700, 20, 10)
        self.assertGreater(a.angular_error((.9, .5), (.5, .5)), b.angular_error((.9, .5), (.5, .5)))
        for distance in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                Geometry(1920, 1080, 355, 225, distance)

    def test_generic_mapping_preserves_out_of_screen_predictions(self):
        self.assertEqual(generic_point(0, 0), (.5, .5))
        self.assertGreater(generic_point(0, math.radians(50))[0], 1)
        self.assertIsNone(cell_at(generic_point(0, math.radians(50))))


class ProtocolTests(unittest.TestCase):
    def test_all_conditions_and_paired_target_orders_are_preserved(self):
        plan = make_plan(config())
        self.assertEqual(len(plan), 8*2*(9+8+8+1))
        self.assertEqual(len({t["trial_id"] for t in plan}), len(plan))
        for cid in {t["condition_id"] for t in plan}:
            for phase in ("angular", "open_loop", "closed_loop", "observation"):
                orders = [[t["target"] for t in plan if t["condition_id"] == cid
                           and t["phase"] == phase and t["engine"] == engine] for engine in ENGINES]
                self.assertEqual(*orders)
        other = make_plan(config())
        self.assertEqual([{k:v for k,v in t.items() if k != "trial_id"} for t in plan],
                         [{k:v for k,v in t.items() if k != "trial_id"} for t in other])

    def test_config_requires_real_dimensions_and_safe_pseudonym(self):
        with self.assertRaises(ValueError):
            validate_config(template())
        cfg = config()
        cfg["participant_code"] = "../person"
        with self.assertRaises(ValueError):
            validate_config(cfg)

    def test_calibrated_followup_preserves_targets_without_repeating_generic_trials(self):
        cfg = config()
        cfg['conditions'] = cfg['conditions'][:1]
        full = make_plan(cfg)
        cfg['engines'] = [ENGINES[1]]
        followup = make_plan(cfg)
        self.assertEqual(len(followup), 26)
        self.assertEqual([(t['phase'], t['target']) for t in followup],
                         [(t['phase'], t['target']) for t in full if t['engine'] == ENGINES[1]])
        cfg['cohort'] = 'target'
        with self.assertRaises(ValueError):
            make_plan(cfg)

    def test_tracking_loss_resets_dwell_and_zero_is_a_valid_cell(self):
        dwell = Dwell(1.2)
        self.assertIsNone(dwell.update(0, 1))
        self.assertIsNone(dwell.update(None, 2))
        self.assertIsNone(dwell.update(0, 2.1))
        self.assertIsNone(dwell.update(0, 3))
        self.assertEqual(dwell.update(0, 3.4), 0)

    def test_blink_reopens_once_with_monotonic_refractory(self):
        blink = BlinkDetector()
        self.assertFalse(blink.detect(.1, now=1))
        self.assertFalse(blink.detect(.1, now=1.1))
        self.assertTrue(blink.detect(.3, now=1.2))
        self.assertFalse(blink.detect(.3, now=1.3))
        self.assertFalse(blink.detect(.1, now=1.4))
        self.assertFalse(blink.detect(.1, now=1.5))
        self.assertFalse(blink.detect(.3, now=1.6))

    def test_missing_tracking_stays_in_open_loop_denominator(self):
        t = trial()
        events = [event("trial_start"), event("sample", gaze=None, reason="face_not_detected"),
                  event("trial_end", status="completed", duration_s=2)]
        report = summarize([t], events, 5)
        self.assertEqual(report["trials"][0]["status"], "insufficient_tracking")
        self.assertEqual(report["conditions"][0]["i2_attempted"], 1)
        self.assertEqual(report["conditions"][0]["i2_ratio"], 0)
        self.assertIsNone(report["conditions"][0]["i3_ratio"])

    def test_closed_loop_error_uses_confirmations_not_open_loop_complement(self):
        t = trial("closed_loop")
        events = [event("trial_start"), event("selection", cell=1, method="blink", elapsed_s=2),
                  event("trial_end", status="completed", duration_s=2)]
        report = summarize([t], events, 1)["conditions"][0]
        self.assertEqual(report["i3_wrong_confirmed"], 1)
        self.assertEqual(report["i3_ratio"], 1)
        events.pop(1)
        report = summarize([t], events, 1)["conditions"][0]
        self.assertIsNone(report["i3_ratio"])
        self.assertEqual(report["closed_without_selection"], 1)

    def test_false_activation_requires_observer_annotation_and_tracking(self):
        t = trial("observation")
        events = [event("trial_start"), event("sample", gaze=[.5, .5], blink=True),
                  event("activation", activation_id="a", cell=0, elapsed_s=2),
                  event("trial_end", status="completed", duration_s=30)]
        self.assertIsNone(summarize_trial(t, events, 1)["unintended_per_min"])
        events.append(event("annotation", activation_id="a", label="unintended"))
        self.assertEqual(summarize_trial(t, events, 1)["unintended_per_min"], 2)
        self.assertIsNone(summarize_trial(t, events, 2)["unintended_per_min"])

    def test_interrupted_and_unstarted_trials_remain_visible(self):
        a, b = trial(), {**trial(), "trial_id": "two"}
        report = summarize([a, b], [event("trial_start")], 5)
        self.assertEqual([t["status"] for t in report["trials"]], ["interrupted", "not_run"])
        self.assertEqual(report["not_run"], 1)

    def test_sessions_never_overwrite_and_journal_rebuilds_the_same_report(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Evidence(folder, config(), [trial()])
            second = Evidence(folder, config(), [trial()])
            self.assertNotEqual(first.folder, second.folder)
            first.append("trial_start", "one")
            first.append("trial_end", "one", status="completed", duration_s=2)
            first.close(5)
            second.close(5)
            rows = [json.loads(line) for line in (first.folder/"events.jsonl").read_text().splitlines()]
            report = json.loads((first.folder/"report.json").read_text())
            self.assertEqual(report, summarize([trial()], rows, 5))
            with self.assertRaises(FileExistsError):
                first.write_json("session.json", {})


if __name__ == "__main__":
    unittest.main()
