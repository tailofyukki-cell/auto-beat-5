from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart_generator import ChartGenerator
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Judgment, Note, NoteType
from persistence import RECENT_SONG_LIMIT, AppPaths, load_profile, record_recent_song


class EnhancementTest(unittest.TestCase):
    def analysis(self) -> AnalysisResult:
        return AnalysisResult(
            music_hash="b" * 64,
            source_path="example.wav",
            duration=4.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            onsets=[1.5, 2.0, 2.5],
            onset_strengths=[1.0, 0.8, 0.85],
            band_energy=[[0.7, 0.1, 0.1, 0.05, 0.05], [0.1, 0.1, 0.6, 0.1, 0.1], [0.1, 0.1, 0.1, 0.3, 0.4]],
            percussive_strengths=[0.3, 0.9, 0.4],
            sustained_segments=[(1.5, 2.6, 0)],
            local_bpms=[(0.0, 120.0), (0.5, 120.0)],
            downbeats=[0.0, 2.0],
            analyzer_version="1.1",
        )

    def test_hold_is_counted_once_in_result(self) -> None:
        chart = Chart(1, "h" * 64, Difficulty.NORMAL, 1, 3.0, notes=[Note(1.0, 0, NoteType.HOLD, 2.0)])
        session = GameSession(chart, JudgmentWindows())
        self.assertEqual(session.press(0, 1.0), Judgment.PERFECT)
        self.assertEqual(session.release(0, 2.0), Judgment.PERFECT)
        result = session.result()
        self.assertEqual(sum(result.judgments.values()), 1)
        self.assertEqual(result.judgments[Judgment.PERFECT.value], 1)
        self.assertEqual(result.accuracy, 100.0)

    def test_hold_replaces_same_lane_tap_at_start(self) -> None:
        chart = ChartGenerator().generate(self.analysis(), Difficulty.NORMAL)
        same_lane_and_time = {(round(note.time, 4), note.lane) for note in chart.notes}
        self.assertEqual(len(same_lane_and_time), len(chart.notes))
        self.assertTrue(any(note.kind is NoteType.HOLD for note in chart.notes))

    def test_recent_song_library_keeps_metadata_without_audio_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = AppPaths(root, root / "settings.json", root / "profile.json", root / "cache", root / "charts", root / "rewards")
            paths.ensure()
            profile = load_profile(paths)
            record_recent_song(paths, profile, self.analysis())
            restored = load_profile(paths)
        self.assertEqual(len(restored["recent_songs"]), 1)
        self.assertEqual(restored["recent_songs"][0]["music_hash"], "b" * 64)
        self.assertEqual(restored["recent_songs"][0]["source_path"], "example.wav")

    def test_recent_song_library_retains_one_hundred_entries_for_scrollable_playlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = AppPaths(root, root / "settings.json", root / "profile.json", root / "cache", root / "charts", root / "rewards")
            paths.ensure()
            profile = load_profile(paths)
            for index in range(RECENT_SONG_LIMIT + 5):
                analysis = self.analysis()
                analysis.music_hash = f"{index:064x}"
                analysis.source_path = f"C:/Music/song_{index:03d}.wav"
                record_recent_song(paths, profile, analysis)
            restored = load_profile(paths)
        self.assertEqual(len(restored["recent_songs"]), RECENT_SONG_LIMIT)
        self.assertEqual(restored["recent_songs"][0]["source_path"], "C:/Music/song_104.wav")
        self.assertNotIn("audio_data", restored["recent_songs"][0])


if __name__ == "__main__":
    unittest.main()
