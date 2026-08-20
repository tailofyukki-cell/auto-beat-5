from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pygame
from app import AutoBeatApp
from chart_generator import ChartGenerator
from models import AnalysisResult, Chart, Difficulty, Note
from rewards import reward_progress
from tutorial import TUTORIAL_STEPS, build_tutorial_chart


class TutorialTest(unittest.TestCase):
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
        self.assertEqual(len(TUTORIAL_STEPS), 4)
        for index, step in enumerate(TUTORIAL_STEPS):
            chart = build_tutorial_chart(index)
            self.assertTrue(chart.metadata["tutorial"])
            self.assertEqual(chart.metadata["tutorial_step"], index)
            self.assertEqual(chart.song_duration, step.duration)
            self.assertEqual(len(chart.notes), len(step.notes))
            self.assertEqual(chart.notes, sorted(chart.notes, key=lambda note: (note.time, note.lane, note.kind.value)))

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
        self.assertEqual(self.app.screen, "tutorial_result")

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

    def test_reward_progress_unlocks_by_lifetime_score_and_ignores_missing_images(self) -> None:
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

        self.app.profile["lifetime_score"] = 75000
        status = reward_progress(self.app.paths, self.app.profile)
        self.assertEqual(status.reward_count, 2)
        self.assertEqual(status.unlocked_count, 0)
        self.assertEqual(status.next_reward.name if status.next_reward else None, "score_100.png")
        self.assertEqual(status.remaining_score, 25000)
        self.assertAlmostEqual(status.progress_ratio, 0.75)

        self.app.profile["lifetime_score"] = 100000
        status = reward_progress(self.app.paths, self.app.profile)
        self.assertEqual(status.unlocked_count, 1)
        self.assertEqual(status.next_reward.name if status.next_reward else None, "score_300.png")
        self.assertEqual(status.remaining_score, 200000)
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
