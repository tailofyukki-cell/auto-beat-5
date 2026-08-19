from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import AutoBeatApp


class UiSmokeTest(unittest.TestCase):
    def test_static_screens_draw(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            os.environ["AUTOBEAT_DATA_DIR"] = directory
            app = AutoBeatApp()
            for screen in ("title", "select", "analyzing", "gallery", "settings"):
                app.screen = screen
                app.draw()
            app.running = False
            app.persist_settings()
        import pygame
        pygame.quit()


if __name__ == "__main__":
    unittest.main()
