from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp, LANE_COLORS
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

    def test_hold_end_draws_regular_note_sized_cap(self) -> None:
        self.app.draw()

        left, _field_width, lane_width, _field_top, line_y = self.app._game_field_geometry()
        end_y = int(line_y - (3.0 - 2.7) * float(self.app.settings["note_speed"]))
        cap_center_x = left + 2 * lane_width + lane_width // 2
        pixel = self.app.surface.get_at((cap_center_x, end_y))[:3]
        self.assertEqual(pixel, LANE_COLORS[2])


if __name__ == "__main__":
    unittest.main()
