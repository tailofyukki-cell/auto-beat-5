from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from chart_generator import ChartGenerator
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Note
from persistence import load_settings, save_chart


class UiWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()

    def test_gallery_preview_draws_unlocked_external_image(self) -> None:
        image_path = self.app.paths.rewards / "reward_001.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image = pygame.Surface((64, 48), pygame.SRCALPHA)
        image.fill((80, 220, 160, 255))
        pygame.image.save(image, str(image_path))
        (self.app.paths.rewards / "reward_config.json").write_text(
            '{"reward_001.png": {"required_score": 100}}', encoding="utf-8"
        )
        self.app.profile["unlocked_rewards"] = ["reward_001.png"]
        reward = self.app.gallery_rewards()[0]
        self.app.open_reward(reward)
        self.assertEqual(self.app.screen, "gallery_preview")
        self.app.draw()

    def test_settings_adjusts_audio_and_judgment_values(self) -> None:
        self.assertEqual(self.app.settings["note_speed"], 625.0)
        original_volume = self.app.settings["music_volume"]
        self.app.settings_selection = 0
        self.app.adjust_setting(1)
        self.assertGreater(self.app.settings["music_volume"], original_volume)
        self.app.settings_selection = 7
        original_good = self.app.settings["judgment_windows_ms"]["good"]
        self.app.adjust_setting(1)
        self.assertGreater(self.app.settings["judgment_windows_ms"]["good"], original_good)
        self.app.screen = "settings"
        self.app.draw()

    def test_note_theme_cycles_persists_and_settings_screen_draws(self) -> None:
        self.assertEqual(self.app.note_theme_key, "standard")
        self.app.settings_selection = 8
        self.app.adjust_setting(1)
        self.assertEqual(self.app.note_theme_key, "neon")
        self.assertEqual(self.app.note_theme_label, "NEON")
        self.assertEqual(self.app.lane_colors[0], (0, 236, 255))
        self.app.persist_settings()
        self.assertEqual(load_settings(self.app.paths)["note_theme"], "neon")
        self.app.screen = "settings"
        self.app.draw()

    def test_tall_focus_increases_lookahead_and_persists(self) -> None:
        _left, standard_width, _lane_width, standard_top, standard_line = self.app._game_field_geometry()
        standard_time = (standard_line - standard_top) / self.app.effective_note_speed
        self.app.settings_selection = 3
        self.app.adjust_setting(1)
        self.assertEqual(self.app.playfield_mode_key, "tall")
        _left, tall_width, _lane_width, tall_top, tall_line = self.app._game_field_geometry()
        tall_time = (tall_line - tall_top) / self.app.effective_note_speed
        self.assertEqual(tall_width, standard_width)
        self.assertLess(tall_top, standard_top)
        self.assertGreater(tall_line, standard_line)
        self.assertGreaterEqual(tall_time, standard_time * 1.28)
        self.app.persist_settings()
        self.assertEqual(load_settings(self.app.paths)["playfield_mode"], "tall")

    def test_combo_milestone_sets_banner(self) -> None:
        chart = Chart(1, "u" * 64, Difficulty.NORMAL, 1, 2.0, notes=[Note(1.0, 0)])
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.session.combo = 50
        self.app._check_combo_milestone()
        self.assertEqual(self.app.combo_banner, "50 COMBO!")
        self.assertGreater(self.app.combo_banner_until, 0)

    def test_playfield_uses_most_of_current_window_height(self) -> None:
        _left, _field_width, _lane_width, field_top, judgment_y = self.app._game_field_geometry()
        _width, height = self.app.size
        self.assertLessEqual(field_top, int(height * 0.03))
        self.assertGreaterEqual(height - judgment_y, 74)
        self.assertGreaterEqual(judgment_y - field_top, int(height * 0.86))
        # 1280×720時の旧フィールド高525pxより広く、解像度は変更しない。
        self.assertGreater(judgment_y - field_top, 525)

    def test_old_easy_cache_is_regenerated_without_chords(self) -> None:
        analysis = AnalysisResult(
            music_hash="c" * 64,
            source_path="fixture.wav",
            duration=4.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5],
            onsets=[0.5, 1.0, 1.5, 2.0],
            onset_strengths=[0.9, 0.8, 0.95, 0.85],
            band_energy=[[0.65, 0.1, 0.1, 0.5, 0.45]] * 4,
            percussive_strengths=[0.7, 0.4, 0.8, 0.5],
            sustained_segments=[],
        )
        old_chart = Chart(
            1, analysis.music_hash, Difficulty.EASY, 1, analysis.duration,
            notes=[Note(1.0, 0), Note(1.0, 4)], generator_version="1.1",
        )
        save_chart(self.app.paths, old_chart)
        self.app.analysis = analysis
        self.app.song_path = Path(analysis.source_path)
        self.app.audio_available = False
        self.app.select_chart(Difficulty.EASY)
        self.assertEqual(self.app.chart.generator_version, ChartGenerator.VERSION)
        grouped: dict[float, list[Note]] = {}
        for note in self.app.chart.notes:
            grouped.setdefault(round(note.time, 4), []).append(note)
        self.assertTrue(all(len(notes) == 1 for notes in grouped.values()))


if __name__ == "__main__":
    unittest.main()
