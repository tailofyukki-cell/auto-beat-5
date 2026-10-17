from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from result_progress import comparison_lines, next_rank_goal


class ResultProgressTest(unittest.TestCase):
    def test_first_play_and_other_chart(self):
        self.assertIn("初回", comparison_lines({"chart_key": "a"}, "a", 100, 80, 3)[0])
        self.assertIn("記録なし", comparison_lines({"chart_key": "b"}, "a", 100, 80, 3)[0])

    def test_best_play_comparison_and_legacy_missing_misses(self):
        previous = {"score": 200, "accuracy": 90, "miss_count": 5}
        last = {"chart_key": "a", "previous_best": previous}
        lines = comparison_lines(last, "a", 150, 92, 2)
        self.assertIn("-50", lines[0])
        self.assertIn("+2.00 pt / MISS -3", lines[1])
        del previous["miss_count"]
        self.assertIn("過去のMISS記録なし", comparison_lines(last, "a", 200, 90, 0)[1])

    def test_rank_boundaries_and_s_plus_requires_no_miss(self):
        for accuracy, rank in ((69.9, "C"), (70, "B"), (80, "A"), (90, "S"), (95, "S+")):
            with self.subTest(accuracy=accuracy):
                self.assertIn(rank, next_rank_goal(accuracy, 1))
        self.assertIn("MISS 0", next_rank_goal(99, 1))
        self.assertIn("ALL PERFECT まで", next_rank_goal(99, 0))
        self.assertIn("達成", next_rank_goal(100, 0))
