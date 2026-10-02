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
from persistence import AppPaths, chart_path, load_chart, save_chart


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

    def test_normal_rule_is_only_slightly_above_easy(self) -> None:
        easy = RULES[Difficulty.EASY]
        normal = RULES[Difficulty.NORMAL]
        hard = RULES[Difficulty.HARD]
        self.assertEqual(normal.strength_percentile, 53)
        self.assertEqual(normal.min_gap, 0.19)
        self.assertEqual(normal.max_notes_per_second, 5.0)
        self.assertEqual(normal.max_chord_ratio, 0.10)
        self.assertEqual(normal.max_hold_ratio, 0.12)
        self.assertEqual(normal.min_hold_duration, 0.85)
        self.assertGreater(normal.max_notes_per_second, easy.max_notes_per_second)
        self.assertLess(normal.max_notes_per_second, hard.max_notes_per_second)
        self.assertLess(normal.max_chord_ratio, hard.max_chord_ratio)
        self.assertLess(normal.max_hold_ratio, hard.max_hold_ratio)

    def test_generator_supports_three_and_seven_lane_charts(self) -> None:
        analysis = self.analysis()
        generator = ChartGenerator()
        three = generator.generate(analysis, Difficulty.NORMAL, lane_count=3)
        seven = generator.generate(analysis, Difficulty.NORMAL, lane_count=7)

        self.assertEqual(three.metadata["lane_count"], 3)
        self.assertEqual(seven.metadata["lane_count"], 7)
        self.assertTrue(all(0 <= note.lane < 3 for note in three.notes))
        self.assertTrue(all(0 <= note.lane < 7 for note in seven.notes))
        self.assertNotEqual(three.seed, seven.seed)


    def test_easy_chart_can_include_gentle_holds(self) -> None:
        chart = ChartGenerator().generate(self.analysis(), Difficulty.EASY)
        ChartValidator().validate(chart)
        self.assertTrue(any(note.kind is NoteType.HOLD for note in chart.notes))
        grouped: dict[float, list[Note]] = {}
        for note in chart.notes:
            grouped.setdefault(round(note.time, 4), []).append(note)
        self.assertTrue(all(len(notes) == 1 for notes in grouped.values()))

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

    def test_chord_frequency_cap_reduces_extra_chords_without_lowering_nps_rule(self) -> None:
        notes: list[Note] = []
        for index in range(20):
            time = 1.2 + index * 0.25
            notes.append(Note(time, 0, strength=1.0 + index * 0.01))
            notes.append(Note(time, 4, strength=0.8 + index * 0.01))

        capped = ChartGenerator()._cap_chord_frequency(notes, RULES[Difficulty.NORMAL].max_chord_ratio)
        grouped: dict[float, list[Note]] = {}
        for note in capped:
            grouped.setdefault(round(note.time, 5), []).append(note)
        chord_events = sum(len(group) > 1 for group in grouped.values())

        self.assertEqual(RULES[Difficulty.NORMAL].max_notes_per_second, 5.0)
        self.assertLessEqual(chord_events, int(len(grouped) * RULES[Difficulty.NORMAL].max_chord_ratio))
        self.assertEqual(len(grouped), 20)

    def test_hold_frequency_cap_keeps_longest_sustains(self) -> None:
        notes = [Note(1.2 + index * 0.3, index % 5, strength=0.7) for index in range(20)]
        analysis = self.analysis()
        analysis.sustained_segments = [
            (1.20, 2.10, 0),
            (2.40, 3.70, 1),
            (3.90, 5.80, 2),
            (6.00, 6.90, 4),
        ]

        ChartGenerator()._add_holds(notes, analysis, RULES[Difficulty.NORMAL])
        holds = [note for note in notes if note.kind is NoteType.HOLD]

        self.assertLessEqual(len(holds), ChartGenerator()._hold_limit(notes, RULES[Difficulty.NORMAL].max_hold_ratio))
        self.assertTrue(any(round(note.time, 2) == 3.90 for note in holds))

    def test_validator_removes_low_difficulty_chords(self) -> None:
        for difficulty in (Difficulty.BEGINNER, Difficulty.EASY):
            chart = Chart(1, "x" * 64, difficulty, 1, 3.0, notes=[
                Note(1.0, 0, strength=1.0), Note(1.0, 1, strength=0.7), Note(1.0, 2, strength=0.6)
            ])
            ChartValidator().validate(chart)
            simultaneous = [note for note in chart.notes if note.time == 1.0]
            self.assertEqual(len(simultaneous), 1, f"{difficulty.label} の同時押しを除去できていません")


    def test_validator_removes_same_hand_taps_during_hold_for_all_difficulties(self) -> None:
        for difficulty in Difficulty:
            chart = Chart(1, f"hold_collision_{difficulty.value}".ljust(64, "x"), difficulty, 1, 4.0, notes=[
                Note(1.0, 0, NoteType.HOLD, 3.0, strength=1.0),
                Note(2.0, 1, strength=0.8),
                Note(2.25, 3, strength=0.7),
            ])
            ChartValidator().validate(chart)
            remaining = {(round(note.time, 3), note.lane, note.kind) for note in chart.notes}
            self.assertNotIn((2.0, 1, NoteType.TAP), remaining, f"{difficulty.label} の同じ手Tapが残っています")
            self.assertIn((2.25, 3, NoteType.TAP), remaining, f"{difficulty.label} の反対側Tapまで消えています")

    def test_game_session_allows_opposite_lane_tap_while_hold_is_active(self) -> None:
        chart = Chart(1, "h" * 64, Difficulty.NORMAL, 1, 4.0, notes=[
            Note(1.0, 0, NoteType.HOLD, 3.0),
            Note(2.0, 3),
        ])
        session = GameSession(chart, JudgmentWindows())
        self.assertEqual(session.press(0, 1.0), Judgment.PERFECT)
        self.assertEqual(session.press(3, 2.0), Judgment.PERFECT)
        self.assertEqual(session.release(3, 2.05), None)
        self.assertEqual(session.release(0, 3.0), Judgment.PERFECT)
        self.assertEqual(session.result().judgments["MISS"], 0)

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
        self.assertEqual(result.rank, "S+")
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

    def test_chart_cache_is_separated_by_lane_count_with_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = AppPaths(root, root / "settings.json", root / "profile.json", root / "cache", root / "charts", root / "rewards")
            paths.ensure()
            three = Chart(1, "l" * 64, Difficulty.NORMAL, 3, 4.0, notes=[Note(1.0, 2)], metadata={"lane_count": 3})
            seven = Chart(1, "l" * 64, Difficulty.NORMAL, 7, 4.0, notes=[Note(1.0, 6)], metadata={"lane_count": 7})
            save_chart(paths, three)
            save_chart(paths, seven)

            self.assertTrue(chart_path(paths, three.music_hash, three.difficulty.value, 3).is_file())
            self.assertTrue(chart_path(paths, seven.music_hash, seven.difficulty.value, 7).is_file())
            self.assertEqual(load_chart(paths, three.music_hash, three.difficulty.value, 3).metadata["lane_count"], 3)
            self.assertEqual(load_chart(paths, seven.music_hash, seven.difficulty.value, 7).metadata["lane_count"], 7)
            self.assertIsNone(load_chart(paths, three.music_hash, three.difficulty.value, 5))


if __name__ == "__main__":
    unittest.main()
