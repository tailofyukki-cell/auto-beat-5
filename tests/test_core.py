from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chart_generator import ChartGenerator, RULES
from chart_validator import ChartValidator
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Judgment, Note, NoteType
from persistence import AppPaths, load_chart, save_chart


class CoreTest(unittest.TestCase):
    def analysis(self) -> AnalysisResult:
        return AnalysisResult(
            music_hash="a" * 64,
            source_path="example.wav",
            duration=8.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5],
            onsets=[0.5, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.1, 3.2, 4.0, 5.0, 5.5, 6.0],
            onset_strengths=[0.9, 0.8, 0.55, 0.9, 0.7, 0.9, 1.0, 0.8, 0.75, 0.9, 0.8, 0.9, 1.0],
            band_energy=[
                [0.6, 0.2, 0.1, 0.05, 0.05], [0.1, 0.1, 0.2, 0.3, 0.3], [0.1, 0.1, 0.5, 0.2, 0.1],
                [0.55, 0.25, 0.1, 0.05, 0.05], [0.1, 0.1, 0.2, 0.3, 0.3], [0.1, 0.1, 0.6, 0.1, 0.1],
                [0.5, 0.3, 0.1, 0.05, 0.05], [0.1, 0.1, 0.1, 0.4, 0.3], [0.1, 0.1, 0.1, 0.2, 0.5],
                [0.55, 0.2, 0.1, 0.1, 0.05], [0.1, 0.1, 0.2, 0.3, 0.3], [0.1, 0.1, 0.6, 0.1, 0.1], [0.5, 0.3, 0.1, 0.05, 0.05],
            ],
            percussive_strengths=[0.7, 0.2, 0.3, 0.8, 0.2, 0.7, 0.8, 0.4, 0.35, 0.9, 0.2, 0.8, 0.9],
            sustained_segments=[(1.0, 2.1, 0), (4.0, 5.3, 4)],
        )

    def test_generator_is_deterministic_and_multilevel(self) -> None:
        analysis = self.analysis()
        generator = ChartGenerator()
        first = generator.generate(analysis, Difficulty.NORMAL)
        second = generator.generate(analysis, Difficulty.NORMAL)
        self.assertEqual(first.to_dict(), second.to_dict())
        easy = generator.generate(analysis, Difficulty.EASY)
        expert = generator.generate(analysis, Difficulty.EXPERT)
        self.assertGreaterEqual(len(expert.notes), len(easy.notes))
        self.assertTrue(all(0 <= note.lane < 5 for note in expert.notes))
        self.assertTrue(any(note.kind is NoteType.HOLD for note in first.notes))

    def test_windowed_lane_balance_spreads_cluster_without_moving_anchor(self) -> None:
        generator = ChartGenerator()
        notes = [
            Note(1.20, 2, source="downbeat"),
            *[Note(1.35 + index * 0.16, 0, source="onset") for index in range(12)],
        ]
        generator._spread_lane_load(notes, RULES[Difficulty.NORMAL])
        self.assertEqual(notes[0].lane, 2, "小節頭アンカーは中央レーンに残す")
        movable_counts = [sum(note.lane == lane for note in notes[1:]) for lane in range(5)]
        self.assertGreaterEqual(sum(count > 0 for count in movable_counts), 4)
        self.assertLessEqual(max(movable_counts) - min(movable_counts), 2)

    def test_low_difficulties_generate_no_simultaneous_notes(self) -> None:
        generator = ChartGenerator()
        for difficulty in (Difficulty.BEGINNER, Difficulty.EASY):
            chart = generator.generate(self.analysis(), difficulty)
            ChartValidator().validate(chart)
            grouped: dict[float, list[Note]] = {}
            for note in chart.notes:
                grouped.setdefault(round(note.time, 4), []).append(note)
            self.assertTrue(
                all(len(notes) == 1 for notes in grouped.values()),
                f"{difficulty.label} に同時押しが残っています",
            )

    def test_validator_removes_low_difficulty_chords(self) -> None:
        for difficulty in (Difficulty.BEGINNER, Difficulty.EASY):
            chart = Chart(1, "x" * 64, difficulty, 1, 3.0, notes=[
                Note(1.0, 0, strength=1.0), Note(1.0, 1, strength=0.7), Note(1.0, 2, strength=0.6)
            ])
            ChartValidator().validate(chart)
            simultaneous = [note for note in chart.notes if note.time == 1.0]
            self.assertEqual(len(simultaneous), 1, f"{difficulty.label} の同時押しを除去できていません")

    def test_game_session_judges_tap_and_hold(self) -> None:
        chart = Chart(1, "z" * 64, Difficulty.NORMAL, 1, 3.0, notes=[
            Note(1.0, 0), Note(1.5, 3, NoteType.HOLD, 2.2)
        ])
        session = GameSession(chart, JudgmentWindows())
        self.assertEqual(session.press(0, 1.0), Judgment.PERFECT)
        self.assertEqual(session.press(3, 1.5), Judgment.PERFECT)
        self.assertEqual(session.release(3, 2.2), Judgment.PERFECT)
        result = session.result()
        self.assertEqual(result.judgments["MISS"], 0)
        self.assertGreater(result.score, 0)

    def test_chart_json_cache_round_trip(self) -> None:
        chart = Chart(1, "q" * 64, Difficulty.EASY, 3, 4.0, notes=[Note(1.0, 2)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = AppPaths(root, root / "settings.json", root / "profile.json", root / "cache", root / "charts", root / "rewards")
            paths.ensure()
            save_chart(paths, chart)
            restored = load_chart(paths, chart.music_hash, chart.difficulty.value)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.to_dict(), chart.to_dict())


if __name__ == "__main__":
    unittest.main()
