import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chart_balance import GAP_LIMITS, balance_chart, internal_gaps
from chart_validator import ChartValidator
from models import AnalysisResult, Chart, Difficulty, Note, NoteType


class ChartBalanceTests(unittest.TestCase):
    def test_v2_limits_and_preservation_of_existing_v1_chart(self):
        self.assertEqual([GAP_LIMITS[d] for d in Difficulty], [2.5, 2.0, 1.5, 1.0, 1.0])
        chart, analysis = self.fixture()
        chart.metadata.update(gap_balance_version=1, gap_balance_moves=3)
        before = deepcopy(chart.to_dict())
        self.assertEqual(balance_chart(chart, analysis), 3)
        self.assertEqual(chart.to_dict(), before)

    def fixture(self, lanes=5):
        analysis = AnalysisResult("test", "test.wav", 12, 22050, 120,
                                  [], [5.0], [0.5], [[1, 0, 0, 0, 0]], [0.4], [])
        chart = Chart(1, "test", Difficulty.NORMAL, 1, 12,
                      notes=[Note(t, i % lanes, strength=0.3)
                             for i, t in enumerate([2, 2.2, 2.4, 2.6, 3, 7])],
                      metadata={"lane_count": lanes})
        ChartValidator().validate(chart)
        return chart, analysis

    def test_balances_safely_deterministically_and_preserves_budget(self):
        for lanes in (3, 5, 7):
            with self.subTest(lanes=lanes):
                chart, analysis = self.fixture(lanes)
                original = deepcopy(chart)
                self.assertGreater(balance_chart(chart, analysis), 0)
                self.assertEqual(chart.metadata["gap_balance_version"], 2)
                self.assertEqual(chart.metadata["gap_balance_limit_seconds"], 1.5)
                self.assertEqual(len(chart.notes), len(original.notes))
                self.assertLess(max(b-a for a, b in internal_gaps(chart)),
                                max(b-a for a, b in internal_gaps(original)))
                self.assertEqual(ChartValidator().validate(chart).removed_notes, 0)
                self.assertEqual(chart.notes[0].time, original.notes[0].time)
                self.assertEqual(chart.notes[-1].time, original.notes[-1].time)
                balance_chart(original, analysis)
                self.assertEqual(chart.to_dict(), original.to_dict())
                snapshot = chart.to_dict()
                balance_chart(chart, analysis)
                self.assertEqual(snapshot, chart.to_dict())

    def test_no_candidate_or_dense_donor_leaves_notes_unchanged(self):
        for case in ("no_onset", "zero_strength", "no_donor", "edges"):
            chart, analysis = self.fixture()
            if case == "no_onset":
                analysis.onsets = []
            elif case == "zero_strength":
                analysis.onset_strengths = [0]
            elif case == "no_donor":
                for n in chart.notes:
                    n.source = "downbeat"
            else:
                analysis.onsets = [0.5, 10]
                analysis.onset_strengths = [1, 1]
            before = [n.to_dict() for n in chart.notes]
            self.assertEqual(balance_chart(chart, analysis), 0)
            self.assertEqual(before, [n.to_dict() for n in chart.notes])

    def test_hold_is_not_an_empty_interval(self):
        chart, analysis = self.fixture()
        chart.notes.append(Note(3, 2, NoteType.HOLD, 7))
        chart.sort()
        before = [n.to_dict() for n in chart.notes]
        self.assertEqual(balance_chart(chart, analysis), 0)
        self.assertEqual(before, [n.to_dict() for n in chart.notes])

    def test_chords_and_holds_are_not_donors(self):
        chart, analysis = self.fixture()
        chart.notes = [Note(2, 0), Note(2, 3), Note(2.2, 1), Note(2.2, 4),
                       Note(3, 2, NoteType.HOLD, 3.5), Note(7, 0)]
        chart.sort()
        before = [n.to_dict() for n in chart.notes]
        self.assertEqual(balance_chart(chart, analysis), 0)
        self.assertEqual(before, [n.to_dict() for n in chart.notes])


if __name__ == "__main__":
    unittest.main()
