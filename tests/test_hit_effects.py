from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp, JUDGMENT_LOG_LIMIT, PERFECT_LANE_FLASH_DURATION
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Judgment, Note


class HitEffectsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_successful_judgment_creates_lane_specific_effect(self) -> None:
        self.app._play_feedback(Judgment.PERFECT, lane=3)

        self.assertEqual(len(self.app.hit_effects), 1)
        effect = self.app.hit_effects[0]
        self.assertEqual(effect.lane, 3)
        self.assertEqual(effect.judgment, Judgment.PERFECT)
        self.assertEqual(effect.duration, PERFECT_LANE_FLASH_DURATION)

    def test_great_keeps_short_hit_effect_duration(self) -> None:
        self.app._play_feedback(Judgment.GREAT, lane=1)

        self.assertEqual(len(self.app.hit_effects), 1)
        self.assertLess(self.app.hit_effects[0].duration, PERFECT_LANE_FLASH_DURATION)

    def test_repeated_hits_replace_only_the_same_lane(self) -> None:
        self.app.profile["unlocked_features"] = ["lane.3", "lane.5", "lane.7"]
        self.app.settings["lane_count"] = 7
        for _ in range(4):
            for lane in range(7):
                self.app._emit_hit_effect(lane, Judgment.PERFECT)
        self.assertEqual(len(self.app.hit_effects), 7)
        self.assertEqual({e.lane for e in self.app.hit_effects}, set(range(7)))


    def test_seven_holds_limit_perspective_particles(self) -> None:
        with patch.object(self.app, "_active_hold_lanes", return_value=set(range(7))), patch("app.pygame.draw.circle") as circle:
            self.app._draw_perspective_hold_sparks(280, 720, 102, 20, 646, 1.0)
        self.assertEqual(circle.call_count, 21)

    def test_miss_does_not_create_distracting_hit_effect(self) -> None:
        self.app._play_feedback(Judgment.MISS, lane=2)

        self.assertEqual(self.app.hit_effects, [])
        self.assertEqual(len(self.app.judgment_log), 1)
        self.assertEqual(self.app.judgment_log[0].judgment, Judgment.MISS)
        self.assertEqual(self.app.judgment_log[0].lane, 2)

    def test_expired_effect_is_removed_when_drawn(self) -> None:
        self.app._play_feedback(Judgment.GREAT, lane=1)
        self.app.hit_effects[0].started_at = time.perf_counter() - 1.0

        self.app._draw_hit_effects(left=100, lane_width=120, field_top=20, line_y=620)

        self.assertEqual(self.app.hit_effects, [])

    def test_perspective_hit_effect_does_not_redraw_a_moving_note(self) -> None:
        self.app._play_feedback(Judgment.GREAT, lane=1)

        with patch.object(self.app, "_draw_perspective_note_bar") as draw_note:
            self.app._draw_perspective_hit_effects(left=280, field_width=720, lane_width=144, field_top=20, line_y=646)

        draw_note.assert_not_called()

    def test_judgment_log_keeps_recent_entries_and_expires_when_drawn(self) -> None:
        chart = Chart(1, "j" * 64, Difficulty.NORMAL, 0, 2.0, notes=[Note(1.0, 0)])
        self.app.session = GameSession(chart, JudgmentWindows())
        for index in range(JUDGMENT_LOG_LIMIT + 3):
            self.app._play_feedback(Judgment.GOOD, lane=index % 5)

        self.assertEqual(len(self.app.judgment_log), JUDGMENT_LOG_LIMIT)
        self.app.judgment_log[0].started_at = time.perf_counter() - self.app.judgment_log[0].duration - 0.1

        self.app._draw_judgment_panel(left=320, field_top=20, line_y=650)

        self.assertEqual(len(self.app.judgment_log), JUDGMENT_LOG_LIMIT - 1)

    def test_judgment_panel_draws_live_counts(self) -> None:
        chart = Chart(1, "p" * 64, Difficulty.NORMAL, 0, 2.0, notes=[Note(1.0, 0)])
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.session.judgment_counts[Judgment.PERFECT.value] = 2
        self.app.session.judgment_counts[Judgment.MISS.value] = 1
        self.app._play_feedback(Judgment.PERFECT, lane=0)

        self.app._draw_judgment_panel(left=320, field_top=20, line_y=650)

        self.assertGreater(len(self.app.judgment_log), 0)


if __name__ == "__main__":
    unittest.main()
