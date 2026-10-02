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
from models import AnalysisResult, Chart, Difficulty, Judgment, Note, NoteType


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


    def test_keyup_during_pause_clears_stale_held_lane(self) -> None:
        self.app.screen = "game"
        self.app.session = GameSession(Chart(1, "p" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(1.0, 0, NoteType.HOLD, 3.0)]), JudgmentWindows())
        self.app.session.press(0, 1.0)
        self.assertEqual(self.app.session.held_lanes, {0})
        self.app.audio = type("Audio", (), {"paused": True})()

        self.app.key_up_event(pygame.event.Event(pygame.KEYUP, {"key": pygame.K_d}))

        self.assertEqual(self.app.session.held_lanes, set())
        self.assertEqual(self.app.session.result().judgments["MISS"], 0)

    def test_resume_syncs_held_lanes_to_current_keyboard_state(self) -> None:
        class FakeAudio:
            paused = True
            def resume(self) -> None:
                self.paused = False
            def pause(self) -> None:
                self.paused = True

        pressed = [False] * 512
        pressed[pygame.K_f] = True
        self.app.screen = "game"
        self.app.audio = FakeAudio()
        self.app.session = GameSession(Chart(1, "r" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(1.0, 1, NoteType.HOLD, 3.0)]), JudgmentWindows())
        self.app.session.press(1, 1.0)
        self.app.session.held_lanes.add(0)

        with patch("pygame.key.get_pressed", return_value=pressed):
            self.app.toggle_pause()

        self.assertFalse(self.app.audio.paused)
        self.assertEqual(self.app.session.held_lanes, {1})

    def test_escape_pause_resume_then_lane_key_is_processed(self) -> None:
        class FakeAudio:
            paused = False
            time = 1.0

            def resume(self) -> None:
                self.paused = False

            def pause(self) -> None:
                self.paused = True

        self.app.screen = "game"
        self.app.audio = FakeAudio()
        self.app.session = GameSession(Chart(1, "e" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(1.0, 0)]), JudgmentWindows())
        pressed = [False] * 512

        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
        self.assertTrue(self.app.audio.paused)
        with patch("pygame.key.get_pressed", return_value=pressed):
            self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_d}))

        self.assertFalse(self.app.audio.paused)
        self.assertEqual(self.app.session.judgment_counts[Judgment.PERFECT.value], 1)

    def test_lane_held_during_resume_works_after_release_and_repress(self) -> None:
        class FakeAudio:
            paused = True
            time = 1.0

            def resume(self) -> None:
                self.paused = False

            def pause(self) -> None:
                self.paused = True

        self.app.screen = "game"
        self.app.audio = FakeAudio()
        self.app.session = GameSession(Chart(1, "b" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(1.0, 0)]), JudgmentWindows())
        pressed = [False] * 512
        pressed[pygame.K_d] = True

        with patch("pygame.key.get_pressed", return_value=pressed):
            self.app.toggle_pause()
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_d}))
        self.assertEqual(self.app.session.judgment_counts[Judgment.PERFECT.value], 0)

        self.app.key_up_event(pygame.event.Event(pygame.KEYUP, {"key": pygame.K_d}))
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_d}))

        self.assertEqual(self.app.session.judgment_counts[Judgment.PERFECT.value], 1)
        self.assertNotIn(0, self.app._resume_blocked_lanes)

    def test_focus_loss_pauses_and_clears_lane_state(self) -> None:
        class FakeAudio:
            paused = False

            def resume(self) -> None:
                self.paused = False

            def pause(self) -> None:
                self.paused = True

        self.app.screen = "game"
        self.app.audio = FakeAudio()
        self.app.session = GameSession(Chart(1, "f" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(1.0, 0, NoteType.HOLD, 3.0)]), JudgmentWindows())
        self.app._lane_keys_down = {0}
        self.app.session.held_lanes = {0}

        self.app._handle_game_focus_lost()

        self.assertTrue(self.app.audio.paused)
        self.assertEqual(self.app._lane_keys_down, set())
        self.assertEqual(self.app.session.held_lanes, set())

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
