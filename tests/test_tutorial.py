from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from tutorial import TUTORIAL_STEPS, build_tutorial_chart


class TutorialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("AUTOBEAT_DATA_DIR")
        self.previous_demo_dir = os.environ.get("AUTOBEAT_DEMO_SONGS_DIR")
        os.environ["AUTOBEAT_DATA_DIR"] = str(Path(self.directory.name) / "data")
        os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = str(Path(self.directory.name) / "demo_songs")
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        if self.previous_data_dir is None:
            os.environ.pop("AUTOBEAT_DATA_DIR", None)
        else:
            os.environ["AUTOBEAT_DATA_DIR"] = self.previous_data_dir
        if self.previous_demo_dir is None:
            os.environ.pop("AUTOBEAT_DEMO_SONGS_DIR", None)
        else:
            os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = self.previous_demo_dir
        self.directory.cleanup()

    def test_fixed_tutorial_charts_are_sorted_and_cover_all_steps(self) -> None:
        self.assertEqual(len(TUTORIAL_STEPS), 4)
        for index, step in enumerate(TUTORIAL_STEPS):
            chart = build_tutorial_chart(index)
            self.assertTrue(chart.metadata["tutorial"])
            self.assertEqual(chart.metadata["tutorial_step"], index)
            self.assertEqual(chart.song_duration, step.duration)
            self.assertEqual(len(chart.notes), len(step.notes))
            self.assertEqual(chart.notes, sorted(chart.notes, key=lambda note: (note.time, note.lane, note.kind.value)))

    def test_tutorial_start_draws_and_reaches_result_without_music_file(self) -> None:
        self.app.screen = "tutorial"
        self.app.draw()
        self.assertGreater(len(self.app.buttons), 0)

        self.app.start_tutorial_step(0)
        self.assertEqual(self.app.screen, "game")
        self.assertTrue(self.app.tutorial_active)
        self.assertIsNotNone(self.app.session)
        self.assertTrue(self.app.countdown_active)

        self.app.countdown_started_at = time.perf_counter() - 4.0
        self.app.update_game()
        self.assertIsNotNone(self.app.tutorial_started_at)

        self.app.tutorial_started_at = time.perf_counter() - self.app.chart.song_duration - 0.1
        self.app.update_game()
        self.assertEqual(self.app.screen, "tutorial_result")

    def test_last_tutorial_step_marks_profile_complete(self) -> None:
        final_step = len(TUTORIAL_STEPS) - 1
        self.app.start_tutorial_step(final_step)
        self.app.countdown_started_at = time.perf_counter() - 4.0
        self.app.update_game()
        self.app.tutorial_started_at = time.perf_counter() - self.app.chart.song_duration - 0.1
        self.app.update_game()
        self.assertTrue(self.app.profile["tutorial_completed"])
        self.assertEqual(self.app.screen, "tutorial_result")

    def test_demo_song_folder_lists_only_supported_audio_files(self) -> None:
        (self.app.paths.demo_songs / "beta.ogg").write_bytes(b"not-an-audio-file")
        (self.app.paths.demo_songs / "alpha.wav").write_bytes(b"not-an-audio-file")
        (self.app.paths.demo_songs / "README.txt").write_text("ignore", encoding="utf-8")
        self.assertEqual([path.name for path in self.app.demo_song_files()], ["alpha.wav", "beta.ogg"])
        self.app.screen = "select"
        self.app.draw()


if __name__ == "__main__":
    unittest.main()
