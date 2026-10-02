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


class VisualizerCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": self.temp.name})
        self.environment.start()
        self.app = AutoBeatApp()

    def tearDown(self):
        pygame.quit()
        self.environment.stop()
        self.temp.cleanup()

    def test_sixty_frames_render_thirty_decorations(self):
        with patch.object(self.app, "_render_audio_visualizer", wraps=self.app._render_audio_visualizer) as render:
            for frame in range(60):
                self.app._draw_audio_visualizer(frame / 60)
            self.assertEqual(render.call_count, 30)

    def test_low_quality_refreshes_fifteen_times_and_switch_invalidates(self):
        self.app.settings["graphics_quality"] = "low"
        with patch.object(self.app, "_render_audio_visualizer", wraps=self.app._render_audio_visualizer) as render:
            for frame in range(60):
                self.app._draw_audio_visualizer(frame / 60)
            self.assertEqual(render.call_count, 15)
            self.app.settings["graphics_quality"] = "standard"
            self.app._draw_audio_visualizer(59 / 60)
            self.assertEqual(render.call_count, 16)

    def test_quality_setting_is_available_and_persists(self):
        from persistence import save_settings, load_settings
        self.assertFalse(self.app.low_graphics_quality)
        self.assertTrue(self.app._setting_row_has_choices(21))
        self.app.settings_selection = 21
        windows = dict(self.app.settings["judgment_windows_ms"])
        self.app.adjust_setting(1)
        self.assertTrue(self.app.low_graphics_quality)
        self.assertEqual(self.app.hold_particle_limit, 14)
        self.assertEqual(self.app.settings["judgment_windows_ms"], windows)
        save_settings(self.app.paths, self.app.settings)
        self.assertEqual(load_settings(self.app.paths)["graphics_quality"], "low")
        self.app.adjust_setting(-1)
        self.assertFalse(self.app.low_graphics_quality)
        self.assertEqual(self.app.hold_particle_limit, 21)
        self.app.settings["graphics_quality"] = "invalid"
        self.assertFalse(self.app.low_graphics_quality)

    def test_settings_quality_row_draws_on_small_logical_screen(self):
        self.app.surface = pygame.Surface((1280, 720))
        self.app.screen = "settings"
        self.app.settings_selection = 21
        with patch.object(self.app, "text", wraps=self.app.text) as text:
            self.app.draw_settings()
        self.assertTrue(any(call.args[0] == "描画品質" for call in text.call_args_list))
        self.assertTrue(all(self.app.surface.get_rect().contains(rect) for rect, _ in self.app.buttons))

    def test_pause_seek_and_new_session(self):
        with patch.object(self.app, "_render_audio_visualizer", wraps=self.app._render_audio_visualizer) as render:
            self.app._draw_audio_visualizer(2.0)
            for _ in range(5):
                self.app._draw_audio_visualizer(2.0)
            self.assertEqual(render.call_count, 1)
            self.app._draw_audio_visualizer(0.0)
            self.app.session = object()
            self.app._draw_audio_visualizer(0.0)
            self.assertEqual(render.call_count, 3)

    def test_size_color_and_analysis_invalidate(self):
        with patch.object(self.app, "_render_audio_visualizer", wraps=self.app._render_audio_visualizer) as render:
            self.app._draw_audio_visualizer(0.0)
            self.app.surface = pygame.Surface((960, 540))
            self.app._draw_audio_visualizer(0.0)
            self.app.analysis = SimpleNamespace(onsets=[])
            self.app._draw_audio_visualizer(0.0)
            with patch.object(self.app, "lane_color", return_value=(255, 100, 50)):
                self.app._draw_audio_visualizer(0.0)
            self.assertEqual(render.call_count, 4)
            self.assertEqual(self.app._visualizer_frame_cache[1].get_size(), (960, 540))

    def test_cached_frame_matches_original_render_and_redraws(self):
        expected = self.app._render_audio_visualizer(1.0)
        self.app.surface.fill((0, 0, 0))
        self.app.surface.blit(expected, (0, 0))
        pixels = pygame.image.tobytes(self.app.surface, "RGB")
        self.assertNotEqual(pixels, bytes(len(pixels)))
        for now in (1.0, 1.01):
            self.app.surface.fill((0, 0, 0))
            self.app._draw_audio_visualizer(now)
            self.assertEqual(pygame.image.tobytes(self.app.surface, "RGB"), pixels)


if __name__ == "__main__":
    unittest.main()
