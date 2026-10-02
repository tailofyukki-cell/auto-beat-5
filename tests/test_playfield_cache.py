"""Pixel reference protects translucent draw ordering during cache changes."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from app import AutoBeatApp, WHITE

# Frozen pre-optimization renderer for exact pixel comparison.
def reference_playfield(self, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, now: float) -> None:
    top_width = self._perspective_top_width(field_width)
    top_left = self.size[0] // 2 - top_width // 2
    cache_key = (self.size, left, field_width, lane_width, field_top, line_y,
                 self.active_lane_count, tuple(self.lane_color(lane) for lane in range(self.active_lane_count)))
    if self._playfield_base_cache is None or self._playfield_base_cache[0] != cache_key:
        layer = pygame.Surface(self.size, pygame.SRCALPHA)
        field_poly = [(top_left, field_top), (top_left + top_width, field_top), (left + field_width, line_y), (left, line_y)]
        pygame.draw.polygon(layer, (7, 12, 28, 245), field_poly)

        # Each lane carries a restrained tint so the highway reads as one neon stage.
        for lane in range(self.active_lane_count):
            color = self.lane_color(lane)
            lane_poly = [
                (top_left + lane * top_width / self.active_lane_count, field_top),
                (top_left + (lane + 1) * top_width / self.active_lane_count, field_top),
                (left + (lane + 1) * lane_width, line_y),
                (left + lane * lane_width, line_y),
            ]
            pygame.draw.polygon(layer, (*color, 13 if lane % 2 == 0 else 8), lane_poly)

        # Depth-compressed cross lines converge into the horizon instead of forming a flat grid.
        for step in range(1, 19):
            ratio = (step / 19) ** 1.72
            y = field_top + (line_y - field_top) * ratio
            left_x, full_width, depth = self._perspective_lane_rect(0, y, left, field_width, lane_width, field_top, line_y)
            alpha = int(24 + depth * 64)
            pygame.draw.line(layer, (79, 156, 210, alpha), (left_x, y), (left_x + full_width * self.active_lane_count, y), 1)
        self._playfield_base_cache = (cache_key, layer)
    # Dynamic primitives overwrite pixels on this copy, preserving the original alpha order.
    layer = self._playfield_base_cache[1].copy()

    # Moving streaks provide speed without covering the note path.
    travel = max(1, line_y - field_top)
    for lane in range(self.active_lane_count):
        color = self.lane_color(lane)
        for streak in range(2):
            phase = (now * (0.20 + streak * 0.035) + lane * 0.13 + streak * 0.41) % 1.0
            start_y = field_top + travel * phase
            end_y = min(line_y, start_y + 18 + 56 * phase)
            start_left, start_width, _ = self._perspective_lane_rect(lane, start_y, left, field_width, lane_width, field_top, line_y)
            end_left, end_width, _ = self._perspective_lane_rect(lane, end_y, left, field_width, lane_width, field_top, line_y)
            x1 = start_left + start_width * (0.28 + streak * 0.44)
            x2 = end_left + end_width * (0.28 + streak * 0.44)
            pygame.draw.line(layer, (*color, 38), (x1, start_y), (x2, end_y), 1)

    for lane in range(self.active_lane_count + 1):
        bottom_x = left + lane * lane_width
        top_x = top_left + lane * top_width / max(1, self.active_lane_count)
        color = WHITE if lane in (0, self.active_lane_count) else tuple(channel // 2 for channel in self.lane_color(max(0, lane - 1)))
        edge_width = 2 if lane in (0, self.active_lane_count) else 1
        pygame.draw.line(layer, (*color, 24), (top_x, field_top), (bottom_x, line_y), edge_width + 7)
        pygame.draw.line(layer, (*color, 70), (top_x, field_top), (bottom_x, line_y), edge_width + 3)
        pygame.draw.line(layer, (*color, 190), (top_x, field_top), (bottom_x, line_y), edge_width)

    average = sum(self._visualizer_levels(now)) / 5.0
    horizon_alpha = int(135 + average * 90)
    horizon_y = field_top + 2
    pygame.draw.line(layer, (72, 215, 255, 26), (top_left - 42, horizon_y), (top_left + top_width + 42, horizon_y), 15)
    pygame.draw.line(layer, (119, 230, 255, horizon_alpha), (top_left - 22, horizon_y), (top_left + top_width + 22, horizon_y), 2)
    pygame.draw.line(layer, (255, 255, 255, 220), (top_left, horizon_y), (top_left + top_width, horizon_y), 1)

    # A broad illuminated judgment deck anchors the near edge.
    deck_top = line_y - max(12, int((line_y - field_top) * 0.025))
    deck_left, deck_lane_width, _ = self._perspective_lane_rect(0, deck_top, left, field_width, lane_width, field_top, line_y)
    deck_poly = [(deck_left, deck_top), (deck_left + deck_lane_width * self.active_lane_count, deck_top), (left + field_width, line_y), (left, line_y)]
    pygame.draw.polygon(layer, (76, 192, 255, 28), deck_poly)
    pygame.draw.line(layer, (72, 204, 255, 35), (left, line_y), (left + field_width, line_y), 15)
    pygame.draw.line(layer, (120, 227, 255, 105), (left, line_y), (left + field_width, line_y), 7)
    pygame.draw.line(layer, (*WHITE, 250), (left, line_y), (left + field_width, line_y), 3)
    self.surface.blit(layer, (0, 0))


class PlayfieldCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": self.temp.name})
        self.env.start()
        self.app = AutoBeatApp()
        self.app.profile["unlocked_features"] = ["lane.3", "lane.5", "lane.7"]

    def tearDown(self):
        pygame.quit()
        self.env.stop()
        self.temp.cleanup()

    def test_pixels_match_reference_after_time_size_and_lane_changes(self):
        for size in ((1280, 720), (1600, 900)):
            for lanes in (3, 5, 7):
                self.app.surface = pygame.Surface(size)
                self.app.settings["lane_count"] = lanes
                geometry = self.app._game_field_geometry()
                for now in (0.0, 0.7, 2.3, 0.0):
                    with self.subTest(size=size, lanes=lanes, now=now):
                        self.app.surface.fill((10, 14, 24))
                        reference_playfield(self.app, *geometry, now)
                        expected = pygame.image.tobytes(self.app.surface, "RGB")
                        self.app.surface.fill((10, 14, 24))
                        self.app._draw_perspective_playfield(*geometry, now)
                        self.assertEqual(pygame.image.tobytes(self.app.surface, "RGB"), expected)

    def test_reuse_and_color_invalidation(self):
        geometry = self.app._game_field_geometry()
        self.app._draw_perspective_playfield(*geometry, 0.0)
        foreground = self.app._playfield_foreground
        scratch = self.app._playfield_scratch
        self.app._draw_perspective_playfield(*geometry, 0.8)
        self.assertIs(self.app._playfield_foreground, foreground)
        self.assertIs(self.app._playfield_scratch, scratch)
        with patch.object(self.app, "lane_color", return_value=(90, 180, 120)):
            self.app._draw_perspective_playfield(*geometry, 0.8)
            self.assertIsNot(self.app._playfield_foreground, foreground)
            # Reset background before comparing compositing with the changed theme.
            self.app.surface.fill((10, 14, 24))
            reference_playfield(self.app, *geometry, 0.8)
            expected = pygame.image.tobytes(self.app.surface, "RGB")
            self.app.surface.fill((10, 14, 24))
            self.app._draw_perspective_playfield(*geometry, 0.8)
            self.assertEqual(pygame.image.tobytes(self.app.surface, "RGB"), expected)
