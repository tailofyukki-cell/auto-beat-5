from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from calibration import CalibrationSession


class CalibrationSessionTest(unittest.TestCase):
    def test_click_schedule_and_median_recommendation_ignore_warmup(self) -> None:
        session = CalibrationSession(started_at=10.0, interval_seconds=0.5, warmup_beats=2, sample_target=5)

        self.assertEqual(session.due_clicks(9.9), [])
        self.assertEqual(session.due_clicks(10.0), [0])
        self.assertEqual(session.due_clicks(10.55), [1])
        self.assertEqual(session.record_press(10.56), None)

        for beat, offset_ms in ((2, 20), (3, 22), (4, 19), (5, 21), (6, 180)):
            self.assertIsNotNone(session.record_press(session.beat_time(beat) + offset_ms / 1000.0))

        self.assertTrue(session.complete)
        self.assertEqual(session.recommendation_ms, 21)
        self.assertEqual(session.remaining_samples, 0)

    def test_duplicate_or_out_of_range_press_is_not_recorded(self) -> None:
        session = CalibrationSession(started_at=0.0, warmup_beats=0, sample_target=3)

        self.assertEqual(session.record_press(0.03), 30.0)
        self.assertIsNone(session.record_press(0.04))
        self.assertIsNone(session.record_press(0.75))
        self.assertEqual(len(session.offsets_ms), 1)


class ComboAndCalibrationAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_combo_banner_reappears_after_miss_reset_and_second_milestone(self) -> None:
        self.app.session = SimpleNamespace(combo=50)
        self.app._check_combo_milestone()
        first_until = self.app.combo_banner_until
        self.assertEqual(self.app.combo_banner, "50 COMBO!")

        self.app.session.combo = 0
        self.app._check_combo_milestone()
        self.app.combo_banner = ""
        self.app.combo_banner_until = 0.0
        self.app.session.combo = 50
        self.app._check_combo_milestone()

        self.assertEqual(self.app.combo_banner, "50 COMBO!")
        self.assertGreater(self.app.combo_banner_until, 0.0)
        self.assertGreaterEqual(self.app.combo_banner_until, first_until)

    def test_settings_launch_and_apply_calibration(self) -> None:
        self.app.set_screen("settings")
        self.app.settings_selection = 11
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(self.app.screen, "calibration")
        self.assertIsNotNone(self.app.calibration)

        self.app.calibration = CalibrationSession(started_at=0.0, warmup_beats=0, sample_target=5)
        for beat in range(5):
            self.app.calibration.record_press(self.app.calibration.beat_time(beat) + 0.018)
        self.app.apply_calibration()

        self.assertEqual(self.app.settings["timing_offset_ms"], 18)
        self.assertEqual(self.app.screen, "settings")

    def test_calibration_space_records_a_single_valid_input(self) -> None:
        self.app.calibration = CalibrationSession(started_at=time.perf_counter() - 2.02, warmup_beats=0)
        self.app.screen = "calibration"
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))

        self.assertEqual(len(self.app.calibration.offsets_ms), 1)

    def test_calibration_screen_draws_progress_and_recommendation(self) -> None:
        session = CalibrationSession(started_at=0.0, warmup_beats=0, sample_target=5)
        for beat in range(5):
            session.record_press(session.beat_time(beat) + 0.02)
        self.app.calibration = session
        self.app.screen = "calibration"

        self.app.draw()

        self.assertEqual(self.app.screen, "calibration")
        self.assertEqual(self.app.calibration.recommendation_ms, 20)


if __name__ == "__main__":
    unittest.main()
