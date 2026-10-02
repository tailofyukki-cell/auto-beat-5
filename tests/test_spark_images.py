from __future__ import annotations
import os
import sys
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from app import AutoBeatApp, WHITE, HOLD_SPARK_ALPHA, HOLD_PARTICLE_LIMIT

def reference_sparks(self, left: int, lane_width: int, field_top: int, line_y: int, now: float) -> None:
    active_lanes = self._active_hold_lanes()
    if not active_lanes:
        return
    band_height = max(42, min(120, line_y - field_top))
    top = max(field_top, line_y - band_height)
    for lane in active_lanes:
        if not 0 <= lane < self.active_lane_count:
            continue
        color = self.lane_color(lane)
        x = left + lane * lane_width
        center_x = x + lane_width // 2
        glow = pygame.Surface((lane_width - 2, line_y - top), pygame.SRCALPHA)
        glow.fill((*color, 24))
        pygame.draw.rect(glow, (*color, HOLD_SPARK_ALPHA), pygame.Rect(lane_width // 2 - 8, 0, 16, line_y - top), border_radius=8)
        pygame.draw.circle(glow, (*color, 150), (lane_width // 2, line_y - top - 10), max(8, lane_width // 9), width=2)
        self.surface.blit(glow, (x, top))
        for index in range(min(9, HOLD_PARTICLE_LIMIT // max(1, len(active_lanes)))):
            phase = now * (7.0 + index * 0.37) + lane * 1.91 + index * 2.13
            spread = lane_width * 0.30
            spark_x = int(center_x + math.sin(phase) * spread)
            spark_y = int(line_y - 12 - ((now * 82 + index * 17 + lane * 11) % band_height))
            radius = 1 + (index % 3)
            alpha = 120 + int((math.sin(phase * 1.7) + 1.0) * 45)
            spark = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
            pygame.draw.circle(spark, (*WHITE, min(235, alpha)), (radius * 3, radius * 3), radius)
            pygame.draw.circle(spark, (*color, min(210, alpha)), (radius * 3, radius * 3), radius + 2, width=1)
            self.surface.blit(spark, (spark_x - radius * 3, spark_y - radius * 3))


class SparkImageTests(unittest.TestCase):
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

    def test_matches_original_across_lanes_times_and_colors(self):
        for count in (3, 5, 7):
            self.app.settings["lane_count"] = count
            with patch.object(self.app, "_active_hold_lanes", return_value=set(range(count))):
                for now in (0, 0.12, 1.7, 0):
                    self.app.surface.fill((12, 20, 32))
                    reference_sparks(self.app, 100, 110, 20, 620, now)
                    expected = pygame.image.tobytes(self.app.surface, "RGB")
                    self.app.surface.fill((12, 20, 32))
                    self.app._draw_hold_sparks(100, 110, 20, 620, now)
                    self.assertEqual(pygame.image.tobytes(self.app.surface, "RGB"), expected)
        with patch.object(self.app, "_active_hold_lanes", return_value={0}):
            self.app._draw_hold_sparks(100, 110, 20, 620, 1)
            first = dict(self.app._hold_spark_images)
            self.app._draw_hold_sparks(100, 110, 20, 620, 1)
            self.assertEqual(first, self.app._hold_spark_images)
            with patch.object(self.app, "lane_color", return_value=(1, 2, 3)):
                self.app._draw_hold_sparks(100, 110, 20, 620, 1)
                self.assertTrue(any(key[0] == (1, 2, 3) for key in self.app._hold_spark_images))

    def test_cache_is_bounded(self):
        with patch.object(self.app, "_active_hold_lanes", return_value={0}):
            for i in range(240):
                with patch.object(self.app, "lane_color", return_value=(i, 20, 40)):
                    self.app._draw_hold_sparks(100, 110, 20, 620, i/60)
        self.assertEqual(len(self.app._hold_spark_images), 2048)
        self.assertLessEqual(sum(s.get_pitch()*s.get_height() for s in self.app._hold_spark_images.values()), 2048*18*18*4)
