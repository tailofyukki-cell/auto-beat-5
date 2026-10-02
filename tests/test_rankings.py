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
from models import Chart, Difficulty, Note, chart_key
from persistence import AppPaths, load_profile, ranking_entries, record_play, song_ranking_summary


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
        self.assertEqual(self.profile["last_play_ranking"]["score_delta"], 0)
        self.assertIn("ステージ支配者", self.profile["last_play_badges"])


    def test_record_play_saves_shareable_result_badges(self) -> None:
        perfect_result = result(50000, 100.0, 500, "S+")
        perfect_result["judgments"] = {"PERFECT": 40, "GREAT": 0, "GOOD": 0, "MISS": 0}
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=perfect_result)
        self.assertIn("神業の演奏", self.profile["last_play_badges"])
        self.assertIn("完璧な集中", self.profile["badges"])
        self.assertIn("Combo Master", self.profile["badges"])

    def test_only_top_ten_are_stored_and_low_score_can_miss_board(self) -> None:
        for score in range(1000, 12000, 1000):
            record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(score, 80.0, score // 100))
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(500, 99.0, 5))
        records = ranking_entries(self.profile, self.chart_key)

        self.assertEqual(len(records), 10)
        self.assertEqual(records[0]["score"], 11000)
        self.assertEqual(records[-1]["score"], 2000)
        self.assertFalse(self.profile["last_play_ranking"]["made_top_ten"])

    def test_song_summary_separates_difficulties_and_other_songs(self) -> None:
        other_key = "x" * 64 + ":normal"
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(5000, 90.0, 50))
        record_play(self.paths, self.profile, chart_key="m" * 64 + ":easy", result=result(6000, 91.0, 60))
        record_play(self.paths, self.profile, chart_key=other_key, result=result(99000, 99.0, 999, "S"))

        summary = song_ranking_summary(self.profile, "m" * 64)
        self.assertEqual(summary["normal"]["score"], 5000)
        self.assertEqual(summary["easy"]["score"], 6000)
        self.assertNotIn("expert", summary)
        self.assertNotIn("x" * 64 + ":normal", summary)

    def test_legacy_profile_without_rankings_remains_usable(self) -> None:
        self.profile.pop("rankings", None)
        record_play(self.paths, self.profile, chart_key=self.chart_key, result=result(5000, 90.0, 50))
        self.assertEqual(ranking_entries(self.profile, self.chart_key)[0]["score"], 5000)

    def test_lane_specific_rankings_do_not_mix_with_legacy_fallback_for_5_lane(self) -> None:
        legacy_key = self.chart_key
        five_key = self.chart_key + ":5lane"
        seven_chart = Chart(1, "m" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(1.0, 6)], metadata={"lane_count": 7})
        seven_key = chart_key(seven_chart)
        record_play(self.paths, self.profile, chart_key=legacy_key, result=result(5000, 90.0, 50))
        record_play(self.paths, self.profile, chart_key=seven_key, result=result(9000, 95.0, 70))

        self.assertEqual(ranking_entries(self.profile, five_key)[0]["score"], 5000)
        self.assertEqual(ranking_entries(self.profile, seven_key)[0]["score"], 9000)
        self.assertNotEqual(ranking_entries(self.profile, five_key)[0]["score"], ranking_entries(self.profile, seven_key)[0]["score"])

    def test_record_play_unlocks_lane_modes_from_5_lane_results(self) -> None:
        profile = load_profile(self.paths)
        low_result = result(1000, 60.0, 5, "C")
        low_result["judgments"] = {"PERFECT": 20, "GREAT": 0, "GOOD": 0, "MISS": 10}
        self.assertEqual(profile["unlocked_features"], ["lane.5"])
        record_play(self.paths, profile, chart_key=self.chart_key + ":5lane", result=low_result)
        record_play(self.paths, profile, chart_key=self.chart_key + ":5lane", result=low_result)
        newly = record_play(self.paths, profile, chart_key=self.chart_key + ":5lane", result=low_result)
        self.assertIn("lane.3", newly)
        self.assertIn("lane.3", profile["unlocked_features"])

        strong_result = result(50000, 98.0, 120, "S")
        strong_result["judgments"] = {"PERFECT": 100, "GREAT": 5, "GOOD": 0, "MISS": 0}
        newly = record_play(self.paths, profile, chart_key=self.chart_key + ":5lane", result=strong_result)
        self.assertIn("lane.7", newly)
        self.assertIn("lane.7", profile["unlocked_features"])


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

    def test_select_screen_shows_song_specific_best_summary(self) -> None:
        self.app.profile["recent_songs"] = [
            {
                "music_hash": "m" * 64,
                "source_path": "C:/music/example.wav",
                "bpm": 128.0,
                "duration": 120.0,
            }
        ]
        self.assertIn("12,345", self.app._song_best_text("m" * 64))
        self.assertIn("--", self.app._song_best_text("z" * 64))
        self.app.set_screen("select")
        self.app.draw()

    def test_song_best_text_prefers_active_lane_mode(self) -> None:
        seven_chart = Chart(1, "m" * 64, Difficulty.NORMAL, 1, 10.0, notes=[Note(1.2, 6)], metadata={"lane_count": 7})
        record_play(self.app.paths, self.app.profile, chart_key=chart_key(seven_chart), result=result(77777, 97.0, 180, "S"))
        self.app.settings["lane_count"] = 7
        text = self.app._song_best_text("m" * 64)
        self.assertIn("NO 77,777 S", text)
        self.assertNotIn("NO 12,345", text)

    def test_lane_best_summary_lists_all_lane_modes(self) -> None:
        seven_chart = Chart(1, "m" * 64, Difficulty.NORMAL, 1, 10.0, notes=[Note(1.2, 6)], metadata={"lane_count": 7})
        record_play(self.app.paths, self.app.profile, chart_key=chart_key(seven_chart), result=result(77777, 97.0, 180, "S"))
        summary = self.app._lane_best_summary("m" * 64, Difficulty.NORMAL)
        self.assertIn("3L --", summary)
        self.assertIn("5L 12,345 S", summary)
        self.assertIn("7L 77,777 S", summary)
        self.app.draw_ranking()

    def test_ranking_lane_tabs_switch_visible_records(self) -> None:
        seven_chart = Chart(1, "m" * 64, Difficulty.NORMAL, 1, 10.0, notes=[Note(1.2, 6)], metadata={"lane_count": 7})
        record_play(self.app.paths, self.app.profile, chart_key=chart_key(seven_chart), result=result(77777, 97.0, 180, "S"))
        self.app.open_ranking()
        self.assertEqual(self.app.ranking_lane_count_value(), 5)
        self.assertEqual(self.app.ranking_entries_for_selected_lane()[0]["score"], 12345)
        self.app.move_ranking_lane_count(1)
        self.assertEqual(self.app.ranking_lane_count_value(), 7)
        self.assertEqual(self.app.ranking_entries_for_selected_lane()[0]["score"], 77777)
        self.app.move_ranking_lane_count(1)
        self.assertEqual(self.app.ranking_lane_count_value(), 3)
        self.assertEqual(self.app.ranking_entries_for_selected_lane(), [])
        self.app.draw_ranking()


if __name__ == "__main__":
    unittest.main()

