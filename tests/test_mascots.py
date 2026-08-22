from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp, MASCOT_MODES
from gameplay import GameSession, JudgmentWindows
from mascots import find_mascot, load_mascot_catalog
from models import AnalysisResult, Chart, Difficulty, Note
from persistence import load_settings


class MascotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("AUTOBEAT_DATA_DIR")
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        if self.previous_data_dir is None:
            os.environ.pop("AUTOBEAT_DATA_DIR", None)
        else:
            os.environ["AUTOBEAT_DATA_DIR"] = self.previous_data_dir
        self.directory.cleanup()

    def test_catalog_uses_manifest_order_and_rejects_unsafe_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cute.png").write_bytes(b"png")
            (root / "cool.webp").write_bytes(b"webp")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "mascots": [
                            {"id": "cute", "name": "CUTE", "file": "cute.png", "scale": 1.2},
                            {"id": "cool", "name": "COOL", "file": "cool.webp", "anchor": "left"},
                            {"id": "bad-path", "file": "../outside.png"},
                            {"id": "cute", "file": "cute.png"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            catalog = load_mascot_catalog(root)
        self.assertEqual([mascot.mascot_id for mascot in catalog], ["cute", "cool"])
        self.assertAlmostEqual(catalog[0].scale, 1.2)
        self.assertEqual(catalog[1].anchor, "left")
        self.assertEqual(find_mascot(catalog, "cool"), catalog[1])
        self.assertIsNone(find_mascot(catalog, "missing"))

    def test_default_mascot_settings_load_and_persist(self) -> None:
        self.assertIn(self.app.mascot_mode_key, MASCOT_MODES)
        self.assertEqual(self.app.mascot_mode_key, "standard")
        self.assertIsNotNone(self.app.selected_mascot)
        self.assertEqual(self.app.selected_mascot.mascot_id, "cute")

        self.app.settings_selection = 12
        self.app.adjust_setting(1)
        self.assertEqual(self.app.mascot_mode_key, "off")
        self.app.settings_selection = 13
        self.app.adjust_setting(1)
        self.app.persist_settings()
        restored = load_settings(self.app.paths)
        self.assertEqual(restored["mascot_mode"], "off")
        self.assertEqual(restored["mascot_id"], "cute")

    def test_game_draws_mascot_without_entering_note_field(self) -> None:
        chart = Chart(1, "m" * 64, Difficulty.NORMAL, 1, 8.0, notes=[Note(2.0, 2)])
        self.app.chart = chart
        self.app.analysis = AnalysisResult(
            music_hash=chart.music_hash,
            source_path="fixture.wav",
            duration=8.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0],
            onsets=[],
            onset_strengths=[],
            band_energy=[],
            percussive_strengths=[],
            sustained_segments=[],
        )
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.screen = "game"
        self.app.draw()

        self.assertIn("cute", self.app.mascot_image_cache)
        self.assertIsNotNone(self.app.mascot_image_cache["cute"])
        self.assertTrue(self.app.mascot_scaled_cache)


if __name__ == "__main__":
    unittest.main()
