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
from chart_summary import build_chart_summary
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Note, NoteType
from persistence import load_chart


def fixture_analysis() -> AnalysisResult:
    return AnalysisResult(
        music_hash="s" * 64,
        source_path="fixture.wav",
        duration=12.0,
        sample_rate=22050,
        bpm=128.0,
        beats=[index * 0.46875 for index in range(28)],
        onsets=[1.3, 1.8, 2.3, 2.8, 3.3, 3.8, 4.3, 4.8],
        onset_strengths=[0.9, 0.75, 0.88, 0.71, 0.94, 0.8, 0.85, 0.73],
        band_energy=[[0.7, 0.2, 0.1, 0.55, 0.42]] * 8,
        percussive_strengths=[0.35, 0.45, 0.38, 0.42, 0.37, 0.48, 0.41, 0.44],
        sustained_segments=[(3.3, 4.5, 1)],
    )


class ChartSummaryTest(unittest.TestCase):
    def test_summary_counts_notes_holds_chords_density_and_validation(self) -> None:
        analysis = fixture_analysis()
        chart = Chart(
            1,
            analysis.music_hash,
            Difficulty.NORMAL,
            1,
            analysis.duration,
            notes=[
                Note(1.2, 0),
                Note(1.2, 3),
                Note(2.0, 1, NoteType.HOLD, 3.0),
                Note(4.0, 2),
            ],
            metadata={"lane_count": 7, "validation_removed": 2, "validation_issues": ["same-lane gap"]},
        )
        summary = build_chart_summary(chart, analysis)

        self.assertEqual(summary.lane_count, 7)
        self.assertEqual(summary.lane_count_label, "7 LANE")
        self.assertEqual(summary.total_notes, 4)
        self.assertEqual(summary.tap_notes, 3)
        self.assertEqual(summary.hold_notes, 1)
        self.assertEqual(summary.chord_events, 1)
        self.assertEqual(summary.max_chord_size, 2)
        self.assertEqual(summary.peak_notes_per_second, 2)
        self.assertEqual(summary.validation_removed, 2)
        self.assertEqual(summary.validation_issues, 1)
        self.assertEqual(summary.lane_usage_text, "4/7 lanes  最大25%")
        self.assertEqual(summary.quality_note, "バランス良好")
        self.assertEqual(summary.first_note_text, "1.20 秒")

    def test_summary_flags_heavy_lane_bias(self) -> None:
        analysis = fixture_analysis()
        chart = Chart(1, analysis.music_hash, Difficulty.NORMAL, 1, analysis.duration, notes=[Note(1.2, 0), Note(1.8, 0), Note(2.4, 0)], metadata={"lane_count": 7})
        summary = build_chart_summary(chart, analysis)
        self.assertEqual(summary.lane_usage_text, "1/7 lanes  最大100%")
        self.assertEqual(summary.quality_note, "レーン偏りを確認")


class ChartSummaryWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()
        self.app.analysis = fixture_analysis()
        self.app.song_path = Path(self.app.analysis.source_path)
        self.app.audio_available = False

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_select_chart_opens_summary_without_starting_game(self) -> None:
        self.app.select_chart(Difficulty.EASY)

        self.assertEqual(self.app.screen, "chart_summary")
        self.assertIsNotNone(self.app.chart)
        self.assertIsNone(self.app.session)
        self.assertEqual(self.app.chart.metadata["gap_balance_version"], 2)
        self.app.draw()

    def test_regenerate_keeps_committed_cache_until_candidate_is_adopted(self) -> None:
        self.app.select_chart(Difficulty.EASY)
        first_chart = self.app.chart
        self.assertIsNotNone(first_chart)
        first_variant = int(first_chart.metadata["generation_variant"])
        self.assertEqual(first_chart.metadata["generation_style"], "standard")
        first_lanes = [note.lane for note in first_chart.notes]

        self.app.regenerate_chart()

        self.assertEqual(self.app.screen, "chart_summary")
        self.assertTrue(self.app.chart_is_pending)
        self.assertEqual(int(self.app.chart.metadata["generation_variant"]), first_variant + 1)
        self.assertEqual(self.app.chart.metadata["generation_style"], "bass")
        self.assertNotEqual([note.lane for note in self.app.chart.notes], first_lanes)
        cached = load_chart(self.app.paths, self.app.analysis.music_hash, Difficulty.EASY.value)
        self.assertIsNotNone(cached)
        self.assertEqual(int(cached.metadata["generation_variant"]), first_variant)

        self.app.discard_pending_chart()
        self.assertFalse(self.app.chart_is_pending)
        self.assertEqual(int(self.app.chart.metadata["generation_variant"]), first_variant)

        self.app.regenerate_chart()
        candidate_variant = int(self.app.chart.metadata["generation_variant"])
        self.app.adopt_pending_chart()
        adopted = load_chart(self.app.paths, self.app.analysis.music_hash, Difficulty.EASY.value)
        self.assertIsNotNone(adopted)
        self.assertEqual(int(adopted.metadata["generation_variant"]), candidate_variant)
        self.assertEqual(adopted.metadata["generation_style"], "bass")
        self.assertEqual(adopted.metadata["gap_balance_version"], 2)
        self.assertFalse(self.app.chart_is_pending)


    def test_regenerate_keeps_only_five_recent_candidates_and_switches_between_them(self) -> None:
        self.app.select_chart(Difficulty.NORMAL)
        committed = self.app.chart
        self.assertIsNotNone(committed)
        for _ in range(7):
            self.app.regenerate_chart()

        self.assertEqual(len(self.app.chart_candidates), 5)
        self.assertEqual(self.app.chart_candidate_index, 4)
        self.assertTrue(self.app.chart_is_pending)
        self.assertEqual([int(chart.metadata["generation_variant"]) for chart in self.app.chart_candidates], [3, 4, 5, 6, 7])

        self.app.move_chart_candidate(-1)
        self.assertEqual(self.app.chart_candidate_index, 3)
        self.assertEqual(int(self.app.chart.metadata["generation_variant"]), 6)
        self.app.draw()

        self.app.adopt_pending_chart()
        self.assertFalse(self.app.chart_is_pending)
        self.assertEqual(len(self.app.chart_candidates), 0)
        self.assertEqual(int(self.app.chart.metadata["generation_variant"]), 6)

    def test_trial_result_allows_explicit_candidate_adoption(self) -> None:
        self.app.select_chart(Difficulty.NORMAL)
        self.app.regenerate_chart()
        candidate_variant = int(self.app.chart.metadata["generation_variant"])
        self.app.session = GameSession(self.app.chart, JudgmentWindows.from_ms(self.app.settings["judgment_windows_ms"]))
        self.app.finish_game()

        self.assertEqual(self.app.screen, "result")
        self.assertTrue(self.app.chart_is_pending)
        self.app.adopt_pending_chart()
        self.assertEqual(self.app.screen, "chart_summary")
        self.assertFalse(self.app.chart_is_pending)
        adopted = load_chart(self.app.paths, self.app.analysis.music_hash, Difficulty.NORMAL.value)
        self.assertEqual(int(adopted.metadata["generation_variant"]), candidate_variant)


if __name__ == "__main__":
    unittest.main()
