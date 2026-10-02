from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Note, NoteType


class HoldEndCapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()
        chart = Chart(
            version=1,
            music_hash="hold_endcap" * 8,
            difficulty=Difficulty.NORMAL,
            seed=1,
            song_duration=6.0,
            notes=[Note(1.5, 2, NoteType.HOLD, 3.0)],
        )
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.screen = "game"
        # 終端だけがレーン内に見える時刻を固定する。
        self.app.audio = SimpleNamespace(time=2.7, paused=False)

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_hold_end_draws_regular_note_sized_cap_in_selected_theme_color(self) -> None:
        self.app.settings["note_theme"] = "pastel"
        self.app.draw()

        left, _field_width, lane_width, _field_top, line_y = self.app._game_field_geometry()
        end_y = int(line_y - (3.0 - 2.7) * float(self.app.settings["note_speed"]))
        cap_center_x = left + 2 * lane_width + lane_width // 2
        pixel = self.app.surface.get_at((cap_center_x, end_y))[:3]
        self.assertEqual(pixel, self.app.lane_colors[2])

    def test_perspective_long_hold_pixels_stay_inside_their_lane(self) -> None:
        self.app.settings["lane_view"] = "perspective"
        self.app.profile["unlocked_features"] = ["lane.3", "lane.5", "lane.7"]
        for count in (3, 5, 7):
            self.app.settings["lane_count"] = count
            self.app.chart.metadata["lane_count"] = count
            self.app._normalize_lane_runtime_settings()
            left, width, lane_width, top, bottom = self.app._game_field_geometry()
            for lane in range(count):
                for first, last in ((top - 4000, bottom + 4000), (top - 900, top + 30),
                                    (bottom - 30, bottom + 900)):
                    self.app.surface.fill((0, 0, 0))
                    self.app._draw_perspective_hold_rail(lane, first, last, left, width, lane_width, top, bottom, (71, 215, 255))
                    painted = pygame.mask.from_threshold(self.app.surface, (0, 0, 0), (1, 1, 1, 255))
                    painted.invert()
                    self.assertGreater(painted.count(), 0)
                    allowed = pygame.Surface(self.app.size, pygame.SRCALPHA)
                    x0, w0, _ = self.app._perspective_lane_rect(lane, top, left, width, lane_width, top, bottom)
                    x1, w1, _ = self.app._perspective_lane_rect(lane, bottom, left, width, lane_width, top, bottom)
                    pygame.draw.polygon(allowed, (255, 255, 255, 255), [(x0, top), (x0+w0, top), (x1+w1, bottom), (x1, bottom)])
                    painted.erase(pygame.mask.from_surface(allowed), (0, 0))
                    self.assertEqual(painted.count(), 0, (count, lane, first, last))

    def test_classic_hold_rail_is_centered_and_clipped(self) -> None:
        left, _, lane_width, top, bottom = self.app._game_field_geometry()
        with patch.object(self.app, "_draw_hold_rail", wraps=self.app._draw_hold_rail) as draw_rail:
            self.app.draw()
        self.assertTrue(draw_rail.called)
        rect = draw_rail.call_args.args[0]
        self.assertEqual(rect.centerx, left + 2 * lane_width + lane_width // 2)
        self.assertGreaterEqual(rect.top, top)
        self.assertLessEqual(rect.bottom, bottom)

    def test_active_hold_draws_spark_glow_near_judgment_line(self) -> None:
        self.app.session.press(2, 1.5)
        left, _field_width, lane_width, field_top, line_y = self.app._game_field_geometry()
        lane_x = left + 2 * lane_width
        self.app.surface.fill((18, 28, 48), pygame.Rect(lane_x, field_top, lane_width - 2, line_y - field_top))

        self.app._draw_hold_sparks(left, lane_width, field_top, line_y, now=2.0)

        glow_x = lane_x + lane_width // 2
        glow_y = line_y - 24
        self.assertNotEqual(self.app.surface.get_at((glow_x, glow_y))[:3], (18, 28, 48))
        self.assertEqual(self.app._active_hold_lanes(), {2})



if __name__ == "__main__":
    unittest.main()
