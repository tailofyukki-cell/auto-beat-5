from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp, BG, NOTE_SKINS, RESOLUTION_PRESETS, SFX_THEMES, TRIAL_PLAY_LIMIT_SECONDS
from chart_generator import ChartGenerator
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Judgment, Note
from persistence import load_settings, save_chart


class UiWorkflowTest(unittest.TestCase):
    def test_media_labels_hide_only_final_extension(self) -> None:
        path = Path(self.directory.name) / "楽曲.ver2.WAV"
        path.write_bytes(b"fixture")
        self.app.profile["recent_songs"] = [{"source_path": str(path), "music_hash": "x" * 64, "bpm": 120, "duration": 10}]
        self.app.open_playlist("normal")
        self.app.text = Mock(wraps=self.app.text)
        self.app.draw()
        displayed = [str(call.args[0]) for call in self.app.text.call_args_list]
        self.assertIn("楽曲.ver2", displayed)
        self.assertNotIn(path.name, displayed)
        self.assertEqual(self.app.profile["recent_songs"][0]["source_path"], str(path))
        self.assertTrue(path.is_file())
        self.app.settings["background_image"] = str(Path(self.directory.name) / "背景.ver2.PNG")
        self.assertEqual(self.app.background_image_label(), "背景.ver2")
        self.assertTrue(self.app.settings["background_image"].endswith(".PNG"))
        self.assertEqual(self.app._unlocked_notification_label("ご褒美.ver2.png"), "ご褒美.ver2")

    def test_playlist_long_labels_fit_allocated_width(self) -> None:
        for font, width in (("body", 236), ("body", 700), ("small", 300)):
            label = self.app._playlist_label("長い曲名とフォルダ名" * 30, font, width)
            self.assertTrue(label.endswith("..."))
            self.assertLessEqual(self.app.fonts[font].size(label)[0], width)
        self.assertEqual(self.app._playlist_label("short", "body", 236), "short")

    def test_playlist_decoration_is_local_and_controls_fit_small_display(self) -> None:
        self.app.display_surface = pygame.display.set_mode((960, 540))
        self.app.surface = self.app._create_render_surface((960, 540))
        self.app._draw_playlist_stage = Mock(wraps=self.app._draw_playlist_stage)
        self.app.open_playlist("normal")
        self.app.message = "フォルダを開きました"
        self.app.draw()
        self.app._draw_playlist_stage.assert_called_once()
        for rect, action in self.app.buttons:
            self.assertTrue(self.app.surface.get_rect().contains(rect))
        self.app.set_screen("settings")
        self.app.draw()
        self.app._draw_playlist_stage.assert_called_once()

    def test_play_screen_shows_pause_hint_outside_lanes(self) -> None:
        self.app.chart = Chart(1, "h" * 64, Difficulty.EASY, 1, 3.0, notes=[Note(1.0, 0)])
        self.app.session = GameSession(self.app.chart, JudgmentWindows())
        self.app.screen = "game"
        self.app.countdown_started_at = None
        self.app.text = Mock(wraps=self.app.text)
        for size in ((960, 540), (1600, 900)):
            self.app.display_surface = pygame.display.set_mode(size)
            self.app.surface = self.app._create_render_surface(size)
            for view in ("classic", "perspective"):
                self.app.settings["lane_view"] = view
                for lane_count in (3, 5, 7):
                    self.app.settings["lane_count"] = lane_count
                    self.app.text.reset_mock()
                    self.app.draw()
                    calls = [call for call in self.app.text.call_args_list if call.args[0] == "ESC：一時停止メニュー"]
                    self.assertEqual(len(calls), 1)
                    x, y = calls[0].kwargs["pos"]
                    w, h = self.app.fonts["small"].size(calls[0].args[0])
                    self.assertLess(x + w, self.app._game_field_geometry()[0])
                    self.assertLessEqual(y + h, self.app.size[1])

    def test_result_settings_button_fits_and_preserves_result(self) -> None:
        chart = Chart(1, "r" * 64, Difficulty.EASY, 1, 3.0, notes=[Note(1.0, 0)])
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        session = self.app.session
        for size in ((960, 540), (1280, 720), (1600, 900)):
            with self.subTest(size=size):
                self.app.display_surface = pygame.display.set_mode(size)
                self.app.surface = self.app._create_render_surface(size)
                self.app.screen = "result"
                self.app.draw()
                rect, action = next((r, a) for r, a in self.app.buttons if getattr(a, "__name__", "") == "open_result_settings")
                song_rect = next(r for r, a in self.app.buttons if getattr(a, "__name__", "") == "return_to_song_select")
                self.assertGreater(rect.left, song_rect.right)
                self.assertEqual(rect.top, song_rect.top)
                self.assertTrue(self.app.surface.get_rect().contains(rect))
                action()
                self.assertEqual(self.app.screen, "settings")
                self.assertIs(self.app.chart, chart)
                self.assertIs(self.app.session, session)
                self.app.draw()

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        self.directory.cleanup()


    def test_result_screen_draws_share_card_and_saves_png(self) -> None:
        chart = Chart(1, "r" * 64, Difficulty.HARD, 1, 3.0, notes=[Note(1.0, 0), Note(1.5, 2), Note(2.0, 4)])
        self.app.chart = chart
        self.app.song_path = Path("C:/Music/shareable_result.wav")
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.session.score = 54321
        self.app.session.max_combo = 120
        self.app.session.combo = 120
        self.app.session.judgment_counts[Judgment.PERFECT.value] = 3
        self.app.profile["last_play_badges"] = ["神業の演奏", "完璧な集中", "Combo Maker"]
        self.app.profile["last_play_ranking"] = {
            "chart_key": "r" * 64 + ":hard",
            "position": 1,
            "new_high_score": True,
            "score_delta": 54321,
            "made_top_ten": True,
        }
        image_path = self.app.paths.rewards / "result_reward.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image = pygame.Surface((80, 50), pygame.SRCALPHA)
        image.fill((120, 220, 255, 255))
        pygame.image.save(image, str(image_path))
        (self.app.paths.rewards / "reward_config.json").write_text(
            '{"result_reward.png": {"required_score": 0}}', encoding="utf-8"
        )
        self.app.newly_unlocked = ["result_reward.png"]
        self.app.screen = "result"
        self.app.draw()
        self.app.save_result_screenshot()
        files = list((self.app.paths.root / "screenshots" / "results").glob("AutoBeat5_shareable_result_5lane_S+_*.png"))
        self.assertEqual(len(files), 1)

    def test_result_can_return_to_difficulty_for_same_song(self) -> None:
        analysis = AnalysisResult(
            music_hash="d" * 64,
            source_path="C:/Music/same_song.wav",
            duration=8.0,
            sample_rate=22050,
            bpm=128.0,
            beats=[0.0, 0.5, 1.0],
            onsets=[1.0],
            onset_strengths=[1.0],
            band_energy=[[0.2, 0.4, 0.8, 0.3, 0.2]],
            percussive_strengths=[0.8],
            sustained_segments=[],
        )
        self.app.analysis = analysis
        self.app.song_path = Path(analysis.source_path)
        self.app.chart = Chart(1, analysis.music_hash, Difficulty.HARD, 1, analysis.duration, notes=[Note(1.0, 2)])
        self.app.session = GameSession(self.app.chart, JudgmentWindows())
        self.app.screen = "result"
        self.app.audio.stop = Mock()

        self.app.draw()
        self.assertTrue(any(getattr(action, "__name__", "") == "return_to_difficulty" for _rect, action in self.app.buttons))
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))

        self.assertEqual(self.app.screen, "difficulty")
        self.assertEqual(self.app.selected_difficulty, list(Difficulty).index(Difficulty.HARD))
        self.assertIs(self.app.analysis, analysis)
        self.assertEqual(self.app.song_path, Path(analysis.source_path))
        self.assertIsNone(self.app.session)
        self.app.audio.stop.assert_called_once_with()
        self.app.draw()

    def test_shop_requires_confirmation_and_spends_wallet_once(self) -> None:
        self.app.profile["wallet_initialized"] = True
        self.app.profile["wallet_score"] = 150000
        self.app.open_shop()
        items = self.app.shop_items()
        self.app.shop_selected_index = next(index for index, item in enumerate(items) if item.item_id == "mascot.cute")
        self.app.draw()
        self.assertTrue(any(getattr(action, "__name__", "") == "activate_shop_purchase" for _rect, action in self.app.buttons))

        self.app.activate_shop_purchase()
        self.assertEqual(self.app.profile["wallet_score"], 150000)
        self.assertEqual(self.app.shop_confirmation_id, "mascot.cute")
        self.app.activate_shop_purchase()

        self.assertEqual(self.app.profile["wallet_score"], 50000)
        self.assertIn("mascot.cute", self.app.profile["unlocked_cosmetics"])
        self.assertFalse(self.app.activate_shop_purchase())
        self.assertEqual(self.app.profile["wallet_score"], 50000)

    def test_title_has_clickable_exit_button(self) -> None:
        self.app.screen = "title"
        self.app.draw()
        exit_action = next(action for _rect, action in self.app.buttons if getattr(action, "__name__", "") == "exit_app")
        exit_action()
        self.assertFalse(self.app.running)

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



    def test_game_draws_subtle_audio_visualizer_behind_lanes(self) -> None:
        analysis = AnalysisResult(
            music_hash="v" * 64,
            source_path="fixture.wav",
            duration=6.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0],
            onsets=[1.0],
            onset_strengths=[1.0],
            band_energy=[[0.2, 0.7, 0.4, 0.5, 0.3]],
            percussive_strengths=[0.8],
            sustained_segments=[],
        )
        self.app.analysis = analysis
        self.app.chart = Chart(1, analysis.music_hash, Difficulty.NORMAL, 1, analysis.duration, notes=[Note(2.0, 2)])
        self.app.session = GameSession(self.app.chart, JudgmentWindows())
        self.app.screen = "game"
        self.app.audio = type("Audio", (), {"time": 1.05, "paused": False})()
        left, _field_width, lane_width, field_top, _line_y = self.app._game_field_geometry()
        self.app.draw()
        width, height = self.app.size
        left_background_pixels = [
            self.app.surface.get_at((x, y))[:3]
            for x in range(12, max(13, left - 40), 28)
            for y in range(int(height * 0.22), int(height * 0.78), 28)
        ]
        right_background_pixels = [
            self.app.surface.get_at((x, y))[:3]
            for x in range(left + _field_width + 40, width - 12, 28)
            for y in range(int(height * 0.22), int(height * 0.78), 28)
        ]
        lane_sample = self.app.surface.get_at((left + lane_width // 2, field_top + 18))[:3]
        self.assertTrue(any(pixel != BG for pixel in left_background_pixels))
        self.assertTrue(any(pixel != BG for pixel in right_background_pixels))
        self.assertEqual(lane_sample, (18, 28, 48))

    def test_settings_draws_mascot_preview_for_selected_character(self) -> None:
        self.app.screen = "settings"
        self.app.settings_selection = 19
        self.app.draw()
        self.assertIn(self.app.selected_mascot.mascot_id, self.app.mascot_image_cache)

    def test_settings_marks_discrete_choice_rows(self) -> None:
        choice_rows = {2, 4, 5, 6, 8, 13, 14, 15, 16, 18, 19, 20, 21}
        for index in range(len(self.app._settings_rows())):
            self.assertEqual(self.app._setting_row_has_choices(index), index in choice_rows)
        self.app.screen = "settings"
        self.app.draw()

    def test_settings_key_config_stays_below_setting_rows(self) -> None:
        self.app.screen = "settings"
        self.app.settings["resolution"] = [1600, 900]
        self.app._apply_display_settings()
        self.app.draw()
        row_count = len(self.app._settings_rows())
        row_rects = [rect for rect, _action in self.app.buttons[:row_count]]
        key_rects = [rect for rect, _action in self.app.buttons[row_count:row_count + self.app.active_lane_count]]
        self.assertTrue(key_rects)
        self.assertGreater(min(rect.top for rect in key_rects), max(rect.bottom for rect in row_rects) + 8)

    def test_small_laptop_resolution_draws_core_flow(self) -> None:
        self.assertIn((960, 540), RESOLUTION_PRESETS)
        self.assertIn((1024, 576), RESOLUTION_PRESETS)
        self.app.settings["resolution"] = [960, 540]
        self.app._apply_display_settings()
        analysis = AnalysisResult(
            music_hash="s" * 64,
            source_path="small-screen.wav",
            duration=8.0,
            sample_rate=22050,
            bpm=128.0,
            beats=[0.0, 0.5, 1.0, 1.5, 2.0],
            onsets=[1.0, 1.5, 2.0],
            onset_strengths=[0.7, 0.8, 0.9],
            band_energy=[[0.2, 0.6, 0.4, 0.5, 0.3]],
            percussive_strengths=[0.8, 0.6, 0.7],
            sustained_segments=[],
        )
        self.app.analysis = analysis
        self.app.chart = Chart(1, analysis.music_hash, Difficulty.EASY, 1, analysis.duration, notes=[Note(2.0, 2)])
        self.app.session = GameSession(self.app.chart, JudgmentWindows())
        self.app.audio = type("Audio", (), {"time": 1.0, "paused": False})()
        self.assertEqual(self.app.display_size, (960, 540))
        self.assertEqual(self.app.size, (1280, 720))
        for screen in ("title", "select", "difficulty", "chart_summary", "shop", "settings", "game"):
            self.app.screen = screen
            self.app.draw()
        left, field_width, lane_width, field_top, line_y = self.app._game_field_geometry()
        self.assertGreaterEqual(left, 300)
        self.assertGreaterEqual(field_width, 620)
        self.assertGreaterEqual(lane_width, 120)
        self.assertLess(line_y, 720)
        self.assertLess(field_top, line_y)
        self.assertEqual(self.app._to_logical_point((480, 270)), (640, 360))

    def test_small_resolution_mouse_click_uses_scaled_coordinates(self) -> None:
        self.app.settings["resolution"] = [960, 540]
        self.app._apply_display_settings()
        called: list[bool] = []
        rect = pygame.Rect(640, 360, 120, 60)
        self.app.buttons = [(rect, lambda: called.append(True))]
        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(480, 270))
        for button_rect, action in self.app.buttons:
            if button_rect.collidepoint(self.app._to_logical_point(event.pos)):
                action()
        self.assertEqual(called, [True])
    def test_background_image_mode_draws_dimmed_custom_image(self) -> None:
        image_path = Path(self.directory.name) / "background.png"
        image = pygame.Surface((96, 54), pygame.SRCALPHA)
        image.fill((240, 40, 90, 255))
        pygame.image.save(image, str(image_path))
        self.app.settings["background_mode"] = "image"
        self.app.settings["background_image"] = str(image_path)
        self.app.settings["background_opacity"] = 0.35

        self.app._draw_game_background(1.0)

        sample = self.app.surface.get_at((16, 16))[:3]
        self.assertNotEqual(sample, BG)
        self.assertLess(sum(sample), 240 + 40 + 90)

    def test_background_settings_cycle_mode_and_opacity(self) -> None:
        self.app.profile["tutorial_completed"] = True
        self.app.profile["unlocked_cosmetics"].extend(["background.image", "background.off", "background.custom_image"])
        self.app.settings_selection = 6
        self.app.adjust_setting(1)
        self.assertEqual(self.app.background_mode_key, "image")
        self.app.settings_selection = 8
        original = self.app.background_opacity
        self.app.adjust_setting(1)
        self.assertGreater(self.app.background_opacity, original)

    def test_sfx_theme_cycles_rebuilds_and_previews_sound(self) -> None:
        self.app.profile["tutorial_completed"] = True
        self.app.profile["unlocked_cosmetics"].extend(["sfx.crystal", "sfx.arcade", "sfx.soft"])
        self.assertIn(self.app.sfx_theme_key, SFX_THEMES)
        self.assertEqual(self.app.sfx_theme_key, "classic")
        played: list[bool] = []
        self.app.preview_sfx_theme = lambda: played.append(True)  # type: ignore[method-assign]
        self.app.settings_selection = 2

        self.app.adjust_setting(1)

        self.assertEqual(self.app.sfx_theme_key, "crystal")
        self.assertEqual(self.app.sfx_theme_label, "CRYSTAL")
        self.assertTrue(played)
        self.assertTrue(self.app.feedback_sounds)


    def test_tutorial_locked_settings_block_theme_changes(self) -> None:
        self.assertFalse(self.app.profile["tutorial_completed"])

        self.app.settings_selection = 2
        self.app.adjust_setting(1)
        self.assertEqual(self.app.sfx_theme_key, "classic")
        self.assertIn("チュートリアル", self.app.message)

        self.app.settings_selection = 6
        self.app.adjust_setting(1)
        self.assertEqual(self.app.background_mode_key, "visualizer")

        self.app.settings_selection = 13
        self.app.adjust_setting(1)
        self.assertEqual(self.app.note_theme_key, "standard")
        self.app.screen = "settings"
        self.app.draw()

    def test_resolution_setting_cycles_through_small_presets(self) -> None:
        self.app.settings["resolution"] = [1280, 720]
        self.app.settings_selection = 16
        self.app.adjust_setting(-1)
        self.assertEqual(self.app.settings["resolution"], [1024, 576])
        self.app.adjust_setting(-1)
        self.assertEqual(self.app.settings["resolution"], [960, 540])
    def test_settings_adjusts_audio_and_judgment_values(self) -> None:
        self.assertEqual(self.app.settings["note_speed"], 625.0)
        original_volume = self.app.settings["music_volume"]
        self.app.settings_selection = 0
        self.app.adjust_setting(1)
        self.assertGreater(self.app.settings["music_volume"], original_volume)
        self.app.settings_selection = 12
        original_good = self.app.settings["judgment_windows_ms"]["good"]
        self.app.adjust_setting(1)
        self.assertGreater(self.app.settings["judgment_windows_ms"]["good"], original_good)
        self.app.screen = "settings"
        self.app.draw()

    def test_note_theme_cycles_persists_and_settings_screen_draws(self) -> None:
        self.app.profile["tutorial_completed"] = True
        self.app.profile["unlocked_cosmetics"].extend(["note_theme.neon", "note_theme.pastel", "note_theme.contrast"])
        self.assertEqual(self.app.note_theme_key, "standard")
        self.app.settings_selection = 13
        self.app.adjust_setting(1)
        self.assertEqual(self.app.note_theme_key, "neon")
        self.assertEqual(self.app.note_theme_label, "NEON")
        self.assertEqual(self.app.lane_colors[0], (0, 236, 255))
        self.app.persist_settings()
        self.assertEqual(load_settings(self.app.paths)["note_theme"], "neon")
        self.app.screen = "settings"
        self.app.draw()

    def test_note_skin_cycles_and_settings_preview_draws(self) -> None:
        self.app.profile["tutorial_completed"] = True
        self.assertIn("glow", NOTE_SKINS)
        self.assertEqual(self.app.note_skin_key, "standard")
        self.app.settings_selection = 14
        self.app.adjust_setting(1)
        self.assertEqual(self.app.note_skin_key, "glow")
        self.app.screen = "settings"
        self.app.settings_selection = 14
        self.app.draw()
        self.app.persist_settings()
        self.assertEqual(load_settings(self.app.paths)["note_skin"], "glow")

    def test_tall_focus_increases_lookahead_and_persists(self) -> None:
        _left, standard_width, _lane_width, standard_top, standard_line = self.app._game_field_geometry()
        standard_time = (standard_line - standard_top) / self.app.effective_note_speed
        self.app.settings_selection = 4
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

    def test_lane_view_cycles_and_draws_perspective_playfield(self) -> None:
        self.assertEqual(self.app.lane_view_key, "classic")
        _classic_left, classic_width, _classic_lane_width, _classic_top, _classic_line = self.app._game_field_geometry()
        self.app.settings_selection = 20
        self.app.adjust_setting(1)
        self.assertEqual(self.app.lane_view_key, "perspective")
        self.assertEqual(self.app.lane_view_label, "3D DEPTH")

        chart = Chart(1, "p" * 64, Difficulty.NORMAL, 1, 4.0, notes=[Note(2.0, 0), Note(2.4, 2), Note(2.8, 4)])
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.audio = type("Audio", (), {"time": 1.0, "paused": False})()
        self.app.screen = "game"
        left, field_width, lane_width, field_top, line_y = self.app._game_field_geometry()
        top_left, top_width, _ = self.app._perspective_lane_rect(0, field_top, left, field_width, lane_width, field_top, line_y)
        _mid_left, mid_width, mid_depth = self.app._perspective_lane_rect(0, (field_top + line_y) / 2, left, field_width, lane_width, field_top, line_y)
        bottom_left, bottom_width, bottom_depth = self.app._perspective_lane_rect(0, line_y, left, field_width, lane_width, field_top, line_y)
        _top_margin, top_height, top_alpha = self.app._perspective_note_metrics(top_width, 0.0)
        _mid_margin, mid_height, _mid_alpha = self.app._perspective_note_metrics(mid_width, mid_depth)
        _bottom_margin, bottom_height, bottom_alpha = self.app._perspective_note_metrics(bottom_width, bottom_depth)

        self.assertGreater(field_width, classic_width)
        self.assertLess(top_width, bottom_width)
        self.assertGreater(bottom_width, top_width * 5)
        self.assertEqual((top_height, mid_height, bottom_height), (18, 18, 18))
        self.assertEqual(bottom_alpha, top_alpha)
        self.assertGreater(top_left, left)
        self.assertAlmostEqual(mid_width - top_width, bottom_width - mid_width, delta=0.01)
        self.assertAlmostEqual(mid_height - top_height, bottom_height - mid_height, delta=1)
        top_bounds = self.app._perspective_note_vertical_bounds(field_top, top_height)
        mid_y = (field_top + line_y) / 2
        mid_bounds = self.app._perspective_note_vertical_bounds(mid_y, mid_height)
        bottom_bounds = self.app._perspective_note_vertical_bounds(line_y, bottom_height)
        self.assertAlmostEqual(top_bounds[1] - field_top, 9.0)
        self.assertAlmostEqual(mid_bounds[1] - mid_y, 9.0)
        self.assertAlmostEqual(bottom_bounds[1] - line_y, 9.0)
        first_y = self.app._note_timing_y(2.0, 1.0, line_y, 400.0)
        second_y = self.app._note_timing_y(2.0, 1.1, line_y, 400.0)
        third_y = self.app._note_timing_y(2.0, 1.2, line_y, 400.0)
        self.assertAlmostEqual(second_y - first_y, third_y - second_y)
        for lane in range(self.app.active_lane_count):
            centers = []
            for y in (line_y - 20, line_y, line_y + 20):
                x, w, depth = self.app._perspective_lane_rect(lane, y, left, field_width, lane_width, field_top, line_y)
                centers.append(x + w / 2)
                _, h, _ = self.app._perspective_note_metrics(w, depth)
                self.assertEqual(self.app._perspective_note_vertical_bounds(y, h), (y - 9, y + 9))
            self.assertAlmostEqual(centers[1] - centers[0], centers[2] - centers[1])
        self.app.draw()
        self.app.persist_settings()
        self.assertEqual(load_settings(self.app.paths)["lane_view"], "perspective")

    def test_chord_guides_only_join_notes_at_the_same_time(self) -> None:
        chart = Chart(
            1,
            "c" * 64,
            Difficulty.NORMAL,
            1,
            5.0,
            notes=[Note(2.0, 0), Note(2.0, 4), Note(2.02, 2)],
        )
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        left, field_width, lane_width, field_top, line_y = self.app._game_field_geometry()
        guides = self.app._visible_chord_guides(1.0, self.app.effective_note_speed, field_top, line_y)

        self.assertEqual(len(guides), 1)
        self.assertEqual(guides[0][1], (0, 4))
        self.app._draw_chord_guides(left, field_width, lane_width, field_top, line_y, 1.0, self.app.effective_note_speed, perspective=False)
        self.app._draw_chord_guides(left, field_width, lane_width, field_top, line_y, 1.0, self.app.effective_note_speed, perspective=True)

    def test_chord_guide_disappears_after_one_note_is_judged(self) -> None:
        chart = Chart(1, "j" * 64, Difficulty.NORMAL, 1, 5.0, notes=[Note(2.0, 0), Note(2.0, 4)])
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        _left, _field_width, _lane_width, field_top, line_y = self.app._game_field_geometry()
        self.app.session.states[0].judged = Judgment.PERFECT

        self.assertEqual(self.app._visible_chord_guides(1.0, self.app.effective_note_speed, field_top, line_y), [])

    def test_lane_count_starts_locked_and_unlocked_modes_change_game_field(self) -> None:
        self.assertEqual(self.app.active_lane_count, 5)
        _left, standard_width, standard_lane_width, _top, _line = self.app._game_field_geometry()
        self.app.settings_selection = 5
        self.app.adjust_setting(-1)
        self.assertEqual(self.app.active_lane_count, 5)
        self.assertIn("3 LANE", self.app.message)

        self.app.profile["unlocked_features"] = ["lane.3", "lane.5", "lane.7"]
        self.app.adjust_setting(-1)
        self.assertEqual(self.app.active_lane_count, 3)
        self.assertEqual(self.app.active_lane_keys, ["d", "space", "k"])
        _left, three_width, three_lane_width, _top, _line = self.app._game_field_geometry()
        self.assertLess(three_width, standard_width)
        self.assertGreaterEqual(three_lane_width, standard_lane_width)
        self.app.adjust_setting(-1)
        self.assertEqual(self.app.active_lane_count, 7)
        self.assertEqual(self.app.active_lane_keys, ["s", "d", "f", "space", "j", "k", "l"])

    def test_variable_lane_input_maps_to_existing_chart_lanes(self) -> None:
        chart = Chart(1, "v" * 64, Difficulty.NORMAL, 1, 3.0, notes=[Note(1.0, 4)])
        self.app.chart = chart
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.profile["unlocked_features"] = ["lane.3", "lane.5"]
        self.app.settings["lane_count"] = 3
        judgment = self.app._press_active_lane(2, 1.0)
        self.assertEqual(judgment, Judgment.PERFECT)
        self.assertEqual(self.app.session.judgment_counts[Judgment.PERFECT.value], 1)

    def test_result_screenshot_filename_includes_lane_mode(self) -> None:
        chart = Chart(1, "w" * 64, Difficulty.NORMAL, 1, 3.0, notes=[Note(1.0, 0)], metadata={"lane_count": 7})
        self.app.chart = chart
        self.app.song_path = Path("C:/Music/lane_result.wav")
        self.app.session = GameSession(chart, JudgmentWindows())
        self.app.screen = "result"
        self.app.draw()
        self.app.save_result_screenshot()
        files = list((self.app.paths.root / "screenshots" / "results").glob("AutoBeat5_lane_result_7lane_*.png"))
        self.assertEqual(len(files), 1)

    def test_full_combo_result_draws_special_media_from_assets(self) -> None:
        full_combo_dir = Path(__file__).resolve().parents[1] / "assets" / "full_combo"
        full_combo_dir.mkdir(parents=True, exist_ok=True)
        media_path = full_combo_dir / "test_full_combo.png"
        image = pygame.Surface((96, 72), pygame.SRCALPHA)
        image.fill((40, 240, 140, 255))
        pygame.draw.circle(image, (255, 240, 80, 255), (48, 36), 24)
        pygame.image.save(image, str(media_path))
        try:
            chart = Chart(1, "f" * 64, Difficulty.NORMAL, 1, 3.0, notes=[Note(1.0, 0)])
            self.app.chart = chart
            self.app.session = GameSession(chart, JudgmentWindows())
            self.app.session.judgment_counts[Judgment.PERFECT.value] = 1
            self.app.session.max_combo = 1
            self.app.session.combo = 1
            self.assertTrue(self.app._is_full_combo_result(self.app.session.result()))
            self.app.screen = "result"
            self.app.draw()
            self.assertTrue(self.app._load_full_combo_media_frames(120, 120))
        finally:
            media_path.unlink(missing_ok=True)
            self.app.full_combo_media_cache.clear()

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

    def test_library_scrolls_selects_and_draws_many_recent_songs(self) -> None:
        entries = [
            {
                "source_path": f"C:/Music/Library Song {index:02d}.wav",
                "music_hash": f"{index:064x}",
                "bpm": 120.0 + index,
                "duration": 90.0 + index,
            }
            for index in range(14)
        ]
        self.app.profile["recent_songs"] = entries
        self.app.open_library()
        self.assertEqual(self.app.screen, "library")
        self.assertEqual(self.app.library_scroll_index, 0)
        self.assertEqual(self.app.library_selected_index, 0)

        self.app.scroll_library(99)
        self.assertEqual(self.app.library_scroll_index, 8)
        self.assertEqual(self.app.library_selected_index, 8)
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_END))
        self.assertEqual(self.app.library_selected_index, 13)
        self.assertEqual(self.app.library_scroll_index, 8)
        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_HOME))
        self.assertEqual(self.app.library_selected_index, 0)
        self.assertEqual(self.app.library_scroll_index, 0)
        self.app.draw()

        selected: list[dict[str, object]] = []
        self.app.load_recent_song = lambda entry: selected.append(entry)  # type: ignore[method-assign]
        self.app.select_library_entry(11)
        self.assertEqual(selected, [entries[11]])

    def test_trial_play_starts_from_chart_summary_button_only_and_draws_result(self) -> None:
        analysis = AnalysisResult(
            music_hash="t" * 64,
            source_path="trial.wav",
            duration=90.0,
            sample_rate=22050,
            bpm=128.0,
            beats=[0.0, 0.5, 1.0],
            onsets=[1.0],
            onset_strengths=[0.8],
            band_energy=[[0.2, 0.6, 0.4, 0.5, 0.3]],
            percussive_strengths=[0.8],
            sustained_segments=[],
        )
        self.app.analysis = analysis
        self.app.chart = Chart(1, analysis.music_hash, Difficulty.EASY, 1, analysis.duration, notes=[Note(2.0, 2)])
        self.app.song_path = Path("trial.wav")
        self.app.audio.load = Mock()
        self.app.audio.play = Mock()
        self.app.audio.stop = Mock()
        self.app.screen = "chart_summary"
        self.app.draw()
        actions = [action for _rect, action in self.app.buttons]
        self.assertIn(self.app.start_trial_game, actions)

        self.app.key_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN}))
        self.assertFalse(self.app.trial_active)

        self.app.set_screen("chart_summary")
        self.app.start_trial_game()
        self.assertTrue(self.app.trial_active)
        self.assertEqual(self.app.trial_end_time, TRIAL_PLAY_LIMIT_SECONDS)
        self.app.finish_game()
        self.assertEqual(self.app.screen, "trial_result")
        self.assertEqual(self.app.profile.get("play_history", []), [])
        self.app.draw()

    def test_trial_play_fades_out_and_ends_after_one_minute_for_long_songs(self) -> None:
        class FakeAudio:
            def __init__(self) -> None:
                self.time = 0.0
                self.paused = False
                self.finished = False
                self.volumes: list[float] = []
                self.stopped = False

            def load(self, *_args) -> None:
                pass

            def play(self, *_args) -> None:
                pass

            def set_volume(self, volume: float) -> None:
                self.volumes.append(volume)

            def stop(self) -> None:
                self.stopped = True

        analysis = AnalysisResult(
            music_hash="f" * 64,
            source_path="trial-long.wav",
            duration=90.0,
            sample_rate=22050,
            bpm=128.0,
            beats=[],
            onsets=[],
            onset_strengths=[],
            band_energy=[],
            percussive_strengths=[],
            sustained_segments=[],
        )
        self.app.analysis = analysis
        self.app.chart = Chart(1, analysis.music_hash, Difficulty.NORMAL, 1, analysis.duration, notes=[Note(2.0, 2)])
        self.app.song_path = Path("trial-long.wav")
        fake_audio = FakeAudio()
        self.app.audio = fake_audio
        self.app.start_trial_game()
        self.app.countdown_started_at = None

        fake_audio.time = TRIAL_PLAY_LIMIT_SECONDS - 1.0
        self.app.update_game()
        self.assertTrue(fake_audio.volumes)
        self.assertAlmostEqual(fake_audio.volumes[-1], float(self.app.settings["music_volume"]) * 0.5)
        self.assertTrue(self.app.trial_fade_started)

        fake_audio.time = TRIAL_PLAY_LIMIT_SECONDS
        self.app.update_game()
        self.assertTrue(fake_audio.stopped)
        self.assertEqual(self.app.screen, "trial_result")
        self.assertEqual(self.app.profile.get("play_history", []), [])

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
