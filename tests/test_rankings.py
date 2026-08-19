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
from models import Chart, Difficulty, Note
from persistence import AppPaths, load_profile, ranking_entries, record_play


def result(score: int, accuracy: float, combo: int, rank: str = "A") -> dict[str, object]:
    return {
        "score": score,
        "accuracy": accuracy,
        "max_combo": combo,
        "rank": rank,
        "judgments": {"PERFECT": 1, "GREAT": 0, "GOOD": 0, "MISS": 0},
        "chart_hash": "m" * 64 + ":normal",
    }


class RankingPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.paths = AppPaths.discover()
        self.profile = load_profile(self.paths)
        self.chart_key = "m" * 64 + ":normal"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_records_are_sorted_by_score_then_accuracy_then_combo(self) -> None:
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(10000, 92.0, 120))
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(12000, 85.0, 100))
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(12000, 95.0, 90, "S"))
        records = ranking_entries(self.profile, self.chart_key)

        self.assertEqual([entry["score"] for entry in records], [12000, 12000, 10000])
        self.assertEqual(records[0]["accuracy"], 95.0)
        self.assertEqual(self.profile["high_scores"][self.chart_key], 12000)
        self.assertEqual(self.profile["last_play_ranking"]["position"], 1)

    def test_only_top_ten_are_stored_and_low_score_can_miss_board(self) -> None:
        for score in range(1000, 12000, 1000):
            record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(score, 80.0, score // 100))
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(500, 99.0, 5))
        records = ranking_entries(self.profile, self.chart_key)

        self.assertEqual(len(records), 10)
        self.assertEqual(records[0]["score"], 11000)
        self.assertEqual(records[-1]["score"], 2000)
        self.assertFalse(self.profile["last_play_ranking"]["made_top_ten"])

    def test_legacy_profile_without_rankings_remains_usable(self) -> None:
        self.profile.pop("rankings", None)
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(5000, 90.0, 50))
        self.assertEqual(ranking_entries(self.profile, self.chart_key)[0]["score"], 5000)


class RankingUiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()
        self.app.chart = Chart(1, "m" * 64, Difficulty.NORMAL, 1, 10.0, notes=[Note(1.2, 0)])
        chart_key = f"{self.app.chart.music_hash}:{self.app.chart.difficulty.value}"
        record_play(self.app.paths, self.app.profile, chart_key=chart_key, result=result(12345, 96.25, 120, "S"))

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_ranking_screen_draws_current_song_and_difficulty_records(self) -> None:
        self.app.open_ranking()
        self.assertEqual(self.app.screen, "ranking")
        self.assertEqual(self.app.current_ranking()[0]["score"], 12345)
        self.app.draw()


if __name__ == "__main__":
    unittest.main()
