from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from persistence import AppPaths, load_profile, purchase_unlock, record_play


class ShopPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.previous_data_dir = os.environ.get("AUTOBEAT_DATA_DIR")
        os.environ["AUTOBEAT_DATA_DIR"] = self.directory.name
        self.paths = AppPaths.discover()
        self.paths.ensure()

    def tearDown(self) -> None:
        if self.previous_data_dir is None:
            os.environ.pop("AUTOBEAT_DATA_DIR", None)
        else:
            os.environ["AUTOBEAT_DATA_DIR"] = self.previous_data_dir
        self.directory.cleanup()

    def test_existing_lifetime_score_migrates_to_wallet_once(self) -> None:
        self.paths.profile.write_text(json.dumps({"lifetime_score": 123456}), encoding="utf-8")
        profile = load_profile(self.paths)
        self.assertEqual(profile["wallet_score"], 123456)
        self.assertTrue(profile["wallet_initialized"])

        profile["wallet_score"] = 23456
        profile["lifetime_score"] = 200000
        from persistence import save_profile

        save_profile(self.paths, profile)
        restored = load_profile(self.paths)
        self.assertEqual(restored["wallet_score"], 23456)

    def test_normal_play_adds_score_to_lifetime_and_wallet(self) -> None:
        profile = load_profile(self.paths)
        result = {
            "score": 4321,
            "accuracy": 90.0,
            "max_combo": 20,
            "rank": "B",
            "judgments": {"PERFECT": 10, "GREAT": 2, "GOOD": 1, "MISS": 0},
        }
        record_play(self.paths, profile, chart_key="song:normal:5lane", result=result)
        self.assertEqual(profile["lifetime_score"], 4321)
        self.assertEqual(profile["wallet_score"], 4321)

    def test_purchase_spends_once_and_persists_unlock(self) -> None:
        profile = load_profile(self.paths)
        profile["wallet_score"] = 150000
        self.assertTrue(purchase_unlock(self.paths, profile, "mascot.cute", 100000))
        self.assertEqual(profile["wallet_score"], 50000)
        self.assertIn("mascot.cute", profile["unlocked_cosmetics"])
        self.assertFalse(purchase_unlock(self.paths, profile, "mascot.cute", 100000))
        self.assertEqual(profile["wallet_score"], 50000)

        restored = load_profile(self.paths)
        self.assertEqual(restored["wallet_score"], 50000)
        self.assertIn("mascot.cute", restored["unlocked_cosmetics"])
        self.assertEqual(restored["purchase_history"][-1]["price"], 100000)

    def test_reward_purchase_materializes_locked_image(self) -> None:
        source = self.paths.rewards / "locked" / "future_reward.png"
        source.write_bytes(b"future image")
        profile = load_profile(self.paths)
        profile["wallet_score"] = 5000

        self.assertTrue(purchase_unlock(self.paths, profile, "reward.future_reward.png", 5000))
        self.assertEqual(profile["wallet_score"], 0)
        self.assertIn("future_reward.png", profile["unlocked_rewards"])
        self.assertEqual((self.paths.rewards / "unlocked" / "future_reward.png").read_bytes(), b"future image")


if __name__ == "__main__":
    unittest.main()
