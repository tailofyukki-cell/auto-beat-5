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
from app import AutoBeatApp


class ComboQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": self.temp.name})
        self.env.start()
        self.app = AutoBeatApp()
        self.sprite = pygame.Surface((160, 240), pygame.SRCALPHA)
        self.sprite.fill((120, 180, 240, 255))

    def tearDown(self):
        pygame.quit()
        self.env.stop()
        self.temp.cleanup()

    def test_mascot_transform_updates_at_thirty_hz_only_in_low_mode(self):
        self.app.settings["graphics_quality"] = "low"
        with patch.object(self.app, "_mascot_frame", return_value=self.sprite) as frame:
            for i in range(120):
                self.app._mascot_display_frame(self.sprite, i * 0.1, 1.0, i / 120)
            self.assertEqual(frame.call_count, 30)
            self.app.settings["graphics_quality"] = "standard"
            for i in range(120):
                self.app._mascot_display_frame(self.sprite, i * 0.1, 1.0, i / 120)
            self.assertEqual(frame.call_count, 150)

    def test_mascot_transform_invalidates_on_seek_source_and_event(self):
        self.app.settings["graphics_quality"] = "low"
        with patch.object(self.app, "_mascot_frame", return_value=self.sprite) as frame:
            self.app._mascot_display_frame(self.sprite, 0, 1, 2)
            self.app._mascot_display_frame(self.sprite, 0, 1, 2)
            self.assertEqual(frame.call_count, 1)
            self.app._mascot_display_frame(self.sprite, 0, 1, 0)
            self.app.mascot_combo_zoom_until += 1
            self.app._mascot_display_frame(self.sprite, 0, 1, 0)
            self.app._mascot_display_frame(self.sprite.copy(), 0, 1, 0)
            self.assertEqual(frame.call_count, 4)

    def test_face_refreshes_thirty_times_and_new_event_invalidates(self):
        self.app.settings["graphics_quality"] = "low"
        rect = self.sprite.get_rect(center=(1000, 400))
        with patch("app.time.perf_counter") as clock, patch("app.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as scale:
            for frame in range(60):
                clock.return_value = frame / 60
                self.app._draw_mascot_face_zoom(self.sprite, rect, 0.5)
            self.assertEqual(scale.call_count, 30)
            self.app.mascot_combo_zoom_until += 1
            self.app._draw_mascot_face_zoom(self.sprite, rect, 0.5)
            self.assertEqual(scale.call_count, 31)
            self.app.settings["graphics_quality"] = "standard"
            self.app._draw_mascot_face_zoom(self.sprite, rect, 0.5)
            self.app._draw_mascot_face_zoom(self.sprite, rect, 0.5)
            self.assertEqual(scale.call_count, 33)

    def test_static_sprite_reuses_copy_without_mutating_source(self):
        cached = self.app._static_cutin_sprite(self.sprite, 100)
        self.assertEqual(cached.get_width(), 100)
        self.assertIs(cached, self.app._static_cutin_sprite(self.sprite, 100))
        cached.set_alpha(25)
        self.assertEqual(self.sprite.get_alpha(), 255)
        self.assertIsNot(cached, self.app._static_cutin_sprite(self.sprite, 120))
        other = self.sprite.copy()
        self.assertIsNot(self.app._static_cutin_sprite(other, 120), self.app._static_cutin_sprite(self.sprite, 120))

    def test_low_cutin_does_not_rotate_and_restores_alpha(self):
        self.app.surface = pygame.Surface((1600, 900))
        self.app.settings["graphics_quality"] = "low"
        with patch.object(self.app, "_combo_cutin_progress", return_value=0.5), patch.object(self.app, "_load_combo_cutin_media", return_value=self.sprite), patch("app.pygame.transform.rotozoom") as rotate:
            self.app._draw_combo_cutin(400, 700, 820)
            rotate.assert_not_called()
        self.assertEqual(self.app._static_cutin_cache[2].get_alpha(), 255)


if __name__ == "__main__":
    unittest.main()
