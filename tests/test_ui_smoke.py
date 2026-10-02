from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import AutoBeatApp, GAME_TITLE, GAME_TAGLINE, WINDOW_TITLE


class UiSmokeTest(unittest.TestCase):
    def test_game_branding(self) -> None:
        self.assertEqual(GAME_TITLE, "オトアソビ")
        self.assertEqual(GAME_TAGLINE, "好きな曲を、遊ぼう。")
        self.assertEqual(WINDOW_TITLE, f"{GAME_TITLE} - {GAME_TAGLINE}")

    def test_static_screens_draw(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.environ["AUTOBEAT_DATA_DIR"] = directory
            app = AutoBeatApp()
            for screen in ("title", "select", "analyzing", "gallery", "shop", "settings"):
                app.screen = screen
                app.draw()
            app.running = False
            app.persist_settings()
        import pygame
        pygame.quit()


if __name__ == "__main__":
    unittest.main()
