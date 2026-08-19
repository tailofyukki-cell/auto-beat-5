from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note


class FakeAudio:
    """曲末の再生状態を制御するための最小限の音源時計。"""

    def __init__(self, current_time: float, finished: bool) -> None:
        self.time = current_time
        self.finished = finished
        self.paused = False
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class AudioEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()
        chart = Chart(
            version=1,
            music_hash="end" * 22,
            difficulty=Difficulty.BEGINNER,
            seed=1,
            song_duration=3.0,
            notes=[Note(1.0, 2)],
        )
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.screen = "game"

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_chart_completion_does_not_cut_audio_tail(self) -> None:
        audio = FakeAudio(current_time=1.3, finished=False)
        self.app.audio = audio

        self.app.update_game()

        self.assertTrue(self.app.session.finished)
        self.assertEqual(self.app.screen, "game")
        self.assertEqual(audio.stop_calls, 0)

    def test_result_starts_only_after_audio_end(self) -> None:
        audio = FakeAudio(current_time=3.0, finished=True)
        self.app.audio = audio

        self.app.update_game()

        self.assertEqual(audio.stop_calls, 1)
        self.assertIn(self.app.screen, {"result", "unlock"})


if __name__ == "__main__":
    unittest.main()
