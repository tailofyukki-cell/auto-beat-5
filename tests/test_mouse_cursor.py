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


class MouseCursorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": self.temp.name})
        self.environment.start()
        self.app = AutoBeatApp()
        self.app.audio = SimpleNamespace(paused=False)
        self.app.session = object()
        self.app.screen = "game"
        pygame.mouse.set_visible(True)

    def tearDown(self):
        pygame.mouse.set_visible(True)
        pygame.quit()
        self.environment.stop()
        self.temp.cleanup()

    def update_at(self, now, moved=False):
        with patch("app.time.perf_counter", return_value=now):
            self.app._update_mouse_cursor(moved=moved)
        return pygame.mouse.get_visible()

    def test_movement_restarts_two_second_visibility(self):
        self.assertFalse(self.update_at(10))
        self.assertTrue(self.update_at(11, True))
        self.assertTrue(self.update_at(12.99))
        self.assertTrue(self.update_at(12.99, True))
        self.assertTrue(self.update_at(14.98))
        self.assertFalse(self.update_at(14.99))

    def test_pause_resume_and_screen_changes(self):
        self.assertFalse(self.update_at(10))
        self.app.audio.paused = True
        self.assertTrue(self.update_at(10.1))
        self.app.audio.paused = False
        self.assertFalse(self.update_at(10.2))
        for screen in ("result", "select", "settings", "title"):
            self.app.screen = screen
            self.assertTrue(self.update_at(11))

    def test_focus_and_new_session_reset_visibility(self):
        self.assertTrue(self.update_at(10, True))
        self.app.session = object()
        self.assertFalse(self.update_at(10.1))
        self.app._cursor_window_focused = False
        self.assertTrue(self.update_at(10.2))
        self.app._cursor_window_focused = True
        self.assertFalse(self.update_at(10.3))

    def test_tutorial_pause_is_visible(self):
        self.app.tutorial_step_index = 0
        self.app.tutorial_paused_at = None
        self.assertFalse(self.update_at(10))
        self.app.tutorial_paused_at = 10
        self.assertTrue(self.update_at(10.1))
