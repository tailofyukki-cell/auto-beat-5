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
from app import AutoBeatApp, COMBO_MILESTONES, MASCOT_MODES
from gameplay import GameSession, JudgmentWindows
from mascots import find_mascot, load_mascot_catalog
from models import AnalysisResult, Chart, Difficulty, Note
from persistence import load_settings, purchase_unlock


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

    def test_unlisted_png_files_are_auto_discovered_after_manifest_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cute.png").write_bytes(b"png")
            (root / "cool_girl.png").write_bytes(b"png")
            (root / "bad name.png").write_bytes(b"png")
            (root / "manifest.json").write_text(
                json.dumps({"mascots": [{"id": "cute", "name": "CUTE", "file": "cute.png"}]}),
                encoding="utf-8",
            )
            catalog = load_mascot_catalog(root)
        self.assertEqual([mascot.mascot_id for mascot in catalog], ["cute", "bad-name", "cool_girl"])
        self.assertEqual(catalog[1].name, "BAD NAME")
        self.assertEqual(catalog[2].name, "COOL GIRL")


    def test_image_files_are_discovered_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "追加キャラ.png").write_bytes(b"png")
            catalog = load_mascot_catalog(root)
        self.assertEqual(len(catalog), 1)
        self.assertTrue(catalog[0].mascot_id.startswith("mascot-"))
        self.assertEqual(catalog[0].name, "追加キャラ")

    def test_default_mascot_settings_load_and_persist(self) -> None:
        self.assertIn(self.app.mascot_mode_key, MASCOT_MODES)
        self.assertEqual(self.app.mascot_mode_key, "standard")
        self.assertIsNotNone(self.app.selected_mascot)
        self.assertEqual(self.app.selected_mascot.mascot_id, "rhythm")

        self.app.settings_selection = 18
        self.app.adjust_setting(1)
        self.assertEqual(self.app.mascot_mode_key, "off")
        self.app.profile["unlocked_cosmetics"] = ["mascot.rhythm", "mascot.cute"]
        self.app.settings_selection = 19
        self.app.adjust_setting(1)
        self.app.persist_settings()
        restored = load_settings(self.app.paths)
        self.assertEqual(restored["mascot_mode"], "off")
        self.assertEqual(restored["mascot_id"], "cute")

    def test_transform_cache_reuses_nearby_frames_and_replaces_source(self) -> None:
        base = pygame.Surface((80, 120), pygame.SRCALPHA)
        first = self.app._mascot_frame(base, 0.0, 1.0)
        self.assertIs(first, self.app._mascot_frame(base, 0.1, 1.001))
        self.assertTrue(first.get_flags() & pygame.SRCALPHA)
        self.assertIsNot(first, self.app._mascot_frame(base, 2.0, 1.02))
        replacement = pygame.Surface((80, 120), pygame.SRCALPHA)
        self.assertIsNot(first, self.app._mascot_frame(replacement, 0.0, 1.0))
        self.assertEqual(len(self.app._mascot_frames), 1)

    def test_transform_cache_stays_bounded(self) -> None:
        base = pygame.Surface((240, 310), pygame.SRCALPHA)
        for index in range(160):
            self.app._mascot_frame(base, index / 4, 1.0 + index / 200)
        self.assertLessEqual(self.app._mascot_frame_bytes, 32 * 1024 * 1024)
        self.assertLessEqual(len(self.app._mascot_frames), 128)
        self.assertEqual(self.app._mascot_frame_bytes,
                         sum(frame.get_pitch() * frame.get_height() for frame in self.app._mascot_frames.values()))

    def test_settings_blocks_locked_mascots_until_shop_purchase(self) -> None:
        self.app.settings["mascot_id"] = "rhythm"
        self.app.settings_selection = 19

        self.app.adjust_setting(1)

        self.assertEqual(self.app.settings["mascot_id"], "rhythm")
        self.assertIn("BEAT SHOP", self.app.message)

        self.app.profile["wallet_initialized"] = True
        self.app.profile["wallet_score"] = 200000
        self.assertTrue(purchase_unlock(self.app.paths, self.app.profile, "mascot.cute", 100000))
        self.app.adjust_setting(1)
        self.assertEqual(self.app.settings["mascot_id"], "cute")

    def test_shop_migration_preserves_mascots_earned_by_old_score_rules(self) -> None:
        self.app.profile["shop_migrated"] = False
        self.app.profile["lifetime_score"] = 200000
        self.app.profile["unlocked_cosmetics"] = ["mascot.rhythm"]

        self.app._migrate_existing_unlocks_to_shop()

        self.assertIn("mascot.cute", self.app.profile["unlocked_cosmetics"])
        self.assertIn("mascot.sexy2", self.app.profile["unlocked_cosmetics"])
        self.assertTrue(self.app.profile["shop_migrated"])

    def test_combo_milestone_triggers_mascot_zoom_and_cutin(self) -> None:
        self.assertIn(150, COMBO_MILESTONES)
        chart = Chart(1, "z" * 64, Difficulty.NORMAL, 1, 8.0, notes=[Note(2.0, 2)])
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.session.combo = 150

        self.app._check_combo_milestone()

        self.assertEqual(self.app.combo_banner, "150 COMBO!")
        self.assertGreater(self.app.mascot_combo_zoom_until, 0.0)
        self.assertGreater(self.app.combo_cutin_until, 0.0)
        self.assertGreater(self.app._combo_zoom_progress(), 0.0)
        self.assertGreater(self.app._combo_cutin_progress(), 0.0)

    def test_combo_cutin_uses_milestone_specific_image_when_available(self) -> None:
        cutin_dir = Path(__file__).resolve().parents[1] / "assets" / "combo_cutin"
        cutin_dir.mkdir(parents=True, exist_ok=True)
        image_path = cutin_dir / "combo_150.png"
        image = pygame.Surface((80, 64), pygame.SRCALPHA)
        image.fill((255, 210, 90, 255))
        pygame.image.save(image, str(image_path))
        try:
            chart = Chart(1, "q" * 64, Difficulty.NORMAL, 1, 8.0, notes=[Note(2.0, 2)])
            self.app.chart = chart
            self.app.session = GameSession(chart, JudgmentWindows())
            self.app.session.combo = 150
            self.app._check_combo_milestone()
            self.assertEqual(self.app.combo_cutin_combo, 150)
            loaded = self.app._load_combo_cutin_media(150, 120, 120)
            self.assertIsNotNone(loaded)
            self.assertEqual(self.app._combo_cutin_media_path(150).name, "combo_150.png")
        finally:
            image_path.unlink(missing_ok=True)
            self.app.combo_cutin_media_cache.clear()

    def test_combo_cutin_uses_default_image_when_milestone_image_is_missing(self) -> None:
        cutin_dir = Path(__file__).resolve().parents[1] / "assets" / "combo_cutin"
        cutin_dir.mkdir(parents=True, exist_ok=True)
        image_path = cutin_dir / "default.png"
        image = pygame.Surface((80, 64), pygame.SRCALPHA)
        image.fill((100, 235, 157, 255))
        pygame.image.save(image, str(image_path))
        try:
            self.assertEqual(self.app._combo_cutin_media_path(200).name, "default.png")
        finally:
            image_path.unlink(missing_ok=True)
            self.app.combo_cutin_media_cache.clear()

    def test_combo_cutin_stays_outside_note_field(self) -> None:
        chart = Chart(1, "x" * 64, Difficulty.NORMAL, 1, 8.0, notes=[Note(2.0, 2)])
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
        self.app.session.combo = 150
        self.app._check_combo_milestone()
        left, field_width, _lane_width, field_top, line_y = self.app._game_field_geometry()
        note_field = pygame.Rect(left, field_top, field_width, line_y - field_top)
        before = self.app.surface.subsurface(note_field).copy()

        self.app._draw_combo_cutin(left, field_width, line_y)

        after = self.app.surface.subsurface(note_field).copy()
        self.assertEqual(pygame.image.tostring(before, "RGBA"), pygame.image.tostring(after, "RGBA"))

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

        self.assertIn("rhythm", self.app.mascot_image_cache)
        self.assertIsNotNone(self.app.mascot_image_cache["rhythm"])
        self.assertTrue(self.app.mascot_scaled_cache)


if __name__ == "__main__":
    unittest.main()
