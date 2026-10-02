from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from chart_generator import ChartGenerator
from models import AnalysisResult, Chart, Difficulty, Judgment, Note, LANE_KEY_PRESETS
from rewards import reward_catalog, reward_progress
from persistence import purchase_unlock, record_play
from tutorial import TUTORIAL_STEPS, build_tutorial_chart, tutorial_steps


class TutorialTest(unittest.TestCase):
    def test_optional_courses_accept_all_inputs_without_profile_changes(self) -> None:
        for count in (3, 5, 7):
            for index in (5, 6, 7):
                with self.subTest(lanes=count, course=index):
                    self.app.profile["unlocked_features"] = ["lane.3", "lane.5", "lane.7"]
                    self.app.settings["lane_count"] = count
                    before = deepcopy(self.app.profile)
                    self.app.start_tutorial_step(index)
                    self.assertTrue(self.app.chart.metadata["tutorial_optional"])
                    self.app.countdown_started_at = time.perf_counter() - 4
                    self.app.update_game()
                    events = []
                    for note in self.app.chart.notes:
                        events.append((note.time, pygame.KEYDOWN, note.lane))
                        events.append((note.end_time or note.time + 0.03, pygame.KEYUP, note.lane))
                    for at, kind, lane in sorted(events):
                        event = pygame.event.Event(kind, key=pygame.key.key_code(LANE_KEY_PRESETS[count][lane]))
                        with patch.object(self.app, "gameplay_time", return_value=at):
                            if kind == pygame.KEYDOWN:
                                self.app.key_event(event)
                            else:
                                self.app.key_up_event(event)
                    self.assertEqual(self.app.session.result().judgments["PERFECT"], len(self.app.chart.notes))
                    self.app.finish_game()
                    self.assertEqual(self.app.screen, "tutorial_result")
                    self.assertEqual(self.app.profile, before)
                    self.app.draw()
                    self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
                    self.assertEqual(self.app.tutorial_step_index, index)
                    self.assertEqual(self.app.screen, "game")
                    self.app.return_to_song_select()
                    self.assertEqual(self.app.screen, "tutorial")

    def test_optional_menu_buttons_do_not_overlap(self) -> None:
        self.app.screen = "tutorial"
        self.app.draw()
        self.assertEqual(len(self.app.buttons), 5)
        for i, (rect, _) in enumerate(self.app.buttons):
            self.assertTrue(pygame.Rect((0, 0), self.app.size).contains(rect))
            self.assertFalse(any(rect.colliderect(other) for other, _ in self.app.buttons[i+1:]))
        self.app.buttons[0][1]()
        self.assertEqual(self.app.tutorial_step_index, 5)
        self.app.buttons[2][1]()
        self.assertEqual(self.app.tutorial_step_index, 7)

    def test_dense_single_taps_have_no_chords_or_holds(self) -> None:
        for count in (3, 5, 7):
            chart = build_tutorial_chart(7, count)
            self.assertEqual(len(chart.notes), 64)
            self.assertTrue(all(note.end_time is None for note in chart.notes))
            self.assertEqual({note.lane for note in chart.notes}, set(range(count)))
            self.assertTrue(all(b.time - a.time == 0.25 for a, b in zip(chart.notes, chart.notes[1:])))
            self.assertEqual(chart.song_duration, 19.75)

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("AUTOBEAT_DATA_DIR")
        self.previous_demo_dir = os.environ.get("AUTOBEAT_DEMO_SONGS_DIR")
        os.environ["AUTOBEAT_DATA_DIR"] = str(Path(self.directory.name) / "data")
        os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = str(Path(self.directory.name) / "demo_songs")
        self.app = AutoBeatApp()

    def tearDown(self) -> None:
        pygame.quit()
        if self.previous_data_dir is None:
            os.environ.pop("AUTOBEAT_DATA_DIR", None)
        else:
            os.environ["AUTOBEAT_DATA_DIR"] = self.previous_data_dir
        if self.previous_demo_dir is None:
            os.environ.pop("AUTOBEAT_DEMO_SONGS_DIR", None)
        else:
            os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = self.previous_demo_dir
        self.directory.cleanup()

    def test_fixed_tutorial_charts_are_sorted_and_cover_all_steps(self) -> None:
        self.assertEqual(len(TUTORIAL_STEPS), 5)
        for index, step in enumerate(TUTORIAL_STEPS):
            chart = build_tutorial_chart(index)
            self.assertTrue(chart.metadata["tutorial"])
            self.assertEqual(chart.metadata["tutorial_step"], index)
            self.assertEqual(chart.song_duration, step.duration)
            self.assertEqual(len(chart.notes), len(step.notes))
            self.assertEqual(chart.notes, sorted(chart.notes, key=lambda note: (note.time, note.lane, note.kind.value)))

    def test_tutorial_charts_follow_active_lane_count(self) -> None:
        for lane_count in (3, 5, 7):
            steps = tutorial_steps(lane_count)
            self.assertEqual(len(steps), 5)
            for index, step in enumerate(steps):
                chart = build_tutorial_chart(index, lane_count)
                self.assertEqual(chart.metadata["lane_count"], lane_count)
                self.assertEqual(chart.metadata["lane_mode"], f"{lane_count}lane")
                self.assertEqual(len(chart.notes), len(step.notes))
                self.assertTrue(all(0 <= note.lane < lane_count for note in chart.notes))
        self.assertTrue(any(note.lane == 6 for note in build_tutorial_chart(1, 7).notes))

    def test_chords_accept_key_events(self) -> None:
        for count, keys in ((3, (pygame.K_d, pygame.K_k)), (5, (pygame.K_f, pygame.K_j)), (7, (pygame.K_f, pygame.K_j))):
            with self.subTest(lanes=count):
                self.app.profile["unlocked_features"] = ["lane.3", "lane.5", "lane.7"]
                self.app.settings["lane_count"] = count
                self.app.start_tutorial_step(2)
                self.app.countdown_started_at = time.perf_counter() - 4.0
                self.app.update_game()
                self.assertEqual(len(self.app.chart.notes), 8)
                for at in (2.0, 3.0, 4.0, 5.0):
                    notes = [note for note in self.app.chart.notes if note.time == at]
                    self.assertEqual(len({note.lane for note in notes}), 2)
                    with patch.object(self.app, "gameplay_time", return_value=at):
                        for key in keys:
                            self.app.key_event(pygame.event.Event(pygame.KEYDOWN, key=key))
                        for key in keys:
                            self.app.key_up_event(pygame.event.Event(pygame.KEYUP, key=key))
                self.assertEqual(self.app.session.result().judgments["PERFECT"], 8)
                self.assertEqual(self.app.session.result().judgments["MISS"], 0)

    def test_app_starts_tutorial_with_selected_lane_count(self) -> None:
        self.app.profile["unlocked_features"] = ["lane.3", "lane.5"]
        self.app.settings["lane_count"] = 3
        self.app.start_tutorial_step(1)
        self.assertEqual(self.app.chart.metadata["lane_count"], 3)
        self.assertTrue(all(0 <= note.lane < 3 for note in self.app.chart.notes))

    def test_tutorial_start_draws_and_reaches_result_without_music_file(self) -> None:
        self.app.screen = "tutorial"
        self.app.draw()
        self.assertGreater(len(self.app.buttons), 0)

        self.app.start_tutorial_step(0)
        self.assertEqual(self.app.screen, "game")
        self.assertTrue(self.app.tutorial_active)
        self.assertIsNotNone(self.app.session)
        self.assertTrue(self.app.countdown_active)

        self.app.countdown_started_at = time.perf_counter() - 4.0
        self.app.update_game()
        self.assertIsNotNone(self.app.tutorial_started_at)

        self.app.tutorial_started_at = time.perf_counter() - self.app.chart.song_duration - 0.1
        self.app.update_game()
        self.assertEqual(self.app.screen, "tutorial_result")

    def test_last_tutorial_step_marks_profile_complete(self) -> None:
        final_step = len(TUTORIAL_STEPS) - 1
        self.app.start_tutorial_step(final_step)
        self.app.countdown_started_at = time.perf_counter() - 4.0
        self.app.update_game()
        self.app.tutorial_started_at = time.perf_counter() - self.app.chart.song_duration - 0.1
        self.app.update_game()
        self.assertTrue(self.app.profile["tutorial_completed"])
        self.assertIn("sfx.crystal", self.app.profile["unlocked_cosmetics"])
        self.assertIn("background.image", self.app.profile["unlocked_cosmetics"])
        self.assertIn("note_theme.neon", self.app.profile["unlocked_cosmetics"])
        self.assertIn("sfx.crystal", self.app.newly_unlocked)
        self.assertEqual(self.app.screen, "tutorial_result")
        self.app.draw()

    def test_demo_song_folder_lists_only_supported_audio_files(self) -> None:
        (self.app.paths.demo_songs / "beta.ogg").write_bytes(b"not-an-audio-file")
        (self.app.paths.demo_songs / "alpha.wav").write_bytes(b"not-an-audio-file")
        (self.app.paths.demo_songs / "README.txt").write_text("ignore", encoding="utf-8")
        self.assertEqual([path.name for path in self.app.demo_song_files()], ["alpha.wav", "beta.ogg"])
        self.app.screen = "select"
        self.app.draw()

    def test_zero_score_reward_is_unlocked_without_a_play_record(self) -> None:
        image_path = self.app.paths.rewards / "trial_welcome.png"
        image = pygame.Surface((16, 16), pygame.SRCALPHA)
        image.fill((80, 220, 160, 255))
        pygame.image.save(image, str(image_path))
        (self.app.paths.rewards / "reward_config.json").write_text(
            '{"trial_welcome.png": {"required_score": 0}}', encoding="utf-8"
        )
        reward = next(item for item in self.app.gallery_rewards() if item.name == "trial_welcome.png")
        self.assertTrue(reward.unlocked)

    def test_judgment_feedback_expires_and_new_hits_replace_it(self) -> None:
        with patch("app.time.perf_counter", return_value=100.0):
            self.app._play_feedback(Judgment.GOOD, lane=2)
        self.assertIsNotNone(self.app.judgment_feedback)
        self.assertEqual(self.app.judgment_feedback.judgment, Judgment.GOOD)

        with patch("app.time.perf_counter", return_value=100.25):
            self.app._play_feedback(Judgment.PERFECT, lane=2)
        self.assertIsNotNone(self.app.judgment_feedback)
        self.assertEqual(self.app.judgment_feedback.judgment, Judgment.PERFECT)

        with patch("app.time.perf_counter", return_value=100.25 + self.app.judgment_feedback.duration + 0.01):
            self.app._draw_judgment_feedback()
        self.assertIsNone(self.app.judgment_feedback)

    def test_reward_manager_lists_missing_images_and_scrolls_many_rewards(self) -> None:
        config: dict[str, dict[str, int]] = {}
        for index in range(8):
            name = f"reward_{index + 1:03d}.png"
            config[name] = {"required_score": (index + 1) * 100000}
            if index < 7:
                image = pygame.Surface((16, 16), pygame.SRCALPHA)
                image.fill((40 + index * 20, 150, 220, 255))
                pygame.image.save(image, str(self.app.paths.rewards / name))
        (self.app.paths.rewards / "reward_config.json").write_text(json.dumps(config), encoding="utf-8")
        self.app.profile["unlocked_rewards"] = ["reward_001.png", "reward_002.png"]

        catalog = reward_catalog(self.app.paths, self.app.profile)
        self.assertEqual(len(catalog), 8)
        self.assertTrue(catalog[0].unlocked)
        self.assertFalse(catalog[-1].exists)

        self.app.open_reward_manager()
        self.assertEqual(self.app.screen, "reward_manager")
        self.app.scroll_reward_manager(20)
        self.assertEqual(self.app.reward_manager_scroll_index, 2)
        self.assertGreaterEqual(self.app.reward_manager_selected_index, 2)
        self.app.draw()

    def test_locked_reward_folder_hidden_attribute_runs_without_console_window(self) -> None:
        from unittest.mock import patch
        import persistence

        locked = self.app.paths.rewards / "locked"
        locked.mkdir(parents=True, exist_ok=True)
        persistence._HIDDEN_LOCKED_REWARD_PATHS.clear()
        with patch("persistence.os.name", "nt"), patch("persistence.subprocess.run") as run:
            persistence.set_locked_rewards_hidden(self.app.paths)
            persistence.set_locked_rewards_hidden(self.app.paths)

        self.assertEqual(run.call_count, 1)
        kwargs = run.call_args.kwargs
        self.assertIs(kwargs["stdin"], persistence.subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], persistence.subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], persistence.subprocess.DEVNULL)
        self.assertIn("creationflags", kwargs)

    def test_locked_reward_is_materialized_after_shop_purchase(self) -> None:
        locked = self.app.paths.rewards / "locked"
        unlocked = self.app.paths.rewards / "unlocked"
        locked.mkdir(parents=True, exist_ok=True)
        image = pygame.Surface((16, 16), pygame.SRCALPHA)
        image.fill((180, 80, 220, 255))
        pygame.image.save(image, str(locked / "secret_reward.png"))
        (self.app.paths.rewards / "reward_config.json").write_text(
            '{"secret_reward.png": {"required_score": 1000}}', encoding="utf-8"
        )

        self.app.profile["wallet_initialized"] = True
        self.app.profile["wallet_score"] = 1000
        reward = next(item for item in self.app.gallery_rewards() if item.name == "secret_reward.png")
        self.assertFalse(reward.unlocked)
        self.assertEqual(reward.path, locked / "secret_reward.png")
        self.assertFalse((unlocked / "secret_reward.png").exists())

        self.assertTrue(purchase_unlock(self.app.paths, self.app.profile, "reward.secret_reward.png", 1000))
        self.assertEqual(self.app.profile["wallet_score"], 0)
        self.assertTrue((unlocked / "secret_reward.png").is_file())
        reward = next(item for item in self.app.gallery_rewards() if item.name == "secret_reward.png")
        self.assertTrue(reward.unlocked)
        self.assertEqual(reward.path, unlocked / "secret_reward.png")

    def test_reward_scan_does_not_rematerialize_already_unlocked_files_each_frame(self) -> None:
        from unittest.mock import patch
        import rewards

        unlocked = self.app.paths.rewards / "unlocked"
        unlocked.mkdir(parents=True, exist_ok=True)
        image = pygame.Surface((20, 20), pygame.SRCALPHA)
        pygame.image.save(image, str(unlocked / "already.png"))
        (self.app.paths.rewards / "reward_config.json").write_text(
            '{"already.png": {"required_score": 0}}', encoding="utf-8"
        )

        with patch("rewards.materialize_unlocked_rewards") as materialize:
            first = rewards.scan_rewards(self.app.paths, {"already.png"}, lifetime_score=0)
            second = rewards.reward_progress(self.app.paths, {"lifetime_score": 0, "unlocked_rewards": ["already.png"]})

        self.assertTrue(first[0].unlocked)
        self.assertEqual(second.unlocked_count, 1)
        materialize.assert_not_called()

    def test_reward_progress_uses_wallet_and_ignores_missing_images(self) -> None:
        for name, color in (("score_100.png", (80, 220, 160, 255)), ("score_300.png", (90, 170, 255, 255))):
            image = pygame.Surface((16, 16), pygame.SRCALPHA)
            image.fill(color)
            pygame.image.save(image, str(self.app.paths.rewards / name))
        (self.app.paths.rewards / "reward_config.json").write_text(
            json.dumps(
                {
                    "score_100.png": {"required_score": 100000},
                    "score_300.png": {"required_score": 300000},
                    "missing_image.png": {"required_score": 200000},
                }
            ),
            encoding="utf-8",
        )

        self.app.profile["wallet_initialized"] = True
        self.app.profile["wallet_score"] = 75000
        status = reward_progress(self.app.paths, self.app.profile)
        self.assertEqual(status.reward_count, 2)
        self.assertEqual(status.unlocked_count, 0)
        self.assertEqual(status.next_reward.name if status.next_reward else None, "score_100.png")
        self.assertEqual(status.remaining_score, 25000)
        self.assertAlmostEqual(status.progress_ratio, 0.75)

        self.app.profile["wallet_score"] = 100000
        status = reward_progress(self.app.paths, self.app.profile)
        self.assertEqual(status.unlocked_count, 0)
        self.assertTrue(purchase_unlock(self.app.paths, self.app.profile, "reward.score_100.png", 100000))
        status = reward_progress(self.app.paths, self.app.profile)
        self.assertEqual(status.unlocked_count, 1)
        self.assertEqual(status.next_reward.name if status.next_reward else None, "score_300.png")
        self.assertEqual(status.remaining_score, 300000)
        self.assertTrue(next(item for item in self.app.gallery_rewards() if item.name == "score_100.png").unlocked)

    def test_bundled_demo_cache_opens_without_first_time_analysis(self) -> None:
        demo = self.app.paths.demo_songs / "trial.wav"
        demo.write_bytes(b"demo audio bytes")
        digest = "d" * 64
        analysis = AnalysisResult(
            music_hash=digest,
            source_path=str(demo),
            duration=4.0,
            sample_rate=22050,
            bpm=120.0,
            beats=[0.0, 0.5, 1.0, 1.5],
            onsets=[1.0],
            onset_strengths=[1.0],
            band_energy=[[0.2, 0.2, 0.2, 0.2, 0.2]],
            percussive_strengths=[1.0],
            sustained_segments=[],
        )
        cache = self.app.paths.demo_songs / "cache" / f"{digest}.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(analysis.to_dict()), encoding="utf-8")
        chart = Chart(1, digest, Difficulty.BEGINNER, 0, 4.0, notes=[Note(1.0, 2)], generator_version=ChartGenerator.VERSION)
        chart_path = self.app.paths.demo_songs / "charts" / digest / "beginner.json"
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        chart_path.write_text(json.dumps(chart.to_dict()), encoding="utf-8")

        with patch("app.music_hash", return_value=digest):
            self.app.load_demo_song(demo)
            self.assertEqual(self.app.screen, "difficulty")
            self.assertEqual(self.app.message, "体験版の同梱キャッシュを読み込みました。")
            self.app.select_chart(Difficulty.BEGINNER)
        self.assertEqual(self.app.screen, "chart_summary")
        self.assertIsNotNone(self.app.chart)
        self.assertEqual(len(self.app.chart.notes), 1)
        self.assertTrue(self.app.message.startswith("体験版の同梱BEGINNER譜面"))


if __name__ == "__main__":
    unittest.main()
