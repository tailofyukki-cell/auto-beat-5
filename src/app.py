"""AutoBeat 5 のPygameアプリケーション。"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pygame

from analyzer import AnalysisProgress, AnalysisWorker, MusicAnalyzer
from audio_clock import AudioClock, AudioClockError
from calibration import CalibrationSession
from chart_generator import ChartGenerator
from chart_summary import build_chart_summary
from chart_validator import ChartValidator
from gameplay import GameSession, JudgmentWindows
from models import AnalysisResult, Chart, Difficulty, Judgment, LANE_NAMES
from persistence import (
    AppPaths,
    load_analysis,
    load_chart,
    load_profile,
    load_settings,
    music_hash,
    ranking_entries,
    record_play,
    song_ranking_summary,
    record_recent_song,
    save_analysis,
    save_chart,
    save_profile,
    save_settings,
)
from rewards import RewardImage, RewardProgress, ensure_reward_template, reward_progress, scan_rewards
from tutorial import TUTORIAL_BEAT_SECONDS, TUTORIAL_STEPS, build_tutorial_chart


WINDOW_TITLE = "AutoBeat 5"
BG = (12, 17, 29)
PANEL = (25, 35, 58)
PANEL_DARK = (18, 25, 43)
WHITE = (235, 242, 255)
MUTED = (150, 170, 200)
CYAN = (71, 215, 255)
MAGENTA = (255, 103, 190)
YELLOW = (255, 210, 90)
GREEN = (100, 235, 157)
RED = (250, 105, 110)
NOTE_THEMES: dict[str, tuple[str, tuple[tuple[int, int, int], ...]]] = {
    "standard": ("STANDARD", ((74, 146, 255), (99, 204, 242), (255, 211, 82), (247, 120, 174), (186, 110, 255))),
    "neon": ("NEON", ((0, 236, 255), (74, 255, 166), (255, 234, 74), (255, 90, 203), (166, 92, 255))),
    "pastel": ("PASTEL", ((120, 190, 255), (133, 232, 214), (255, 224, 134), (255, 167, 192), (199, 166, 255))),
    "contrast": ("HIGH CONTRAST", ((72, 180, 255), (56, 255, 214), (255, 238, 46), (255, 120, 56), (255, 76, 198))),
}
# 既存のテスト・外部拡張との互換性を保つ標準テーマの別名。
LANE_COLORS = NOTE_THEMES["standard"][1]
RESOLUTION_PRESETS = ((1280, 720), (1600, 900), (1920, 1080))
COMBO_MILESTONES = (50, 100, 500)
COUNTDOWN_SECONDS = 3.0
PLAYFIELD_MODES: dict[str, tuple[str, float]] = {
    "standard": ("STANDARD", 1.0),
    # 判定時刻は変えず、表示上の到達速度を抑えて先読み時間を増やす。
    "tall": ("TALL FOCUS", 0.82),
}
JUDGMENT_COLORS = {Judgment.PERFECT: CYAN, Judgment.GREAT: GREEN, Judgment.GOOD: YELLOW, Judgment.MISS: RED}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac"}
LIBRARY_VISIBLE_ROWS = 6
LIBRARY_ROW_HEIGHT = 72


@dataclass(slots=True)
class HitEffect:
    """判定線上に短時間だけ残る、レーン位置確認用の視覚フィードバック。"""

    lane: int
    judgment: Judgment
    started_at: float
    duration: float = 0.18


class AutoBeatApp:
    def __init__(self) -> None:
        pygame.mixer.pre_init(44100, -16, 2, 256)
        pygame.init()
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            # 再生不可環境でも譜面確認や設定編集は可能にする。
            self.audio_available = False
        else:
            self.audio_available = True

        self.paths = AppPaths.discover()
        self.paths.ensure()
        ensure_reward_template(self.paths)
        self.settings = load_settings(self.paths)
        self.settings.setdefault("music_volume", 0.8)
        self.settings.setdefault("sfx_volume", 0.7)
        self.settings.setdefault("note_speed", 650.0)
        self.settings.setdefault("playfield_mode", "standard")
        if self.settings["playfield_mode"] not in PLAYFIELD_MODES:
            self.settings["playfield_mode"] = "standard"
        self.settings.setdefault("note_theme", "standard")
        if self.settings["note_theme"] not in NOTE_THEMES:
            self.settings["note_theme"] = "standard"
        self.settings.setdefault("timing_offset_ms", 0)
        self.settings.setdefault("fullscreen", False)
        self.settings.setdefault("resolution", [1280, 720])
        self.settings.setdefault("judgment_windows_ms", {})
        for name, default in (("perfect", 45), ("great", 90), ("good", 140)):
            self.settings["judgment_windows_ms"].setdefault(name, default)
        self.profile = load_profile(self.paths)
        width, height = self.settings["resolution"]
        flags = pygame.FULLSCREEN if self.settings["fullscreen"] else 0
        self.surface = pygame.display.set_mode((int(width), int(height)), flags)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.fonts = self._build_fonts()
        self.running = True
        self.screen = "title"
        self.message = ""
        self.error = ""
        self.buttons: list[tuple[pygame.Rect, Callable[[], None]]] = []
        self.song_path: Path | None = None
        self.analysis = None
        self.chart: Chart | None = None
        # committed_chart はディスクへ保存済みの確定譜面、pending_chart は未保存の試作候補。
        self.committed_chart: Chart | None = None
        self.pending_chart: Chart | None = None
        self.worker: AnalysisWorker | None = None
        self.progress = AnalysisProgress(0, "")
        self.selected_difficulty = 0
        self.library_scroll_index = 0
        self.library_selected_index = 0
        self.session: GameSession | None = None
        self.audio = AudioClock()
        self.tutorial_step_index: int | None = None
        self.tutorial_started_at: float | None = None
        self.tutorial_paused_at: float | None = None
        self.tutorial_next_click_at = 0.0
        self.key_capture_lane: int | None = None
        self.settings_selection = 0
        self.newly_unlocked: list[str] = []
        self.gallery_page = 0
        self.selected_reward: RewardImage | None = None
        self.combo_banner = ""
        self.combo_banner_until = 0.0
        self.hit_effects: list[HitEffect] = []
        self.countdown_started_at: float | None = None
        self.calibration: CalibrationSession | None = None
        self.start_banner_until = 0.0
        self.feedback_sounds = self._build_feedback_sounds()
        self._set_sfx_volume()

    @property
    def size(self) -> tuple[int, int]:
        return self.surface.get_size()

    def _game_field_geometry(self) -> tuple[int, int, int, int, int]:
        """ウィンドウ解像度を変えず、選択したモードに応じて縦方向の表示領域を決める。"""
        width, height = self.size
        field_width = min(620, width - 420)
        left = (width - field_width) // 2
        lane_width = field_width // 5
        if self.playfield_mode_key == "tall":
            # 画面の上下余白を圧縮し、同じレーン幅のまま物理的な表示距離も伸ばす。
            field_top = max(8, int(height * 0.012))
            judgment_y = max(field_top + 250, height - max(50, int(height * 0.07)))
        else:
            field_top = max(18, int(height * 0.028))
            judgment_y = max(field_top + 240, height - max(74, int(height * 0.103)))
        return left, field_width, lane_width, field_top, judgment_y

    def _countdown_remaining(self) -> float:
        if self.countdown_started_at is None:
            return 0.0
        return max(0.0, COUNTDOWN_SECONDS - (time.perf_counter() - self.countdown_started_at))

    @property
    def countdown_active(self) -> bool:
        return self.countdown_started_at is not None and self._countdown_remaining() > 0.0

    @property
    def tutorial_active(self) -> bool:
        return self.tutorial_step_index is not None

    @property
    def game_paused(self) -> bool:
        return self.tutorial_paused_at is not None if self.tutorial_active else self.audio.paused

    def gameplay_time(self) -> float:
        """通常プレイは音源時計、チュートリアルは単調時計を判定に用いる。"""
        if not self.tutorial_active or self.tutorial_started_at is None:
            return self.audio.time if not self.tutorial_active else 0.0
        end = self.tutorial_paused_at if self.tutorial_paused_at is not None else time.perf_counter()
        return max(0.0, end - self.tutorial_started_at)

    def _start_after_countdown(self) -> None:
        """カウント終了後、通常曲またはチュートリアルの時計・判定を開始する。"""
        self.countdown_started_at = None
        if self.tutorial_active:
            self.tutorial_started_at = time.perf_counter()
            self.tutorial_paused_at = None
            self.tutorial_next_click_at = 0.0
        else:
            self.audio.play()
        self.start_banner_until = time.perf_counter() + 0.42

    @staticmethod
    def resource_path(relative_path: str) -> Path:
        """開発時とPyInstaller配布時の両方で同梱アセットを解決する。"""
        bundled_root = getattr(sys, "_MEIPASS", None)
        root = Path(bundled_root) if bundled_root else Path(__file__).resolve().parents[1]
        return root / relative_path

    def _font_from_asset(self, size: int, *, bold: bool = False) -> pygame.font.Font:
        """OSのフォント構成に依存せず、日本語グリフを持つ同梱フォントを優先する。"""
        bundled_font = self.resource_path("fonts/NotoSansCJK-Regular.ttc")
        if bundled_font.is_file():
            try:
                font = pygame.font.Font(str(bundled_font), size)
                font.set_bold(bold)
                return font
            except pygame.error:
                pass
        for family in ("Yu Gothic UI", "Yu Gothic", "Meiryo", "MS Gothic", "Noto Sans CJK JP"):
            candidate = pygame.font.match_font(family, bold=bold)
            if candidate:
                return pygame.font.Font(candidate, size)
        return pygame.font.SysFont(None, size, bold=bold)

    def _build_fonts(self) -> dict[str, pygame.font.Font]:
        return {
            "title": self._font_from_asset(56, bold=True),
            "h1": self._font_from_asset(32, bold=True),
            "body": self._font_from_asset(20),
            "small": self._font_from_asset(15),
            "mono": pygame.font.SysFont("consolas", 18, bold=True),
        }

    @property
    def playfield_mode_key(self) -> str:
        key = str(self.settings.get("playfield_mode", "standard"))
        return key if key in PLAYFIELD_MODES else "standard"

    @property
    def playfield_mode_label(self) -> str:
        return PLAYFIELD_MODES[self.playfield_mode_key][0]

    @property
    def effective_note_speed(self) -> float:
        return float(self.settings["note_speed"]) * PLAYFIELD_MODES[self.playfield_mode_key][1]

    @property
    def note_theme_key(self) -> str:
        key = str(self.settings.get("note_theme", "standard"))
        return key if key in NOTE_THEMES else "standard"

    @property
    def lane_colors(self) -> tuple[tuple[int, int, int], ...]:
        return NOTE_THEMES[self.note_theme_key][1]

    @property
    def note_theme_label(self) -> str:
        return NOTE_THEMES[self.note_theme_key][0]

    def text(
        self,
        value: str,
        font: str = "body",
        color: tuple[int, int, int] = WHITE,
        center: tuple[int, int] | None = None,
        pos: tuple[int, int] | None = None,
    ) -> pygame.Rect:
        rendered = self.fonts[font].render(value, True, color)
        rect = rendered.get_rect()
        if center:
            rect.center = center
        elif pos:
            rect.topleft = pos
        self.surface.blit(rendered, rect)
        return rect

    def panel(self, rect: pygame.Rect, color: tuple[int, int, int] = PANEL, radius: int = 14) -> None:
        pygame.draw.rect(self.surface, color, rect, border_radius=radius)

    def button(self, label: str, rect: pygame.Rect, action: Callable[[], None], *, accent: tuple[int, int, int] = CYAN) -> None:
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        self.panel(rect, tuple(min(255, channel + 18) for channel in PANEL) if hovered else PANEL_DARK, 10)
        pygame.draw.rect(self.surface, accent if hovered else (65, 85, 120), rect, width=2, border_radius=10)
        self.text(label, "body", accent if hovered else WHITE, center=rect.center)
        self.buttons.append((rect, action))

    def heading(self, title: str, subtitle: str = "") -> None:
        width, _ = self.size
        self.text(title, "h1", center=(width // 2, 55))
        if subtitle:
            self.text(subtitle, "small", MUTED, center=(width // 2, 91))
        pygame.draw.line(self.surface, (56, 72, 105), (48, 112), (width - 48, 112), 1)

    def _build_feedback_sounds(self) -> dict[Judgment, pygame.mixer.Sound]:
        if not self.audio_available or not pygame.mixer.get_init():
            return {}
        sample_rate, _format, channels = pygame.mixer.get_init()

        def tone(frequency: float, duration: float = 0.045) -> pygame.mixer.Sound:
            frames = max(1, int(sample_rate * duration))
            samples = array("h")
            for index in range(frames):
                envelope = max(0.0, 1.0 - index / frames)
                value = int(9000 * envelope * math.sin(2 * math.pi * frequency * index / sample_rate))
                for _ in range(channels):
                    samples.append(value)
            return pygame.mixer.Sound(buffer=samples)

        try:
            return {
                Judgment.PERFECT: tone(880),
                Judgment.GREAT: tone(720),
                Judgment.GOOD: tone(540),
                Judgment.MISS: tone(180, 0.070),
            }
        except pygame.error:
            return {}

    def _set_sfx_volume(self) -> None:
        volume = max(0.0, min(1.0, float(self.settings.get("sfx_volume", 0.7))))
        for sound in self.feedback_sounds.values():
            sound.set_volume(volume)

    def _emit_hit_effect(self, lane: int, judgment: Judgment | None) -> None:
        """成功判定の入力位置だけを、短いリングと火花で示す。"""
        if judgment is None or judgment is Judgment.MISS or not 0 <= lane < 5:
            return
        self.hit_effects.append(HitEffect(lane=lane, judgment=judgment, started_at=time.perf_counter()))
        # 重い連打でも画面を埋めないよう、最新8件だけを保持する。
        self.hit_effects = self.hit_effects[-8:]

    def _draw_hit_effects(self, left: int, lane_width: int, line_y: int) -> None:
        """ノーツ・判定文字を覆わない、0.18秒で消える控えめなレーン別エフェクトを描く。"""
        now = time.perf_counter()
        self.hit_effects = [effect for effect in self.hit_effects if now - effect.started_at < effect.duration]
        for effect in self.hit_effects:
            progress = max(0.0, min(1.0, (now - effect.started_at) / effect.duration))
            alpha = int(165 * (1.0 - progress) ** 1.7)
            if alpha <= 0:
                continue
            # 判定の成否ではなく、押したレーンを即座に追えるテーマ色を使う。
            color = self.lane_colors[effect.lane]
            layer_height = 92
            layer = pygame.Surface((lane_width, layer_height), pygame.SRCALPHA)
            center = (lane_width // 2, layer_height // 2)
            radius = int(12 + lane_width * (0.09 + 0.16 * progress))
            width = max(1, int(3 * (1.0 - progress)))
            pygame.draw.circle(layer, (*color, alpha), center, radius, width=width)
            # 十字方向の短いスパークで、どのレーンを押したかだけを残す。
            spark_inner = max(4, int(radius * 0.62))
            spark_outer = radius + int(8 + 10 * progress)
            for angle in (0.0, math.pi / 2, math.pi, math.pi * 1.5):
                dx, dy = math.cos(angle), math.sin(angle)
                start = (int(center[0] + dx * spark_inner), int(center[1] + dy * spark_inner))
                end = (int(center[0] + dx * spark_outer), int(center[1] + dy * spark_outer))
                pygame.draw.line(layer, (*color, max(0, alpha - 35)), start, end, width=width)
            x = left + effect.lane * lane_width
            self.surface.blit(layer, (x, line_y - layer_height // 2))

    def _play_feedback(self, judgment: Judgment | None, lane: int | None = None) -> None:
        if judgment is not None and judgment in self.feedback_sounds:
            self.feedback_sounds[judgment].play()
        if lane is not None:
            self._emit_hit_effect(lane, judgment)
        self._check_combo_milestone()

    def _check_combo_milestone(self) -> None:
        """現在の連続コンボが節目へ到達した瞬間に、毎回バナーを表示する。"""
        if not self.session:
            return
        if self.session.combo in COMBO_MILESTONES:
            self.combo_banner = f"{self.session.combo} COMBO!"
            self.combo_banner_until = time.perf_counter() + 1.8

    def select_song_path(self, path: Path) -> None:
        """外部選択・同梱デモ曲のどちらからでも、同じ解析フローへ進める。"""
        if not path.is_file():
            self.error = "音楽ファイルが見つかりません。"
            return
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            self.error = "MP3 / WAV / OGG / FLAC の音楽ファイルを選択してください。"
            return
        self.song_path = path
        self.analysis = None
        self.chart = None
        self.committed_chart = None
        self.pending_chart = None
        self.error = ""
        self.begin_analysis()

    def choose_file(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askopenfilename(
                title="音楽ファイルを選択",
                filetypes=[("Audio", "*.mp3 *.wav *.ogg *.flac"), ("All files", "*.*")],
            )
            root.destroy()
        except Exception as error:
            self.error = f"ファイル選択を開けませんでした: {error}"
            return
        if selected:
            self.select_song_path(Path(selected))

    def demo_song_files(self) -> list[Path]:
        """制作者が配布物へ追加したデモ曲だけを、名前順で取得する。"""
        folder = self.paths.demo_songs
        if folder is None:
            return []
        try:
            return sorted(
                (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS),
                key=lambda path: path.name.lower(),
            )
        except OSError:
            return []

    def is_demo_song(self, path: Path | None = None) -> bool:
        """同梱デモ曲かどうかを、フォルダ境界を解決して判定する。"""
        folder = self.paths.demo_songs
        candidate = path or self.song_path
        if folder is None or candidate is None:
            return False
        try:
            return candidate.resolve().parent == folder.resolve()
        except OSError:
            return False

    def _load_demo_analysis(self, path: Path) -> AnalysisResult | None:
        """配布物に入れた解析キャッシュを検証して読み込む。壊れていれば通常解析へ戻す。"""
        folder = self.paths.demo_songs
        if folder is None:
            return None
        try:
            digest = music_hash(path)
            cache_file = folder / "cache" / f"{digest}.json"
            if not cache_file.is_file():
                return None
            analysis = AnalysisResult.from_dict(json.loads(cache_file.read_text(encoding="utf-8")))
            if analysis.music_hash != digest or analysis.analyzer_version != MusicAnalyzer.VERSION:
                return None
            analysis.source_path = str(path.resolve())
            return analysis
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _load_demo_chart(self, difficulty: Difficulty) -> Chart | None:
        folder = self.paths.demo_songs
        if folder is None or self.analysis is None:
            return None
        try:
            chart_file = folder / "charts" / self.analysis.music_hash / f"{difficulty.value}.json"
            if not chart_file.is_file():
                return None
            chart = Chart.from_dict(json.loads(chart_file.read_text(encoding="utf-8")))
            if chart.music_hash != self.analysis.music_hash or chart.generator_version != ChartGenerator.VERSION:
                return None
            return chart
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def load_demo_song(self, path: Path) -> None:
        if not path.is_file():
            self.error = "同梱デモ曲が見つかりません。"
            return
        analysis = self._load_demo_analysis(path)
        if analysis is None:
            self.message = "同梱キャッシュを確認できないため、デモ曲を解析します。"
            self.select_song_path(path)
            return
        self.song_path = path
        self.analysis = analysis
        self.chart = None
        self.committed_chart = None
        self.pending_chart = None
        self.error = ""
        self.message = "体験版の同梱キャッシュを読み込みました。"
        self.screen = "difficulty"

    def library_entries(self) -> list[dict[str, object]]:
        """プロフィールに保存された解析済み楽曲を、安全に一覧化する。"""
        entries = self.profile.get("recent_songs", [])
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]

    def _clamp_library_position(self) -> None:
        entries = self.library_entries()
        if not entries:
            self.library_scroll_index = 0
            self.library_selected_index = 0
            return
        self.library_selected_index = max(0, min(self.library_selected_index, len(entries) - 1))
        max_scroll = max(0, len(entries) - LIBRARY_VISIBLE_ROWS)
        self.library_scroll_index = max(0, min(self.library_scroll_index, max_scroll))
        if self.library_selected_index < self.library_scroll_index:
            self.library_scroll_index = self.library_selected_index
        elif self.library_selected_index >= self.library_scroll_index + LIBRARY_VISIBLE_ROWS:
            self.library_scroll_index = self.library_selected_index - LIBRARY_VISIBLE_ROWS + 1

    def open_library(self) -> None:
        self._clamp_library_position()
        self.screen = "library"

    def scroll_library(self, delta: int) -> None:
        entries = self.library_entries()
        if not entries:
            return
        max_scroll = max(0, len(entries) - LIBRARY_VISIBLE_ROWS)
        self.library_scroll_index = max(0, min(self.library_scroll_index + delta, max_scroll))
        first_visible = self.library_scroll_index
        last_visible = min(len(entries) - 1, first_visible + LIBRARY_VISIBLE_ROWS - 1)
        self.library_selected_index = max(first_visible, min(self.library_selected_index, last_visible))

    def move_library_selection(self, delta: int) -> None:
        entries = self.library_entries()
        if not entries:
            return
        self.library_selected_index = max(0, min(self.library_selected_index + delta, len(entries) - 1))
        self._clamp_library_position()

    def select_library_entry(self, index: int) -> None:
        entries = self.library_entries()
        if not (0 <= index < len(entries)):
            return
        self.library_selected_index = index
        self._clamp_library_position()
        self.load_recent_song(entries[index])

    def select_current_library_entry(self) -> None:
        self.select_library_entry(self.library_selected_index)

    def load_recent_song(self, entry: dict[str, object]) -> None:
        path = Path(str(entry.get("source_path", ""))).expanduser()
        if not path.exists() or not path.is_file():
            self.error = "ライブラリーの音源ファイルが見つかりません。移動・削除されている可能性があります。"
            return
        self.song_path = path
        try:
            digest = music_hash(path)
        except OSError:
            self.error = "ライブラリーの音源を読み取れません。"
            return
        if digest != entry.get("music_hash"):
            self.message = "音源が更新されているため、再解析します。"
        self.analysis = None
        self.chart = None
        self.committed_chart = None
        self.pending_chart = None
        self.begin_analysis()

    def begin_analysis(self) -> None:
        if not self.song_path:
            self.error = "先に音楽ファイルを選択してください。"
            return
        try:
            digest = music_hash(self.song_path)
        except OSError:
            self.error = "音楽ファイルを読み取れません。"
            return
        cached = load_analysis(self.paths, digest)
        if cached and cached.analyzer_version == MusicAnalyzer.VERSION:
            self.analysis = cached
            record_recent_song(self.paths, self.profile, cached)
            self.message = "解析キャッシュを読み込みました。"
            self.screen = "difficulty"
            return
        self.progress = AnalysisProgress(0.0, "解析を開始しています")
        self.worker = AnalysisWorker(self.song_path)
        self.worker.start()
        self.screen = "analyzing"

    def poll_worker(self) -> None:
        """解析ワーカーのキューを処理し、完了・失敗時は同一フレームで必ず終了する。"""
        worker = self.worker
        if worker is None:
            return
        while not worker.events.empty():
            event = worker.events.get_nowait()
            if isinstance(event, AnalysisProgress):
                self.progress = event
            elif isinstance(event, Exception):
                self.error = str(event)
                if self.worker is worker:
                    self.worker = None
                self.screen = "select"
                return
            else:
                self.analysis = event
                save_analysis(self.paths, event)
                record_recent_song(self.paths, self.profile, event)
                if self.worker is worker:
                    self.worker = None
                self.message = "解析とキャッシュ保存が完了しました。"
                self.screen = "difficulty"
                return

    def _generate_chart(self, difficulty: Difficulty, *, variant: int, persist: bool = True) -> Chart:
        """解析済み楽曲から指定variantの譜面を生成する。試作候補は明示採用まで保存しない。"""
        if not self.analysis:
            raise RuntimeError("解析結果がありません。")
        chart = ChartGenerator().generate(self.analysis, difficulty, variant=variant)
        report = ChartValidator().validate(chart)
        chart.metadata["validation_removed"] = report.removed_notes
        chart.metadata["validation_issues"] = report.issues[:20]
        if persist:
            save_chart(self.paths, chart)
        return chart

    def select_chart(self, difficulty: Difficulty) -> None:
        """譜面を用意して概要画面へ進む。プレイ開始はユーザー確認後に行う。"""
        if not self.analysis:
            self.error = "解析結果がありません。"
            self.screen = "select"
            return
        self.selected_difficulty = list(Difficulty).index(difficulty)
        chart = load_chart(self.paths, self.analysis.music_hash, difficulty.value)
        if chart is None and self.is_demo_song():
            chart = self._load_demo_chart(difficulty)
            if chart is not None:
                save_chart(self.paths, chart)
                self.message = f"体験版の同梱{difficulty.label}譜面を読み込みました（{len(chart.notes)}ノーツ）。"
        if chart is None or chart.generator_version != ChartGenerator.VERSION:
            chart = self._generate_chart(difficulty, variant=0)
            self.message = f"{difficulty.label}譜面を生成しました（{len(chart.notes)}ノーツ）。"
        elif not self.message.startswith("体験版の同梱"):
            self.message = f"{difficulty.label}譜面キャッシュを読み込みました。"
        self.chart = chart
        self.committed_chart = chart
        self.pending_chart = None
        self.screen = "chart_summary"

    @property
    def chart_is_pending(self) -> bool:
        return self.pending_chart is not None and self.chart is self.pending_chart

    def regenerate_chart(self) -> None:
        """確定済み譜面を残したまま、次の決定論的variantを未保存の試作候補として生成する。"""
        if not self.analysis or not self.chart:
            self.error = "再生成する譜面がありません。"
            self.screen = "difficulty"
            return
        base_chart = self.pending_chart or self.committed_chart or self.chart
        previous_variant = int(base_chart.metadata.get("generation_variant", 0))
        self.pending_chart = self._generate_chart(base_chart.difficulty, variant=previous_variant + 1, persist=False)
        self.chart = self.pending_chart
        self.message = f"{self.chart.difficulty.label}の試作候補を生成しました。プレイ後に採用を選べます。"
        self.screen = "chart_summary"

    def adopt_pending_chart(self) -> None:
        """試遊済み候補を、この曲・難易度の確定キャッシュとして保存する。"""
        if self.pending_chart is None:
            return
        save_chart(self.paths, self.pending_chart)
        self.committed_chart = self.pending_chart
        self.chart = self.pending_chart
        self.pending_chart = None
        self.message = "試作候補を採用して保存しました。"
        self.set_screen("chart_summary")

    def discard_pending_chart(self) -> None:
        """未保存の試作候補を破棄し、以前の確定譜面へ戻す。"""
        if self.pending_chart is None:
            return
        self.pending_chart = None
        if self.committed_chart is not None:
            self.chart = self.committed_chart
        self.message = "試作候補を破棄し、以前の譜面を残しました。"
        self.set_screen("chart_summary")

    def start_game(self) -> None:
        if not self.chart or not self.analysis or not self.song_path:
            return
        self.tutorial_step_index = None
        self.tutorial_started_at = None
        self.tutorial_paused_at = None
        if not self.audio_available:
            self.error = "音声デバイスを初期化できないため、プレイを開始できません。"
            self.screen = "difficulty"
            return
        try:
            self.audio.load(self.song_path, self.analysis.duration, float(self.settings["music_volume"]))
            windows = JudgmentWindows.from_ms(self.settings["judgment_windows_ms"])
            self.session = GameSession(
                self.chart,
                windows,
                timing_offset=float(self.settings.get("timing_offset_ms", 0)) / 1000.0,
            )
            self.combo_banner = ""
            self.hit_effects = []
            self.countdown_started_at = time.perf_counter()
            self.start_banner_until = 0.0
            self.error = ""
            self.screen = "game"
        except AudioClockError as error:
            self.error = str(error)
            self.screen = "difficulty"

    def start_tutorial(self) -> None:
        """音源なし・メトロノーム型の最初の課題を開始する。"""
        self.start_tutorial_step(0)

    def start_tutorial_step(self, step_index: int) -> None:
        if not self.audio_available or not self.feedback_sounds:
            self.error = "効果音を初期化できないため、チュートリアルを開始できません。"
            self.set_screen("tutorial")
            return
        try:
            chart = build_tutorial_chart(step_index)
        except (IndexError, ValueError) as error:
            self.error = f"チュートリアルを準備できませんでした: {error}"
            self.set_screen("tutorial")
            return
        windows = JudgmentWindows.from_ms(self.settings["judgment_windows_ms"])
        self.chart = chart
        self.session = GameSession(
            chart,
            windows,
            timing_offset=float(self.settings.get("timing_offset_ms", 0)) / 1000.0,
        )
        self.tutorial_step_index = step_index
        self.tutorial_started_at = None
        self.tutorial_paused_at = None
        self.tutorial_next_click_at = 0.0
        self.combo_banner = ""
        self.hit_effects = []
        self.countdown_started_at = time.perf_counter()
        self.start_banner_until = 0.0
        self.error = ""
        self.screen = "game"

    def finish_tutorial_step(self) -> None:
        if self.tutorial_step_index is None:
            return
        if self.tutorial_step_index == len(TUTORIAL_STEPS) - 1:
            self.profile["tutorial_completed"] = True
            save_profile(self.paths, self.profile)
        self.screen = "tutorial_result"

    def update_tutorial_metronome(self, elapsed: float) -> None:
        sound = self.feedback_sounds.get(Judgment.PERFECT)
        if sound is None:
            return
        while elapsed >= self.tutorial_next_click_at:
            sound.play()
            self.tutorial_next_click_at += TUTORIAL_BEAT_SECONDS

    def begin_calibration(self) -> None:
        """0.5秒間隔のクリックに合わせた入力でTiming Offsetを測定する。"""
        if not self.audio_available or not self.feedback_sounds:
            self.error = "効果音を初期化できないため、入力タイミングを測定できません。"
            return
        self.calibration = CalibrationSession(started_at=time.perf_counter() + 0.8)
        self.message = ""
        self.error = ""
        self.set_screen("calibration")

    def update_calibration(self) -> None:
        if self.screen != "calibration" or self.calibration is None:
            return
        sound = self.feedback_sounds.get(Judgment.PERFECT)
        if sound is None:
            return
        for _beat in self.calibration.due_clicks(time.perf_counter()):
            sound.play()

    def apply_calibration(self) -> None:
        if not self.calibration:
            return
        recommendation = self.calibration.recommendation_ms
        if recommendation is None:
            self.error = "少なくとも5回入力してから適用してください。"
            return
        self.settings["timing_offset_ms"] = recommendation
        self.persist_settings()
        self.message = f"Timing Offset を {recommendation:+d} ms に設定しました。"
        self.calibration = None
        self.set_screen("settings")

    def _current_chart_key(self) -> str | None:
        if self.chart is None:
            return None
        return f"{self.chart.music_hash}:{self.chart.difficulty.value}"

    def current_ranking(self, *, limit: int = 10) -> list[dict[str, object]]:
        chart_key = self._current_chart_key()
        return [] if chart_key is None else ranking_entries(self.profile, chart_key, limit=limit)

    def open_ranking(self) -> None:
        if self.chart is None:
            self.error = "先に譜面を選択してください。"
            return
        self.set_screen("ranking")

    def finish_game(self) -> None:
        if not self.session or not self.chart:
            return
        if self.tutorial_active:
            self.finish_tutorial_step()
            return
        result = self.session.result().to_dict()
        self.newly_unlocked = record_play(self.paths, self.profile, chart_key=result["chart_hash"], result=result)
        self.screen = "unlock" if self.newly_unlocked else "result"

    def toggle_pause(self) -> None:
        # カウントダウン中は音源未開始のため、ESCは中止操作として扱う。
        if self.countdown_active:
            return
        if self.tutorial_active:
            if self.tutorial_paused_at is None:
                self.tutorial_paused_at = time.perf_counter()
            else:
                paused_for = time.perf_counter() - self.tutorial_paused_at
                if self.tutorial_started_at is not None:
                    self.tutorial_started_at += paused_for
                self.tutorial_next_click_at += paused_for
                self.tutorial_paused_at = None
        elif self.audio.paused:
            self.audio.resume()
        else:
            self.audio.pause()

    def retry_game(self) -> None:
        if self.tutorial_active and self.tutorial_step_index is not None:
            self.start_tutorial_step(self.tutorial_step_index)
            return
        self.audio.stop()
        self.start_game()

    def return_to_song_select(self) -> None:
        if self.tutorial_active:
            self.countdown_started_at = None
            self.tutorial_step_index = None
            self.tutorial_started_at = None
            self.tutorial_paused_at = None
            self.session = None
            self.set_screen("tutorial")
            return
        self.audio.stop()
        self.countdown_started_at = None
        self.session = None
        self.set_screen("select")

    def open_reward(self, reward: RewardImage) -> None:
        if not reward.unlocked:
            self.message = "この画像はまだ解放されていません。"
            return
        self.selected_reward = reward
        self.set_screen("gallery_preview")

    def gallery_rewards(self) -> list[RewardImage]:
        return scan_rewards(
            self.paths,
            set(self.profile.get("unlocked_rewards", [])),
            lifetime_score=int(self.profile.get("lifetime_score", 0)),
        )

    def reward_status(self) -> RewardProgress:
        """リザルト・解放画面・ギャラリーで共通利用する累積スコア進捗。"""
        return reward_progress(self.paths, self.profile)

    def draw_reward_progress(self, rect: pygame.Rect, *, compact: bool = False) -> RewardProgress:
        """累積スコアと次の画像解放までの距離を横長の進捗表示として描画する。"""
        status = self.reward_status()
        self.panel(rect, PANEL_DARK, 8)
        if compact:
            self.text(
                f"REWARD SCORE  {status.lifetime_score:,} pts  ·  {status.unlocked_count}/{status.reward_count} unlocked",
                "small",
                WHITE,
                pos=(rect.left + 18, rect.top + 10),
            )
        else:
            self.text("REWARD SCORE", "small", MAGENTA, pos=(rect.left + 18, rect.top + 16))
            self.text(
                f"{status.lifetime_score:,} pts  ·  {status.unlocked_count}/{status.reward_count} unlocked",
                "small",
                WHITE,
                pos=(rect.left + 18, rect.top + 39),
            )
        if status.next_reward is None or status.next_required_score is None:
            message = "すべての設定済み画像を解放済みです" if status.reward_count else "rewards フォルダへ画像を追加すると解放目標を作れます"
            self.text(message, "small", GREEN, pos=(rect.left + 18, rect.top + (38 if compact else 64)))
            return status

        bar_left = rect.left + 18
        bar_width = rect.width - 36
        bar_top = rect.top + (55 if compact else rect.height - 28)
        pygame.draw.rect(self.surface, (50, 66, 94), pygame.Rect(bar_left, bar_top, bar_width, 9), border_radius=4)
        filled = max(2, int(bar_width * status.progress_ratio))
        pygame.draw.rect(self.surface, MAGENTA, pygame.Rect(bar_left, bar_top, filled, 9), border_radius=4)
        self.text(
            f"NEXT  {status.next_reward.name}  ·  あと {status.remaining_score:,} pts",
            "small",
            YELLOW,
            pos=(rect.left + 18, rect.top + (32 if compact else rect.height - 54)),
        )
        return status

    def _load_scaled_reward(self, reward: RewardImage, max_width: int, max_height: int) -> pygame.Surface | None:
        try:
            image = pygame.image.load(str(reward.path)).convert_alpha()
            scale = min(max_width / image.get_width(), max_height / image.get_height(), 1.0)
            return pygame.transform.smoothscale(
                image,
                (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale))),
            )
        except pygame.error:
            return None

    def draw_title(self) -> None:
        width, height = self.size
        self.text("AUTO BEAT 5", "title", CYAN, center=(width // 2, height // 2 - 165))
        self.text("あなたの音楽を、あなたの譜面へ。", "body", MUTED, center=(width // 2, height // 2 - 110))
        self.button("PLAY", pygame.Rect(width // 2 - 160, height // 2 - 55, 320, 50), lambda: self.set_screen("select"))
        self.button("TUTORIAL", pygame.Rect(width // 2 - 160, height // 2 + 7, 320, 46), lambda: self.set_screen("tutorial"), accent=GREEN)
        self.button("GALLERY", pygame.Rect(width // 2 - 160, height // 2 + 65, 320, 46), lambda: self.set_screen("gallery"), accent=MAGENTA)
        self.button("SETTINGS", pygame.Rect(width // 2 - 160, height // 2 + 123, 320, 46), lambda: self.set_screen("settings"), accent=YELLOW)
        self.text("MP3 / WAV / OGG / FLAC ・ 5 lanes ・ offline", "small", MUTED, center=(width // 2, height - 42))

    def _song_best_text(self, music_hash: str) -> str:
        """選曲リスト用に、難易度別の自己ベストを横並びの短い表記へ整える。"""
        summary = song_ranking_summary(self.profile, music_hash)
        labels: list[str] = []
        for difficulty in Difficulty:
            entry = summary.get(difficulty.value)
            if entry is None:
                labels.append(f"{difficulty.label[:2]} --")
            else:
                labels.append(f"{difficulty.label[:2]} {int(entry.get('score', 0)):,} {entry.get('rank', 'D')}")
        return "  |  ".join(labels)

    def draw_select(self) -> None:
        width, height = self.size
        self.heading("楽曲選択", "ユーザーが利用権限を持つ音楽ファイル、または同梱デモ曲を選択してください")
        selected = str(self.song_path) if self.song_path else "まだ選択されていません"
        self.panel(pygame.Rect(100, 145, width - 200, 112))
        self.text("選択中の楽曲", "small", MUTED, pos=(130, 162))
        self.text(Path(selected).name if self.song_path else selected, "h1" if self.song_path else "body", pos=(130, 190))
        if self.song_path:
            self.text(str(self.song_path), "small", MUTED, pos=(130, 228))
        self.button("音楽ファイルを選択", pygame.Rect(width // 2 - 190, 270, 380, 42), self.choose_file)

        y = 342
        demos = self.demo_song_files()[:3]
        if demos:
            self.text("DEMO SONGS", "body", GREEN, pos=(125, y))
            y += 31
            for demo in demos:
                rect = pygame.Rect(120, y, width - 240, 48)
                self.panel(rect, (27, 54, 61), 7)
                self.text(demo.name, "body", WHITE, pos=(rect.left + 16, rect.top + 13))
                self.text("同梱デモ曲", "small", GREEN, pos=(rect.right - 112, rect.top + 16))
                self.buttons.append((rect, lambda selected_demo=demo: self.load_demo_song(selected_demo)))
                y += 56

        recent = self.library_entries()
        if recent:
            self.text("RECENT LIBRARY", "body", YELLOW, pos=(125, y))
            y += 31
            self.button(f"ライブラリーを開く  {len(recent)} 曲  [L]", pygame.Rect(120, y, width - 240, 48), self.open_library, accent=YELLOW)
        elif not demos:
            self.text("解析した楽曲は、ここから再選択できます。", "small", MUTED, center=(width // 2, 410))
            self.text("demo_songs フォルダへ制作者のデモ曲を追加できます。", "small", GREEN, center=(width // 2, 440))
        self.button("戻る", pygame.Rect(50, height - 72, 140, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_library(self) -> None:
        width, height = self.size
        entries = self.library_entries()
        self._clamp_library_position()
        self.heading(
            "RECENT LIBRARY",
            f"解析済み {len(entries)} 曲  ・  マウスホイール / ↑↓ / PageUp・PageDownでスクロール  ・  Enterで選択",
        )
        list_rect = pygame.Rect(100, 145, width - 200, LIBRARY_VISIBLE_ROWS * LIBRARY_ROW_HEIGHT + 16)
        self.panel(list_rect)
        if not entries:
            self.text("解析済みの楽曲はまだありません。", "body", MUTED, center=(width // 2, list_rect.centery))
        else:
            visible = entries[self.library_scroll_index : self.library_scroll_index + LIBRARY_VISIBLE_ROWS]
            for offset, entry in enumerate(visible):
                index = self.library_scroll_index + offset
                row = pygame.Rect(list_rect.left + 16, list_rect.top + 8 + offset * LIBRARY_ROW_HEIGHT, list_rect.width - 52, LIBRARY_ROW_HEIGHT - 8)
                selected = index == self.library_selected_index
                self.panel(row, PANEL if selected else PANEL_DARK, 7)
                if selected:
                    pygame.draw.rect(self.surface, CYAN, pygame.Rect(row.left, row.top + 6, 4, row.height - 12), border_radius=2)
                source_path = Path(str(entry.get("source_path", "")))
                song_name = source_path.name or "不明な楽曲"
                digest = str(entry.get("music_hash", ""))
                exists = source_path.is_file()
                self.text(f"{index + 1:02d}. {song_name}", "body", WHITE, pos=(row.left + 16, row.top + 9))
                self.text(
                    f"{float(entry.get('bpm', 0.0)):.1f} BPM   {float(entry.get('duration', 0.0)):.1f} sec",
                    "small",
                    MUTED,
                    pos=(row.right - 225, row.top + 12),
                )
                summary_color = CYAN if song_ranking_summary(self.profile, digest) else MUTED
                self.text(f"BEST  {self._song_best_text(digest)}", "small", summary_color, pos=(row.left + 16, row.top + 38))
                if not exists:
                    self.text("FILE MISSING", "small", RED, pos=(row.right - 122, row.top + 38))
                self.buttons.append((row, lambda selected_index=index: self.select_library_entry(selected_index)))

            if len(entries) > LIBRARY_VISIBLE_ROWS:
                track = pygame.Rect(list_rect.right - 22, list_rect.top + 12, 8, list_rect.height - 24)
                pygame.draw.rect(self.surface, PANEL_DARK, track, border_radius=4)
                thumb_height = max(30, int(track.height * LIBRARY_VISIBLE_ROWS / len(entries)))
                max_scroll = len(entries) - LIBRARY_VISIBLE_ROWS
                progress = self.library_scroll_index / max_scroll if max_scroll else 0.0
                thumb_top = track.top + int((track.height - thumb_height) * progress)
                pygame.draw.rect(self.surface, YELLOW, pygame.Rect(track.left, thumb_top, track.width, thumb_height), border_radius=4)

        self.text(
            f"{self.library_scroll_index + 1 if entries else 0}-{min(len(entries), self.library_scroll_index + LIBRARY_VISIBLE_ROWS)} / {len(entries)}",
            "small",
            MUTED,
            center=(width // 2, height - 112),
        )
        self.button("選曲へ  [ESC]", pygame.Rect(50, height - 72, 180, 40), lambda: self.set_screen("select"), accent=MUTED)

    def draw_tutorial(self) -> None:
        width, height = self.size
        completed = bool(self.profile.get("tutorial_completed", False))
        subtitle = "音源なし。クリック音に合わせて基本操作を練習します。"
        if completed:
            subtitle += "  チュートリアル完了済み"
        self.heading("TUTORIAL", subtitle)
        panel = pygame.Rect(width // 2 - 450, 145, 900, 360)
        self.panel(panel)
        for index, step in enumerate(TUTORIAL_STEPS):
            y = panel.top + 24 + index * 78
            row = pygame.Rect(panel.left + 24, y, panel.width - 48, 62)
            self.panel(row, PANEL_DARK, 8)
            self.text(step.title, "body", GREEN if completed else CYAN, pos=(row.left + 18, row.top + 10))
            self.text(step.instruction, "small", MUTED, pos=(row.left + 18, row.top + 36))
            self.text(f"{len(step.notes)} NOTES", "small", YELLOW, pos=(row.right - 105, row.top + 23))
        self.button("最初から始める  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), self.start_tutorial, accent=GREEN)
        self.button("タイトルへ  [ESC]", pygame.Rect(width // 2 - 150, height - 72, 300, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_tutorial_result(self) -> None:
        if not self.session or self.tutorial_step_index is None:
            self.set_screen("tutorial")
            return
        width, height = self.size
        result = self.session.result()
        step = TUTORIAL_STEPS[self.tutorial_step_index]
        is_last = self.tutorial_step_index == len(TUTORIAL_STEPS) - 1
        self.heading("TUTORIAL RESULT", "すべての判定結果です。苦手な操作は何度でも練習できます。")
        self.panel(pygame.Rect(width // 2 - 360, 150, 720, 310))
        self.text(step.title, "h1", CYAN, center=(width // 2, 198))
        self.text(result.rank, "title", GREEN if result.rank in {"S", "A"} else CYAN, center=(width // 2, 285))
        self.text(f"PERFECT {result.judgments['PERFECT']}   GREAT {result.judgments['GREAT']}   GOOD {result.judgments['GOOD']}   MISS {result.judgments['MISS']}", "body", MUTED, center=(width // 2, 357))
        self.text(f"ACCURACY  {result.accuracy:.2f}%", "body", WHITE, center=(width // 2, 398))
        if is_last:
            self.text("チュートリアル完了。次は PLAY から好きな曲を選びましょう。", "body", GREEN, center=(width // 2, 500))
            self.button("タイトルへ  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), lambda: self.set_screen("title"), accent=GREEN)
        else:
            self.button("次の課題へ  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), lambda: self.start_tutorial_step(self.tutorial_step_index + 1), accent=GREEN)
        self.button("もう一度練習  [R]", pygame.Rect(width // 2 - 190, height - 72, 185, 40), self.retry_game, accent=CYAN)
        self.button("課題一覧へ  [ESC]", pygame.Rect(width // 2 + 5, height - 72, 185, 40), self.return_to_song_select, accent=MUTED)

    def draw_analyzing(self) -> None:
        width, height = self.size
        self.heading("音楽を解析しています", Path(self.song_path).name if self.song_path else "")
        self.panel(pygame.Rect(width // 2 - 310, height // 2 - 60, 620, 155))
        self.text(self.progress.stage, "body", center=(width // 2, height // 2 - 15))
        bar = pygame.Rect(width // 2 - 235, height // 2 + 35, 470, 24)
        pygame.draw.rect(self.surface, (47, 62, 87), bar, border_radius=12)
        pygame.draw.rect(self.surface, CYAN, pygame.Rect(bar.left, bar.top, int(bar.width * self.progress.ratio), bar.height), border_radius=12)
        self.text(f"{self.progress.ratio * 100:.0f}%", "mono", center=(width // 2, height // 2 + 80))

    def draw_difficulty(self) -> None:
        width, height = self.size
        self.heading("難易度選択", Path(self.song_path).name if self.song_path else "")
        if self.analysis:
            self.text(f"推定 BPM: {self.analysis.bpm:.1f}   楽曲長: {self.analysis.duration:.1f} 秒", "body", MUTED, center=(width // 2, 155))
        difficulties = list(Difficulty)
        descriptions = ["拍の骨格だけを叩く", "基本リズム中心", "主要な音を幅広く反映", "細かなリズムと複合入力", "高密度な細部まで反映"]
        for index, difficulty in enumerate(difficulties):
            y = 205 + index * 76
            selected = index == self.selected_difficulty
            rect = pygame.Rect(width // 2 - 280, y, 560, 58)
            self.panel(rect, (37, 57, 88) if selected else PANEL_DARK, 10)
            pygame.draw.rect(self.surface, CYAN if selected else (60, 78, 110), rect, width=2, border_radius=10)
            self.text(difficulty.label, "body", CYAN if selected else WHITE, pos=(rect.left + 24, rect.top + 17))
            self.text(descriptions[index], "small", MUTED, pos=(rect.left + 205, rect.top + 21))
            self.buttons.append((rect, lambda i=index: setattr(self, "selected_difficulty", i)))
        self.button("この難易度でプレイ", pygame.Rect(width // 2 - 190, height - 100, 380, 48), lambda: self.select_chart(difficulties[self.selected_difficulty]), accent=GREEN)
        self.button("楽曲選択へ", pygame.Rect(50, height - 72, 150, 40), lambda: self.set_screen("select"), accent=MUTED)

    def draw_chart_summary(self) -> None:
        if not self.analysis or not self.chart:
            self.set_screen("difficulty")
            return
        width, height = self.size
        summary = build_chart_summary(self.chart, self.analysis)
        variant = int(self.chart.metadata.get("generation_variant", 0)) + 1
        state_label = "試作候補（未保存）" if self.chart_is_pending else "確定譜面"
        self.heading("譜面概要", f"{summary.difficulty_label}  ・  {state_label}  ・  生成候補 {variant}")
        left_panel = pygame.Rect(95, 150, 485, 370)
        right_panel = pygame.Rect(width - 580, 150, 485, 370)
        self.panel(left_panel)
        self.panel(right_panel)
        self.text("楽曲解析", "body", CYAN, pos=(left_panel.left + 28, left_panel.top + 26))
        analysis_rows = [
            ("推定 BPM", f"{summary.bpm:.1f}"),
            ("楽曲長", f"{summary.duration_seconds:.1f} 秒"),
            ("最初の入力", summary.first_note_text),
            ("譜面傾向", summary.tendency),
        ]
        for index, (label, value) in enumerate(analysis_rows):
            y = left_panel.top + 78 + index * 61
            self.text(label, "small", MUTED, pos=(left_panel.left + 30, y))
            self.text(value, "body" if index < 3 else "small", WHITE, pos=(left_panel.left + 180, y - 4))
        self.text("譜面構成", "body", GREEN, pos=(right_panel.left + 28, right_panel.top + 26))
        chart_rows = [
            ("総ノーツ", f"{summary.total_notes}"),
            ("TAP / HOLD", f"{summary.tap_notes} / {summary.hold_notes}"),
            ("平均密度", f"{summary.notes_per_second:.2f} NPS  ({summary.notes_per_minute} / min)"),
            ("最大密度", f"{summary.peak_notes_per_second} notes / sec"),
            ("同時押し", f"{summary.chord_events} 回  (最大 {summary.max_chord_size} 個)"),
            ("安全補正", f"{summary.validation_removed} ノーツ除去 / {summary.validation_issues} 注意"),
            ("自己ベスト", f"{self.current_ranking(limit=1)[0]['score']:,} pts" if self.current_ranking(limit=1) else "記録なし"),
        ]
        for index, (label, value) in enumerate(chart_rows):
            y = right_panel.top + 72 + index * 43
            self.text(label, "small", MUTED, pos=(right_panel.left + 30, y))
            self.text(value, "small", WHITE, pos=(right_panel.left + 170, y))
        self.button("この候補でプレイ  [ENTER]" if self.chart_is_pending else "この譜面でプレイ  [ENTER]", pygame.Rect(width // 2 - 300, height - 122, 290, 50), self.start_game, accent=GREEN)
        self.button("新しい候補を生成  [R]", pygame.Rect(width // 2 + 10, height - 122, 290, 50), self.regenerate_chart, accent=YELLOW)
        if self.chart_is_pending:
            self.button("以前の譜面に戻す  [D]", pygame.Rect(width // 2 - 130, height - 66, 260, 38), self.discard_pending_chart, accent=MAGENTA)
        else:
            self.button("ランキング  [L]", pygame.Rect(width // 2 - 130, height - 66, 260, 38), self.open_ranking, accent=MAGENTA)
        self.button("難易度選択へ  [ESC]", pygame.Rect(45, height - 70, 190, 40), lambda: self.set_screen("difficulty"), accent=MUTED)

    def draw_ranking(self) -> None:
        if self.chart is None:
            self.set_screen("title")
            return
        width, height = self.size
        entries = self.current_ranking()
        self.heading("LOCAL RANKING", f"{self.chart.difficulty.label}  ・  この曲と難易度の自己ベスト上位10件")
        panel = pygame.Rect(width // 2 - 430, 145, 860, 430)
        self.panel(panel)
        headers = [("#", 58), ("SCORE", 125), ("ACCURACY", 345), ("MAX COMBO", 540), ("RANK", 735)]
        for label, x in headers:
            self.text(label, "small", MUTED, pos=(panel.left + x, panel.top + 22))
        pygame.draw.line(self.surface, (66, 84, 118), (panel.left + 28, panel.top + 52), (panel.right - 28, panel.top + 52), 1)
        if not entries:
            self.text("この譜面のプレイ記録はまだありません。", "body", MUTED, center=(width // 2, panel.centery))
        for index, entry in enumerate(entries):
            y = panel.top + 66 + index * 35
            if index % 2 == 0:
                self.panel(pygame.Rect(panel.left + 20, y - 4, panel.width - 40, 29), PANEL_DARK, 5)
            self.text(f"{index + 1}", "mono", YELLOW if index == 0 else WHITE, pos=(panel.left + 60, y))
            self.text(f"{int(entry.get('score', 0)):,}", "mono", CYAN if index == 0 else WHITE, pos=(panel.left + 125, y))
            self.text(f"{float(entry.get('accuracy', 0.0)):.2f}%", "small", WHITE, pos=(panel.left + 345, y + 2))
            self.text(str(int(entry.get('max_combo', 0))), "mono", WHITE, pos=(panel.left + 560, y))
            rank_label = str(entry.get("rank", "D"))
            self.text(rank_label, "mono", GREEN if rank_label == "S" else WHITE, pos=(panel.left + 750, y))
        self.button("譜面概要へ  [ESC]", pygame.Rect(width // 2 - 160, height - 80, 320, 44), lambda: self.set_screen("chart_summary"), accent=MAGENTA)

    def draw_game(self) -> None:
        if not self.session or not self.chart:
            self.set_screen("title")
            return
        width, height = self.size
        left, field_width, lane_width, field_top, line_y = self._game_field_geometry()
        counting_down = self.countdown_active
        now = self.gameplay_time() if not counting_down else 0.0
        for lane in range(5):
            x = left + lane * lane_width
            color = self.lane_colors[lane]
            pygame.draw.rect(self.surface, (18, 28, 48), pygame.Rect(x, field_top, lane_width - 2, line_y - field_top))
            pygame.draw.line(self.surface, tuple(channel // 3 for channel in color), (x, field_top), (x, line_y), 1)
            self.text(self.settings["keys"][lane].upper(), "mono", color, center=(x + lane_width // 2, line_y + 30))
        pygame.draw.line(self.surface, WHITE, (left, line_y), (left + field_width, line_y), 3)
        speed = self.effective_note_speed
        if not counting_down:
            for state in self.session.states:
                if state.complete:
                    continue
                note = state.note
                y = line_y - (note.time - now) * speed
                x = left + note.lane * lane_width + 7
                cap_width = lane_width - 14
                cap_height = 18
                lane_color = self.lane_colors[note.lane]
                if note.kind.value == "hold" and note.end_time is not None:
                    end_y = line_y - (note.end_time - now) * speed
                    # 始点または終点のどちらかが見えている間は描画を続ける。
                    # 押下済みの始点が画面外へ抜けても、終端キャップを残して離す位置を示す。
                    if max(y, end_y) < field_top - 15 or min(y, end_y) > height + 40:
                        continue
                    top, bottom = sorted((int(y), int(end_y)))
                    rail_color = tuple(max(0, channel // 2) for channel in lane_color)
                    pygame.draw.rect(self.surface, rail_color, pygame.Rect(x + lane_width // 2 - 9, top, 18, max(8, bottom - top)), border_radius=8)
                    # 終端は通常ノーツと同じ大きさのキャップにし、淡い輪郭で「ここで離す」を示す。
                    if field_top - cap_height <= end_y <= height + cap_height:
                        end_cap = pygame.Rect(x, int(end_y) - cap_height // 2, cap_width, cap_height)
                        pygame.draw.rect(self.surface, lane_color, end_cap, border_radius=7)
                        end_outline = tuple(min(255, channel + 70) for channel in lane_color)
                        pygame.draw.rect(self.surface, end_outline, end_cap, width=2, border_radius=7)
                    if field_top - cap_height <= y <= height + cap_height:
                        pygame.draw.rect(self.surface, lane_color, pygame.Rect(x, int(y) - cap_height // 2, cap_width, cap_height), border_radius=7)
                else:
                    if y < field_top - 15 or y > height + 40:
                        continue
                    pygame.draw.rect(self.surface, lane_color, pygame.Rect(x, int(y) - cap_height // 2, cap_width, cap_height), border_radius=7)
        self._draw_hit_effects(left, lane_width, line_y)
        self.text(f"SCORE  {self.session.score:07d}", "mono", pos=(45, 45))
        self.text(f"COMBO  {self.session.combo}", "mono", YELLOW, pos=(45, 75))
        self.text(f"{now:.1f} / {self.chart.song_duration:.1f}", "mono", MUTED, pos=(width - 190, 45))
        self.text("TUTORIAL" if self.tutorial_active else self.chart.difficulty.label, "mono", GREEN if self.tutorial_active else CYAN, pos=(width - 150, 75))
        if self.tutorial_active:
            self.text(str(self.chart.metadata.get("tutorial_instruction", "")), "small", GREEN, center=(width // 2, 34))
        if self.playfield_mode_key == "tall":
            self.text("TALL FOCUS  •  LOOKAHEAD +29%", "small", GREEN, pos=(width - 225, 105))
        if counting_down:
            self.panel(pygame.Rect(width // 2 - 170, height // 2 - 105, 340, 210), (20, 30, 51), 18)
            self.text(str(max(1, math.ceil(self._countdown_remaining()))), "title", CYAN, center=(width // 2, height // 2 - 28))
            self.text("準備してください", "body", WHITE, center=(width // 2, height // 2 + 42))
            self.text("ESC で楽曲選択へ戻る", "small", MUTED, center=(width // 2, height // 2 + 75))
        elif time.perf_counter() < self.start_banner_until:
            self.text("START!", "title", GREEN, center=(width // 2, height // 2))
        elif self.session.latest_judgment:
            self.text(self.session.latest_judgment.value, "h1", JUDGMENT_COLORS[self.session.latest_judgment], center=(width // 2, height // 2))
        if time.perf_counter() < self.combo_banner_until:
            self.text(self.combo_banner, "title", MAGENTA, center=(width // 2, height // 2 - 75))
        if self.game_paused:
            self.panel(pygame.Rect(width // 2 - 205, height // 2 - 130, 410, 260), (25, 35, 58), 16)
            self.text("PAUSED", "h1", YELLOW, center=(width // 2, height // 2 - 90))
            self.button("再開  [ESC]", pygame.Rect(width // 2 - 160, height // 2 - 48, 320, 42), self.toggle_pause, accent=GREEN)
            self.button("リトライ  [R]", pygame.Rect(width // 2 - 160, height // 2 + 6, 320, 42), self.retry_game, accent=CYAN)
            self.button("チュートリアルへ  [Q]" if self.tutorial_active else "楽曲選択へ  [Q]", pygame.Rect(width // 2 - 160, height // 2 + 60, 320, 42), self.return_to_song_select, accent=MUTED)

    def draw_result(self) -> None:
        if not self.session:
            self.set_screen("title")
            return
        result = self.session.result()
        width, height = self.size
        self.heading("RESULT", self.chart.difficulty.label if self.chart else "")
        self.text(result.rank, "title", CYAN, center=(width // 2, 205))
        self.text(f"SCORE  {result.score:07d}", "h1", center=(width // 2, 280))
        self.text(f"MAX COMBO  {result.max_combo}     ACCURACY  {result.accuracy:.2f}%", "body", MUTED, center=(width // 2, 325))
        last_ranking = self.profile.get("last_play_ranking", {})
        if isinstance(last_ranking, dict) and last_ranking.get("chart_key") == result.chart_hash:
            position = int(last_ranking.get("position", 0))
            if last_ranking.get("new_high_score"):
                self.text("NEW HIGH SCORE!", "body", GREEN, center=(width // 2, 352))
            elif position > 0:
                self.text(f"LOCAL RANK  #{position}", "small", MAGENTA, center=(width // 2, 352))
        labels = ["PERFECT", "GREAT", "GOOD", "MISS"]
        for index, label in enumerate(labels):
            self.panel(pygame.Rect(width // 2 - 320 + index * 165, 380, 150, 78))
            self.text(label, "small", MUTED, center=(width // 2 - 245 + index * 165, 405))
            self.text(str(result.judgments[label]), "h1", center=(width // 2 - 245 + index * 165, 435))
        self.draw_reward_progress(pygame.Rect(width // 2 - 320, 478, 640, 76), compact=True)
        if self.chart_is_pending:
            self.panel(pygame.Rect(width // 2 - 385, height - 190, 770, 46), (44, 61, 92), 10)
            self.text("試作候補をプレイしました。どちらを残しますか？", "body", YELLOW, center=(width // 2, height - 167))
            self.button("この候補を採用・保存  [A]", pygame.Rect(width // 2 - 350, height - 132, 335, 42), self.adopt_pending_chart, accent=GREEN)
            self.button("以前の譜面を残す  [D]", pygame.Rect(width // 2 + 15, height - 132, 335, 42), self.discard_pending_chart, accent=MAGENTA)
            self.button("候補をもう一度プレイ", pygame.Rect(width // 2 - 230, height - 78, 220, 40), self.start_game, accent=CYAN)
            self.button("タイトルへ", pygame.Rect(width // 2 + 10, height - 78, 220, 40), lambda: self.set_screen("title"), accent=MUTED)
        else:
            self.button("もう一度プレイ", pygame.Rect(width // 2 - 300, height - 125, 190, 48), self.start_game, accent=GREEN)
            self.button("ランキング", pygame.Rect(width // 2 - 95, height - 125, 190, 48), self.open_ranking, accent=MAGENTA)
            self.button("タイトルへ", pygame.Rect(width // 2 + 110, height - 125, 190, 48), lambda: self.set_screen("title"), accent=MUTED)

    def draw_unlock(self) -> None:
        width, height = self.size
        self.heading("NEW IMAGE UNLOCKED", "累積スコアにより新しいご褒美画像を解放しました")
        self.text("解放済み", "h1", MAGENTA, center=(width // 2, 195))
        for index, name in enumerate(self.newly_unlocked[:3]):
            self.text(name, "body", center=(width // 2, 245 + index * 32))
        unlocked_lookup = {reward.name: reward for reward in self.gallery_rewards()}
        first_reward = unlocked_lookup.get(self.newly_unlocked[0]) if self.newly_unlocked else None
        if first_reward is not None:
            preview = self._load_scaled_reward(first_reward, 300, 190)
            if preview is not None:
                self.surface.blit(preview, preview.get_rect(center=(width // 2, 390)))
        self.draw_reward_progress(pygame.Rect(width // 2 - 280, 492, 560, 76), compact=True)
        self.button("ギャラリーで見る", pygame.Rect(width // 2 - 170, height - 118, 340, 42), lambda: self.set_screen("gallery"), accent=MAGENTA)
        self.button("リザルトを見る", pygame.Rect(width // 2 - 170, height - 66, 340, 38), lambda: self.set_screen("result"), accent=CYAN)

    def draw_gallery(self) -> None:
        width, height = self.size
        rewards = self.gallery_rewards()
        page_size = 8
        page_count = max(1, math.ceil(len(rewards) / page_size))
        self.gallery_page = max(0, min(self.gallery_page, page_count - 1))
        status = self.reward_status()
        next_text = "全画像を解放済み" if status.next_reward is None else f"次: {status.next_reward.name} まで {status.remaining_score:,} pts"
        self.heading("GALLERY", f"累積 {status.lifetime_score:,} pts  ·  解放 {status.unlocked_count}/{status.reward_count}  ·  {next_text}")
        if not rewards:
            self.text("rewards フォルダへ PNG / JPEG / WebP を追加してください。", "body", MUTED, center=(width // 2, height // 2 - 20))
            self.text("reward_config.json で必要累積スコアを設定できます。", "small", MUTED, center=(width // 2, height // 2 + 20))
        else:
            cards_per_row = 4
            for local_index, reward in enumerate(rewards[self.gallery_page * page_size : (self.gallery_page + 1) * page_size]):
                col, row = local_index % cards_per_row, local_index // cards_per_row
                rect = pygame.Rect(95 + col * 275, 155 + row * 230, 235, 195)
                self.panel(rect)
                if reward.unlocked:
                    image = self._load_scaled_reward(reward, rect.width - 18, rect.height - 55)
                    if image:
                        self.surface.blit(image, image.get_rect(center=(rect.centerx, rect.top + 72)))
                    else:
                        self.text("読み込み失敗", "small", RED, center=(rect.centerx, rect.top + 70))
                else:
                    pygame.draw.circle(self.surface, (58, 70, 94), (rect.centerx, rect.top + 70), 34)
                    pygame.draw.rect(self.surface, (92, 106, 137), pygame.Rect(rect.centerx - 18, rect.top + 70, 36, 28), border_radius=5)
                    pygame.draw.arc(self.surface, (92, 106, 137), pygame.Rect(rect.centerx - 15, rect.top + 46, 30, 34), math.pi, 2 * math.pi, 4)
                    self.text("LOCKED", "small", (180, 190, 210), center=(rect.centerx, rect.top + 120))
                required = "条件未設定" if reward.required_score is None else f"{reward.required_score:,} pts"
                self.text(reward.name, "small", WHITE if reward.unlocked else MUTED, center=(rect.centerx, rect.bottom - 35))
                self.text(required, "small", MUTED, center=(rect.centerx, rect.bottom - 16))
                self.buttons.append((rect, lambda selected=reward: self.open_reward(selected)))
        if page_count > 1:
            self.button("← 前へ", pygame.Rect(width // 2 - 220, height - 72, 180, 40), lambda: setattr(self, "gallery_page", max(0, self.gallery_page - 1)), accent=MAGENTA)
            self.button("次へ →", pygame.Rect(width // 2 + 40, height - 72, 180, 40), lambda: setattr(self, "gallery_page", min(page_count - 1, self.gallery_page + 1)), accent=MAGENTA)
        self.button("タイトルへ", pygame.Rect(45, height - 72, 150, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_gallery_preview(self) -> None:
        width, height = self.size
        reward = self.selected_reward
        if reward is None or not reward.unlocked:
            self.set_screen("gallery")
            return
        self.heading("GALLERY PREVIEW", reward.name)
        self.panel(pygame.Rect(80, 145, width - 160, height - 255))
        image = self._load_scaled_reward(reward, width - 220, height - 350)
        if image:
            self.surface.blit(image, image.get_rect(center=(width // 2, height // 2 - 10)))
        else:
            self.text("画像を読み込めませんでした。", "body", RED, center=(width // 2, height // 2))
        if reward.required_score is not None:
            self.text(f"解放条件: 累積 {reward.required_score:,} pts", "small", MUTED, center=(width // 2, height - 95))
        self.button("ギャラリーへ戻る", pygame.Rect(width // 2 - 160, height - 65, 320, 42), lambda: self.set_screen("gallery"), accent=MAGENTA)

    def _settings_rows(self) -> list[tuple[str, str]]:
        windows = self.settings["judgment_windows_ms"]
        return [
            ("音楽音量", f"{self.settings['music_volume'] * 100:.0f}%"),
            ("効果音音量", f"{self.settings['sfx_volume'] * 100:.0f}%"),
            ("ノーツ速度", f"{self.settings['note_speed']:.0f}"),
            ("プレイ表示", self.playfield_mode_label),
            ("Timing Offset", f"{self.settings['timing_offset_ms']} ms"),
            ("判定幅 PERFECT", f"{windows['perfect']} ms"),
            ("判定幅 GREAT", f"{windows['great']} ms"),
            ("判定幅 GOOD", f"{windows['good']} ms"),
            ("ノーツ配色", self.note_theme_label),
            ("フルスクリーン", "ON" if self.settings["fullscreen"] else "OFF"),
            ("解像度", f"{self.settings['resolution'][0]} x {self.settings['resolution'][1]}"),
            ("入力タイミング測定", "ENTER"),
        ]

    def draw_settings(self) -> None:
        width, height = self.size
        self.heading("SETTINGS", "↑↓で項目選択、←→で変更。プレイ表示・ノーツ配色はENTERでも切替、入力タイミング測定はENTERで開始")
        self.panel(pygame.Rect(width // 2 - 390, 135, 780, 495))
        for index, (name, value) in enumerate(self._settings_rows()):
            y = 145 + index * 31
            rect = pygame.Rect(width // 2 - 360, y, 720, 30)
            selected = index == self.settings_selection
            if selected:
                self.panel(rect, (44, 61, 92), 6)
                pygame.draw.rect(self.surface, CYAN, rect, width=1, border_radius=6)
            self.text(name, "small" if index >= 4 else "body", pos=(rect.left + 16, rect.top + (6 if index >= 4 else 3)))
            self.text(value, "mono", CYAN if selected else WHITE, pos=(rect.left + 470, rect.top + 5))
            self.buttons.append((rect, lambda selected_index=index: setattr(self, "settings_selection", selected_index)))
        self.text("KEY CONFIG", "body", YELLOW, pos=(width // 2 - 360, 523))
        for lane, name in enumerate(LANE_NAMES):
            y = 555 + (lane // 3) * 40
            x = width // 2 - 360 + (lane % 3) * 240
            rect = pygame.Rect(x, y, 215, 32)
            self.panel(rect, (52, 46, 73) if self.key_capture_lane == lane else PANEL_DARK, 8)
            self.text(f"{name}: {self.settings['keys'][lane].upper()}", "small", center=rect.center)
            self.buttons.append((rect, lambda selected=lane: setattr(self, "key_capture_lane", selected)))
        self.button("設定を保存", pygame.Rect(width // 2 - 175, 638, 350, 42), self.persist_settings, accent=GREEN)
        self.button("タイトルへ", pygame.Rect(45, height - 65, 150, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_calibration(self) -> None:
        width, height = self.size
        calibration = self.calibration
        if calibration is None:
            self.set_screen("settings")
            return
        self.heading("INPUT TIMING CALIBRATION", "クリック音に合わせて SPACE を押してください。人の反応のばらつきは中央値でならします")
        self.panel(pygame.Rect(width // 2 - 390, 145, 780, 425), PANEL, 16)
        now = time.perf_counter()
        elapsed = max(0.0, now - calibration.started_at)
        current_phase = elapsed % calibration.interval_seconds if now >= calibration.started_at else 0.0
        pulse = 0.45 + 0.55 * (1.0 - min(1.0, current_phase / calibration.interval_seconds))
        radius = int(48 + 24 * pulse)
        pygame.draw.circle(self.surface, (38, 61, 91), (width // 2, 265), radius + 10)
        pygame.draw.circle(self.surface, CYAN, (width // 2, 265), radius, width=4)
        self.text("CLICK", "h1", CYAN, center=(width // 2, 265))
        self.text("SPACE", "body", WHITE, center=(width // 2, 340))
        for index in range(calibration.sample_target):
            x = width // 2 - 180 + index * 40
            color = GREEN if index < len(calibration.offsets_ms) else (59, 74, 103)
            pygame.draw.circle(self.surface, color, (x, 395), 11)
        self.text(f"入力: {len(calibration.offsets_ms)} / {calibration.sample_target}", "body", center=(width // 2, 430))
        latest = calibration.latest_offset_ms
        if latest is not None:
            self.text(f"直近のずれ: {latest:+d} ms", "small", MUTED, center=(width // 2, 462))
        recommendation = calibration.recommendation_ms
        if recommendation is None:
            self.text("最初の2回はリズムに慣れるためのウォームアップです。", "small", MUTED, center=(width // 2, 502))
            self.text("ESC: 設定へ戻る", "small", MUTED, center=(width // 2, height - 78))
        else:
            self.panel(pygame.Rect(width // 2 - 260, 485, 520, 54), (34, 67, 75), 10)
            self.text(f"推奨 Timing Offset: {recommendation:+d} ms", "body", GREEN, center=(width // 2, 512))
            self.text("A または ENTER: 適用    R: やり直す    ESC: 設定へ戻る", "small", WHITE, center=(width // 2, height - 78))

    def _apply_display_settings(self) -> None:
        width, height = self.settings["resolution"]
        flags = pygame.FULLSCREEN if self.settings["fullscreen"] else 0
        self.surface = pygame.display.set_mode((int(width), int(height)), flags)

    def adjust_setting(self, direction: int) -> None:
        if direction == 0:
            return
        windows = self.settings["judgment_windows_ms"]
        index = self.settings_selection
        if index == 0:
            self.settings["music_volume"] = max(0.0, min(1.0, round(float(self.settings["music_volume"]) + 0.05 * direction, 2)))
            if self.audio_available:
                self.audio.set_volume(float(self.settings["music_volume"]))
        elif index == 1:
            self.settings["sfx_volume"] = max(0.0, min(1.0, round(float(self.settings["sfx_volume"]) + 0.05 * direction, 2)))
            self._set_sfx_volume()
        elif index == 2:
            self.settings["note_speed"] = max(250, min(1200, float(self.settings["note_speed"]) + 25 * direction))
        elif index == 3:
            modes = list(PLAYFIELD_MODES)
            current_mode = self.playfield_mode_key
            current_index = modes.index(current_mode)
            self.settings["playfield_mode"] = modes[(current_index + direction) % len(modes)]
        elif index == 4:
            self.settings["timing_offset_ms"] = max(-200, min(200, int(self.settings["timing_offset_ms"]) + 5 * direction))
        elif index == 5:
            windows["perfect"] = max(15, min(windows["great"] - 5, int(windows["perfect"]) + 5 * direction))
        elif index == 6:
            windows["great"] = max(windows["perfect"] + 5, min(windows["good"] - 5, int(windows["great"]) + 5 * direction))
        elif index == 7:
            windows["good"] = max(windows["great"] + 5, min(250, int(windows["good"]) + 5 * direction))
        elif index == 8:
            themes = list(NOTE_THEMES)
            current_theme = self.note_theme_key
            current_index = themes.index(current_theme)
            self.settings["note_theme"] = themes[(current_index + direction) % len(themes)]
        elif index == 9:
            self.settings["fullscreen"] = not self.settings["fullscreen"]
            self._apply_display_settings()
        elif index == 10:
            current = tuple(self.settings["resolution"])
            try:
                resolution_index = RESOLUTION_PRESETS.index(current)
            except ValueError:
                resolution_index = 0
            resolution_index = (resolution_index + direction) % len(RESOLUTION_PRESETS)
            self.settings["resolution"] = list(RESOLUTION_PRESETS[resolution_index])
            if not self.settings["fullscreen"]:
                self._apply_display_settings()
        self.message = "設定を変更しました。保存してください。"

    def persist_settings(self) -> None:
        try:
            save_settings(self.paths, self.settings)
            self.message = "設定を保存しました。"
            self.error = ""
        except ValueError as error:
            self.error = str(error)

    def set_screen(self, screen: str) -> None:
        self.screen = screen
        self.error = ""
        self.key_capture_lane = None

    def draw_overlay(self) -> None:
        width, _ = self.size
        if self.message:
            self.text(self.message, "small", GREEN, center=(width // 2, 125))
        if self.error:
            self.panel(pygame.Rect(width // 2 - 430, 124, 860, 44), (82, 31, 43), 8)
            self.text(self.error, "small", RED, center=(width // 2, 146))

    def draw(self) -> None:
        self.surface.fill(BG)
        self.buttons = []
        {
            "title": self.draw_title,
            "select": self.draw_select,
            "library": self.draw_library,
            "tutorial": self.draw_tutorial,
            "tutorial_result": self.draw_tutorial_result,
            "analyzing": self.draw_analyzing,
            "difficulty": self.draw_difficulty,
            "chart_summary": self.draw_chart_summary,
            "ranking": self.draw_ranking,
            "game": self.draw_game,
            "result": self.draw_result,
            "unlock": self.draw_unlock,
            "gallery": self.draw_gallery,
            "gallery_preview": self.draw_gallery_preview,
            "settings": self.draw_settings,
            "calibration": self.draw_calibration,
        }[self.screen]()
        if self.screen not in {"title", "game", "calibration"}:
            self.draw_overlay()
        pygame.display.flip()

    def key_event(self, event: pygame.event.Event) -> None:
        key = pygame.key.name(event.key).lower()
        if self.key_capture_lane is not None:
            if key in self.settings["keys"]:
                self.error = "同じキーを複数レーンには割り当てられません。"
            elif key not in {"escape", "return"}:
                self.settings["keys"][self.key_capture_lane] = key
                self.key_capture_lane = None
                self.message = "キーを変更しました。保存してください。"
            return
        if self.screen == "title":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.set_screen("select")
            elif event.key == pygame.K_t:
                self.set_screen("tutorial")
            elif event.key == pygame.K_g:
                self.set_screen("gallery")
            elif event.key == pygame.K_s:
                self.set_screen("settings")
        elif self.screen == "select":
            if event.key == pygame.K_l:
                self.open_library()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("title")
        elif self.screen == "library":
            if event.key == pygame.K_UP:
                self.move_library_selection(-1)
            elif event.key == pygame.K_DOWN:
                self.move_library_selection(1)
            elif event.key == pygame.K_PAGEUP:
                self.move_library_selection(-LIBRARY_VISIBLE_ROWS)
            elif event.key == pygame.K_PAGEDOWN:
                self.move_library_selection(LIBRARY_VISIBLE_ROWS)
            elif event.key == pygame.K_HOME:
                self.library_selected_index = 0
                self._clamp_library_position()
            elif event.key == pygame.K_END:
                self.library_selected_index = max(0, len(self.library_entries()) - 1)
                self._clamp_library_position()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_current_library_entry()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("select")
        elif self.screen == "tutorial":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_tutorial()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("title")
        elif self.screen == "tutorial_result":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.tutorial_step_index == len(TUTORIAL_STEPS) - 1:
                    self.set_screen("title")
                elif self.tutorial_step_index is not None:
                    self.start_tutorial_step(self.tutorial_step_index + 1)
            elif event.key == pygame.K_r:
                self.retry_game()
            elif event.key == pygame.K_ESCAPE:
                self.return_to_song_select()
        elif self.screen == "difficulty":
            if event.key == pygame.K_UP:
                self.selected_difficulty = max(0, self.selected_difficulty - 1)
            elif event.key == pygame.K_DOWN:
                self.selected_difficulty = min(4, self.selected_difficulty + 1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_chart(list(Difficulty)[self.selected_difficulty])
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("select")
        elif self.screen == "chart_summary":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_game()
            elif event.key == pygame.K_r:
                self.regenerate_chart()
            elif event.key == pygame.K_d and self.chart_is_pending:
                self.discard_pending_chart()
            elif event.key == pygame.K_l and not self.chart_is_pending:
                self.open_ranking()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("difficulty")
        elif self.screen == "ranking":
            if event.key == pygame.K_ESCAPE:
                self.set_screen("chart_summary")
        elif self.screen == "result" and self.chart_is_pending:
            if event.key == pygame.K_a:
                self.adopt_pending_chart()
            elif event.key == pygame.K_d:
                self.discard_pending_chart()
        elif self.screen == "settings":
            if event.key == pygame.K_UP:
                self.settings_selection = (self.settings_selection - 1) % len(self._settings_rows())
            elif event.key == pygame.K_DOWN:
                self.settings_selection = (self.settings_selection + 1) % len(self._settings_rows())
            elif event.key == pygame.K_LEFT:
                self.adjust_setting(-1)
            elif event.key == pygame.K_RIGHT:
                self.adjust_setting(1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.settings_selection in (3, 8):
                self.adjust_setting(1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.settings_selection == 11:
                self.begin_calibration()
            elif event.key == pygame.K_ESCAPE:
                self.persist_settings()
                self.set_screen("title")
        elif self.screen == "calibration":
            if event.key == pygame.K_ESCAPE:
                self.calibration = None
                self.set_screen("settings")
            elif self.calibration and self.calibration.recommendation_ms is not None and event.key in (pygame.K_a, pygame.K_RETURN):
                self.apply_calibration()
            elif event.key == pygame.K_r:
                self.begin_calibration()
            elif event.key == pygame.K_SPACE and self.calibration:
                offset = self.calibration.record_press(time.perf_counter())
                if offset is not None:
                    self.message = f"入力を記録しました: {offset:+.0f} ms"
        elif self.screen == "gallery":
            if event.key == pygame.K_LEFT:
                self.gallery_page = max(0, self.gallery_page - 1)
            elif event.key == pygame.K_RIGHT:
                self.gallery_page += 1
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("title")
        elif self.screen == "gallery_preview":
            if event.key == pygame.K_ESCAPE:
                self.set_screen("gallery")
        elif self.screen == "game":
            if self.countdown_active:
                if event.key == pygame.K_ESCAPE:
                    self.return_to_song_select()
                return
            if self.game_paused:
                if event.key == pygame.K_ESCAPE:
                    self.toggle_pause()
                elif event.key == pygame.K_r:
                    self.retry_game()
                elif event.key == pygame.K_q:
                    self.return_to_song_select()
            elif event.key == pygame.K_ESCAPE:
                self.toggle_pause()
            else:
                try:
                    lane = self.settings["keys"].index(key)
                except ValueError:
                    return
                self._play_feedback(self.session.press(lane, self.gameplay_time()) if self.session else None, lane)
        elif event.key == pygame.K_ESCAPE:
            self.set_screen("title")

    def key_up_event(self, event: pygame.event.Event) -> None:
        if self.screen != "game" or not self.session or self.game_paused:
            return
        key = pygame.key.name(event.key).lower()
        try:
            lane = self.settings["keys"].index(key)
        except ValueError:
            return
        self._play_feedback(self.session.release(lane, self.gameplay_time()), lane)

    def update_game(self) -> None:
        if self.screen != "game" or not self.session:
            return
        if self.countdown_active:
            return
        if self.countdown_started_at is not None:
            try:
                self._start_after_countdown()
            except AudioClockError as error:
                self.error = str(error)
                self.screen = "tutorial" if self.tutorial_active else "difficulty"
            return
        if self.game_paused:
            return
        current_time = self.gameplay_time()
        if self.tutorial_active:
            self.update_tutorial_metronome(current_time)
        for judgment in self.session.tick(current_time):
            self._play_feedback(judgment)
        if self.tutorial_active:
            if current_time >= self.chart.song_duration:
                self.finish_game()
            return
        # 最後のノーツが判定済みでも、曲末の余韻・無音区間・アウトロは再生し切る。
        # session.finished は譜面の終了、audio.finished は音源そのものの終了を表す。
        if self.audio.finished:
            self.audio.stop()
            self.finish_game()

    def run(self) -> None:
        while self.running:
            self.poll_worker()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.MOUSEWHEEL and self.screen == "library":
                    self.scroll_library(-event.y)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    for rect, action in self.buttons:
                        if rect.collidepoint(event.pos):
                            action()
                            break
                elif event.type == pygame.KEYDOWN:
                    self.key_event(event)
                elif event.type == pygame.KEYUP:
                    self.key_up_event(event)
            self.update_calibration()
            self.update_game()
            self.draw()
            self.clock.tick(120)
        self.persist_settings()
        pygame.quit()


def main() -> None:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    AutoBeatApp().run()


if __name__ == "__main__":
    main()
