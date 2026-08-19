from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from models import Judgment


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
        self.assertLessEqual(effect.duration, 0.20)

    def test_miss_does_not_create_distracting_hit_effect(self) -> None:
        self.app._play_feedback(Judgment.MISS, lane=2)

        self.assertEqual(self.app.hit_effects, [])

    def test_expired_effect_is_removed_when_drawn(self) -> None:
        self.app._play_feedback(Judgment.GREAT, lane=1)
        self.app.hit_effects[0].started_at = time.perf_counter() - 1.0

        self.app._draw_hit_effects(left=100, lane_width=120, line_y=620)

        self.assertEqual(self.app.hit_effects, [])


if __name__ == "__main__":
    unittest.main()
