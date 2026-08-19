from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp, COUNTDOWN_SECONDS
from chart_generator import ChartGenerator, START_LEAD_IN_SECONDS
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Note


class CountdownTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()
        self.chart = Chart(1, "countdown" * 8, Difficulty.NORMAL, 1, 8.0, notes=[Note(1.5, 2)])
        self.app.chart = self.chart
        self.app.analysis = AnalysisResult(
            music_hash=self.chart.music_hash,
            source_path="fixture.wav",
            duration=8.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[],
            onsets=[],
            onset_strengths=[],
            band_energy=[],
            percussive_strengths=[],
            sustained_segments=[],
        )
        self.app.song_path = Path("fixture.wav")
        self.app.audio_available = True
        self.app.audio.load = Mock()
        self.app.audio.play = Mock()
        self.app.audio.stop = Mock()

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_start_game_waits_three_seconds_before_audio_playback(self) -> None:
        self.app.start_game()

        self.assertEqual(self.app.screen, "game")
        self.assertTrue(self.app.countdown_active)
        self.app.audio.play.assert_not_called()
        self.assertIsNotNone(self.app.session)

        self.app.countdown_started_at = time.perf_counter() - COUNTDOWN_SECONDS - 0.01
        self.app.update_game()

        self.app.audio.play.assert_called_once()
        self.assertFalse(self.app.countdown_active)
        self.assertGreater(self.app.start_banner_until, time.perf_counter())

    def test_countdown_ignores_lane_inputs_and_escape_cancels(self) -> None:
        self.app.start_game()
        assert self.app.session is not None
        with patch.object(GameSession, "press", return_value=None) as press:
            self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_d}))
            press.assert_not_called()

        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
        self.assertEqual(self.app.screen, "select")
        self.app.audio.stop.assert_called_once()

    def test_generated_charts_reserve_lead_in_after_music_starts(self) -> None:
        analysis = AnalysisResult(
            music_hash="l" * 64,
            source_path="fixture.wav",
            duration=5.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
            onsets=[0.10, 0.40, 0.95, 1.2, 1.5, 2.0, 2.5, 3.0],
            onset_strengths=[0.9] * 8,
            band_energy=[[0.5, 0.3, 0.4, 0.2, 0.1]] * 8,
            percussive_strengths=[0.5] * 8,
            sustained_segments=[],
        )
        chart = ChartGenerator().generate(analysis, Difficulty.NORMAL)

        self.assertTrue(chart.notes)
        self.assertTrue(all(note.time >= START_LEAD_IN_SECONDS for note in chart.notes))
        self.assertEqual(chart.metadata["start_lead_in_seconds"], START_LEAD_IN_SECONDS)


if __name__ == "__main__":
    unittest.main()
