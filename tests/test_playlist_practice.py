from __future__ import annotations

import copy
import hashlib
import json
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
from chart_generator import ChartGenerator
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Note, NoteType


class FakePracticeAudio:
    def __init__(self, current_time: float) -> None:
        self.time = current_time
        self.finished = False
        self.paused = False
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class PlaylistPracticeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("AUTOBEAT_DATA_DIR")
        self.previous_demo_dir = os.environ.get("AUTOBEAT_DEMO_SONGS_DIR")
        root = Path(self.directory.name)
        os.environ["AUTOBEAT_DATA_DIR"] = str(root / "data")
        os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = str(root / "demo_songs")
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

    def _set_chart_context(self) -> None:
        chart = Chart(
            1,
            "p" * 64,
            Difficulty.NORMAL,
            1,
            10.0,
            notes=[
                Note(1.0, 0),
                Note(4.0, 1),
                Note(5.0, 2, NoteType.HOLD, 8.0),
                Note(7.5, 3),
            ],
            generator_version=ChartGenerator.VERSION,
        )
        self.app.chart = chart
        self.app.analysis = AnalysisResult(
            music_hash=chart.music_hash,
            source_path="fixture.mp3",
            duration=10.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[],
            onsets=[],
            onset_strengths=[],
            band_energy=[],
            percussive_strengths=[],
            sustained_segments=[],
        )
        self.app.song_path = Path("fixture.mp3")

    def test_playlist_combines_demo_and_library_by_music_hash(self) -> None:
        demo = self.app.paths.demo_songs / "demo.mp3"
        demo.write_bytes(b"demo")
        user_same = Path(self.directory.name) / "same-copy.mp3"
        user_same.write_bytes(b"same")
        user_only = Path(self.directory.name) / "user.mp3"
        user_only.write_bytes(b"user")
        demo_hash = hashlib.sha256(b"demo").hexdigest()
        user_hash = "b" * 64
        (self.app.paths.demo_songs / "demo_manifest.json").write_text(
            json.dumps({"songs": [{"file": demo.name, "music_hash": demo_hash, "bpm": 128.0, "duration": 99.0}]}),
            encoding="utf-8",
        )
        self.app.profile["recent_songs"] = [
            {"music_hash": demo_hash, "source_path": str(user_same), "bpm": 128.0, "duration": 99.0, "last_used": "2026-01-02T00:00:00+00:00"},
            {"music_hash": user_hash, "source_path": str(user_only), "bpm": 100.0, "duration": 88.0, "last_used": "2026-01-03T00:00:00+00:00"},
            {"music_hash": "c" * 64, "source_path": str(Path(self.directory.name) / "missing.ogg"), "bpm": 90.0, "duration": 60.0, "last_used": ""},
        ]

        entries = self.app.playlist_entries()
        self.assertEqual(len(entries), 3)
        duplicated = next(entry for entry in entries if entry.music_hash == demo_hash)
        self.assertEqual(duplicated.source, "both")
        self.assertEqual(duplicated.path, user_same)
        self.assertTrue(duplicated.exists)
        missing = next(entry for entry in entries if entry.music_hash == "c" * 64)
        self.assertFalse(missing.exists)

        self.app.open_playlist("practice")
        self.assertEqual(self.app.screen, "select")
        self.assertEqual(self.app.launch_mode, "practice")
        self.app.draw()

        selected: list[dict[str, object]] = []
        self.app.load_recent_song = lambda entry: selected.append(entry)  # type: ignore[method-assign]
        self.app.select_playlist_entry(next(index for index, entry in enumerate(entries) if entry.music_hash == demo_hash))
        self.assertEqual(selected[0]["music_hash"], demo_hash)
        self.assertEqual(selected[0]["source_path"], str(user_same))

    def test_title_practice_to_demo_cache_reaches_practice_setup(self) -> None:
        demo = self.app.paths.demo_songs / "trial.mp3"
        demo.write_bytes(b"demo audio")
        digest = "d" * 64
        (self.app.paths.demo_songs / "demo_manifest.json").write_text(
            json.dumps({"songs": [{"file": demo.name, "music_hash": digest, "bpm": 120.0, "duration": 8.0}]}),
            encoding="utf-8",
        )
        analysis = AnalysisResult(digest, str(demo), 8.0, 22050, 120.0, [], [], [], [], [], [])
        cache = self.app.paths.demo_songs / "cache" / f"{digest}.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(analysis.to_dict()), encoding="utf-8")
        chart = Chart(1, digest, Difficulty.BEGINNER, 0, 8.0, notes=[Note(3.5, 2)], generator_version=ChartGenerator.VERSION)
        chart_path = self.app.paths.demo_songs / "charts" / digest / "beginner.json"
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        chart_path.write_text(json.dumps(chart.to_dict()), encoding="utf-8")

        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_p}))
        self.assertEqual(self.app.screen, "select")
        self.assertEqual(self.app.launch_mode, "practice")
        with patch("app.music_hash", return_value=digest):
            self.app.select_current_playlist_entry()
            self.assertEqual(self.app.screen, "difficulty")
            self.app.select_chart(Difficulty.BEGINNER)
        self.assertEqual(self.app.screen, "practice_setup")
        self.assertEqual(self.app.practice_start, 0.0)
        self.assertEqual(self.app.practice_end, 8.0)

    def test_practice_chart_clips_end_and_excludes_notes_before_start(self) -> None:
        self._set_chart_context()
        self.app.practice_start = 4.0
        self.app.practice_end = 7.0
        practice = self.app._practice_chart()
        self.assertEqual([note.time for note in practice.notes], [4.0, 5.0])
        self.assertEqual(practice.notes[1].end_time, 7.0)
        self.assertEqual(practice.song_duration, 7.0)

    def test_practice_countdown_starts_audio_at_selected_offset_and_escape_returns_setup(self) -> None:
        self._set_chart_context()
        self.app.practice_start = 4.0
        self.app.practice_end = 7.0
        self.app.audio_available = True
        self.app.audio.load = Mock()
        self.app.audio.play = Mock()
        self.app.audio.stop = Mock()

        self.app.start_practice()
        self.assertEqual(self.app.screen, "game")
        self.assertTrue(self.app.practice_active)
        self.assertTrue(self.app.countdown_active)
        self.app.audio.play.assert_not_called()

        self.app.countdown_started_at = time.perf_counter() - COUNTDOWN_SECONDS - 0.01
        self.app.update_game()
        self.app.audio.play.assert_called_once_with(4.0)

        self.app.start_practice()
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))
        self.assertEqual(self.app.screen, "practice_setup")
        self.assertFalse(self.app.practice_active)

    def test_practice_finish_never_records_score_or_rewards(self) -> None:
        self._set_chart_context()
        self.app.practice_start = 4.0
        self.app.practice_end = 7.0
        self.app.practice_active = True
        self.app.session = GameSession(self.app._practice_chart(), JudgmentWindows())
        self.app.profile["lifetime_score"] = 987
        before = copy.deepcopy(self.app.profile)

        self.app.finish_game()

        self.assertEqual(self.app.screen, "practice_result")
        self.assertEqual(self.app.profile, before)

    def test_practice_end_loops_or_opens_practice_summary(self) -> None:
        self._set_chart_context()
        self.app.practice_start = 4.0
        self.app.practice_end = 7.0
        self.app.practice_active = True
        self.app.screen = "game"
        self.app.session = GameSession(self.app._practice_chart(), JudgmentWindows())
        audio = FakePracticeAudio(7.0)
        self.app.audio = audio  # type: ignore[assignment]

        self.app.practice_loop = False
        self.app.update_game()
        self.assertEqual(audio.stop_calls, 1)
        self.assertEqual(self.app.screen, "practice_result")

        self.app.screen = "game"
        self.app.practice_active = True
        self.app.session = GameSession(self.app._practice_chart(), JudgmentWindows())
        self.app.audio = FakePracticeAudio(7.0)  # type: ignore[assignment]
        self.app.practice_loop = True
        with patch.object(self.app, "start_practice") as restart:
            self.app.update_game()
        restart.assert_called_once_with(countdown=False)
        self.assertEqual(self.app.practice_round, 1)


if __name__ == "__main__":
    unittest.main()
