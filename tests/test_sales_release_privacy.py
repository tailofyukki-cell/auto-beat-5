from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import persistence


def load_tool(name: str):
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PREPARE = load_tool("prepare_sales_release")
PREFLIGHT = load_tool("release_preflight")


class SalesReleasePrivacyTests(unittest.TestCase):
    digest = "a" * 64
    stray_digest = "b" * 64

    def create_demo_source(self, root: Path) -> None:
        demo = root / "demo_songs"
        (demo / "cache").mkdir(parents=True)
        (demo / "charts" / self.digest).mkdir(parents=True)
        (demo / "charts" / self.stray_digest).mkdir(parents=True)
        (demo / "demo.mp3").write_bytes(b"demo audio")
        (demo / "private_song.wav").write_bytes(b"private audio")
        (demo / "README.txt").write_text("demo bundle\n", encoding="utf-8")
        (demo / "cache" / f"{self.digest}.json").write_text("{}\n", encoding="utf-8")
        (demo / "cache" / f"{self.stray_digest}.json").write_text("{}\n", encoding="utf-8")
        (demo / "charts" / self.digest / "beginner.json").write_text("{}\n", encoding="utf-8")
        (demo / "charts" / self.stray_digest / "beginner.json").write_text("{}\n", encoding="utf-8")
        (demo / "demo_manifest.json").write_text(
            json.dumps({"version": 1, "songs": [{"file": "demo.mp3", "music_hash": self.digest}]}, indent=2),
            encoding="utf-8",
        )

    def make_release_app(self, root: Path) -> Path:
        app = root / "AutoBeat5"
        demo = app / "demo_songs"
        (demo / "cache").mkdir(parents=True)
        (demo / "charts" / self.digest).mkdir(parents=True)
        (demo / "demo.mp3").write_bytes(b"demo audio")
        (demo / "README.txt").write_text("demo bundle\n", encoding="utf-8")
        (demo / "cache" / f"{self.digest}.json").write_text("{}\n", encoding="utf-8")
        (demo / "charts" / self.digest / "beginner.json").write_text("{}\n", encoding="utf-8")
        (demo / "demo_manifest.json").write_text(
            json.dumps({"version": 1, "songs": [{"file": "demo.mp3", "music_hash": self.digest}]}, indent=2),
            encoding="utf-8",
        )
        (app / "RELEASE_CHANNEL.txt").write_text("AutoBeat5_Release_RC1\n", encoding="utf-8")
        return app

    def test_staging_copies_only_manifest_authorized_demo_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            self.create_demo_source(workspace)
            destination = workspace / "stage" / "demo_songs"
            with mock.patch.object(PREPARE, "ROOT", workspace):
                PREPARE.stage_demo_bundle(destination)

            copied = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
            self.assertIn("demo.mp3", copied)
            self.assertIn(f"cache/{self.digest}.json", copied)
            self.assertIn(f"charts/{self.digest}/beginner.json", copied)
            self.assertNotIn("private_song.wav", copied)
            self.assertNotIn(f"cache/{self.stray_digest}.json", copied)
            self.assertNotIn(f"charts/{self.stray_digest}/beginner.json", copied)

    def test_preflight_rejects_personal_profile_or_unapproved_demo_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = self.make_release_app(Path(temporary))
            PREFLIGHT.assert_demo_bundle_is_allowlisted(app)
            (app / "profile.json").write_text('{"recent_songs": []}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Personal player data"):
                PREFLIGHT.assert_demo_bundle_is_allowlisted(app)
            (app / "profile.json").unlink()
            (app / "demo_songs" / "private_song.wav").write_bytes(b"private audio")
            with self.assertRaisesRegex(RuntimeError, "Unapproved file"):
                PREFLIGHT.assert_demo_bundle_is_allowlisted(app)

    def test_packaged_release_uses_isolated_appdata_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "AutoBeat5.exe"
            executable.write_bytes(b"placeholder")
            (Path(temporary) / "RELEASE_CHANNEL.txt").write_text("AutoBeat5_Release_RC1\n", encoding="utf-8")
            with mock.patch.object(persistence.sys, "frozen", True, create=True), mock.patch.object(
                persistence.sys, "executable", str(executable)
            ):
                self.assertEqual(persistence.data_namespace(), "AutoBeat5_Release_RC1")


if __name__ == "__main__":
    unittest.main()
