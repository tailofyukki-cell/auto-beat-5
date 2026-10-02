from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

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
PACKAGE_ZIP = load_tool("package_trial_zip")
PDF_BUILDER = load_tool("build_user_guide_pdf")


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
        app = root / "Otoasobi"
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

    def test_user_guide_pdf_builder_creates_pdf_from_screenshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            screenshots = workspace / "docs" / "user_manual" / "screenshots"
            screenshots.mkdir(parents=True)
            Image.new("RGB", (320, 180), (20, 30, 45)).save(screenshots / "01_title.png")
            output = workspace / "docs" / "Otoasobi_User_Guide.pdf"
            with mock.patch.object(PDF_BUILDER, "SCREENSHOTS", screenshots), mock.patch.object(
                PDF_BUILDER, "OUTPUT", output
            ), mock.patch.object(PDF_BUILDER, "PREVIEWS", workspace / "previews"), mock.patch.object(
                PDF_BUILDER, "PAGES", [PDF_BUILDER.PAGES[0]]
            ):
                self.assertEqual(PDF_BUILDER.build_pdf(), output)
            self.assertTrue(output.read_bytes().startswith(b"%PDF"))
    def test_staging_copies_mascot_assets_from_dedicated_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            self.create_demo_source(workspace)
            (workspace / "rewards" / "locked").mkdir(parents=True)
            (workspace / "rewards" / "reward_config.json").write_text(
                json.dumps({"secret.png": {"required_score": 1000}}) + "\n", encoding="utf-8"
            )
            (workspace / "rewards" / "locked" / "secret.png").write_bytes(b"png")
            (workspace / "licenses").mkdir()
            (workspace / "assets" / "mascots").mkdir(parents=True)
            (workspace / "assets" / "mascots" / "manifest.json").write_text(
                json.dumps({"version": 1, "mascots": [{"id": "cute", "file": "cute.png"}]}) + "\n",
                encoding="utf-8",
            )
            (workspace / "assets" / "mascots" / "cute.png").write_bytes(b"sprite")
            (workspace / "RELEASE_README.txt").write_text("Otoasobi\n", encoding="utf-8")
            (workspace / "docs").mkdir()
            (workspace / "docs" / "sales_release_rc1_test_checklist.md").write_text("checklist\\n", encoding="utf-8")
            (workspace / "docs" / "AutoBeat5_User_Guide.pdf").write_bytes(b"pdf")
            dist = workspace / "dist"
            dist.mkdir()
            (dist / "AutoBeat5.exe").write_bytes(b"exe")
            stage = workspace / "stage" / "Otoasobi"
            with mock.patch.object(PREPARE, "ROOT", workspace):
                PREPARE.stage_assets(dist, stage)

            staged_manifest = json.loads((stage / "assets" / "mascots" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(staged_manifest["mascots"][0]["id"], "cute")
            self.assertEqual((stage / "assets" / "mascots" / "cute.png").read_bytes(), b"sprite")
            self.assertEqual((stage / "Otoasobi_User_Guide.pdf").read_bytes(), b"pdf")
            self.assertTrue((stage / "Otoasobi.exe").is_file())
            self.assertFalse((stage / "AutoBeat5.exe").exists())
            self.assertFalse((stage / "RC1_TEST_CHECKLIST.md").exists())
            self.assertFalse((stage / "RELEASE_CHANNEL.txt").exists())
            self.assertTrue((stage / "rewards" / "locked").is_dir())
            self.assertTrue((stage / "rewards" / "unlocked").is_dir())
            self.assertEqual((stage / "rewards" / "locked" / "secret.png").read_bytes(), b"png")

    def test_preflight_requires_mascot_catalog(self) -> None:
        self.assertIn("Otoasobi/assets/mascots/manifest.json", PREFLIGHT.REQUIRED_ENTRIES)

    def test_preflight_requires_user_guide_pdf(self) -> None:
        self.assertIn("Otoasobi/Otoasobi_User_Guide.pdf", PREFLIGHT.REQUIRED_ENTRIES)

    def test_sales_package_names_match(self) -> None:
        self.assertEqual(PACKAGE_ZIP.OUTPUT.name, "Otoasobi_Windows.zip")
        self.assertEqual(PACKAGE_ZIP.OUTPUT, PREFLIGHT.DEFAULT_ZIP)
        self.assertEqual(PACKAGE_ZIP.README_NAME, "README.txt")
        self.assertIn("Otoasobi/README.txt", PREFLIGHT.REQUIRED_ENTRIES)
        self.assertNotIn("Otoasobi/TRIAL_README.txt", PREFLIGHT.REQUIRED_ENTRIES)

    def test_trial_zip_requires_user_guide_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            staging = workspace / "release" / "_staging" / "Otoasobi"
            (staging / "demo_songs").mkdir(parents=True)
            (staging / "rewards" / "locked").mkdir(parents=True)
            (staging / "rewards" / "unlocked").mkdir()
            (staging / "Otoasobi.exe").write_bytes(b"exe")
            (staging / "README.txt").write_text("Otoasobi\n", encoding="utf-8")
            (staging / "demo_songs" / "demo_manifest.json").write_text("{}\n", encoding="utf-8")
            (staging / "demo_songs" / "ここから始まる.wav").write_bytes(b"audio")
            (staging / "rewards" / "reward_config.json").write_text(
                json.dumps({"musical_trophy.png": {"required_score": 0}}) + "\n", encoding="utf-8"
            )
            (staging / "rewards" / "locked" / "musical_trophy.png").write_bytes(b"png")
            output = workspace / "release" / "Otoasobi_Windows.zip"
            with mock.patch.object(PACKAGE_ZIP, "STAGING", staging), mock.patch.object(PACKAGE_ZIP, "OUTPUT", output):
                PACKAGE_ZIP.create_zip()
                with self.assertRaisesRegex(RuntimeError, "Otoasobi/Otoasobi_User_Guide.pdf"):
                    PACKAGE_ZIP.verify_unicode_filenames()

            (staging / "Otoasobi_User_Guide.pdf").write_bytes(b"pdf")
            with mock.patch.object(PACKAGE_ZIP, "STAGING", staging), mock.patch.object(PACKAGE_ZIP, "OUTPUT", output):
                PACKAGE_ZIP.create_zip()
                PACKAGE_ZIP.verify_unicode_filenames()
                with __import__("zipfile").ZipFile(output) as archive:
                    info = archive.getinfo("Otoasobi/rewards/locked/musical_trophy.png")
                self.assertTrue(info.external_attr & 0x02)

    def test_zip_preserves_empty_reward_directories(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            stage = workspace / "stage"
            (stage / "rewards" / "locked").mkdir(parents=True)
            (stage / "rewards" / "unlocked").mkdir()
            (stage / "Otoasobi.exe").write_bytes(b"exe")
            (stage / "rewards" / "reward_config.json").write_text("{}", encoding="utf-8")
            (stage / "rewards" / "ご褒美.png").write_bytes(b"image")
            output = workspace / "release.zip"
            with mock.patch.object(PACKAGE_ZIP, "STAGING", stage), mock.patch.object(PACKAGE_ZIP, "OUTPUT", output):
                PACKAGE_ZIP.create_zip()
            with zipfile.ZipFile(output) as archive:
                for folder in ("locked", "unlocked"):
                    info = archive.getinfo(f"Otoasobi/rewards/{folder}/")
                    self.assertTrue(info.is_dir())
                    self.assertTrue(info.external_attr & 0x10)
                self.assertTrue(archive.getinfo("Otoasobi/rewards/locked/").external_attr & 0x02)
                archive.extractall(workspace / "python")
            PREFLIGHT.assert_reward_bundle(workspace / "python" / "Otoasobi")
            if sys.platform == "win32":
                expanded = PREFLIGHT.expand_with_windows(output, workspace / "windows")
                PREFLIGHT.assert_reward_bundle(expanded)

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
            executable = Path(temporary) / "Otoasobi.exe"
            executable.write_bytes(b"placeholder")
            with mock.patch.object(persistence.sys, "frozen", True, create=True), mock.patch.object(
                persistence.sys, "executable", str(executable)
            ):
                self.assertEqual(persistence.data_namespace(), "AutoBeat5_Release_RC1")


if __name__ == "__main__":
    unittest.main()

