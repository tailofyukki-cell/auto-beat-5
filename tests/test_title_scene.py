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
from app import AutoBeatApp


class TitleSceneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": self.temporary.name})
        self.environment.start()
        self.app = AutoBeatApp()

    def tearDown(self):
        pygame.quit()
        self.environment.stop()
        self.temporary.cleanup()

    def test_buttons_fit_and_do_not_overlap_at_each_resolution(self):
        for size in ((960, 540), (1280, 720), (1600, 900), (1920, 1080)):
            with self.subTest(size=size):
                self.app.display_surface = pygame.display.set_mode(size)
                self.app.surface = self.app._create_render_surface(size)
                self.app.draw()
                bounds = self.app.surface.get_rect()
                rects = [rect for rect, _ in self.app.buttons]
                self.assertGreaterEqual(len(rects), 7)
                for index, rect in enumerate(rects):
                    self.assertTrue(bounds.contains(rect), rect)
                    self.assertFalse(any(rect.colliderect(other) for other in rects[index + 1:]))

    def test_animation_changes_pixels_and_reuses_scene(self):
        with patch("pygame.time.get_ticks", return_value=1000):
            self.app.draw()
        scene = self.app._title_scene
        first = pygame.image.tobytes(self.app.surface, "RGB")
        with patch("pygame.time.get_ticks", return_value=2000):
            self.app.draw()
        self.assertIs(scene, self.app._title_scene)
        self.assertNotEqual(first, pygame.image.tobytes(self.app.surface, "RGB"))

    def test_menu_actions_and_title_resources_release(self):
        self.app.draw()
        normal = self.app.buttons[1 if self.app._title_scene.sprite else 0][1]
        normal()
        self.assertEqual(self.app.screen, "select")
        self.app.draw()
        self.assertIsNone(self.app._title_scene)

    def test_missing_mascot_keeps_menu_usable(self):
        self.app.mascot_catalog = ()
        self.app.draw()
        self.assertIsNone(self.app._title_scene.sprite)
        self.assertEqual(len(self.app.buttons), 7)


if __name__ == "__main__":
    unittest.main()
