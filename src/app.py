"""AutoBeat 5 のPygameアプリケーション。"""
from __future__ import annotations

import json
import math
from bisect import bisect_left, bisect_right
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
from chart_generator import CHART_STYLE_LABELS, ChartGenerator
from chart_summary import build_chart_summary
from chart_validator import ChartValidator
from chart_balance import balance_chart
from gameplay import GameSession, JudgmentWindows
from mascots import Mascot, find_mascot, load_mascot_catalog
from mascot_dialogue import mascot_result_line
from title_scene import TitleScene
from models import AnalysisResult, Chart, Difficulty, Judgment, LANE_KEY_PRESETS, LANE_NAMES_BY_COUNT, Note, PlayResult, chart_key, chart_lane_count
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
    lane_feature_id,
    mascot_cosmetic_id,
    mascot_required_score,
    is_feature_unlocked,
    is_cosmetic_unlocked,
    is_mascot_unlocked,
    purchase_unlock,
    reward_thresholds,
    materialize_unlocked_rewards,
    unlock_score_cosmetics,
    unlock_tutorial_cosmetics,
    cosmetic_id,
    active_library_folder,
    assign_recent_song_folder,
    library_folders,
    normalize_library_folder_name,
    record_recent_song,
    set_active_library_folder,
    save_analysis,
    save_chart,
    save_profile,
    save_settings,
)
from rewards import RewardCatalogItem, RewardImage, RewardProgress, ensure_reward_template, reward_catalog, reward_progress, scan_rewards
from tutorial import TUTORIAL_BEAT_SECONDS, TUTORIAL_STEPS, build_tutorial_chart, tutorial_steps, optional_tutorial_steps


GAME_TITLE = "オトアソビ"
GAME_TAGLINE = "好きな曲を、遊ぼう。"
WINDOW_TITLE = f"{GAME_TITLE} - {GAME_TAGLINE}"
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
NOTE_SKINS: dict[str, tuple[str, str]] = {
    "standard": ("STANDARD", "現行互換の丸角バー"),
    "glow": ("GLOW", "発光でPERFECT感を強める"),
    "crystal": ("CRYSTAL", "透明感のある結晶風"),
    "arcade": ("ARCADE", "太い輪郭のレトロゲーム風"),
    "minimal": ("MINIMAL", "細いラインで視認性重視"),
    "pixel": ("PIXEL", "ドット感のあるブロック形状"),
    "heart": ("HEART", "かわいい報酬向けハート"),
    "star": ("STAR", "達成感の強い星形"),
    "diamond": ("DIAMOND", "鋭いひし形ノーツ"),
    "ribbon_hold": ("RIBBON HOLD", "長押しをリボン状に強調"),
    "neon_line": ("NEON LINE", "細い光線の近未来風"),
    "accessible": ("ACCESSIBLE", "白枠と形で見分けやすい"),
}
SFX_THEMES: dict[str, tuple[str, dict[Judgment, tuple[float, float, str]]]] = {
    "classic": (
        "CLASSIC",
        {
            Judgment.PERFECT: (880, 0.045, "sine"),
            Judgment.GREAT: (720, 0.045, "sine"),
            Judgment.GOOD: (540, 0.045, "sine"),
            Judgment.MISS: (180, 0.070, "sine"),
        },
    ),
    "crystal": (
        "CRYSTAL",
        {
            Judgment.PERFECT: (1320, 0.055, "bell"),
            Judgment.GREAT: (1050, 0.052, "bell"),
            Judgment.GOOD: (820, 0.050, "bell"),
            Judgment.MISS: (240, 0.090, "soft_noise"),
        },
    ),
    "arcade": (
        "ARCADE",
        {
            Judgment.PERFECT: (1040, 0.040, "square"),
            Judgment.GREAT: (860, 0.040, "square"),
            Judgment.GOOD: (650, 0.045, "triangle"),
            Judgment.MISS: (140, 0.095, "buzz"),
        },
    ),
    "soft": (
        "SOFT",
        {
            Judgment.PERFECT: (760, 0.060, "triangle"),
            Judgment.GREAT: (640, 0.055, "triangle"),
            Judgment.GOOD: (500, 0.055, "triangle"),
            Judgment.MISS: (220, 0.085, "soft_noise"),
        },
    ),
}
# 既存のテスト・外部拡張との互換性を保つ標準テーマの別名。
LANE_COLORS = NOTE_THEMES["standard"][1]
BASE_RENDER_SIZE = (1280, 720)
RESOLUTION_PRESETS = ((960, 540), (1024, 576), (1280, 720), (1600, 900), (1920, 1080))
COMBO_MILESTONES = tuple(range(50, 501, 50))
COUNTDOWN_SECONDS = 3.0
TRIAL_PLAY_LIMIT_SECONDS = 60.0
TRIAL_FADE_SECONDS = 2.0
PLAYFIELD_MODES: dict[str, tuple[str, float]] = {
    "standard": ("STANDARD", 1.0),
    # 判定時刻は変えず、表示上の到達速度を抑えて先読み時間を増やす。
    "tall": ("TALL FOCUS", 0.82),
}
LANE_VIEW_MODES: dict[str, str] = {
    "classic": "CLASSIC",
    "perspective": "3D DEPTH",
}
MASCOT_MODES: dict[str, tuple[str, float]] = {
    "off": ("OFF", 0.0),
    "subtle": ("SUBTLE", 0.55),
    "standard": ("STANDARD", 1.0),
}
LANE_COUNT_OPTIONS = (3, 5, 7)
LANE_COUNT_LABELS = {3: "3 LANE", 5: "5 LANE", 7: "7 LANE"}
BACKGROUND_MODES: dict[str, str] = {
    "visualizer": "VISUALIZER",
    "image": "IMAGE",
    "off": "OFF",
}
JUDGMENT_COLORS = {Judgment.PERFECT: CYAN, Judgment.GREAT: GREEN, Judgment.GOOD: YELLOW, Judgment.MISS: RED}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FULL_COMBO_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | {".gif"}
COMBO_CUTIN_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | {".gif"}
LIBRARY_VISIBLE_ROWS = 6
LIBRARY_ROW_HEIGHT = 72
PLAYLIST_VISIBLE_ROWS = 7
PLAYLIST_ROW_HEIGHT = 62
PRACTICE_MIN_DURATION = 3.0
PRACTICE_DEFAULT_DURATION = 12.0
REWARD_MANAGER_VISIBLE_ROWS = 6
REWARD_MANAGER_ROW_HEIGHT = 58
JUDGMENT_FEEDBACK_DURATION = 0.60
JUDGMENT_LOG_DURATION = 3.20
JUDGMENT_LOG_LIMIT = 8
PERFECT_LANE_FLASH_DURATION = 0.28
HOLD_SPARK_ALPHA = 92
HOLD_PARTICLE_LIMIT = 21
MASCOT_COMBO_ZOOM_DURATION = 0.72
COMBO_CUTIN_DURATION = 1.15
VISUALIZER_ALPHA = 72
VISUALIZER_UPDATE_HZ = 30
VISUALIZER_DECAY_SECONDS = 0.42
CHART_CANDIDATE_LIMIT = 5
SHOP_VISIBLE_ROWS = 7
SHOP_ROW_HEIGHT = 58


@dataclass(slots=True)
class HitEffect:
    """判定線上に短時間だけ残る、レーン位置確認用の視覚フィードバック。"""

    lane: int
    judgment: Judgment
    started_at: float
    duration: float = 0.18


@dataclass(slots=True)
class JudgmentFeedback:
    """中央に短時間だけ表示する最新判定。"""

    judgment: Judgment
    started_at: float
    duration: float = JUDGMENT_FEEDBACK_DURATION


@dataclass(slots=True)
class JudgmentLogEntry:
    """プレイ画面左側に残す直近判定の履歴。"""

    judgment: Judgment
    started_at: float
    lane: int | None = None
    duration: float = JUDGMENT_LOG_DURATION


@dataclass(slots=True)
class PlaylistEntry:
    """デモ曲と解析済みユーザー曲を同じ一覧へ載せる表示・選択用モデル。"""

    music_hash: str
    path: Path
    source: str
    exists: bool
    bpm: float = 0.0
    duration: float = 0.0
    last_used: str = ""
    folder: str = "ホーム"

    @property
    def source_label(self) -> str:
        return {"demo": "DEMO", "library": "MY MUSIC", "both": "DEMO + MY MUSIC"}.get(self.source, "MY MUSIC")


@dataclass(frozen=True, slots=True)
class ShopItem:
    item_id: str
    category: str
    name: str
    price: int
    owned: bool
    available: bool
    asset_path: Path | None = None
    mascot_id: str | None = None


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
        self.settings.setdefault("sfx_theme", "classic")
        if self.settings["sfx_theme"] not in SFX_THEMES:
            self.settings["sfx_theme"] = "classic"
        self.settings.setdefault("note_speed", 650.0)
        self.settings.setdefault("playfield_mode", "standard")
        if self.settings["playfield_mode"] not in PLAYFIELD_MODES:
            self.settings["playfield_mode"] = "standard"
        self.settings.setdefault("lane_view", "classic")
        if self.settings["lane_view"] not in LANE_VIEW_MODES:
            self.settings["lane_view"] = "classic"
        self._normalize_lane_runtime_settings()
        self.settings.setdefault("background_mode", "visualizer")
        if self.settings["background_mode"] not in BACKGROUND_MODES:
            self.settings["background_mode"] = "visualizer"
        self.settings.setdefault("background_opacity", 0.28)
        self.settings.setdefault("background_image", "")
        self.settings.setdefault("note_theme", "standard")
        if self.settings["note_theme"] not in NOTE_THEMES:
            self.settings["note_theme"] = "standard"
        self.settings.setdefault("note_skin", "standard")
        if self.settings["note_skin"] not in NOTE_SKINS:
            self.settings["note_skin"] = "standard"
        self.settings.setdefault("mascot_mode", "standard")
        if self.settings["mascot_mode"] not in MASCOT_MODES:
            self.settings["mascot_mode"] = "standard"
        self.settings.setdefault("mascot_id", "rhythm")
        self.profile = load_profile(self.paths)
        self.mascot_catalog = load_mascot_catalog(self.resource_path("assets/mascots"))
        self._migrate_existing_unlocks_to_shop()
        if not self.mascot_catalog:
            self.settings["mascot_mode"] = "off"
        elif find_mascot(self.mascot_catalog, self.settings["mascot_id"]) is None:
            rhythm = find_mascot(self.mascot_catalog, "rhythm")
            self.settings["mascot_id"] = (rhythm or self.mascot_catalog[0]).mascot_id
        if self.mascot_catalog and not self.is_mascot_available(str(self.settings.get("mascot_id", ""))):
            first_unlocked = next((mascot for mascot in self.mascot_catalog if self.is_mascot_available(mascot.mascot_id)), self.mascot_catalog[0])
            self.settings["mascot_id"] = first_unlocked.mascot_id
        self.settings.setdefault("timing_offset_ms", 0)
        self.settings.setdefault("fullscreen", False)
        self.settings.setdefault("resolution", [1280, 720])
        self.settings.setdefault("judgment_windows_ms", {})
        for name, default in (("perfect", 45), ("great", 90), ("good", 140)):
            self.settings["judgment_windows_ms"].setdefault(name, default)
        width, height = self.settings["resolution"]
        flags = pygame.FULLSCREEN if self.settings["fullscreen"] else 0
        self.display_surface = pygame.display.set_mode((int(width), int(height)), flags)
        self.surface = self._create_render_surface((int(width), int(height)))
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.fonts = self._build_fonts()
        self._playfield_base_cache: tuple[tuple, pygame.Surface] | None = None
        self._hud_text_cache: dict[str, tuple[tuple, pygame.Surface]] = {}
        self._note_draw_index: tuple | None = None
        self._background_composite_cache: tuple[tuple, pygame.Surface] | None = None
        self._visualizer_frame_cache: tuple[tuple, pygame.Surface] | None = None
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
        self.chart_candidates: list[Chart] = []
        self.chart_candidate_index = -1
        self.worker: AnalysisWorker | None = None
        self.progress = AnalysisProgress(0, "")
        self.selected_difficulty = 0
        self.ranking_lane_count: int | None = None
        self.library_scroll_index = 0
        self.library_selected_index = 0
        self.playlist_scroll_index = 0
        self.playlist_selected_index = 0
        self.launch_mode = "normal"
        self.practice_active = False
        self.trial_active = False
        self.trial_end_time = 0.0
        self.trial_fade_started = False
        self.practice_start = 0.0
        self.practice_end = 0.0
        self.practice_loop = True
        self.practice_round = 0
        self.practice_best_accuracy = 0.0
        self.reward_manager_scroll_index = 0
        self.reward_manager_selected_index = 0
        self.shop_scroll_index = 0
        self.shop_selected_index = 0
        self.shop_confirmation_id: str | None = None
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
        self.mascot_combo_zoom_until = 0.0
        self.combo_cutin_until = 0.0
        self.combo_cutin_combo = 0
        self.hit_effects: list[HitEffect] = []
        self.judgment_feedback: JudgmentFeedback | None = None
        self.judgment_log: list[JudgmentLogEntry] = []
        self._lane_keys_down: set[int] = set()
        self._resume_blocked_lanes: set[int] = set()
        self.countdown_started_at: float | None = None
        self.calibration: CalibrationSession | None = None
        self.start_banner_until = 0.0
        self.mascot_image_cache: dict[str, pygame.Surface | None] = {}
        self.mascot_scaled_cache: dict[tuple[str, int], pygame.Surface] = {}
        self._mascot_frame_base: pygame.Surface | None = None
        self._mascot_frames: dict[tuple[int, int], pygame.Surface] = {}
        self._mascot_frame_bytes = 0
        self.feedback_sounds = self._build_feedback_sounds()
        self._set_sfx_volume()
        self.background_image_cache: dict[tuple[str, tuple[int, int]], pygame.Surface | None] = {}
        self.full_combo_media_cache: dict[tuple[tuple[str, ...], int, int], list[pygame.Surface]] = {}
        self.combo_cutin_media_cache: dict[tuple[str, int, int], pygame.Surface | None] = {}
        self.combo_cutin_media_cache: dict[tuple[str, int, int], pygame.Surface | None] = {}

    def _logical_render_size(self, display_size: tuple[int, int]) -> tuple[int, int]:
        width, height = display_size
        if width < BASE_RENDER_SIZE[0] or height < BASE_RENDER_SIZE[1]:
            return BASE_RENDER_SIZE
        return width, height

    def _create_render_surface(self, display_size: tuple[int, int]) -> pygame.Surface:
        logical_size = self._logical_render_size(display_size)
        if logical_size == display_size:
            return self.display_surface
        return pygame.Surface(logical_size).convert()

    @property
    def size(self) -> tuple[int, int]:
        return self.surface.get_size()

    @property
    def display_size(self) -> tuple[int, int]:
        return self.display_surface.get_size()

    def _to_logical_point(self, pos: tuple[int, int]) -> tuple[int, int]:
        display_width, display_height = self.display_size
        logical_width, logical_height = self.size
        if (display_width, display_height) == (logical_width, logical_height):
            return pos
        return (
            max(0, min(logical_width - 1, int(pos[0] * logical_width / max(1, display_width)))),
            max(0, min(logical_height - 1, int(pos[1] * logical_height / max(1, display_height)))),
        )

    def _present(self) -> None:
        if self.surface is not self.display_surface:
            display_size = self.display_size
            scaled = pygame.transform.smoothscale(self.surface, display_size)
            self.display_surface.blit(scaled, (0, 0))
        pygame.display.flip()

    def _visible_rows(self, maximum: int, row_height: int, top: int, bottom_reserved: int, minimum: int = 3) -> int:
        _width, height = self.size
        available = max(row_height * minimum, height - top - bottom_reserved)
        return max(minimum, min(maximum, available // row_height))

    def _playlist_visible_rows(self) -> int:
        return self._visible_rows(PLAYLIST_VISIBLE_ROWS, PLAYLIST_ROW_HEIGHT, 172, 104)

    def _library_visible_rows(self) -> int:
        return self._visible_rows(LIBRARY_VISIBLE_ROWS, LIBRARY_ROW_HEIGHT, 145, 104)

    def _reward_manager_visible_rows(self) -> int:
        return self._visible_rows(REWARD_MANAGER_VISIBLE_ROWS, REWARD_MANAGER_ROW_HEIGHT, 232, 104)
    def _game_field_geometry(self) -> tuple[int, int, int, int, int]:
        """ウィンドウ解像度を変えず、選択したモードとレーン数に応じて表示領域を決める。"""
        width, height = self.size
        lane_count = self.active_lane_count
        if self.lane_view_key == "perspective":
            target_width = {3: 500, 5: 720, 7: 800}.get(lane_count, 720)
            side_margin = 500 if width <= BASE_RENDER_SIZE[0] else 600
        else:
            target_width = {3: 420, 5: 620, 7: 760}.get(lane_count, 620)
            side_margin = 330 if width < 1180 else 420
        field_width = min(target_width, max(lane_count * 74, width - side_margin))
        lane_width = max(1, field_width // lane_count)
        field_width = lane_width * lane_count
        left = (width - field_width) // 2
        if self.playfield_mode_key == "tall":
            # 画面の上下余白を圧縮し、同じレーン幅のまま物理的な表示距離も伸ばす。
            field_top = max(8, int(height * 0.012))
            judgment_y = max(field_top + 250, height - max(50, int(height * 0.07)))
        else:
            field_top = max(18, int(height * 0.028))
            judgment_y = max(field_top + 240, height - max(74, int(height * 0.103)))
        return left, field_width, lane_width, field_top, judgment_y

    def _perspective_top_width(self, field_width: int) -> int:
        return max(self.active_lane_count * 12, int(field_width * 0.15))

    def _perspective_lane_rect(self, lane: int, y: float, left: int, field_width: int, lane_width: int, field_top: int, line_y: int) -> tuple[float, float, float]:
        progress = max(0.0, (float(y) - field_top) / max(1, line_y - field_top))
        # 位置・横幅・高さを同じ線形進行へ揃え、判定直前の見かけ上の加減速を防ぐ。
        depth = min(1.0, progress)
        top_width = self._perspective_top_width(field_width)
        top_lane_width = top_width / max(1, self.active_lane_count)
        top_left = self.size[0] / 2 - top_width / 2
        bottom_left = float(left)
        # Continue the trajectory past the judgment line until the note is removed.
        lane_left = top_left + (bottom_left - top_left) * progress + lane * (top_lane_width + (lane_width - top_lane_width) * progress)
        width = top_lane_width + (lane_width - top_lane_width) * progress
        return lane_left, width, depth

    def _perspective_note_metrics(self, lane_width: float, depth: float, height_scale: float = 1.0) -> tuple[float, int, int]:
        """Use classic note thickness; only width follows the perspective lane."""
        note_height = max(1, int(18 * height_scale))
        margin = lane_width * 0.08
        body_alpha = 255
        return margin, note_height, body_alpha

    @staticmethod
    def _note_timing_y(note_time: float, now: float, line_y: int, speed: float) -> float:
        """Keep classic and perspective notes on the same constant-speed timing axis."""
        return line_y - (note_time - now) * speed

    @staticmethod
    def _perspective_note_vertical_bounds(timing_y: float, note_height: int, height_scale: float = 1.0) -> tuple[float, float]:
        """Center the cap on the timing axis, exactly as in classic mode."""
        return float(timing_y) - note_height / 2, float(timing_y) + note_height / 2

    def _draw_perspective_playfield(self, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, now: float) -> None:
        top_width = self._perspective_top_width(field_width)
        top_left = self.size[0] // 2 - top_width // 2
        cache_key = (self.size, left, field_width, lane_width, field_top, line_y,
                     self.active_lane_count, tuple(self.lane_color(lane) for lane in range(self.active_lane_count)))
        if self._playfield_base_cache is None or self._playfield_base_cache[0] != cache_key:
            layer = pygame.Surface(self.size, pygame.SRCALPHA)
            field_poly = [(top_left, field_top), (top_left + top_width, field_top), (left + field_width, line_y), (left, line_y)]
            pygame.draw.polygon(layer, (7, 12, 28, 245), field_poly)
    
            # Each lane carries a restrained tint so the highway reads as one neon stage.
            for lane in range(self.active_lane_count):
                color = self.lane_color(lane)
                lane_poly = [
                    (top_left + lane * top_width / self.active_lane_count, field_top),
                    (top_left + (lane + 1) * top_width / self.active_lane_count, field_top),
                    (left + (lane + 1) * lane_width, line_y),
                    (left + lane * lane_width, line_y),
                ]
                pygame.draw.polygon(layer, (*color, 13 if lane % 2 == 0 else 8), lane_poly)
    
            # Depth-compressed cross lines converge into the horizon instead of forming a flat grid.
            for step in range(1, 19):
                ratio = (step / 19) ** 1.72
                y = field_top + (line_y - field_top) * ratio
                left_x, full_width, depth = self._perspective_lane_rect(0, y, left, field_width, lane_width, field_top, line_y)
                alpha = int(24 + depth * 64)
                pygame.draw.line(layer, (79, 156, 210, alpha), (left_x, y), (left_x + full_width * self.active_lane_count, y), 1)
            self._playfield_base_cache = (cache_key, layer)
        if getattr(self, "_playfield_foreground_key", None) != cache_key:
            layer = pygame.Surface(self.size, pygame.SRCALPHA)
            for lane in range(self.active_lane_count + 1):
                bottom_x = left + lane * lane_width
                top_x = top_left + lane * top_width / max(1, self.active_lane_count)
                color = WHITE if lane in (0, self.active_lane_count) else tuple(channel // 2 for channel in self.lane_color(max(0, lane - 1)))
                edge_width = 2 if lane in (0, self.active_lane_count) else 1
                pygame.draw.line(layer, (*color, 24), (top_x, field_top), (bottom_x, line_y), edge_width + 7)
                pygame.draw.line(layer, (*color, 70), (top_x, field_top), (bottom_x, line_y), edge_width + 3)
                pygame.draw.line(layer, (*color, 190), (top_x, field_top), (bottom_x, line_y), edge_width)

            # A broad illuminated judgment deck anchors the near edge.
            deck_top = line_y - max(12, int((line_y - field_top) * 0.025))
            deck_left, deck_lane_width, _ = self._perspective_lane_rect(0, deck_top, left, field_width, lane_width, field_top, line_y)
            deck_poly = [(deck_left, deck_top), (deck_left + deck_lane_width * self.active_lane_count, deck_top), (left + field_width, line_y), (left, line_y)]
            pygame.draw.polygon(layer, (76, 192, 255, 28), deck_poly)
            pygame.draw.line(layer, (72, 204, 255, 35), (left, line_y), (left + field_width, line_y), 15)
            pygame.draw.line(layer, (120, 227, 255, 105), (left, line_y), (left + field_width, line_y), 7)
            pygame.draw.line(layer, (*WHITE, 250), (left, line_y), (left + field_width, line_y), 3)

            # Color-key copying preserves RGBA pixels instead of blending them twice.
            layer.set_alpha(None)
            layer.set_colorkey((0, 0, 0), pygame.RLEACCEL)
            self._playfield_foreground = layer
            self._playfield_scratch = pygame.Surface(self.size, pygame.SRCALPHA)
            self._playfield_foreground_key = cache_key
        layer = self._playfield_scratch
        base = self._playfield_base_cache[1]
        base.set_alpha(None)
        layer.blit(base, (0, 0))

        # Moving streaks provide speed without covering the note path.
        travel = max(1, line_y - field_top)
        for lane in range(self.active_lane_count):
            color = self.lane_color(lane)
            for streak in range(1 if self.low_graphics_quality else 2):
                phase = (now * (0.20 + streak * 0.035) + lane * 0.13 + streak * 0.41) % 1.0
                start_y = field_top + travel * phase
                end_y = min(line_y, start_y + 18 + 56 * phase)
                start_left, start_width, _ = self._perspective_lane_rect(lane, start_y, left, field_width, lane_width, field_top, line_y)
                end_left, end_width, _ = self._perspective_lane_rect(lane, end_y, left, field_width, lane_width, field_top, line_y)
                x1 = start_left + start_width * (0.28 + streak * 0.44)
                x2 = end_left + end_width * (0.28 + streak * 0.44)
                pygame.draw.line(layer, (*color, 38), (x1, start_y), (x2, end_y), 1)

        layer.blit(self._playfield_foreground, (0, 0))

        average = sum(self._visualizer_levels(now)) / 5.0
        horizon_alpha = int(135 + average * 90)
        horizon_y = field_top + 2
        pygame.draw.line(layer, (72, 215, 255, 26), (top_left - 42, horizon_y), (top_left + top_width + 42, horizon_y), 15)
        pygame.draw.line(layer, (119, 230, 255, horizon_alpha), (top_left - 22, horizon_y), (top_left + top_width + 22, horizon_y), 2)
        pygame.draw.line(layer, (255, 255, 255, 220), (top_left, horizon_y), (top_left + top_width, horizon_y), 1)

        self.surface.blit(layer, (0, 0))

    def _blit_local_primitives(self, commands: list[tuple]) -> None:
        """Rasterize translucent primitives in visible bounds, preserving draw order."""
        shapes = []
        for kind, color, *args in commands:
            closed = False
            if kind == "line":
                points, width = args[:2], args[2] if len(args) > 2 else 1
            elif kind == "lines":
                closed, points = args[:2]
                width = args[2] if len(args) > 2 else 1
            else:
                points, width = args[0], args[1] if len(args) > 1 else 0
            # Round before translating so offscreen primitives retain their original pixels.
            shapes.append((kind, color, [(int(x), int(y)) for x, y in points], width, closed))
        if not shapes:
            return
        points = [point for _, _, vertices, _, _ in shapes for point in vertices]
        padding = max(width for _, _, _, width, _ in shapes) + 2
        min_x, max_x = min(x for x, _ in points), max(x for x, _ in points)
        min_y, max_y = min(y for _, y in points), max(y for _, y in points)
        bounds = pygame.Rect(min_x - padding, min_y - padding,
                             max_x - min_x + padding * 2 + 1,
                             max_y - min_y + padding * 2 + 1).clip(self.surface.get_rect())
        if not bounds:
            return
        # Pool bookkeeping costs more than allocation for small effects.
        if bounds.width * bounds.height < 32768:
            layer = pygame.Surface(bounds.size, pygame.SRCALPHA)
        else:
            pool = getattr(self, "_decoration_surface_pool", None)
            if pool is None:
                pool = self._decoration_surface_pool = {}
            layer = pool.get(bounds.size)
            if layer is None:
                layer = pygame.Surface(bounds.size, pygame.SRCALPHA)
                memory = layer.get_pitch() * layer.get_height()
                while pool and (len(pool) >= 32 or sum(s.get_pitch() * s.get_height() for s in pool.values()) + memory > 8 * 1024 * 1024):
                    del pool[next(iter(pool))]
                if memory <= 8 * 1024 * 1024:
                    pool[bounds.size] = layer
            else:
                layer.fill((0, 0, 0, 0))
        for kind, color, vertices, width, closed in shapes:
            local = [(x - bounds.x, y - bounds.y) for x, y in vertices]
            if kind == "line":
                pygame.draw.line(layer, color, local[0], local[1], width)
            elif kind == "lines":
                pygame.draw.lines(layer, color, closed, local, width)
            else:
                pygame.draw.polygon(layer, color, local, width)
        self.surface.blit(layer, bounds.topleft)


    def _draw_perspective_note_bar(self, lane: int, y: float, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, color: tuple[int, int, int], *, height_scale: float = 1.0) -> None:
        lane_left, width, depth = self._perspective_lane_rect(lane, y, left, field_width, lane_width, field_top, line_y)
        margin, note_height, body_alpha = self._perspective_note_metrics(width, depth, height_scale)
        x1 = lane_left + margin
        x2 = lane_left + width - margin
        y1, y2 = self._perspective_note_vertical_bounds(y, note_height, height_scale)
        commands: list[tuple] = []

        # Keep the cap crisp: depth-dependent trails shift its visual center and obscure timing.
        center = (x1 + x2) / 2
        glow = 3
        commands.append(("polygon", (*color, 12 + int(depth * 45)), [(x1 - glow * 1.6, y1 - glow), (x2 + glow * 1.6, y1 - glow), (x2 + glow * 1.6, y2 + glow), (x1 - glow * 1.6, y2 + glow)]))
        commands.append(("polygon", (*color, 45 + int(depth * 90)), [(x1 - glow * 0.65, y1 - glow * 0.45), (x2 + glow * 0.65, y1 - glow * 0.45), (x2 + glow * 0.65, y2 + glow * 0.45), (x1 - glow * 0.65, y2 + glow * 0.45)]))
        commands.append(("polygon", (*color, body_alpha), [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]))
        commands.append(("line", (*WHITE, 220), (x1 + 2, y1 + 2), (x2 - 2, y1 + 2), 1))
        commands.append(("line", (*WHITE, 110), (center, y1 + 2), (center, y2 - 1), max(1, int(width * 0.025))))
        commands.append(("polygon", (*WHITE, 195), [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], 1))
        self._blit_local_primitives(commands)

    def _draw_perspective_hold_rail(self, lane: int, y1: float, y2: float, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, color: tuple[int, int, int]) -> None:
        top_y, bottom_y = sorted((float(y1), float(y2)))
        # Clip before projecting: an offscreen endpoint would bend the rail across lanes.
        top_y, bottom_y = max(field_top, top_y), min(line_y, bottom_y)
        if bottom_y <= top_y:
            return
        top_left, top_width, top_depth = self._perspective_lane_rect(lane, top_y, left, field_width, lane_width, field_top, line_y)
        bottom_left, bottom_width, bottom_depth = self._perspective_lane_rect(lane, bottom_y, left, field_width, lane_width, field_top, line_y)
        top_half = min(top_width * 0.20, max(1.0, top_width * 0.08))
        bottom_half = min(bottom_width * 0.20, max(1.0, bottom_width * 0.08))
        top_center = top_left + top_width / 2
        bottom_center = bottom_left + bottom_width / 2
        commands: list[tuple] = []
        rail = [(top_center - top_half, top_y), (top_center + top_half, top_y), (bottom_center + bottom_half, bottom_y), (bottom_center - bottom_half, bottom_y)]
        commands.append(("polygon", (*color, 36), [(top_center - top_half * 2.0, top_y), (top_center + top_half * 2.0, top_y), (bottom_center + bottom_half * 2.0, bottom_y), (bottom_center - bottom_half * 2.0, bottom_y)]))
        commands.append(("polygon", (*color, 105), rail))
        # Taper the glow and core too; a constant-width stroke overflows narrow distant lanes.
        for tint, ratio in (((*color, 65), 0.14), ((*WHITE, 205), 0.015)):
            commands.append(("polygon", tint, [(top_center - top_width * ratio, top_y),
                                               (top_center + top_width * ratio, top_y),
                                               (bottom_center + bottom_width * ratio, bottom_y),
                                               (bottom_center - bottom_width * ratio, bottom_y)]))
        commands.append(("line", (*color, 210), (top_center - top_half, top_y), (bottom_center - bottom_half, bottom_y), 1))
        commands.append(("line", (*color, 210), (top_center + top_half, top_y), (bottom_center + bottom_half, bottom_y), 1))
        self._blit_local_primitives(commands)

    def _draw_perspective_hold_sparks(self, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, now: float) -> None:
        lanes = sorted(self._active_hold_lanes())
        particles = min(5, self.hold_particle_limit // max(1, len(lanes)))
        for lane in lanes:
            color = self.lane_color(lane)
            for index in range(particles):
                t = (now * 0.75 + lane * 0.17 + index * 0.19) % 1.0
                y = field_top + (line_y - field_top) * (0.18 + 0.76 * t)
                lane_left, width, depth = self._perspective_lane_rect(lane, y, left, field_width, lane_width, field_top, line_y)
                x = int(lane_left + width * (0.35 + 0.3 * math.sin(now * 8 + index)))
                pygame.draw.circle(self.surface, (*color, 210), (x, int(y)), max(1, int(2 + depth * 3)))

    def _draw_perspective_hit_effects(self, left: int, field_width: int, lane_width: int, field_top: int, line_y: int) -> None:
        now = time.perf_counter()
        self.hit_effects = [effect for effect in self.hit_effects if now - effect.started_at <= effect.duration]
        for effect in self.hit_effects:
            progress = max(0.0, min(1.0, (now - effect.started_at) / effect.duration))
            color = self.lane_color(effect.lane)
            fade = (1.0 - progress) ** 1.45
            commands: list[tuple] = []
            bottom_left, bottom_width, _ = self._perspective_lane_rect(effect.lane, line_y, left, field_width, lane_width, field_top, line_y)
            impact_x = int(bottom_left + bottom_width / 2)
            impact_half = bottom_width * (0.12 + progress * 0.22)
            commands.append(("line", (*color, int(180 * fade)), (impact_x - impact_half, line_y - 2), (impact_x + impact_half, line_y - 2), max(1, int(4 * fade))))
            commands.append(("line", (*WHITE, int(120 * fade)), (impact_x - impact_half * 0.7, line_y - 3), (impact_x + impact_half * 0.7, line_y - 3), 1))
            if effect.judgment is Judgment.PERFECT:
                top_left, top_width, _ = self._perspective_lane_rect(effect.lane, field_top, left, field_width, lane_width, field_top, line_y)
                lane_poly = [(top_left, field_top), (top_left + top_width, field_top), (bottom_left + bottom_width, line_y), (bottom_left, line_y)]
                commands.append(("polygon", (*color, int(105 * fade)), lane_poly))
                commands.append(("polygon", (*WHITE, int(38 * fade)), lane_poly, max(2, int(6 * fade))))
                for spread in (0.20, 0.34, 0.48):
                    half = bottom_width * spread * (0.65 + progress)
                    commands.append(("line", (*color, int(170 * fade)), (impact_x - half, line_y - 2), (impact_x + half, line_y - 2), max(1, int(5 * fade))))
                for ray in range(7):
                    angle = math.pi * (0.12 + 0.76 * ray / 6)
                    length = (24 + bottom_width * 0.32) * (0.75 + progress)
                    end = (impact_x + math.cos(angle) * length, line_y - math.sin(angle) * length)
                    commands.append(("line", (*WHITE, int(195 * fade)), (impact_x, line_y - 3), end, max(1, int(3 * fade))))
            self._blit_local_primitives(commands)

    def _drawable_states(self, now: float, speed: float, field_top: int, line_y: int) -> list:
        """Find overlapping note intervals; retain long HOLDs and backward seeks."""
        if self.session is None:
            return []
        states = self.session.states
        if speed <= 0:
            return states
        cache = self._note_draw_index
        if cache is None or cache[0] is not self.session or cache[1] is not states or cache[2] != len(states):
            starts, ends = [], []
            latest_end = float("-inf")
            for state in states:
                note = state.note
                starts.append(note.time)
                latest_end = max(latest_end, note.end_time if note.end_time is not None else note.time)
                ends.append(latest_end)
            cache = (self.session, states, len(states), starts, ends)
            self._note_draw_index = cache
        earliest = now + (line_y - (self.size[1] + 45)) / speed - 1e-9
        latest = now + (line_y - (field_top - 25)) / speed + 1e-9
        return states[bisect_left(cache[4], earliest):bisect_right(cache[3], latest)]

    def _visible_chord_guides(self, now: float, speed: float, field_top: int, line_y: int) -> list[tuple[float, tuple[int, ...]]]:
        """Return visible simultaneous-note starts without changing judgment state."""
        if self.session is None:
            return []
        grouped: dict[float, list[tuple[float, int]]] = {}
        for state in self._drawable_states(now, speed, field_top, line_y):
            if state.complete:
                continue
            note = state.note
            y = self._note_timing_y(note.time, now, line_y, speed)
            if field_top - 25 <= y <= self.size[1] + 45:
                grouped.setdefault(round(note.time, 4), []).append((y, self.source_to_active_lane(note.lane)))
        guides: list[tuple[float, tuple[int, ...]]] = []
        for notes in grouped.values():
            lanes = tuple(sorted({lane for _y, lane in notes}))
            if len(lanes) > 1:
                guides.append((sum(y for y, _lane in notes) / len(notes), lanes))
        return guides

    def _draw_chord_guides(self, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, now: float, speed: float, *, perspective: bool) -> None:
        guides = self._visible_chord_guides(now, speed, field_top, line_y)
        if not guides:
            return
        commands: list[tuple] = []
        for y, lanes in guides:
            centers: list[tuple[int, int]] = []
            for lane in lanes:
                if perspective:
                    lane_left, width, _depth = self._perspective_lane_rect(lane, y, left, field_width, lane_width, field_top, line_y)
                    x = lane_left + width / 2
                else:
                    x = left + lane * lane_width + lane_width / 2
                centers.append((int(x), int(y)))
            start, end = centers[0], centers[-1]
            commands.append(("line", (*CYAN, 24), start, end, 3))
            commands.append(("line", (*WHITE, 108), start, end, 1))
        self._blit_local_primitives(commands)

    def _draw_perspective_game_field(self, left: int, field_width: int, lane_width: int, field_top: int, line_y: int, now: float, counting_down: bool) -> None:
        active_keys = self.active_lane_keys
        self._draw_perspective_playfield(left, field_width, lane_width, field_top, line_y, now)
        for lane in range(self.active_lane_count):
            color = self.lane_color(lane)
            self.text(active_keys[lane].upper(), "mono", color, center=(left + lane * lane_width + lane_width // 2, line_y + 30))
        if not counting_down:
            speed = self.effective_note_speed
            self._draw_chord_guides(left, field_width, lane_width, field_top, line_y, now, speed, perspective=True)
            drawable: list[tuple[float, object]] = []
            for state in self._drawable_states(now, speed, field_top, line_y):
                if state.complete:
                    continue
                note = state.note
                y = self._note_timing_y(note.time, now, line_y, speed)
                end_y = self._note_timing_y(note.end_time, now, line_y, speed) if note.kind.value == "hold" and note.end_time is not None else y
                if max(y, end_y) < field_top - 25 or min(y, end_y) > self.size[1] + 45:
                    continue
                drawable.append((max(y, end_y), state))
            for _sort_y, state in sorted(drawable, key=lambda item: item[0]):
                note = state.note
                lane = self.source_to_active_lane(note.lane)
                color = self.lane_color(lane)
                y = self._note_timing_y(note.time, now, line_y, speed)
                if note.kind.value == "hold" and note.end_time is not None:
                    end_y = self._note_timing_y(note.end_time, now, line_y, speed)
                    self._draw_perspective_hold_rail(lane, y, end_y, left, field_width, lane_width, field_top, line_y, color)
                    if field_top - 25 <= end_y <= self.size[1] + 45:
                        self._draw_perspective_note_bar(lane, end_y, left, field_width, lane_width, field_top, line_y, color)
                if field_top - 25 <= y <= self.size[1] + 45:
                    self._draw_perspective_note_bar(lane, y, left, field_width, lane_width, field_top, line_y, color)
        self._draw_perspective_hold_sparks(left, field_width, lane_width, field_top, line_y, now)
        self._draw_perspective_hit_effects(left, field_width, lane_width, field_top, line_y)

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

    def current_tutorial_steps(self) -> tuple:
        return tutorial_steps(self.active_lane_count)

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
        """カウント終了後、通常曲・練習・チュートリアルの時計・判定を開始する。"""
        self.countdown_started_at = None
        if self.tutorial_active:
            self.tutorial_started_at = time.perf_counter()
            self.tutorial_paused_at = None
            self.tutorial_next_click_at = 0.0
        else:
            self.audio.play(self.practice_start if self.practice_active else 0.0)
            if self.trial_active:
                self.trial_fade_started = False
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
            "hud_score": pygame.font.SysFont("consolas", 34, bold=True),
            "hud_combo": pygame.font.SysFont("consolas", 46, bold=True),
            "hud_rank": pygame.font.SysFont("consolas", 34, bold=True),
        }

    @property
    def playfield_mode_key(self) -> str:
        key = str(self.settings.get("playfield_mode", "standard"))
        return key if key in PLAYFIELD_MODES else "standard"

    @property
    def playfield_mode_label(self) -> str:
        return PLAYFIELD_MODES[self.playfield_mode_key][0]

    @property
    def lane_view_key(self) -> str:
        key = str(self.settings.get("lane_view", "classic"))
        return key if key in LANE_VIEW_MODES else "classic"

    @property
    def lane_view_label(self) -> str:
        return LANE_VIEW_MODES[self.lane_view_key]

    def _normalize_lane_runtime_settings(self) -> None:
        lane_count = self.settings.get("lane_count", 5)
        if lane_count not in LANE_KEY_PRESETS:
            lane_count = 5
        self.settings["lane_count"] = int(lane_count)
        lane_keys = self.settings.get("lane_keys")
        if not isinstance(lane_keys, dict):
            lane_keys = {}
        normalized: dict[str, list[str]] = {}
        for count, defaults in LANE_KEY_PRESETS.items():
            raw = lane_keys.get(str(count), lane_keys.get(count))
            if count == 5 and not isinstance(raw, list):
                raw = self.settings.get("keys")
            if not isinstance(raw, list) or len(raw) != count or len(set(raw)) != count:
                raw = list(defaults)
            normalized[str(count)] = [str(key).lower() for key in raw]
        self.settings["lane_keys"] = normalized
        self.settings["keys"] = list(normalized["5"])



    def tutorial_cosmetic_unlock_ids(self) -> list[str]:
        ids = [cosmetic_id("sfx", key) for key in SFX_THEMES]
        ids.extend(cosmetic_id("background", key) for key in BACKGROUND_MODES)
        ids.extend(cosmetic_id("note_theme", key) for key in NOTE_THEMES)
        ids.extend(cosmetic_id("note_skin", key) for key in NOTE_SKINS)
        ids.extend(cosmetic_id("lane_view", key) for key in LANE_VIEW_MODES)
        ids.append(cosmetic_id("background", "custom_image"))
        return ids

    def _migrate_existing_unlocks_to_shop(self) -> None:
        """Preserve items earned under the former lifetime-score unlock rules."""
        if self.profile.get("shop_migrated", False):
            return
        mascot_items = [
            (mascot_cosmetic_id(mascot.mascot_id), self.mascot_unlock_requirement(mascot.mascot_id))
            for mascot in self.mascot_catalog
        ]
        unlock_score_cosmetics(self.profile, mascot_items)
        lifetime_score = int(self.profile.get("lifetime_score", 0))
        rewards = set(self.profile.get("unlocked_rewards", []))
        for name, price in reward_thresholds(self.paths).items():
            if lifetime_score >= price:
                rewards.add(name)
        self.profile["unlocked_rewards"] = sorted(rewards)
        materialize_unlocked_rewards(self.paths, rewards)
        self.profile["shop_migrated"] = True
        save_profile(self.paths, self.profile)

    def is_tutorial_cosmetic_unlocked(self, category: str, item_id: str) -> bool:
        return is_cosmetic_unlocked(self.profile, cosmetic_id(category, item_id))

    def _locked_tutorial_setting_message(self, label: str) -> str:
        return f"{label}はチュートリアルを最後までクリアすると選択できます。"

    def is_lane_mode_unlocked(self, lane_count: int) -> bool:
        return is_feature_unlocked(self.profile, lane_feature_id(lane_count))

    def lane_unlock_message(self, lane_count: int) -> str:
        stats = self.profile.get("unlock_stats", {}) if isinstance(self.profile.get("unlock_stats"), dict) else {}
        if lane_count == 3:
            low_remaining = max(0, 3 - int(stats.get("five_lane_low_rank_count", 0)))
            miss_remaining = max(0, 3 - int(stats.get("five_lane_high_miss_count", 0)))
            return f"3 LANEは5 LANEでC以下あと{low_remaining}回、またはMISS率25%以上あと{miss_remaining}回で解放"
        if lane_count == 7:
            a_remaining = max(0, 3 - int(stats.get("five_lane_a_or_better_count", 0)))
            return f"7 LANEは5 LANEでS以上1回、またはA以上あと{a_remaining}回で解放"
        return "5 LANEは最初から解放済みです"

    def mascot_unlock_requirement(self, mascot_id: str) -> int:
        ids = [mascot.mascot_id for mascot in self.mascot_catalog]
        try:
            index = ids.index(str(mascot_id).casefold())
        except ValueError:
            index = 0
        return mascot_required_score(str(mascot_id), index)

    def is_mascot_available(self, mascot_id: str) -> bool:
        return is_mascot_unlocked(self.profile, mascot_id, self.mascot_unlock_requirement(mascot_id))

    def _unlocked_notification_label(self, item_id: str) -> str:
        if item_id == "lane.3":
            return "3 LANE MODE"
        if item_id == "lane.7":
            return "7 LANE MODE"
        if item_id.startswith("mascot."):
            mascot = find_mascot(self.mascot_catalog, item_id.split(".", 1)[1])
            return f"MASCOT {mascot.name if mascot else item_id.split('.', 1)[1].upper()}"
        if item_id.startswith("sfx."):
            return f"SFX {item_id.split('.', 1)[1].upper()}"
        if item_id.startswith("background."):
            return f"BACKGROUND {item_id.split('.', 1)[1].replace('_', ' ').upper()}"
        if item_id.startswith("note_theme."):
            return f"NOTE COLOR {item_id.split('.', 1)[1].upper()}"
        if item_id.startswith("note_skin."):
            return f"NOTE SKIN {item_id.split('.', 1)[1].replace('_', ' ').upper()}"
        if item_id.startswith("lane_view."):
            return f"LANE VIEW {item_id.split('.', 1)[1].replace('_', ' ').upper()}"
        return Path(item_id).stem

    def _unlocked_notification_detail(self, item_id: str) -> str:
        if item_id == "lane.3":
            return "少ないキーで曲に慣れられる練習向けモードです"
        if item_id == "lane.7":
            return "より広いレーンで高難度の譜面に挑戦できます"
        if item_id.startswith("mascot."):
            return "設定画面から新しいマスコットを選べます"
        if item_id.startswith(("sfx.", "background.", "note_theme.", "note_skin.", "lane_view.")):
            return "チュートリアル完了特典として設定画面で選べます"
        return "ギャラリーで新しいご褒美画像を見られます"

    @property
    def active_lane_count(self) -> int:
        count = self.settings.get("lane_count", 5)
        if count not in LANE_KEY_PRESETS:
            count = 5
        if not self.is_lane_mode_unlocked(int(count)):
            self.settings["lane_count"] = 5
            return 5
        return int(count)

    @property
    def active_lane_keys(self) -> list[str]:
        self._normalize_lane_runtime_settings()
        return list(self.settings["lane_keys"][str(self.active_lane_count)])

    @property
    def active_lane_names(self) -> tuple[str, ...]:
        return LANE_NAMES_BY_COUNT.get(self.active_lane_count, LANE_NAMES_BY_COUNT[5])

    @property
    def lane_count_label(self) -> str:
        return LANE_COUNT_LABELS[self.active_lane_count]

    def lane_color(self, lane: int) -> tuple[int, int, int]:
        colors = self.lane_colors
        return colors[lane % len(colors)]

    def source_lane_count(self) -> int:
        return chart_lane_count(self.chart) if self.chart is not None else 5

    def source_to_active_lane(self, source_lane: int) -> int:
        active_count = self.active_lane_count
        source_count = self.source_lane_count()
        if source_count == active_count:
            return max(0, min(active_count - 1, source_lane))
        if source_count <= 1:
            return 0
        return max(0, min(active_count - 1, round(source_lane * (active_count - 1) / (source_count - 1))))

    def active_to_source_lanes(self, active_lane: int) -> list[int]:
        return [lane for lane in range(self.source_lane_count()) if self.source_to_active_lane(lane) == active_lane]

    @property
    def background_mode_key(self) -> str:
        key = str(self.settings.get("background_mode", "visualizer"))
        return key if key in BACKGROUND_MODES else "visualizer"

    @property
    def background_mode_label(self) -> str:
        return BACKGROUND_MODES[self.background_mode_key]

    @property
    def background_opacity(self) -> float:
        return max(0.0, min(0.65, float(self.settings.get("background_opacity", 0.28))))

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

    @property
    def note_skin_key(self) -> str:
        key = str(self.settings.get("note_skin", "standard"))
        return key if key in NOTE_SKINS else "standard"

    @property
    def note_skin_label(self) -> str:
        return NOTE_SKINS[self.note_skin_key][0]

    @property
    def mascot_mode_key(self) -> str:
        key = str(self.settings.get("mascot_mode", "standard"))
        return key if key in MASCOT_MODES else "standard"

    @property
    def mascot_mode_label(self) -> str:
        return MASCOT_MODES[self.mascot_mode_key][0]

    @property
    def selected_mascot(self) -> Mascot | None:
        return find_mascot(self.mascot_catalog, self.settings.get("mascot_id"))

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
        mouse = self._to_logical_point(pygame.mouse.get_pos())
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

    @property
    def sfx_theme_key(self) -> str:
        key = str(self.settings.get("sfx_theme", "classic"))
        return key if key in SFX_THEMES else "classic"

    @property
    def sfx_theme_label(self) -> str:
        return SFX_THEMES[self.sfx_theme_key][0]

    def _build_feedback_sounds(self) -> dict[Judgment, pygame.mixer.Sound]:
        if not self.audio_available or not pygame.mixer.get_init():
            return {}
        sample_rate, _format, channels = pygame.mixer.get_init()
        _label, spec = SFX_THEMES[self.sfx_theme_key]

        def waveform(phase: float, shape: str, index: int) -> float:
            if shape == "square":
                return 1.0 if math.sin(phase) >= 0 else -1.0
            if shape == "triangle":
                return 2.0 / math.pi * math.asin(math.sin(phase))
            if shape == "bell":
                return math.sin(phase) * 0.76 + math.sin(phase * 2.01) * 0.20 + math.sin(phase * 3.0) * 0.08
            if shape == "buzz":
                return math.sin(phase) * 0.65 + math.sin(phase * 0.51) * 0.28
            if shape == "soft_noise":
                noise = (((index * 1103515245 + 12345) >> 16) & 0x7FFF) / 16384.0 - 1.0
                return math.sin(phase) * 0.55 + noise * 0.18
            return math.sin(phase)

        def tone(frequency: float, duration: float, shape: str) -> pygame.mixer.Sound:
            frames = max(1, int(sample_rate * duration))
            samples = array("h")
            for index in range(frames):
                progress = index / frames
                envelope = max(0.0, 1.0 - progress) ** (1.4 if shape in {"bell", "soft_noise"} else 1.0)
                phase = 2 * math.pi * frequency * index / sample_rate
                value = int(8200 * envelope * max(-1.0, min(1.0, waveform(phase, shape, index))))
                for _ in range(channels):
                    samples.append(value)
            return pygame.mixer.Sound(buffer=samples)

        try:
            sounds = {judgment: tone(*params) for judgment, params in spec.items()}
        except pygame.error:
            return {}
        return sounds

    def _set_sfx_volume(self) -> None:
        volume = max(0.0, min(1.0, float(self.settings.get("sfx_volume", 0.7))))
        for sound in self.feedback_sounds.values():
            sound.set_volume(volume)

    def _rebuild_feedback_sounds(self) -> None:
        self.feedback_sounds = self._build_feedback_sounds()
        self._set_sfx_volume()
        self.background_image_cache: dict[tuple[str, tuple[int, int]], pygame.Surface | None] = {}
        self.full_combo_media_cache: dict[tuple[tuple[str, ...], int, int], list[pygame.Surface]] = {}

    def preview_sfx_theme(self, judgment: Judgment = Judgment.PERFECT) -> None:
        sound = self.feedback_sounds.get(judgment)
        if sound is not None:
            sound.play()

    def _emit_hit_effect(self, lane: int, judgment: Judgment | None) -> None:
        """成功判定の入力位置だけを、短いリングと火花で示す。"""
        if judgment is None or judgment is Judgment.MISS or not 0 <= lane < self.active_lane_count:
            return
        duration = PERFECT_LANE_FLASH_DURATION if judgment is Judgment.PERFECT else 0.18
        self.hit_effects = [effect for effect in self.hit_effects if effect.lane != lane]
        self.hit_effects.append(HitEffect(lane=lane, judgment=judgment, started_at=time.perf_counter(), duration=duration))
        # Keep each lane responsive, without stacking old flashes on repeated hits.
        self.hit_effects = self.hit_effects[-7:]

    def _load_background_image(self, target_size: tuple[int, int]) -> pygame.Surface | None:
        path = self.current_background_image_path()
        if path is None or not path.is_file():
            return None
        cache_key = (str(path), target_size)
        if cache_key in self.background_image_cache:
            return self.background_image_cache[cache_key]
        try:
            source = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            self.background_image_cache[cache_key] = None
            return None
        target_width, target_height = target_size
        scale = max(target_width / max(1, source.get_width()), target_height / max(1, source.get_height()))
        scaled_size = (max(1, int(source.get_width() * scale)), max(1, int(source.get_height() * scale)))
        image = pygame.transform.smoothscale(source, scaled_size)
        cropped = pygame.Surface(target_size, pygame.SRCALPHA)
        cropped.blit(image, image.get_rect(center=(target_width // 2, target_height // 2)))
        self.background_image_cache[cache_key] = cropped
        return cropped

    def _draw_background_image(self) -> None:
        image = self._load_background_image(self.size)
        if image is None:
            return
        opacity = self.background_opacity
        if opacity <= 0.0:
            return
        key = (image, self.size, opacity, BG)
        if self._background_composite_cache is None or self._background_composite_cache[0] != key:
            # draw() clears to BG before this pass. Preserve both original alpha blends.
            composite = pygame.Surface(self.size).convert()
            composite.fill(BG)
            layer = image.copy()
            layer.set_alpha(int(255 * opacity))
            composite.blit(layer, (0, 0))
            dark = pygame.Surface(self.size, pygame.SRCALPHA)
            dark.fill((0, 0, 0, int(120 + 90 * (1.0 - opacity))))
            composite.blit(dark, (0, 0))
            self._background_composite_cache = (key, composite)
        self.surface.blit(self._background_composite_cache[1], (0, 0))

    def _draw_game_background(self, now: float) -> None:
        mode = self.background_mode_key
        if mode == "image":
            self._draw_background_image()
        elif mode == "visualizer":
            self._draw_audio_visualizer(now)

    def _visualizer_levels(self, now: float) -> tuple[float, ...]:
        base = [0.20 + 0.10 * (math.sin(now * 1.25 + lane * 0.95) + 1.0) for lane in range(5)]
        if self.analysis is not None and self.analysis.onsets:
            index = bisect_right(self.analysis.onsets, now) - 1
            if index >= 0:
                elapsed = max(0.0, now - float(self.analysis.onsets[index]))
                pulse = max(0.0, 1.0 - elapsed / VISUALIZER_DECAY_SECONDS)
                energies = self.analysis.band_energy[index] if index < len(self.analysis.band_energy) else []
                if energies:
                    peak = max(0.001, max(float(value) for value in energies))
                    levels = [max(0.0, min(1.0, float(value) / peak)) for value in energies[:5]]
                    while len(levels) < 5:
                        levels.append(levels[-1] if levels else 0.0)
                    strength = self.analysis.onset_strengths[index] if index < len(self.analysis.onset_strengths) else peak
                    lift = max(0.18, min(1.0, float(strength)))
                    return tuple(max(base[lane], min(1.0, levels[lane] * (0.38 + 0.62 * pulse) * lift)) for lane in range(5))
        return tuple(base)

    @property
    def low_graphics_quality(self) -> bool:
        return self.settings.get("graphics_quality", "standard") == "low"

    @property
    def hold_particle_limit(self) -> int:
        return 14 if self.low_graphics_quality else HOLD_PARTICLE_LIMIT

    def _draw_audio_visualizer(self, now: float) -> None:
        # Only decoration is sampled; gameplay and input retain their own clock.
        update_hz = 15 if self.low_graphics_quality else VISUALIZER_UPDATE_HZ
        frame = math.floor(now * update_hz + 1e-9)
        key = (frame, update_hz, self.size, id(self.analysis), id(self.session),
               tuple(self.lane_color(band) for band in range(5)))
        cached = self._visualizer_frame_cache
        if cached is None or cached[0] != key:
            cached = (key, self._render_audio_visualizer(frame / update_hz))
            self._visualizer_frame_cache = cached
        self.surface.blit(cached[1], (0, 0))

    def _render_audio_visualizer(self, now: float) -> pygame.Surface:
        levels = self._visualizer_levels(now)
        width, height = self.size
        layer = pygame.Surface((width, height), pygame.SRCALPHA)
        if not levels:
            return layer
        average = sum(levels) / max(1, len(levels))
        center_y = int(height * 0.48)
        steps = 96 if self.low_graphics_quality else 176
        for band, level in enumerate(levels[:5]):
            color = self.lane_color(band)
            muted = tuple(max(0, int(channel * 0.58)) for channel in color)
            amplitude = height * (0.030 + 0.055 * level)
            baseline = center_y + int((band - 2) * height * 0.070)
            phase = now * (1.65 + band * 0.20) + band * 1.7
            for strand in range(2 if self.low_graphics_quality else 3):
                points = []
                strand_phase = phase + strand * 0.74
                strand_offset = (strand - 1) * max(5, int(height * 0.012))
                for step in range(steps):
                    ratio = step / (steps - 1)
                    x = int(width * ratio)
                    taper = 0.35 + 0.65 * math.sin(math.pi * ratio)
                    wave = math.sin(ratio * math.tau * (2.4 + band * 0.72) + strand_phase)
                    fine = math.sin(ratio * math.tau * (11.0 + band * 1.4) - strand_phase * 0.68) * 0.34
                    micro = math.sin(ratio * math.tau * 31.0 + now * 2.8 + band) * 0.10
                    y = int(baseline + strand_offset + (wave + fine + micro) * amplitude * taper)
                    points.append((x, y))
                alpha = max(18, int((VISUALIZER_ALPHA - strand * 12) * (0.62 + level * 0.38)))
                pygame.draw.lines(layer, (*muted, alpha), False, points, 1)

        bar_count = 36 if self.low_graphics_quality else 72
        bar_top = int(height * 0.16)
        bar_bottom = int(height * 0.84)
        for column in range(bar_count):
            ratio = column / max(1, bar_count - 1)
            nearest = min(len(levels) - 1, int(ratio * len(levels)))
            level = levels[nearest]
            shimmer = 0.5 + 0.5 * math.sin(now * 4.0 + column * 0.63)
            alpha = int(8 + 26 * level * shimmer)
            if alpha <= 8:
                continue
            x = int(width * ratio)
            gap = max(8, width // bar_count)
            bar_height = int((bar_bottom - bar_top) * (0.16 + 0.28 * level) * shimmer)
            y1 = center_y - bar_height // 2
            y2 = center_y + bar_height // 2
            pygame.draw.line(layer, (46, 72, 104, alpha), (x, y1), (x, y2), max(1, gap // 7))

        grid_alpha = max(12, int(26 + average * 22))
        for offset in range(-5, 6):
            y = center_y + offset * max(16, height // 38)
            pygame.draw.line(layer, (30, 52, 79, grid_alpha), (0, y), (width, y), 1)
        for column in range(28):
            x = int(width * column / 27)
            drift = int(math.sin(now * 0.65 + column * 0.8) * 7)
            pygame.draw.line(layer, (26, 47, 72, 18), (x + drift, int(height * 0.11)), (x - drift, int(height * 0.89)), 1)
        return layer

    def _active_hold_lanes(self) -> set[int]:
        if not self.session:
            return set()
        return {
            self.source_to_active_lane(state.note.lane)
            for state in self.session.states
            if state.active_hold and state.note.lane in self.session.held_lanes and not state.complete
        }

    def _draw_hold_sparks(self, left: int, lane_width: int, field_top: int, line_y: int, now: float) -> None:
        active_lanes = self._active_hold_lanes()
        if not active_lanes:
            return
        band_height = max(42, min(120, line_y - field_top))
        top = max(field_top, line_y - band_height)
        for lane in active_lanes:
            if not 0 <= lane < self.active_lane_count:
                continue
            color = self.lane_color(lane)
            x = left + lane * lane_width
            center_x = x + lane_width // 2
            glow = pygame.Surface((lane_width - 2, line_y - top), pygame.SRCALPHA)
            glow.fill((*color, 24))
            pygame.draw.rect(glow, (*color, HOLD_SPARK_ALPHA), pygame.Rect(lane_width // 2 - 8, 0, 16, line_y - top), border_radius=8)
            pygame.draw.circle(glow, (*color, 150), (lane_width // 2, line_y - top - 10), max(8, lane_width // 9), width=2)
            self.surface.blit(glow, (x, top))
            for index in range(min(9, self.hold_particle_limit // max(1, len(active_lanes)))):
                phase = now * (7.0 + index * 0.37) + lane * 1.91 + index * 2.13
                spread = lane_width * 0.30
                spark_x = int(center_x + math.sin(phase) * spread)
                spark_y = int(line_y - 12 - ((now * 82 + index * 17 + lane * 11) % band_height))
                radius = 1 + (index % 3)
                alpha = 120 + int((math.sin(phase * 1.7) + 1.0) * 45)
                cache = getattr(self, "_hold_spark_images", None)
                if cache is None:
                    cache = self._hold_spark_images = {}
                key = (color, radius, alpha)
                spark = cache.get(key)
                if spark is None:
                    spark = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
                    pygame.draw.circle(spark, (*WHITE, min(235, alpha)), (radius * 3, radius * 3), radius)
                    pygame.draw.circle(spark, (*color, min(210, alpha)), (radius * 3, radius * 3), radius + 2, width=1)
                    if len(cache) >= 2048:
                        del cache[next(iter(cache))]
                    cache[key] = spark
                self.surface.blit(spark, (spark_x - radius * 3, spark_y - radius * 3))

    def _draw_hit_effects(self, left: int, lane_width: int, field_top: int, line_y: int) -> None:
        """ノーツ・判定文字を覆わない、短時間のレーン別エフェクトを描く。"""
        now = time.perf_counter()
        self.hit_effects = [effect for effect in self.hit_effects if now - effect.started_at < effect.duration]
        for effect in self.hit_effects:
            progress = max(0.0, min(1.0, (now - effect.started_at) / effect.duration))
            alpha = int(165 * (1.0 - progress) ** 1.7)
            if alpha <= 0:
                continue
            # 判定の成否ではなく、押したレーンを即座に追えるテーマ色を使う。
            color = self.lane_color(effect.lane)
            if effect.judgment is Judgment.PERFECT:
                flash_alpha = int(135 * (1.0 - progress) ** 1.35)
                if flash_alpha > 0:
                    flash = pygame.Surface((lane_width - 2, max(1, line_y - field_top)), pygame.SRCALPHA)
                    flash.fill((*color, flash_alpha))
                    glow_width = max(4, int(lane_width * (0.12 + 0.12 * (1.0 - progress))))
                    pygame.draw.rect(flash, (*WHITE, max(0, flash_alpha - 35)), flash.get_rect(), width=glow_width)
                    self.surface.blit(flash, (left + effect.lane * lane_width, field_top))
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

    def _show_judgment_feedback(self, judgment: Judgment | None, lane: int | None = None) -> None:
        """最新判定を中央表示と左側履歴へ反映する。"""
        if judgment is not None:
            now = time.perf_counter()
            self.judgment_feedback = JudgmentFeedback(judgment=judgment, started_at=now)
            self.judgment_log.append(JudgmentLogEntry(judgment=judgment, lane=lane, started_at=now))
            self.judgment_log = self.judgment_log[-JUDGMENT_LOG_LIMIT:]

    def _draw_judgment_feedback(self) -> None:
        """判定文字を0.6秒で上方へ少し移動させながらフェードアウトする。"""
        feedback = self.judgment_feedback
        if feedback is None:
            return
        elapsed = time.perf_counter() - feedback.started_at
        if elapsed >= feedback.duration:
            self.judgment_feedback = None
            return
        progress = max(0.0, min(1.0, elapsed / feedback.duration))
        fade_start = 0.55
        alpha = 255 if progress <= fade_start else int(255 * (1.0 - (progress - fade_start) / (1.0 - fade_start)))
        if alpha <= 0:
            self.judgment_feedback = None
            return
        rendered = self.fonts["h1"].render(feedback.judgment.value, True, JUDGMENT_COLORS[feedback.judgment])
        rendered.set_alpha(alpha)
        width, height = self.size
        offset_y = int(12 * progress)
        self.surface.blit(rendered, rendered.get_rect(center=(width // 2, height // 2 - offset_y)))

    def _hud_panel_width(self, left: int) -> int:
        return min(260, left - 38)

    def _draw_neon_hud_card(self, rect: pygame.Rect, accent: tuple[int, int, int], now: float, glow_strength: float = 0.0) -> None:
        """サンプルの切り欠きパネルを、半透明ネオン枠として描く。"""
        cut = 10
        points = [
            (rect.left + cut, rect.top),
            (rect.right - cut, rect.top),
            (rect.right, rect.top + cut),
            (rect.right, rect.bottom - cut),
            (rect.right - cut, rect.bottom),
            (rect.left + cut, rect.bottom),
            (rect.left, rect.bottom - cut),
            (rect.left, rect.top + cut),
        ]
        commands: list[tuple] = []
        glow_alpha = int(24 + 88 * max(0.0, min(1.0, glow_strength)))
        commands.append(("polygon", (*accent, glow_alpha // 2), [(x, y + 3) for x, y in points], 7))
        commands.append(("polygon", (5, 12, 28, 238), points))
        commands.append(("lines", (*accent, 150 + glow_alpha // 2), True, points, 1))

        rail_y = rect.top + 5
        rail_start = rect.left + 22
        rail_end = rect.right - 18
        commands.append(("line", (*accent, 65), (rail_start, rail_y), (rail_end, rail_y), 3))
        shimmer = (now * 0.28) % 1.0
        shimmer_x = int(rail_start + (rail_end - rail_start) * shimmer)
        commands.append(("line", (*WHITE, 225), (shimmer_x - 5, rail_y), (shimmer_x + 5, rail_y), 2))

        for x, y, sx, sy in (
            (rect.left + 4, rect.top + 13, 1, 1),
            (rect.right - 4, rect.top + 13, -1, 1),
            (rect.left + 4, rect.bottom - 13, 1, -1),
            (rect.right - 4, rect.bottom - 13, -1, -1),
        ):
            commands.append(("line", (*accent, 125), (x, y), (x + sx * 8, y), 2))
            commands.append(("line", (*accent, 125), (x, y), (x, y + sy * 8), 2))
        self._blit_local_primitives(commands)

    def _live_accuracy_rank(self) -> tuple[float, str]:
        if not self.session:
            return 0.0, "D"
        counts = self.session.judgment_counts
        judged = sum(int(counts.get(judgment.value, 0)) for judgment in Judgment)
        weighted = (
            int(counts.get(Judgment.PERFECT.value, 0))
            + int(counts.get(Judgment.GREAT.value, 0)) * 0.8
            + int(counts.get(Judgment.GOOD.value, 0)) * 0.5
        )
        accuracy = 0.0 if judged == 0 else weighted / judged * 100.0
        misses = int(counts.get(Judgment.MISS.value, 0))
        rank = "S+" if accuracy >= 98 and misses == 0 else "S" if accuracy >= 95 else "A" if accuracy >= 90 else "B" if accuracy >= 80 else "C" if accuracy >= 70 else "D"
        return accuracy, rank

    def _draw_judgment_panel(self, left: int, field_top: int, line_y: int) -> None:
        """左側の統計カードへ判定数、ライブRATE、直近判定をまとめる。"""
        if not self.session:
            return
        now = time.perf_counter()
        self.judgment_log = [entry for entry in self.judgment_log if now - entry.started_at < entry.duration]

        panel_width = self._hud_panel_width(left)
        if panel_width < 170:
            return
        x = 18
        stats_rect = pygame.Rect(x, 243, panel_width, min(282, max(250, line_y - 330)))
        self._draw_neon_hud_card(stats_rect, CYAN, now)
        self.text("JUDGMENT", "mono", MUTED, pos=(stats_rect.left + 17, stats_rect.top + 15))

        rows = (Judgment.PERFECT, Judgment.GREAT, Judgment.GOOD, Judgment.MISS)
        row_y = stats_rect.top + 48
        for judgment in rows:
            color = JUDGMENT_COLORS[judgment]
            count = self.session.judgment_counts.get(judgment.value, 0)
            self.text(judgment.value, "body", color, pos=(stats_rect.left + 18, row_y))
            value = self.fonts["mono"].render(f"{count:04d}", True, MUTED if count == 0 else WHITE)
            self.surface.blit(value, value.get_rect(topright=(stats_rect.right - 18, row_y + 2)))
            row_y += 28

        divider_y = stats_rect.top + 164
        pygame.draw.line(self.surface, (54, 83, 116), (stats_rect.left + 15, divider_y), (stats_rect.right - 15, divider_y), 1)
        accuracy, rank = self._live_accuracy_rank()
        self.text("RATE", "small", MUTED, pos=(stats_rect.left + 18, divider_y + 12))
        self.text(f"{accuracy:05.2f}%", "body", WHITE, pos=(stats_rect.left + 18, divider_y + 34))
        rank_color = self._result_grade_color(rank)
        rank_badge = pygame.Rect(stats_rect.right - 72, divider_y + 13, 48, 48)
        badge_points = [
            (rank_badge.centerx, rank_badge.top),
            (rank_badge.right, rank_badge.centery),
            (rank_badge.centerx, rank_badge.bottom),
            (rank_badge.left, rank_badge.centery),
        ]
        badge_layer = pygame.Surface(self.size, pygame.SRCALPHA)
        pygame.draw.polygon(badge_layer, (*rank_color, 35), badge_points)
        pygame.draw.polygon(badge_layer, (*rank_color, 210), badge_points, width=2)
        self.surface.blit(badge_layer, (0, 0))
        rank_text = self.fonts["hud_rank"].render(rank, True, rank_color)
        self.surface.blit(rank_text, rank_text.get_rect(center=rank_badge.center))

        recent_y = stats_rect.bottom - 47
        pygame.draw.line(self.surface, (54, 83, 116), (stats_rect.left + 15, recent_y - 8), (stats_rect.right - 15, recent_y - 8), 1)
        self.text("RECENT", "small", MUTED, pos=(stats_rect.left + 18, recent_y))
        for entry in reversed(self.judgment_log[-1:]):
            elapsed = max(0.0, now - entry.started_at)
            alpha = max(70, int(255 * (1.0 - elapsed / entry.duration)))
            label = entry.judgment.value
            keys = self.active_lane_keys
            if entry.lane is not None and 0 <= entry.lane < len(keys):
                label = f"{keys[entry.lane].upper()}  {label}"
            rendered = self.fonts["small"].render(label, True, JUDGMENT_COLORS[entry.judgment])
            rendered.set_alpha(alpha)
            self.surface.blit(rendered, rendered.get_rect(topright=(stats_rect.right - 18, recent_y)))

        info_rect = pygame.Rect(x, stats_rect.bottom + 8, panel_width, 58)
        if info_rect.bottom < line_y - 8:
            self._draw_neon_hud_card(info_rect, GREEN, now)
            difficulty = self.chart.difficulty.label if self.chart else "---"
            self.text(difficulty, "small", GREEN, pos=(info_rect.left + 16, info_rect.top + 10))
            self.text(f"{self.active_lane_count} LANE", "small", WHITE, center=(info_rect.centerx, info_rect.top + 18))
            self.text(f"SPEED {int(self.settings['note_speed'])}", "small", MUTED, pos=(info_rect.left + 16, info_rect.top + 34))

    def _hud_text_surface(self, slot: str, value: str, font: str, color: tuple[int, int, int]) -> pygame.Surface:
        """Keep only the current text image for each HUD slot."""
        key = (value, self.fonts[font], color)
        cached = self._hud_text_cache.get(slot)
        if cached is None or cached[0] != key:
            cached = (key, self.fonts[font].render(value, True, color))
            self._hud_text_cache[slot] = cached
        return cached[1]

    def _draw_score_hud(self, left: int, now: float) -> None:
        """サンプルに合わせ、SCOREとCOMBOを独立した大型カードで描く。"""
        if not self.session:
            return
        panel_width = self._hud_panel_width(left)
        if panel_width < 170:
            self.text(f"SCORE  {self.session.score:07d}", "mono", pos=(25, 38))
            self.text(f"COMBO  {self.session.combo}", "mono", YELLOW, pos=(25, 68))
            return

        x = 18
        score_rect = pygame.Rect(x, 18, panel_width, 98)
        combo_rect = pygame.Rect(x, 124, panel_width, 111)
        latest_hit = 0.0
        perfect_hit = False
        clock_now = time.perf_counter()
        for effect in self.hit_effects:
            elapsed = clock_now - effect.started_at
            if 0.0 <= elapsed <= effect.duration:
                latest_hit = max(latest_hit, 1.0 - elapsed / max(0.001, effect.duration))
                perfect_hit = perfect_hit or effect.judgment is Judgment.PERFECT

        self._draw_neon_hud_card(score_rect, CYAN, now, latest_hit if perfect_hit else latest_hit * 0.5)
        self._draw_neon_hud_card(combo_rect, MAGENTA, now, latest_hit)

        self.text("SCORE", "body", MUTED, pos=(score_rect.left + 20, score_rect.top + 15))
        pygame.draw.line(self.surface, (80, 211, 238), (score_rect.left + 20, score_rect.top + 42), (score_rect.right - 20, score_rect.top + 42), 2)
        score_value = f"{self.session.score:07d}"
        score_glow = self._hud_text_surface("score_glow", score_value, "hud_score", CYAN)
        score_glow.set_alpha(70 + int(latest_hit * 120))
        score_text = self._hud_text_surface("score", score_value, "hud_score", WHITE)
        score_position = score_text.get_rect(center=(score_rect.centerx, score_rect.top + 68))
        self.surface.blit(score_glow, score_position.move(0, 2))
        self.surface.blit(score_text, score_position)

        self.text("COMBO", "body", MUTED, pos=(combo_rect.left + 20, combo_rect.top + 14))
        combo_value = f"{self.session.combo:04d}"
        combo_glow = self._hud_text_surface("combo_glow", combo_value, "hud_combo", MAGENTA)
        combo_glow.set_alpha(95 + int(latest_hit * 120))
        combo_text = self._hud_text_surface("combo", combo_value, "hud_combo", WHITE if self.session.combo == 0 else (225, 207, 255))
        combo_position = combo_text.get_rect(center=(combo_rect.centerx, combo_rect.top + 66))
        self.surface.blit(combo_glow, combo_position.move(0, 3))
        self.surface.blit(combo_text, combo_position)

        layer = pygame.Surface(self.size, pygame.SRCALPHA)
        meter_rect = pygame.Rect(combo_rect.left + 18, combo_rect.bottom - 17, combo_rect.width - 36, 4)
        pygame.draw.rect(layer, (54, 67, 91, 210), meter_rect, border_radius=2)
        meter_width = int(meter_rect.width * min(1.0, (self.session.combo % 50) / 50.0))
        if self.session.combo > 0 and self.session.combo % 50 == 0:
            meter_width = meter_rect.width
        if meter_width > 0:
            fill_rect = pygame.Rect(meter_rect.left, meter_rect.top, meter_width, meter_rect.height)
            pygame.draw.rect(layer, (*MAGENTA, 230), fill_rect, border_radius=2)
            pygame.draw.line(layer, (*WHITE, 220), (fill_rect.left, fill_rect.top), (fill_rect.right, fill_rect.top), 1)
            sparkle_x = fill_rect.right
            pygame.draw.line(layer, (*WHITE, 235), (sparkle_x - 5, meter_rect.centery), (sparkle_x + 5, meter_rect.centery), 1)
            pygame.draw.line(layer, (*WHITE, 235), (sparkle_x, meter_rect.centery - 5), (sparkle_x, meter_rect.centery + 5), 1)
        self.surface.blit(layer, (0, 0))

    def _play_feedback(self, judgment: Judgment | None, lane: int | None = None) -> None:
        if judgment is not None and judgment in self.feedback_sounds:
            self.feedback_sounds[judgment].play()
        self._show_judgment_feedback(judgment, lane)
        if lane is not None:
            self._emit_hit_effect(lane, judgment)
        self._check_combo_milestone()

    def _check_combo_milestone(self) -> None:
        """現在の連続コンボが節目へ到達した瞬間に、毎回バナーとマスコット演出を表示する。"""
        if not self.session:
            return
        if self.session.combo in COMBO_MILESTONES:
            now = time.perf_counter()
            self.combo_banner = f"{self.session.combo} COMBO!"
            self.combo_banner_until = now + 1.8
            self.mascot_combo_zoom_until = now + MASCOT_COMBO_ZOOM_DURATION
            self.combo_cutin_until = now + COMBO_CUTIN_DURATION
            self.combo_cutin_combo = int(self.session.combo)

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
        self.chart_candidates = []
        self.chart_candidate_index = -1
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

    def choose_background_file(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askopenfilename(
                title="背景画像を選択",
                filetypes=[("Image", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")],
            )
            root.destroy()
        except Exception as error:
            self.error = f"背景画像の選択を開けませんでした: {error}"
            return
        if selected:
            candidate = Path(selected)
            if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                self.error = "背景には PNG / JPEG / WebP を選択してください。"
                return
            self.settings["background_image"] = str(candidate)
            self.settings["background_mode"] = "image"
            self.background_image_cache.clear()
            self.message = "背景画像を変更しました。保存してください。"

    def packaged_background_files(self) -> list[Path]:
        folder = self.resource_path("assets/backgrounds")
        try:
            return sorted(
                (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS),
                key=lambda path: path.name.lower(),
            )
        except OSError:
            return []

    def current_background_image_path(self) -> Path | None:
        value = str(self.settings.get("background_image", "")).strip()
        if not value:
            packaged = self.packaged_background_files()
            return packaged[0] if packaged else None
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate
        return self.resource_path(f"assets/backgrounds/{value}")

    def background_image_label(self) -> str:
        path = self.current_background_image_path()
        if path is None:
            return "未選択"
        return path.stem

    def cycle_background_image(self, direction: int) -> None:
        packaged = self.packaged_background_files()
        current = self.current_background_image_path()
        if not packaged:
            self.choose_background_file()
            return
        try:
            current_resolved = current.resolve() if current is not None else None
        except OSError:
            current_resolved = None
        resolved = []
        for path in packaged:
            try:
                resolved.append(path.resolve())
            except OSError:
                resolved.append(path)
        current_index = resolved.index(current_resolved) if current_resolved in resolved else 0
        selected = packaged[(current_index + direction) % len(packaged)]
        self.settings["background_image"] = selected.name
        self.settings["background_mode"] = "image"
        self.background_image_cache.clear()

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
        lane_count = self.active_lane_count
        chart_files = [folder / "charts" / self.analysis.music_hash / f"{lane_count}lane" / f"{difficulty.value}.json"]
        if lane_count == 5:
            chart_files.append(folder / "charts" / self.analysis.music_hash / f"{difficulty.value}.json")
        for chart_file in chart_files:
            try:
                if not chart_file.is_file():
                    continue
                chart = Chart.from_dict(json.loads(chart_file.read_text(encoding="utf-8")))
                chart.metadata.setdefault("lane_count", lane_count)
                chart.metadata.setdefault("lane_mode", f"{lane_count}lane")
                if chart.music_hash != self.analysis.music_hash or chart.generator_version != ChartGenerator.VERSION:
                    continue
                if chart_lane_count(chart) != lane_count:
                    continue
                return chart
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
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
        self.chart_candidates = []
        self.chart_candidate_index = -1
        self.error = ""
        self.message = "体験版の同梱キャッシュを読み込みました。"
        self.screen = "difficulty"

    @property
    def current_library_folder(self) -> str:
        return active_library_folder(self.profile)

    def current_library_folders(self) -> list[str]:
        return library_folders(self.profile)

    def cycle_library_folder(self, direction: int) -> None:
        folders = self.current_library_folders()
        current = self.current_library_folder
        try:
            index = folders.index(current)
        except ValueError:
            index = 0
        selected = folders[(index + direction) % len(folders)]
        set_active_library_folder(self.paths, self.profile, selected)
        self.playlist_selected_index = 0
        self.playlist_scroll_index = 0
        self.message = f"フォルダを開きました: {selected}"

    def create_library_folder(self) -> None:
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            name = simpledialog.askstring("フォルダ作成", "新しいフォルダ名", parent=root)
            root.destroy()
        except Exception as error:
            self.error = f"フォルダ作成画面を開けませんでした: {error}"
            return
        if not name:
            return
        folder = set_active_library_folder(self.paths, self.profile, normalize_library_folder_name(name))
        self.playlist_selected_index = 0
        self.playlist_scroll_index = 0
        self.message = f"フォルダを作成しました: {folder}"

    def move_selected_playlist_song_to_current_folder(self) -> None:
        entries = self.playlist_entries(include_all_user_songs=True)
        if not (0 <= self.playlist_selected_index < len(entries)):
            return
        entry = entries[self.playlist_selected_index]
        if entry.source == "demo":
            self.message = "デモ曲は移動できません。ユーザー曲を選択してください。"
            return
        folder = self.current_library_folder
        changed = assign_recent_song_folder(self.paths, self.profile, entry.music_hash, str(entry.path), folder)
        self.message = f"{entry.path.stem} を {folder} に移動しました。" if changed else "この曲はユーザーライブラリに見つかりませんでした。"
        self._clamp_playlist_position()

    def playlist_entries(self, *, include_all_user_songs: bool = False) -> list[PlaylistEntry]:
        """同梱デモ曲とユーザー解析曲を、現在のライブラリフォルダ単位で一覧化する。"""
        by_hash: dict[str, PlaylistEntry] = {}
        current_folder = self.current_library_folder
        show_home = current_folder == "ホーム" or include_all_user_songs
        folder = self.paths.demo_songs
        manifest_file = folder / "demo_manifest.json" if folder is not None else None
        try:
            manifest_songs = json.loads(manifest_file.read_text(encoding="utf-8")).get("songs", []) if manifest_file and manifest_file.is_file() else []
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            manifest_songs = []
        if show_home:
            for raw in manifest_songs:
                if not isinstance(raw, dict):
                    continue
                path = folder / str(raw.get("file", "")) if folder is not None else Path()
                digest = str(raw.get("music_hash", ""))
                if not digest or path.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                by_hash[digest] = PlaylistEntry(
                    music_hash=digest,
                    path=path,
                    source="demo",
                    exists=path.is_file(),
                    bpm=float(raw.get("bpm", 0.0)),
                    duration=float(raw.get("duration", 0.0)),
                    folder="ホーム",
                )
            # マニフェストがない開発時にも、フォルダ内のデモ曲は一覧へ残す。
            for path in self.demo_song_files():
                try:
                    digest = music_hash(path)
                except OSError:
                    continue
                by_hash.setdefault(digest, PlaylistEntry(digest, path, "demo", path.is_file(), folder="ホーム"))
        for entry in self.library_entries():
            digest = str(entry.get("music_hash", ""))
            if not digest:
                continue
            entry_folder = normalize_library_folder_name(entry.get("folder"))
            if not include_all_user_songs and entry_folder != current_folder:
                continue
            path = Path(str(entry.get("source_path", ""))).expanduser()
            existing = by_hash.get(digest)
            if existing is not None:
                existing.source = "both"
                existing.folder = entry_folder
                # ユーザーが手元に置いた同じ曲を優先し、デモが欠損しても使えるようにする。
                if path.is_file():
                    existing.path = path
                    existing.exists = True
                existing.last_used = str(entry.get("last_used", ""))
                continue
            by_hash[digest] = PlaylistEntry(
                music_hash=digest,
                path=path,
                source="library",
                exists=path.is_file(),
                bpm=float(entry.get("bpm", 0.0)),
                duration=float(entry.get("duration", 0.0)),
                last_used=str(entry.get("last_used", "")),
                folder=entry_folder,
            )
        return sorted(by_hash.values(), key=lambda entry: (entry.source != "demo", entry.last_used), reverse=True)

    def _clamp_playlist_position(self) -> None:
        entries = self.playlist_entries()
        if not entries:
            self.playlist_scroll_index = 0
            self.playlist_selected_index = 0
            return
        self.playlist_selected_index = max(0, min(self.playlist_selected_index, len(entries) - 1))
        visible_rows = self._playlist_visible_rows()
        max_scroll = max(0, len(entries) - visible_rows)
        self.playlist_scroll_index = max(0, min(self.playlist_scroll_index, max_scroll))
        if self.playlist_selected_index < self.playlist_scroll_index:
            self.playlist_scroll_index = self.playlist_selected_index
        elif self.playlist_selected_index >= self.playlist_scroll_index + visible_rows:
            self.playlist_scroll_index = self.playlist_selected_index - visible_rows + 1

    def open_playlist(self, launch_mode: str = "normal") -> None:
        self.launch_mode = "practice" if launch_mode == "practice" else "normal"
        self._clamp_playlist_position()
        self.set_screen("select")

    def scroll_playlist(self, delta: int) -> None:
        entries = self.playlist_entries()
        if not entries:
            return
        visible_rows = self._playlist_visible_rows()
        max_scroll = max(0, len(entries) - visible_rows)
        self.playlist_scroll_index = max(0, min(self.playlist_scroll_index + delta, max_scroll))
        self.playlist_selected_index = max(self.playlist_scroll_index, min(self.playlist_selected_index, self.playlist_scroll_index + visible_rows - 1))

    def move_playlist_selection(self, delta: int) -> None:
        entries = self.playlist_entries()
        if not entries:
            return
        self.playlist_selected_index = max(0, min(self.playlist_selected_index + delta, len(entries) - 1))
        self._clamp_playlist_position()

    def select_playlist_entry(self, index: int) -> None:
        entries = self.playlist_entries()
        if not (0 <= index < len(entries)):
            return
        self.playlist_selected_index = index
        self._clamp_playlist_position()
        entry = entries[index]
        if not entry.exists:
            self.error = "この曲の音源ファイルが見つかりません。再リンク機能は次の更新で追加します。"
            return
        if entry.source in {"demo", "both"} and self.is_demo_song(entry.path):
            self.load_demo_song(entry.path)
            return
        self.load_recent_song({"music_hash": entry.music_hash, "source_path": str(entry.path), "folder": entry.folder})

    def select_current_playlist_entry(self) -> None:
        self.select_playlist_entry(self.playlist_selected_index)

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
        visible_rows = self._library_visible_rows()
        max_scroll = max(0, len(entries) - visible_rows)
        self.library_scroll_index = max(0, min(self.library_scroll_index, max_scroll))
        if self.library_selected_index < self.library_scroll_index:
            self.library_scroll_index = self.library_selected_index
        elif self.library_selected_index >= self.library_scroll_index + visible_rows:
            self.library_scroll_index = self.library_selected_index - visible_rows + 1

    def open_library(self) -> None:
        self._clamp_library_position()
        self.screen = "library"

    def scroll_library(self, delta: int) -> None:
        entries = self.library_entries()
        if not entries:
            return
        visible_rows = self._library_visible_rows()
        max_scroll = max(0, len(entries) - visible_rows)
        self.library_scroll_index = max(0, min(self.library_scroll_index + delta, max_scroll))
        first_visible = self.library_scroll_index
        last_visible = min(len(entries) - 1, first_visible + visible_rows - 1)
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

    def reward_manager_entries(self) -> list[RewardCatalogItem]:
        """設定・画像ファイル・累積スコアを突合した報酬管理一覧。"""
        return reward_catalog(self.paths, self.profile)

    def shop_items(self) -> list[ShopItem]:
        items = [
            ShopItem(
                item_id=mascot_cosmetic_id(mascot.mascot_id),
                category="MASCOT",
                name=mascot.name,
                price=self.mascot_unlock_requirement(mascot.mascot_id),
                owned=self.is_mascot_available(mascot.mascot_id),
                available=mascot.image_path.is_file(),
                asset_path=mascot.image_path,
                mascot_id=mascot.mascot_id,
            )
            for mascot in self.mascot_catalog
        ]
        for reward in self.reward_manager_entries():
            if reward.required_score is None:
                continue
            items.append(
                ShopItem(
                    item_id=f"reward.{reward.name}",
                    category="REWARD",
                    name=Path(reward.name).stem.replace("_", " ").upper(),
                    price=int(reward.required_score),
                    owned=reward.unlocked,
                    available=reward.exists,
                    asset_path=reward.path if reward.exists else None,
                )
            )
        return items

    def _clamp_shop_position(self) -> None:
        items = self.shop_items()
        if not items:
            self.shop_selected_index = 0
            self.shop_scroll_index = 0
            return
        self.shop_selected_index = max(0, min(self.shop_selected_index, len(items) - 1))
        max_scroll = max(0, len(items) - SHOP_VISIBLE_ROWS)
        self.shop_scroll_index = max(0, min(self.shop_scroll_index, max_scroll))
        if self.shop_selected_index < self.shop_scroll_index:
            self.shop_scroll_index = self.shop_selected_index
        elif self.shop_selected_index >= self.shop_scroll_index + SHOP_VISIBLE_ROWS:
            self.shop_scroll_index = self.shop_selected_index - SHOP_VISIBLE_ROWS + 1

    def open_shop(self) -> None:
        self.shop_confirmation_id = None
        self._clamp_shop_position()
        self.set_screen("shop")

    def move_shop_selection(self, delta: int) -> None:
        items = self.shop_items()
        if not items:
            return
        self.shop_selected_index = max(0, min(self.shop_selected_index + delta, len(items) - 1))
        self.shop_confirmation_id = None
        self._clamp_shop_position()

    def activate_shop_purchase(self) -> None:
        items = self.shop_items()
        if not (0 <= self.shop_selected_index < len(items)):
            return
        item = items[self.shop_selected_index]
        if item.owned:
            self.message = f"{item.name} は購入済みです。"
            self.shop_confirmation_id = None
            return
        if not item.available:
            self.error = f"{item.name} の素材がまだ追加されていません。"
            self.shop_confirmation_id = None
            return
        balance = int(self.profile.get("wallet_score", 0))
        if balance < item.price:
            self.message = f"BEAT POINTがあと {item.price - balance:,} 必要です。"
            self.shop_confirmation_id = None
            return
        if self.shop_confirmation_id != item.item_id:
            self.shop_confirmation_id = item.item_id
            self.message = f"{item.name} を {item.price:,} BPで購入しますか？ もう一度ENTERで決定"
            return
        if purchase_unlock(self.paths, self.profile, item.item_id, item.price):
            self.message = f"{item.name} を購入しました。設定またはギャラリーで使用できます。"
        else:
            self.error = "購入を完了できませんでした。残高と購入状態を確認してください。"
        self.shop_confirmation_id = None

    def _clamp_reward_manager_position(self) -> None:
        entries = self.reward_manager_entries()
        if not entries:
            self.reward_manager_scroll_index = 0
            self.reward_manager_selected_index = 0
            return
        self.reward_manager_selected_index = max(0, min(self.reward_manager_selected_index, len(entries) - 1))
        visible_rows = self._reward_manager_visible_rows()
        max_scroll = max(0, len(entries) - visible_rows)
        self.reward_manager_scroll_index = max(0, min(self.reward_manager_scroll_index, max_scroll))
        if self.reward_manager_selected_index < self.reward_manager_scroll_index:
            self.reward_manager_scroll_index = self.reward_manager_selected_index
        elif self.reward_manager_selected_index >= self.reward_manager_scroll_index + visible_rows:
            self.reward_manager_scroll_index = self.reward_manager_selected_index - visible_rows + 1

    def open_reward_manager(self) -> None:
        self._clamp_reward_manager_position()
        self.set_screen("reward_manager")

    def scroll_reward_manager(self, delta: int) -> None:
        entries = self.reward_manager_entries()
        if not entries:
            return
        visible_rows = self._reward_manager_visible_rows()
        max_scroll = max(0, len(entries) - visible_rows)
        self.reward_manager_scroll_index = max(0, min(self.reward_manager_scroll_index + delta, max_scroll))
        first_visible = self.reward_manager_scroll_index
        last_visible = min(len(entries) - 1, first_visible + visible_rows - 1)
        self.reward_manager_selected_index = max(first_visible, min(self.reward_manager_selected_index, last_visible))

    def move_reward_manager_selection(self, delta: int) -> None:
        entries = self.reward_manager_entries()
        if not entries:
            return
        self.reward_manager_selected_index = max(0, min(self.reward_manager_selected_index + delta, len(entries) - 1))
        self._clamp_reward_manager_position()

    def select_reward_manager_entry(self, index: int) -> None:
        entries = self.reward_manager_entries()
        if not (0 <= index < len(entries)):
            return
        self.reward_manager_selected_index = index
        self._clamp_reward_manager_position()
        item = entries[index]
        if not item.exists:
            self.error = "設定はありますが、画像ファイルが rewards フォルダに見つかりません。"
            return
        if item.required_score is None:
            self.error = "この画像には reward_config.json の price 設定がありません。"
            return
        if not item.unlocked:
            self.message = f"{Path(item.name).stem} はBEAT SHOPで購入できます。あと {int(item.remaining_score or 0):,} BPです。"
            return
        self.open_reward(RewardImage(item.name, item.path, item.required_score, True))

    def show_reward_folder(self) -> None:
        self.message = f"画像フォルダ: {self.paths.rewards}"

    def show_reward_config(self) -> None:
        self.message = f"設定ファイル: {self.paths.rewards / 'reward_config.json'}"

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
            record_recent_song(self.paths, self.profile, cached, folder=self.current_library_folder)
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
                record_recent_song(self.paths, self.profile, event, folder=self.current_library_folder)
                if self.worker is worker:
                    self.worker = None
                self.message = "解析とキャッシュ保存が完了しました。"
                self.screen = "difficulty"
                return

    def _generate_chart(self, difficulty: Difficulty, *, variant: int, persist: bool = True) -> Chart:
        """解析済み楽曲から指定variantの譜面を生成する。試作候補は明示採用まで保存しない。"""
        if not self.analysis:
            raise RuntimeError("解析結果がありません。")
        style = ChartGenerator.candidate_style(self.analysis, variant)
        chart = ChartGenerator().generate(self.analysis, difficulty, variant=variant, lane_count=self.active_lane_count, style=style)
        report = ChartValidator().validate(chart)
        chart.metadata["validation_removed"] = report.removed_notes
        chart.metadata["validation_issues"] = report.issues[:20]
        balance_chart(chart, self.analysis)
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
        chart = load_chart(self.paths, self.analysis.music_hash, difficulty.value, self.active_lane_count)
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
        self.chart_candidates = []
        self.chart_candidate_index = -1
        if self.launch_mode == "practice":
            self.open_practice_setup()
        else:
            self.screen = "chart_summary"

    @property
    def chart_is_pending(self) -> bool:
        return self.pending_chart is not None and self.chart is self.pending_chart

    def _candidate_variant_numbers(self) -> list[int]:
        charts = [chart for chart in [self.committed_chart, *self.chart_candidates] if chart is not None]
        return [int(chart.metadata.get("generation_variant", 0)) for chart in charts]

    def _select_chart_candidate(self, index: int) -> None:
        if not self.chart_candidates:
            self.pending_chart = None
            self.chart_candidate_index = -1
            if self.committed_chart is not None:
                self.chart = self.committed_chart
            return
        self.chart_candidate_index = max(0, min(index, len(self.chart_candidates) - 1))
        self.pending_chart = self.chart_candidates[self.chart_candidate_index]
        self.chart = self.pending_chart

    def regenerate_chart(self) -> None:
        """確定済み譜面を残したまま、直近5件まで未保存候補を保持して生成する。"""
        if not self.analysis or not self.chart:
            self.error = "再生成する譜面がありません。"
            self.screen = "difficulty"
            return
        base_chart = self.committed_chart or self.pending_chart or self.chart
        next_variant = max(self._candidate_variant_numbers() or [int(base_chart.metadata.get("generation_variant", 0))]) + 1
        candidate = self._generate_chart(base_chart.difficulty, variant=next_variant, persist=False)
        self.chart_candidates.append(candidate)
        if len(self.chart_candidates) > CHART_CANDIDATE_LIMIT:
            self.chart_candidates = self.chart_candidates[-CHART_CANDIDATE_LIMIT:]
        self._select_chart_candidate(len(self.chart_candidates) - 1)
        self.message = f"{self.chart.difficulty.label}の試作候補 {self.chart_candidate_index + 1}/{len(self.chart_candidates)} を生成しました。採用するまで保存されません。"
        self.screen = "chart_summary"

    def move_chart_candidate(self, direction: int) -> None:
        """生成済みの試作候補を前後に切り替える。"""
        if not self.chart_candidates:
            self.message = "まだ試作候補がありません。Rで生成できます。"
            return
        self._select_chart_candidate((self.chart_candidate_index + direction) % len(self.chart_candidates))
        variant = int(self.chart.metadata.get("generation_variant", 0)) + 1 if self.chart else 0
        self.message = f"試作候補 {self.chart_candidate_index + 1}/{len(self.chart_candidates)}（生成候補 {variant}）を表示中です。"

    def adopt_pending_chart(self) -> None:
        """選択中の試作候補を、この曲・難易度の確定キャッシュとして保存する。"""
        if self.pending_chart is None:
            return
        save_chart(self.paths, self.pending_chart)
        self.committed_chart = self.pending_chart
        self.chart = self.pending_chart
        self.pending_chart = None
        self.chart_candidates = []
        self.chart_candidate_index = -1
        self.message = "試作候補を採用して保存しました。"
        self.set_screen("chart_summary")

    def discard_pending_chart(self) -> None:
        """未保存の試作候補をすべて破棄し、以前の確定譜面へ戻す。"""
        if self.pending_chart is None and not self.chart_candidates:
            return
        self.pending_chart = None
        self.chart_candidates = []
        self.chart_candidate_index = -1
        if self.committed_chart is not None:
            self.chart = self.committed_chart
        self.message = "試作候補を破棄し、以前の譜面を残しました。"
        self.set_screen("chart_summary")

    def _practice_chart(self) -> Chart:
        """開始位置より前のノーツを含めず、区間練習だけの判定対象を作る。"""
        if self.chart is None:
            raise RuntimeError("練習する譜面がありません。")
        notes: list[Note] = []
        for note in self.chart.notes:
            if note.time < self.practice_start - 0.001 or note.time > self.practice_end + 0.001:
                continue
            if note.end_time is not None and note.end_time > self.practice_end + 0.001:
                # 区間末尾をまたぐ長押しは練習範囲に収め、離すタイミングを明確にする。
                notes.append(Note(note.time, note.lane, note.kind, self.practice_end, note.source, note.strength))
            else:
                notes.append(Note(note.time, note.lane, note.kind, note.end_time, note.source, note.strength))
        return Chart(
            version=self.chart.version,
            music_hash=self.chart.music_hash,
            difficulty=self.chart.difficulty,
            seed=self.chart.seed,
            song_duration=self.practice_end,
            notes=notes,
            generator_version=self.chart.generator_version,
            metadata={**self.chart.metadata, "practice_start": self.practice_start, "practice_end": self.practice_end},
        )

    def open_practice_setup(self) -> None:
        if not self.analysis or not self.chart:
            self.error = "練習する解析結果または譜面がありません。"
            self.set_screen("select")
            return
        self.practice_start = 0.0
        self.practice_end = min(float(self.analysis.duration), PRACTICE_DEFAULT_DURATION)
        self.practice_loop = True
        self.practice_round = 0
        self.practice_best_accuracy = 0.0
        self.set_screen("practice_setup")

    def adjust_practice_boundary(self, target: str, delta: float) -> None:
        if not self.analysis:
            return
        duration = float(self.analysis.duration)
        if target == "start":
            self.practice_start = max(0.0, min(self.practice_start + delta, self.practice_end - PRACTICE_MIN_DURATION))
        else:
            self.practice_end = min(duration, max(self.practice_start + PRACTICE_MIN_DURATION, self.practice_end + delta))
        self.message = f"練習区間: {self.practice_start:.1f} - {self.practice_end:.1f} sec"

    def start_practice(self, *, countdown: bool = True) -> None:
        if not self.chart or not self.analysis or not self.song_path:
            return
        if not self.audio_available:
            self.error = "音声デバイスを初期化できないため、練習を開始できません。"
            self.set_screen("practice_setup")
            return
        try:
            practice_chart = self._practice_chart()
            if not practice_chart.notes:
                self.error = "この区間にはノーツがありません。区間を広げてください。"
                self.set_screen("practice_setup")
                return
            self.audio.load(self.song_path, self.analysis.duration, float(self.settings["music_volume"]))
            windows = JudgmentWindows.from_ms(self.settings["judgment_windows_ms"])
            self.session = GameSession(practice_chart, windows, timing_offset=float(self.settings.get("timing_offset_ms", 0)) / 1000.0)
            self._reset_lane_input_state()
            self.practice_active = True
            self.trial_active = False
            self.trial_end_time = 0.0
            self.trial_fade_started = False
            self.tutorial_step_index = None
            self.combo_banner = ""
            self.mascot_combo_zoom_until = 0.0
            self.combo_cutin_until = 0.0
            self.hit_effects = []
            self.judgment_feedback = None
            self.judgment_log = []
            self.start_banner_until = 0.0
            self.error = ""
            self.screen = "game"
            if countdown:
                self.countdown_started_at = time.perf_counter()
            else:
                self.countdown_started_at = None
                self.audio.play(self.practice_start)
                self.start_banner_until = time.perf_counter() + 0.30
        except AudioClockError as error:
            self.error = str(error)
            self.set_screen("practice_setup")

    def start_game(self) -> None:
        self._start_song_game(trial=False)

    def start_trial_game(self) -> None:
        self._start_song_game(trial=True)

    def _start_song_game(self, *, trial: bool) -> None:
        if not self.chart or not self.analysis or not self.song_path:
            return
        self.practice_active = False
        self.trial_active = trial
        self.trial_end_time = min(float(self.analysis.duration), TRIAL_PLAY_LIMIT_SECONDS) if trial else 0.0
        self.trial_fade_started = False
        self.tutorial_step_index = None
        self.tutorial_started_at = None
        self.tutorial_paused_at = None
        if not self.audio_available:
            self.error = "音声デバイスを初期化できないため、プレイを開始できません。"
            self.screen = "chart_summary" if trial else "difficulty"
            return
        try:
            self.audio.load(self.song_path, self.analysis.duration, float(self.settings["music_volume"]))
            windows = JudgmentWindows.from_ms(self.settings["judgment_windows_ms"])
            self.session = GameSession(
                self.chart,
                windows,
                timing_offset=float(self.settings.get("timing_offset_ms", 0)) / 1000.0,
            )
            self._reset_lane_input_state()
            self.combo_banner = ""
            self.mascot_combo_zoom_until = 0.0
            self.combo_cutin_until = 0.0
            self.hit_effects = []
            self.judgment_feedback = None
            self.judgment_log = []
            self.countdown_started_at = time.perf_counter()
            self.start_banner_until = 0.0
            self.error = ""
            self.screen = "game"
        except AudioClockError as error:
            self.error = str(error)
            self.screen = "chart_summary" if trial else "difficulty"

    def start_tutorial(self) -> None:
        """音源なし・メトロノーム型の最初の課題を開始する。"""
        self.start_tutorial_step(0)

    def start_tutorial_step(self, step_index: int) -> None:
        if not self.audio_available or not self.feedback_sounds:
            self.error = "効果音を初期化できないため、チュートリアルを開始できません。"
            self.set_screen("tutorial")
            return
        try:
            chart = build_tutorial_chart(step_index, self.active_lane_count)
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
        self._reset_lane_input_state()
        self.tutorial_step_index = step_index
        self.practice_active = False
        self.trial_active = False
        self.newly_unlocked = []
        self.tutorial_started_at = None
        self.tutorial_paused_at = None
        self.tutorial_next_click_at = 0.0
        self.combo_banner = ""
        self.mascot_combo_zoom_until = 0.0
        self.combo_cutin_until = 0.0
        self.hit_effects = []
        self.judgment_feedback = None
        self.judgment_log = []
        self.countdown_started_at = time.perf_counter()
        self.start_banner_until = 0.0
        self.error = ""
        self.screen = "game"

    def finish_tutorial_step(self) -> None:
        if self.tutorial_step_index is None:
            return
        if not self.chart.metadata.get("tutorial_optional") and self.tutorial_step_index == len(self.current_tutorial_steps()) - 1:
            self.profile["tutorial_completed"] = True
            self.newly_unlocked = unlock_tutorial_cosmetics(self.profile, self.tutorial_cosmetic_unlock_ids())
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
        return chart_key(self.chart)

    def current_ranking(self, *, limit: int = 10) -> list[dict[str, object]]:
        chart_key = self._current_chart_key()
        return [] if chart_key is None else ranking_entries(self.profile, chart_key, limit=limit)

    def ranking_lane_count_value(self) -> int:
        if self.ranking_lane_count in LANE_COUNT_OPTIONS:
            return int(self.ranking_lane_count)
        return chart_lane_count(self.chart) if self.chart is not None else self.active_lane_count

    def ranking_entries_for_selected_lane(self, *, limit: int = 10) -> list[dict[str, object]]:
        if self.chart is None:
            return []
        key = self._chart_key_for(self.chart.music_hash, self.chart.difficulty, self.ranking_lane_count_value())
        return ranking_entries(self.profile, key, limit=limit)

    def set_ranking_lane_count(self, lane_count: int) -> None:
        if lane_count in LANE_COUNT_OPTIONS:
            self.ranking_lane_count = int(lane_count)

    def move_ranking_lane_count(self, direction: int) -> None:
        current = self.ranking_lane_count_value()
        index = LANE_COUNT_OPTIONS.index(current) if current in LANE_COUNT_OPTIONS else 1
        self.ranking_lane_count = LANE_COUNT_OPTIONS[(index + direction) % len(LANE_COUNT_OPTIONS)]

    @staticmethod
    def _chart_key_for(music_hash: str, difficulty: Difficulty, lane_count: int) -> str:
        return f"{music_hash}:{difficulty.value}:{lane_count}lane"

    def _best_entry_for_lane(self, music_hash: str, difficulty: Difficulty, lane_count: int) -> dict[str, object] | None:
        entries = ranking_entries(self.profile, self._chart_key_for(music_hash, difficulty, lane_count), limit=1)
        return entries[0] if entries else None

    def _lane_best_summary(self, music_hash: str, difficulty: Difficulty) -> str:
        labels: list[str] = []
        for lane_count in LANE_COUNT_OPTIONS:
            entry = self._best_entry_for_lane(music_hash, difficulty, lane_count)
            if entry is None:
                labels.append(f"{lane_count}L --")
            else:
                labels.append(f"{lane_count}L {int(entry.get('score', 0)):,} {entry.get('rank', 'D')}")
        return "  |  ".join(labels)

    def open_ranking(self) -> None:
        if self.chart is None:
            self.error = "先に譜面を選択してください。"
            return
        self.ranking_lane_count = chart_lane_count(self.chart)
        self.set_screen("ranking")

    def finish_game(self) -> None:
        if not self.session or not self.chart:
            return
        if self.practice_active:
            self.practice_best_accuracy = max(self.practice_best_accuracy, self.session.result().accuracy)
            self.set_screen("practice_result")
            return
        if self.trial_active:
            self.trial_active = False
            self.trial_fade_started = False
            self.set_screen("trial_result")
            return
        if self.tutorial_active:
            self.finish_tutorial_step()
            return
        result = self.session.result().to_dict()
        self.newly_unlocked = record_play(self.paths, self.profile, chart_key=result["chart_hash"], result=result)
        save_profile(self.paths, self.profile)
        self.screen = "unlock" if self.newly_unlocked else "result"

    def _lane_from_key_name(self, key_name: str) -> int | None:
        try:
            return self.active_lane_keys.index(key_name)
        except ValueError:
            return None

    def _best_source_lane_for_press(self, active_lane: int, audio_time: float) -> int | None:
        if not self.session:
            return None
        source_lanes = self.active_to_source_lanes(active_lane)
        if not source_lanes:
            return None
        target_time = audio_time + self.session.timing_offset
        best_lane: int | None = None
        best_delta = float("inf")
        for source_lane in source_lanes:
            state = self.session._nearest_unjudged(source_lane, target_time)
            if state is None:
                continue
            delta = abs(state.note.time - target_time)
            if delta < best_delta:
                best_lane = source_lane
                best_delta = delta
        return best_lane

    def _press_active_lane(self, active_lane: int, audio_time: float) -> Judgment | None:
        if not self.session:
            return None
        source_lane = self._best_source_lane_for_press(active_lane, audio_time)
        if source_lane is None:
            return None
        return self.session.press(source_lane, audio_time)

    def _release_active_lane(self, active_lane: int, audio_time: float) -> Judgment | None:
        if not self.session:
            return None
        source_lanes = self.active_to_source_lanes(active_lane)
        for source_lane in source_lanes:
            if any(state.note.lane == source_lane and state.active_hold for state in self.session.states):
                return self.session.release(source_lane, audio_time)
        return None

    def _physical_active_lanes(self) -> set[int]:
        try:
            pressed = pygame.key.get_pressed()
        except pygame.error:
            return set(self._lane_keys_down)
        active: set[int] = set()
        for active_lane, key_name in enumerate(self.active_lane_keys):
            try:
                key_code = pygame.key.key_code(str(key_name))
            except ValueError:
                continue
            if key_code < len(pressed) and pressed[key_code]:
                active.add(active_lane)
        return active

    def _reset_lane_input_state(self, *, clear_session: bool = True) -> None:
        self._lane_keys_down.clear()
        self._resume_blocked_lanes.clear()
        if clear_session and self.session:
            self.session.held_lanes.clear()

    def _sync_held_lanes_from_keyboard(self) -> None:
        """再開時の実キー状態を反映し、押しっぱなしを新規TAPとして誤判定させない。"""
        if not self.session:
            self._reset_lane_input_state(clear_session=False)
            return
        pressed_active = self._physical_active_lanes()
        self._lane_keys_down = set(pressed_active)

        active_hold_sources = {state.note.lane for state in self.session.states if state.active_hold and not state.complete}
        held_sources: set[int] = set()
        active_hold_lanes: set[int] = set()
        for active_lane in pressed_active:
            sources = set(self.active_to_source_lanes(active_lane))
            if sources & active_hold_sources:
                held_sources.update(sources & active_hold_sources)
                active_hold_lanes.add(active_lane)
        self.session.held_lanes = held_sources
        self._resume_blocked_lanes = pressed_active - active_hold_lanes

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
                self._sync_held_lanes_from_keyboard()
        elif self.audio.paused:
            self.audio.resume()
            self._sync_held_lanes_from_keyboard()
        else:
            self.audio.pause()

    def _handle_game_focus_lost(self) -> None:
        """フォーカス喪失時は自動停止し、OSがKEYUPを落としても入力を残さない。"""
        if self.screen != "game" or not self.session:
            return
        if not self.countdown_active and not self.game_paused:
            self.toggle_pause()
        self._reset_lane_input_state()

    def retry_game(self) -> None:
        if self.practice_active:
            self.audio.stop()
            self.start_practice()
            return
        if self.trial_active:
            self.audio.stop()
            self.start_trial_game()
            return
        if self.tutorial_active and self.tutorial_step_index is not None:
            self.start_tutorial_step(self.tutorial_step_index)
            return
        self.audio.stop()
        self.start_game()

    def return_to_practice_setup(self) -> None:
        """練習中断時は通常選曲へ流さず、設定済みの区間調整画面へ戻る。"""
        self.audio.stop()
        self.countdown_started_at = None
        self.session = None
        self.practice_active = False
        self.set_screen("practice_setup")

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
        self.practice_active = False
        self.trial_active = False
        self.trial_end_time = 0.0
        self.trial_fade_started = False
        self.set_screen("select")

    def return_to_difficulty(self) -> None:
        """Keep the current song analysis and choose another difficulty."""
        if self.analysis is None or self.song_path is None:
            self.return_to_song_select()
            return
        self.audio.stop()
        self.countdown_started_at = None
        self.session = None
        self.practice_active = False
        self.trial_active = False
        self.trial_end_time = 0.0
        self.trial_fade_started = False
        self.launch_mode = "normal"
        if self.chart is not None:
            self.selected_difficulty = list(Difficulty).index(self.chart.difficulty)
        self.message = "同じ曲で別の難易度を選べます。"
        self.set_screen("difficulty")

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
            lifetime_score=None,
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
                f"BEAT POINT  {int(self.profile.get('wallet_score', 0)):,} BP  ·  {status.unlocked_count}/{status.reward_count} owned",
                "small",
                WHITE,
                pos=(rect.left + 18, rect.top + 10),
            )
        else:
            self.text("BEAT POINT", "small", MAGENTA, pos=(rect.left + 18, rect.top + 16))
            self.text(
                f"{int(self.profile.get('wallet_score', 0)):,} BP  ·  {status.unlocked_count}/{status.reward_count} owned",
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
            f"SHOP  {Path(status.next_reward.name).stem}  ·  あと {status.remaining_score:,} BP",
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

    def _mascot_surface(self, mascot: Mascot, target_height: int) -> pygame.Surface | None:
        """原画像は一度だけ読み込み、ゲーム中は小さな縮小版だけを変形する。"""
        if mascot.mascot_id not in self.mascot_image_cache:
            try:
                self.mascot_image_cache[mascot.mascot_id] = pygame.image.load(str(mascot.image_path)).convert_alpha()
            except pygame.error:
                self.mascot_image_cache[mascot.mascot_id] = None
        source = self.mascot_image_cache.get(mascot.mascot_id)
        if source is None:
            return None
        cache_key = (mascot.mascot_id, target_height)
        cached = self.mascot_scaled_cache.get(cache_key)
        if cached is not None:
            return cached
        height = max(1, min(target_height, source.get_height()))
        width = max(1, round(source.get_width() * height / source.get_height()))
        cached = pygame.transform.smoothscale(source, (width, height))
        self.mascot_scaled_cache[cache_key] = cached
        return cached

    def _mascot_frame(self, base: pygame.Surface, angle: float, zoom: float) -> pygame.Surface:
        """Reuse nearby transforms with a bounded LRU cache for the current source image."""
        if base is not self._mascot_frame_base:
            self._mascot_frames.clear()
            self._mascot_frame_bytes = 0
            self._mascot_frame_base = base
        key = (round(angle * 4), max(1, round(zoom * 200)))
        sprite = self._mascot_frames.pop(key, None)
        if sprite is not None:
            self._mascot_frames[key] = sprite
            return sprite
        sprite = pygame.transform.rotozoom(base, key[0] / 4, key[1] / 200)
        size = sprite.get_pitch() * sprite.get_height()
        limit = 32 * 1024 * 1024
        while self._mascot_frames and (self._mascot_frame_bytes + size > limit or len(self._mascot_frames) >= 128):
            evicted = self._mascot_frames.pop(next(iter(self._mascot_frames)))
            self._mascot_frame_bytes -= evicted.get_pitch() * evicted.get_height()
        if size <= limit:
            self._mascot_frames[key] = sprite
            self._mascot_frame_bytes += size
        return sprite

    def _mascot_display_frame(self, base: pygame.Surface, angle: float, zoom: float, now: float) -> pygame.Surface:
        if not self.low_graphics_quality:
            self._mascot_display_cache = None
            return self._mascot_frame(base, angle, zoom)
        # Sample only image transforms; the caller still positions the sprite each frame.
        key = (math.floor(now * 30 + 1e-9), base, self.size, self.mascot_mode_key,
               self.mascot_combo_zoom_until, id(self.session))
        cached = getattr(self, "_mascot_display_cache", None)
        if cached is None or cached[0] != key:
            cached = (key, self._mascot_frame(base, angle, zoom))
            self._mascot_display_cache = cached
        return cached[1]

    def _mascot_beat_pulse(self, now: float) -> float:
        """直近の解析ビートから0〜1の短い跳ね返りを作る。"""
        if self.analysis is not None and self.analysis.beats:
            beat_index = bisect_right(self.analysis.beats, now) - 1
            if beat_index >= 0:
                elapsed = max(0.0, now - float(self.analysis.beats[beat_index]))
                return max(0.0, 1.0 - elapsed / 0.20)
        # チュートリアル等で解析データがない時も、一定のリズムで小さく動かす。
        phase = now % TUTORIAL_BEAT_SECONDS
        return max(0.0, 1.0 - phase / 0.20)

    def _draw_mascot(self, now: float, left: int, field_width: int, line_y: int) -> None:
        """ノーツ領域外の横余白に、軽量なビート同期マスコットを描く。"""
        mascot = self.selected_mascot
        intensity = MASCOT_MODES[self.mascot_mode_key][1]
        if mascot is None or intensity <= 0.0:
            return
        width, height = self.size
        side_width = max(0, (width - field_width) // 2)
        if side_width < 150:
            return
        target_height = min(int(height * 0.43), int(side_width * 1.35), 310)
        target_height = max(150, round(target_height * mascot.scale))
        base = self._mascot_surface(mascot, target_height)
        if base is None:
            return
        pulse = self._mascot_beat_pulse(now) * intensity
        combo_zoom_progress = self._combo_zoom_progress() * intensity
        sway = math.sin(now * math.tau * 1.15) * intensity
        bob = sway * 2.5 + pulse * 9.0 + combo_zoom_progress * 8.0
        angle = sway * 1.4 + pulse * 2.2
        zoom = 1.0 + pulse * 0.035 + combo_zoom_progress * 0.06 - abs(sway) * 0.008
        sprite = self._mascot_display_frame(base, angle, zoom, now)
        if mascot.anchor == "left":
            center_x = max(sprite.get_width() // 2 + 18, left - side_width // 2)
        else:
            center_x = min(width - sprite.get_width() // 2 - 18, left + field_width + side_width // 2)
        bottom = min(height - 14, line_y - 8)
        rect = sprite.get_rect(midbottom=(center_x, int(bottom - bob)))
        # 右上の曲情報・左上のスコアへ近づかないよう、プレイフィールド下寄りに限定する。
        if rect.top < 150:
            rect.top = 150
        sprite.set_alpha(145 if self.countdown_active or self.game_paused else 255)
        self.surface.blit(sprite, rect)
        sprite.set_alpha(255)
        if combo_zoom_progress > 0.0 and not (self.countdown_active or self.game_paused):
            self._draw_mascot_face_zoom(sprite, rect, combo_zoom_progress)

    def _combo_zoom_progress(self) -> float:
        remaining = self.mascot_combo_zoom_until - time.perf_counter()
        if remaining <= 0.0:
            return 0.0
        progress = max(0.0, min(1.0, remaining / MASCOT_COMBO_ZOOM_DURATION))
        return progress ** 0.55

    def _draw_mascot_face_zoom(self, sprite: pygame.Surface, rect: pygame.Rect, progress: float) -> None:
        """コンボ節目で、マスコット上部を顔アップ風に短く拡大表示する。"""
        cache_key = (int(time.perf_counter() * 30), self.size,
                     self.settings.get("mascot_id"), self.mascot_combo_zoom_until)
        cached = getattr(self, "_face_zoom_frame", None)
        if self.low_graphics_quality and cached is not None and cached[0] == cache_key:
            bubble, target_size = cached[1:]
            self.surface.blit(bubble, bubble.get_rect(center=(rect.centerx, max(78, rect.top + target_size // 5))))
            return
        source_width, source_height = sprite.get_size()
        if source_width < 20 or source_height < 20:
            return
        crop_size = max(20, min(source_width, source_height) // 2)
        crop = pygame.Rect(0, 0, crop_size, crop_size)
        crop.center = (source_width // 2, max(crop_size // 2, int(source_height * 0.30)))
        crop.clamp_ip(sprite.get_rect())
        face = sprite.subsurface(crop).copy()
        target_size = max(54, int(crop_size * (1.24 + progress * 0.34)))
        face = pygame.transform.smoothscale(face, (target_size, target_size))
        border = 4
        bubble = pygame.Surface((target_size + border * 2, target_size + border * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(bubble, (*MAGENTA, int(105 + 90 * progress)), bubble.get_rect())
        pygame.draw.ellipse(bubble, (*WHITE, int(170 + 60 * progress)), bubble.get_rect(), width=3)
        bubble.blit(face, (border, border))
        bubble.set_alpha(int(210 + 45 * progress))
        if self.low_graphics_quality:
            self._face_zoom_frame = (cache_key, bubble, target_size)
        else:
            self._face_zoom_frame = None
        bubble_rect = bubble.get_rect(center=(rect.centerx, max(78, rect.top + target_size // 5)))
        self.surface.blit(bubble, bubble_rect)

    def _combo_cutin_progress(self) -> float:
        remaining = self.combo_cutin_until - time.perf_counter()
        if remaining <= 0.0:
            return 0.0
        return max(0.0, min(1.0, remaining / COMBO_CUTIN_DURATION))

    def _combo_cutin_media_path(self, combo: int) -> Path | None:
        folder = self.resource_path("assets/combo_cutin")
        if not folder.exists():
            return None
        stems = (f"combo_{combo}", str(combo), "default")
        for stem in stems:
            for suffix in sorted(COMBO_CUTIN_MEDIA_EXTENSIONS):
                path = folder / f"{stem}{suffix}"
                if path.is_file():
                    return path
        return None

    def _load_combo_cutin_media(self, combo: int, max_width: int, max_height: int) -> pygame.Surface | None:
        path = self._combo_cutin_media_path(combo)
        if path is None:
            return None
        cache_key = (str(path), max_width, max_height)
        if cache_key in self.combo_cutin_media_cache:
            return self.combo_cutin_media_cache[cache_key]
        try:
            image = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            self.combo_cutin_media_cache[cache_key] = None
            return None
        scale = min(max_width / max(1, image.get_width()), max_height / max(1, image.get_height()), 1.0)
        if scale < 1.0:
            image = pygame.transform.smoothscale(image, (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale))))
        self.combo_cutin_media_cache[cache_key] = image
        return image

    def _static_cutin_sprite(self, source: pygame.Surface, max_width: int) -> pygame.Surface:
        cached = getattr(self, "_static_cutin_cache", None)
        if cached is None or cached[0] is not source or cached[1] != max_width:
            scale = min(1.0, max_width / max(1, source.get_width()))
            size = (max(1, int(source.get_width() * scale)), max(1, int(source.get_height() * scale)))
            image = pygame.transform.smoothscale(source, size) if scale < 1.0 else source.copy()
            cached = (source, max_width, image)
            self._static_cutin_cache = cached
        return cached[2]

    def _draw_combo_cutin(self, left: int, field_width: int, line_y: int) -> None:
        progress = self._combo_cutin_progress()
        mascot = self.selected_mascot
        intensity = MASCOT_MODES[self.mascot_mode_key][1]
        if progress <= 0.0 or intensity <= 0.0 or self.countdown_active or self.game_paused:
            return
        width, height = self.size
        right_edge = left + field_width
        available = width - right_edge - 28
        if available < 185:
            return
        panel_width = min(360, max(190, available - 20))
        panel_height = min(180, max(128, int(height * 0.22)))
        slide = int((1.0 - progress) * 70)
        alpha = int(235 * min(1.0, progress * 2.2))
        panel = pygame.Rect(width - panel_width - 26 + slide, max(124, int(height * 0.22)), panel_width, panel_height)
        if panel.left < right_edge + 12:
            panel.left = right_edge + 12
        layer = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        pygame.draw.rect(layer, (11, 18, 32, min(205, alpha)), layer.get_rect(), border_radius=14)
        pygame.draw.rect(layer, (*MAGENTA, min(215, alpha)), layer.get_rect(), width=2, border_radius=14)
        for offset in range(-panel.height, panel.width, 32):
            pygame.draw.line(layer, (*CYAN, max(0, alpha // 4)), (offset, panel.height), (offset + panel.height, 0), 1)
        self.surface.blit(layer, panel)

        combo_value = self.combo_cutin_combo or (self.session.combo if self.session else 0)
        target_height = max(96, min(panel.height + 46, int(panel.width * 0.68)))
        media = self._load_combo_cutin_media(combo_value, panel.width - 92, panel.height + 36)
        if media is not None:
            zoom = 1.0 + 0.10 * math.sin(progress * math.pi)
            sprite = (self._static_cutin_sprite(media, panel.width - 100) if self.low_graphics_quality
                      else pygame.transform.rotozoom(media, -1.5 + 3.0 * math.sin(progress * math.pi), zoom))
            sprite.set_alpha(alpha)
            sprite_rect = sprite.get_rect(midright=(panel.right - 8, min(panel.bottom + 20, line_y - 8)))
            self.surface.blit(sprite, sprite_rect)
            sprite.set_alpha(255)
        elif mascot is not None:
            base = self._mascot_surface(mascot, round(target_height * mascot.scale))
            if base is not None:
                zoom = 1.0 + 0.14 * math.sin(progress * math.pi)
                sprite = (self._static_cutin_sprite(base, panel.width - 100) if self.low_graphics_quality
                          else pygame.transform.rotozoom(base, -2.5 + 5.0 * math.sin(progress * math.pi), zoom))
                sprite.set_alpha(alpha)
                sprite_rect = sprite.get_rect(midright=(panel.right - 8, min(panel.bottom + 22, line_y - 8)))
                if sprite_rect.left < panel.left + 90:
                    scale = (panel.width - 100) / max(1, sprite.get_width())
                    sprite = pygame.transform.smoothscale(sprite, (max(1, int(sprite.get_width() * scale)), max(1, int(sprite.get_height() * scale))))
                    sprite.set_alpha(alpha)
                    sprite_rect = sprite.get_rect(midright=(panel.right - 8, min(panel.bottom + 22, line_y - 8)))
                self.surface.blit(sprite, sprite_rect)
                sprite.set_alpha(255)

        combo_text = self.combo_banner or f"{self.session.combo} COMBO!" if self.session else "COMBO!"
        text_alpha = min(255, alpha + 20)
        label = self.fonts["small"].render("COMBO CUT-IN", True, MUTED)
        label.set_alpha(text_alpha)
        self.surface.blit(label, (panel.left + 18, panel.top + 18))
        combo = self.fonts["h1"].render(combo_text, True, YELLOW)
        combo.set_alpha(text_alpha)
        self.surface.blit(combo, combo.get_rect(midleft=(panel.left + 18, panel.top + panel.height // 2 + 4)))

    def draw_title(self) -> None:
        scene = getattr(self, "_title_scene", None)
        if scene is None or scene.size != self.size or scene.mascot != self.selected_mascot:
            self._title_scene = TitleScene(self, GAME_TITLE, GAME_TAGLINE)
        self._title_scene.draw(self, GAME_TITLE)

    def _song_best_text(self, music_hash: str) -> str:
        """選曲リスト用に、難易度別の自己ベストを横並びの短い表記へ整える。"""
        labels: list[str] = []
        for difficulty in Difficulty:
            entry = self._best_entry_for_lane(music_hash, difficulty, self.active_lane_count)
            if entry is None:
                labels.append(f"{difficulty.label[:2]} --")
            else:
                labels.append(f"{difficulty.label[:2]} {int(entry.get('score', 0)):,} {entry.get('rank', 'D')}")
        return "  |  ".join(labels)

    def _playlist_label(self, value: str, font: str, max_width: int) -> str:
        face = self.fonts[font]
        if face.size(value)[0] <= max_width:
            return value
        low, high = 0, len(value)
        while low < high:
            middle = (low + high + 1) // 2
            if face.size(value[:middle] + "...")[0] <= max_width:
                low = middle
            else:
                high = middle - 1
        return value[:low] + "..."

    def _draw_playlist_stage(self, now: float, accent: tuple[int, int, int]) -> None:
        width, height = self.size
        # Time-based decoration only; the song audio remains stopped.
        for side in (0, 1):
            for index in range(9):
                x = 12 + index * 8 if not side else width - 16 - index * 8
                amplitude = int(25 + 80 * (0.5 + 0.5 * math.sin(now * 1.8 + index * 0.65)))
                color = (24, 93, 116) if index % 2 == 0 else (102, 39, 81)
                pygame.draw.line(self.surface, color, (x, height // 2 - amplitude), (x, height // 2 + amplitude), 3)
        for index in range(14):
            x = (index * 179 + now * 13) % width
            y = height - 13 - (index % 3) * 6
            pygame.draw.line(self.surface, (28, 89, 109), (x, y), (x + 27, y), 1)
        pygame.draw.line(self.surface, accent, (50, 105), (width // 2 - 10, 105), 2)
        pygame.draw.line(self.surface, MAGENTA, (width // 2 + 10, 105), (width - 50, 105), 2)
        pygame.draw.line(self.surface, YELLOW, (50, 20), (94, 20), 3)
        pygame.draw.line(self.surface, MAGENTA, (103, 20), (122, 20), 3)

    def draw_select(self) -> None:
        """通常・練習モードで共有する、デモ曲とユーザー曲の統合プレイリスト。"""
        width, height = self.size
        entries = self.playlist_entries()
        self._clamp_playlist_position()
        visible_rows = self._playlist_visible_rows()
        mode_label = "PRACTICE" if self.launch_mode == "practice" else "NORMAL PLAY"
        mode_color = GREEN if self.launch_mode == "practice" else CYAN
        folder = self.current_library_folder
        folders = self.current_library_folders()
        now = pygame.time.get_ticks() / 1000.0
        self._draw_playlist_stage(now, mode_color)
        self.text("PLAYLIST", "title", WHITE, pos=(50, 24))
        self.text(mode_label, "small", mode_color, pos=(350, 52))
        self.text(f"{len(entries):02d} TRACKS", "h1", mode_color, pos=(width - 295, 35))
        self.text(self._playlist_label(folder, "small", width - 700), "small", MUTED, pos=(350, 76))
        self.button("音楽を追加  [I]", pygame.Rect(width - 240, 124, 190, 36), self.choose_file, accent=YELLOW)
        self.button("◁", pygame.Rect(50, 124, 42, 36), lambda: self.cycle_library_folder(-1), accent=MUTED)
        self.button(self._playlist_label(folder, "body", 236), pygame.Rect(100, 124, 260, 36), lambda: None, accent=CYAN)
        self.button("▷", pygame.Rect(368, 124, 42, 36), lambda: self.cycle_library_folder(1), accent=MUTED)
        self.button("フォルダ作成 [N]", pygame.Rect(430, 124, 185, 36), self.create_library_folder, accent=GREEN)
        list_rect = pygame.Rect(95, 172, width - 190, visible_rows * PLAYLIST_ROW_HEIGHT + 16)
        pygame.draw.line(self.surface, (33, 68, 91), list_rect.topleft, list_rect.bottomleft, 1)
        pygame.draw.line(self.surface, (68, 40, 74), list_rect.topright, list_rect.bottomright, 1)
        if not entries:
            self.text("楽曲がありません。音楽を追加して解析するか、demo_songs フォルダへデモ曲を入れてください。", "body", MUTED, center=list_rect.center)
        else:
            start = self.playlist_scroll_index
            end = min(len(entries), start + visible_rows)
            for index in range(start, end):
                entry = entries[index]
                row = pygame.Rect(list_rect.left + 14, list_rect.top + 8 + (index - start) * PLAYLIST_ROW_HEIGHT, list_rect.width - 48, PLAYLIST_ROW_HEIGHT - 7)
                selected = index == self.playlist_selected_index
                hovered = row.collidepoint(self._to_logical_point(pygame.mouse.get_pos()))
                self.panel(row, (20, 34, 49) if hovered else (11, 19, 32), 5)
                if selected:
                    self._draw_neon_hud_card(row, mode_color, now, 0.65 + 0.15 * math.sin(now * 2))
                    pygame.draw.line(self.surface, MAGENTA, (row.right - 130, row.top + 5), (row.right - 25, row.top + 5), 2)
                elif hovered:
                    pygame.draw.rect(self.surface, (57, 110, 135), row, 1, border_radius=5)
                self.text(f"{index + 1:02d}", "mono", mode_color if selected else MUTED, center=(row.left + 30, row.centery))
                name_color = WHITE if entry.exists else MUTED
                name = self._playlist_label(entry.path.stem or '不明な楽曲', "body", row.width - 315)
                self.text(name, "body", name_color, pos=(row.left + 60, row.top + 8))
                metadata = self._playlist_label(f"{entry.bpm:.1f} BPM   {entry.duration:.1f} sec   /   {entry.folder}", "small", row.width - 590)
                self.text(metadata, "small", MUTED, pos=(row.left + 60, row.top + 34))
                tag_color = GREEN if entry.source == "demo" else (YELLOW if entry.source == "library" else CYAN)
                self.text(entry.source_label, "small", tag_color, pos=(row.right - 230, row.top + 10))
                best_color = CYAN if song_ranking_summary(self.profile, entry.music_hash) else MUTED
                self.text(f"BEST  {self._song_best_text(entry.music_hash)}", "small", best_color, pos=(row.right - 510, row.top + 34))
                if not entry.exists:
                    self.text("MISSING", "small", RED, pos=(row.right - 95, row.top + 34))
                self.buttons.append((row, lambda selected_index=index: self.select_playlist_entry(selected_index)))
            if len(entries) > visible_rows:
                track = pygame.Rect(list_rect.right - 20, list_rect.top + 10, 7, list_rect.height - 20)
                pygame.draw.rect(self.surface, PANEL_DARK, track, border_radius=3)
                thumb_height = max(28, int(track.height * visible_rows / len(entries)))
                max_scroll = len(entries) - visible_rows
                progress = self.playlist_scroll_index / max_scroll if max_scroll else 0.0
                thumb_top = track.top + int((track.height - thumb_height) * progress)
                pygame.draw.rect(self.surface, mode_color, pygame.Rect(track.left, thumb_top, track.width, thumb_height), border_radius=3)
        self.text(f"{self.playlist_scroll_index + 1 if entries else 0}-{min(len(entries), self.playlist_scroll_index + visible_rows)} / {len(entries)}", "small", MUTED, center=(width // 2, height - 112))
        self.button("タイトルへ  [ESC]", pygame.Rect(50, height - 72, 180, 40), lambda: self.set_screen("title"), accent=MUTED)
        self.button("選択曲をここへ移動 [M]", pygame.Rect(250, height - 72, 260, 40), self.move_selected_playlist_song_to_current_folder, accent=GREEN)
        if entries:
            self.button("選択する  [ENTER]", pygame.Rect(width - 290, height - 74, 240, 44), self.select_current_playlist_entry, accent=mode_color)

    def draw_library(self) -> None:
        width, height = self.size
        entries = self.library_entries()
        self._clamp_library_position()
        visible_rows = self._library_visible_rows()
        self.heading(
            "RECENT LIBRARY",
            f"解析済み {len(entries)} 曲  ・  マウスホイール / ↑↓ / PageUp・PageDownでスクロール  ・  Enterで選択",
        )
        list_rect = pygame.Rect(100, 145, width - 200, visible_rows * LIBRARY_ROW_HEIGHT + 16)
        self.panel(list_rect)
        if not entries:
            self.text("解析済みの楽曲はまだありません。", "body", MUTED, center=(width // 2, list_rect.centery))
        else:
            visible = entries[self.library_scroll_index : self.library_scroll_index + visible_rows]
            for offset, entry in enumerate(visible):
                index = self.library_scroll_index + offset
                row = pygame.Rect(list_rect.left + 16, list_rect.top + 8 + offset * LIBRARY_ROW_HEIGHT, list_rect.width - 52, LIBRARY_ROW_HEIGHT - 8)
                selected = index == self.library_selected_index
                self.panel(row, PANEL if selected else PANEL_DARK, 7)
                if selected:
                    pygame.draw.rect(self.surface, CYAN, pygame.Rect(row.left, row.top + 6, 4, row.height - 12), border_radius=2)
                source_path = Path(str(entry.get("source_path", "")))
                song_name = source_path.stem or "不明な楽曲"
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

            if len(entries) > visible_rows:
                track = pygame.Rect(list_rect.right - 22, list_rect.top + 12, 8, list_rect.height - 24)
                pygame.draw.rect(self.surface, PANEL_DARK, track, border_radius=4)
                thumb_height = max(30, int(track.height * visible_rows / len(entries)))
                max_scroll = len(entries) - visible_rows
                progress = self.library_scroll_index / max_scroll if max_scroll else 0.0
                thumb_top = track.top + int((track.height - thumb_height) * progress)
                pygame.draw.rect(self.surface, YELLOW, pygame.Rect(track.left, thumb_top, track.width, thumb_height), border_radius=4)

        self.text(
            f"{self.library_scroll_index + 1 if entries else 0}-{min(len(entries), self.library_scroll_index + visible_rows)} / {len(entries)}",
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
        self.heading("TUTORIAL", f"{self.lane_count_label}  ・  {subtitle}")
        panel = pygame.Rect(width // 2 - 450, 145, 900, 350)
        self.panel(panel)
        for index, step in enumerate(self.current_tutorial_steps()):
            y = panel.top + 18 + index * 64
            row = pygame.Rect(panel.left + 24, y, panel.width - 48, 56)
            self.panel(row, PANEL_DARK, 8)
            self.text(step.title, "body", GREEN if completed else CYAN, pos=(row.left + 18, row.top + 10))
            self.text(step.instruction, "small", MUTED, pos=(row.left + 18, row.top + 32))
            self.text(f"{len(step.notes)} NOTES", "small", YELLOW, pos=(row.right - 105, row.top + 23))
        optional_steps = optional_tutorial_steps(self.active_lane_count)
        column_width = panel.width // len(optional_steps)
        for index, step in enumerate(optional_steps):
            target = len(self.current_tutorial_steps()) + index
            label = step.title.removeprefix("任意練習: ") + "（任意）"
            self.button(label, pygame.Rect(panel.left + index * column_width, panel.bottom + 16, column_width - 12, 42),
                        lambda target=target: self.start_tutorial_step(target), accent=CYAN)
        self.button("最初から始める  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), self.start_tutorial, accent=GREEN)
        self.button("タイトルへ  [ESC]", pygame.Rect(width // 2 - 150, height - 72, 300, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_tutorial_result(self) -> None:
        if not self.session or self.tutorial_step_index is None:
            self.set_screen("tutorial")
            return
        width, height = self.size
        result = self.session.result()
        step = (self.current_tutorial_steps() + optional_tutorial_steps(self.active_lane_count))[self.tutorial_step_index]
        optional = bool(self.chart.metadata.get("tutorial_optional"))
        is_last = self.tutorial_step_index == len(self.current_tutorial_steps()) - 1
        self.heading("TUTORIAL RESULT", "すべての判定結果です。苦手な操作は何度でも練習できます。")
        self.panel(pygame.Rect(width // 2 - 360, 150, 720, 310))
        self.text(step.title, "h1", CYAN, center=(width // 2, 198))
        self.text(result.rank, "title", GREEN if result.rank in {"S", "A"} else CYAN, center=(width // 2, 285))
        self.text(f"PERFECT {result.judgments['PERFECT']}   GREAT {result.judgments['GREAT']}   GOOD {result.judgments['GOOD']}   MISS {result.judgments['MISS']}", "body", MUTED, center=(width // 2, 357))
        self.text(f"ACCURACY  {result.accuracy:.2f}%", "body", WHITE, center=(width // 2, 398))
        if optional:
            self.button("もう一度練習  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), self.retry_game, accent=GREEN)
        elif is_last:
            self.text("チュートリアル完了。次は PLAY から好きな曲を選びましょう。", "body", GREEN, center=(width // 2, 482))
            if self.newly_unlocked:
                labels = " / ".join(self._unlocked_notification_label(item) for item in self.newly_unlocked[:3])
                self.text(f"NEW UNLOCK  {labels}", "small", YELLOW, center=(width // 2, 520))
            self.button("タイトルへ  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), lambda: self.set_screen("title"), accent=GREEN)
        else:
            self.button("次の課題へ  [ENTER]", pygame.Rect(width // 2 - 190, height - 130, 380, 48), lambda: self.start_tutorial_step(self.tutorial_step_index + 1), accent=GREEN)
        self.button("もう一度練習  [R]", pygame.Rect(width // 2 - 190, height - 72, 185, 40), self.retry_game, accent=CYAN)
        self.button("課題一覧へ  [ESC]", pygame.Rect(width // 2 + 5, height - 72, 185, 40), self.return_to_song_select, accent=MUTED)

    def draw_analyzing(self) -> None:
        width, height = self.size
        self.heading("音楽を解析しています", Path(self.song_path).stem if self.song_path else "")
        self.panel(pygame.Rect(width // 2 - 310, height // 2 - 60, 620, 155))
        self.text(self.progress.stage, "body", center=(width // 2, height // 2 - 15))
        bar = pygame.Rect(width // 2 - 235, height // 2 + 35, 470, 24)
        pygame.draw.rect(self.surface, (47, 62, 87), bar, border_radius=12)
        pygame.draw.rect(self.surface, CYAN, pygame.Rect(bar.left, bar.top, int(bar.width * self.progress.ratio), bar.height), border_radius=12)
        self.text(f"{self.progress.ratio * 100:.0f}%", "mono", center=(width // 2, height // 2 + 80))

    def draw_difficulty(self) -> None:
        width, height = self.size
        self.heading("難易度選択", f"{Path(self.song_path).stem if self.song_path else ''}  ・  {self.lane_count_label}")
        if self.analysis:
            self.text(f"推定 BPM: {self.analysis.bpm:.1f}   楽曲長: {self.analysis.duration:.1f} 秒", "body", MUTED, center=(width // 2, 145 if height < 650 else 155))
        difficulties = list(Difficulty)
        descriptions = ["拍の骨格だけを叩く", "基本リズム中心", "主要な音を幅広く反映", "細かなリズムと複合入力", "高密度な細部まで反映"]
        compact = height < 650
        card_top = 150 if compact else 205
        card_gap = 55 if compact else 76
        card_height = 48 if compact else 58
        card_width = min(560, width - 180)
        for index, difficulty in enumerate(difficulties):
            y = card_top + index * card_gap
            selected = index == self.selected_difficulty
            rect = pygame.Rect(width // 2 - card_width // 2, y, card_width, card_height)
            self.panel(rect, (37, 57, 88) if selected else PANEL_DARK, 10)
            pygame.draw.rect(self.surface, CYAN if selected else (60, 78, 110), rect, width=2, border_radius=10)
            self.text(difficulty.label, "body", CYAN if selected else WHITE, pos=(rect.left + 24, rect.top + (12 if compact else 17)))
            self.text(descriptions[index], "small", MUTED, pos=(rect.left + (180 if compact else 205), rect.top + (17 if compact else 21)))
            if self.analysis:
                best = self._best_entry_for_lane(self.analysis.music_hash, difficulty, self.active_lane_count)
                best_text = "BEST --" if best is None else f"BEST {int(best.get('score', 0)):,} {best.get('rank', 'D')}"
                self.text(best_text, "small", YELLOW if best else MUTED, pos=(rect.right - 165, rect.top + (17 if compact else 21)))
            self.buttons.append((rect, lambda i=index: setattr(self, "selected_difficulty", i)))
        button_y = height - (90 if compact else 100)
        self.button("この難易度で練習" if self.launch_mode == "practice" else "この難易度でプレイ", pygame.Rect(width // 2 - 190, button_y, 380, 48), lambda: self.select_chart(difficulties[self.selected_difficulty]), accent=GREEN)
        self.button("楽曲選択へ", pygame.Rect(50, height - 72, 150, 40), lambda: self.set_screen("select"), accent=MUTED)
    def draw_practice_setup(self) -> None:
        if not self.analysis or not self.chart:
            self.set_screen("select")
            return
        width, height = self.size
        duration = float(self.analysis.duration)
        self.heading("PRACTICE SETUP", f"{Path(self.song_path).stem if self.song_path else ''}  ・  {self.chart.difficulty.label}  ・  {chart_lane_count(self.chart)} LANE  ・  スコア・報酬へは反映されません")
        panel = pygame.Rect(width // 2 - 420, 160, 840, 300)
        self.panel(panel)
        self.text("練習する区間", "body", GREEN, pos=(panel.left + 32, panel.top + 28))
        self.text(f"{self.practice_start:.1f} sec  →  {self.practice_end:.1f} sec", "title", WHITE, center=(width // 2, panel.top + 95))
        timeline = pygame.Rect(panel.left + 40, panel.top + 145, panel.width - 80, 14)
        pygame.draw.rect(self.surface, (49, 65, 94), timeline, border_radius=7)
        start_x = timeline.left + int(timeline.width * self.practice_start / max(0.1, duration))
        end_x = timeline.left + int(timeline.width * self.practice_end / max(0.1, duration))
        pygame.draw.rect(self.surface, GREEN, pygame.Rect(start_x, timeline.top, max(8, end_x - start_x), timeline.height), border_radius=7)
        pygame.draw.circle(self.surface, WHITE, (start_x, timeline.centery), 10)
        pygame.draw.circle(self.surface, WHITE, (end_x, timeline.centery), 10)
        self.text(f"曲全体: {duration:.1f} sec", "small", MUTED, pos=(panel.left + 40, panel.top + 172))
        self.text("開始位置  ← / →  0.1秒   Shift+← / →  1秒", "small", MUTED, pos=(panel.left + 40, panel.top + 207))
        self.text("終了位置  A / D  0.1秒   Shift+A / D  1秒", "small", MUTED, pos=(panel.left + 40, panel.top + 232))
        self.text("ループ", "small", MUTED, pos=(panel.left + 40, panel.top + 262))
        self.button("ON" if self.practice_loop else "OFF", pygame.Rect(panel.left + 125, panel.top + 252, 90, 30), lambda: setattr(self, "practice_loop", not self.practice_loop), accent=GREEN if self.practice_loop else MUTED)
        self.button("練習を始める  [ENTER]", pygame.Rect(width // 2 - 220, height - 125, 440, 50), self.start_practice, accent=GREEN)
        self.button("プレイリストへ  [ESC]", pygame.Rect(50, height - 72, 200, 40), lambda: self.set_screen("select"), accent=MUTED)

    def draw_practice_result(self) -> None:
        if not self.session:
            self.set_screen("practice_setup")
            return
        width, height = self.size
        result = self.session.result()
        self.heading("PRACTICE SUMMARY", f"{self.practice_start:.1f} - {self.practice_end:.1f} sec  ・  練習記録は通常ランキング・報酬へ反映されません")
        self.panel(pygame.Rect(width // 2 - 340, 150, 680, 285))
        self.text(f"ACCURACY  {result.accuracy:.2f}%", "title", GREEN, center=(width // 2, 230))
        self.text(f"BEST IN THIS SESSION  {self.practice_best_accuracy:.2f}%", "body", CYAN, center=(width // 2, 285))
        self.text(f"PERFECT {result.judgments['PERFECT']}   GREAT {result.judgments['GREAT']}   GOOD {result.judgments['GOOD']}   MISS {result.judgments['MISS']}", "body", MUTED, center=(width // 2, 340))
        self.text(f"LOOPS  {self.practice_round + 1}", "small", YELLOW, center=(width // 2, 385))
        self.button("同じ区間をもう一度  [R]", pygame.Rect(width // 2 - 300, height - 130, 285, 46), self.start_practice, accent=GREEN)
        self.button("区間を調整", pygame.Rect(width // 2 + 15, height - 130, 285, 46), lambda: self.set_screen("practice_setup"), accent=CYAN)
        self.button("タイトルへ", pygame.Rect(width // 2 - 150, height - 72, 300, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_trial_result(self) -> None:
        if not self.session:
            self.set_screen("chart_summary")
            return
        width, height = self.size
        result = self.session.result()
        played_seconds = min(self.trial_end_time or float(self.chart.song_duration if self.chart else 0.0), TRIAL_PLAY_LIMIT_SECONDS)
        self.heading("TRIAL SUMMARY", f"{chart_lane_count(self.chart) if self.chart else self.active_lane_count} LANE  ・  お試しプレイの結果はランキング・報酬には反映されません")
        self.panel(pygame.Rect(width // 2 - 350, 150, 700, 300))
        self.text(f"PLAY TIME  {played_seconds:.1f} sec", "body", CYAN, center=(width // 2, 210))
        self.text(f"SCORE  {result.score:07d}", "h1", WHITE, center=(width // 2, 265))
        self.text(f"ACCURACY  {result.accuracy:.2f}%", "body", GREEN, center=(width // 2, 320))
        self.text(f"PERFECT {result.judgments['PERFECT']}   GREAT {result.judgments['GREAT']}   GOOD {result.judgments['GOOD']}   MISS {result.judgments['MISS']}", "body", MUTED, center=(width // 2, 374))
        self.button("譜面概要へ", pygame.Rect(width // 2 - 250, height - 126, 230, 46), lambda: self.set_screen("chart_summary"), accent=CYAN)
        self.button("楽曲選択へ  [ESC]", pygame.Rect(width // 2 + 20, height - 126, 230, 46), self.return_to_song_select, accent=MUTED)

    def draw_chart_summary(self) -> None:
        if not self.analysis or not self.chart:
            self.set_screen("difficulty")
            return
        width, height = self.size
        summary = build_chart_summary(self.chart, self.analysis)
        variant = int(self.chart.metadata.get("generation_variant", 0)) + 1
        state_label = "試作候補（未保存）" if self.chart_is_pending else "確定譜面"
        candidate_label = ""
        if self.chart_candidates:
            candidate_label = f"  ・  比較 {self.chart_candidate_index + 1}/{len(self.chart_candidates)}（最大{CHART_CANDIDATE_LIMIT}）"
        style_label = CHART_STYLE_LABELS.get(self.chart.metadata.get("generation_style", "standard"), "標準")
        self.heading("譜面概要", f"{summary.difficulty_label}  ・  {summary.lane_count_label}  ・  {state_label}  ・  {style_label}  ・  生成候補 {variant}{candidate_label}")
        left_panel = pygame.Rect(95, 150, 485, 370)
        right_panel = pygame.Rect(width - 580, 150, 485, 370)
        self.panel(left_panel)
        self.panel(right_panel)
        self.text("楽曲解析", "body", CYAN, pos=(left_panel.left + 28, left_panel.top + 26))
        if self.chart.metadata.get("gap_balance_version") in (1, 2):
            balance_version = self.chart.metadata["gap_balance_version"]
            moves = self.chart.metadata.get("gap_balance_moves", 0)
            self.text(f"新方式: 空白バランス v{balance_version} / {moves}ノーツ再配置", "small", GREEN,
                      pos=(left_panel.left + 28, left_panel.bottom - 30))
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
            ("レーン使用", summary.lane_usage_text),
            ("品質メモ", summary.quality_note),
            ("安全補正", f"{summary.validation_removed} ノーツ除去 / {summary.validation_issues} 注意"),
            ("自己ベスト", f"{self.current_ranking(limit=1)[0]['score']:,} pts" if self.current_ranking(limit=1) else "記録なし"),
            ("レーン別BEST", self._lane_best_summary(self.chart.music_hash, self.chart.difficulty)),
        ]
        for index, (label, value) in enumerate(chart_rows):
            y = right_panel.top + 66 + index * 32
            self.text(label, "small", MUTED, pos=(right_panel.left + 30, y))
            self.text(value, "small", WHITE, pos=(right_panel.left + 170, y))
        self.button("お試しプレイ", pygame.Rect(width // 2 - 530, height - 122, 210, 50), self.start_trial_game, accent=CYAN)
        self.button("この候補でプレイ  [ENTER]" if self.chart_is_pending else "この譜面でプレイ  [ENTER]", pygame.Rect(width // 2 - 300, height - 122, 250, 50), self.start_game, accent=GREEN)
        self.button("新しい候補  [R]", pygame.Rect(width // 2 - 30, height - 122, 220, 50), self.regenerate_chart, accent=YELLOW)
        if self.chart_candidates:
            self.button("← 前候補", pygame.Rect(width // 2 + 210, height - 122, 150, 50), lambda: self.move_chart_candidate(-1), accent=CYAN)
            self.button("次候補 →", pygame.Rect(width // 2 + 380, height - 122, 150, 50), lambda: self.move_chart_candidate(1), accent=CYAN)
        if self.chart_is_pending:
            self.button("採用・保存  [A]", pygame.Rect(width // 2 - 285, height - 66, 220, 38), self.adopt_pending_chart, accent=GREEN)
            self.button("候補を破棄  [D]", pygame.Rect(width // 2 - 45, height - 66, 220, 38), self.discard_pending_chart, accent=MAGENTA)
        else:
            self.button("ランキング  [L]", pygame.Rect(width // 2 - 130, height - 66, 260, 38), self.open_ranking, accent=MAGENTA)
        self.button("難易度選択へ  [ESC]", pygame.Rect(45, height - 70, 190, 40), lambda: self.set_screen("difficulty"), accent=MUTED)

    def draw_ranking(self) -> None:
        if self.chart is None:
            self.set_screen("title")
            return
        width, height = self.size
        lane_filter = self.ranking_lane_count_value()
        entries = self.ranking_entries_for_selected_lane()
        self.heading("LOCAL RANKING", f"{self.chart.difficulty.label}  ・  {lane_filter} LANE  ・  ←→でレーン別ランキングを切替")
        tab_total_width = 540
        for index, lane_count in enumerate(LANE_COUNT_OPTIONS):
            entry = self._best_entry_for_lane(self.chart.music_hash, self.chart.difficulty, lane_count)
            rect = pygame.Rect(width // 2 - tab_total_width // 2 + index * 180, 118, 168, 24)
            active = lane_count == lane_filter
            self.panel(rect, (37, 57, 88) if active else PANEL_DARK, 6)
            label = f"{lane_count}L --" if entry is None else f"{lane_count}L {int(entry.get('score', 0)):,}"
            self.text(label, "small", CYAN if active else MUTED, center=rect.center)
            self.buttons.append((rect, lambda selected_lane=lane_count: self.set_ranking_lane_count(selected_lane)))
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
        self._draw_game_background(now)
        if self.lane_view_key == "perspective":
            self._draw_perspective_game_field(left, field_width, lane_width, field_top, line_y, now, counting_down)
        else:
            active_keys = self.active_lane_keys
            for lane in range(self.active_lane_count):
                x = left + lane * lane_width
                color = self.lane_color(lane)
                pygame.draw.rect(self.surface, (18, 28, 48), pygame.Rect(x, field_top, lane_width - 2, line_y - field_top))
                pygame.draw.line(self.surface, tuple(channel // 3 for channel in color), (x, field_top), (x, line_y), 1)
                self.text(active_keys[lane].upper(), "mono", color, center=(x + lane_width // 2, line_y + 30))
            pygame.draw.line(self.surface, WHITE, (left, line_y), (left + field_width, line_y), 3)
            speed = self.effective_note_speed
            if not counting_down:
                self._draw_chord_guides(left, field_width, lane_width, field_top, line_y, now, speed, perspective=False)
                for state in self._drawable_states(now, speed, field_top, line_y):
                    if state.complete:
                        continue
                    note = state.note
                    y = self._note_timing_y(note.time, now, line_y, speed)
                    display_lane = self.source_to_active_lane(note.lane)
                    x = left + display_lane * lane_width + 7
                    cap_width = lane_width - 14
                    cap_height = 18
                    lane_color = self.lane_color(display_lane)
                    if note.kind.value == "hold" and note.end_time is not None:
                        end_y = self._note_timing_y(note.end_time, now, line_y, speed)
                        # 始点または終点のどちらかが見えている間は描画を続ける。
                        # 押下済みの始点が画面外へ抜けても、終端キャップを残して離す位置を示す。
                        if max(y, end_y) < field_top - 15 or min(y, end_y) > height + 40:
                            continue
                        top, bottom = sorted((int(y), int(end_y)))
                        top, bottom = max(field_top, top), min(line_y, bottom)
                        if bottom > top:
                            center_x = left + display_lane * lane_width + lane_width // 2
                            self._draw_hold_rail(pygame.Rect(center_x - 9, top, 18, bottom - top), lane_color)
                        # 終端は通常ノーツと同じ大きさのキャップにし、淡い輪郭で「ここで離す」を示す。
                        if field_top - cap_height <= end_y <= height + cap_height:
                            end_cap = pygame.Rect(x, int(end_y) - cap_height // 2, cap_width, cap_height)
                            self._draw_note_cap(end_cap, lane_color, lane_index=display_lane)
                        if field_top - cap_height <= y <= height + cap_height:
                            self._draw_note_cap(pygame.Rect(x, int(y) - cap_height // 2, cap_width, cap_height), lane_color, lane_index=display_lane)
                    else:
                        if y < field_top - 15 or y > height + 40:
                            continue
                        self._draw_note_cap(pygame.Rect(x, int(y) - cap_height // 2, cap_width, cap_height), lane_color, lane_index=display_lane)
            self._draw_hold_sparks(left, lane_width, field_top, line_y, now)
            self._draw_hit_effects(left, lane_width, field_top, line_y)
        self._draw_mascot(now, left, field_width, line_y)
        self._draw_combo_cutin(left, field_width, line_y)
        self._draw_score_hud(left, now)
        self._draw_judgment_panel(left, field_top, line_y)
        if self.practice_active:
            self.text(f"{now:.1f} / {self.practice_end:.1f}  ({self.practice_start:.1f}-{self.practice_end:.1f})", "mono", MUTED, pos=(width - 300, 45))
            self.text(f"PRACTICE  {'LOOP ON' if self.practice_loop else 'LOOP OFF'}  #{self.practice_round + 1}", "mono", GREEN, pos=(width - 330, 75))
            self.text("練習記録はスコア・報酬・ランキングへ反映されません  [L] ループ切替  [Q] 区間設定へ", "small", MUTED, center=(width // 2, 34))
        else:
            self.text(f"{now:.1f} / {self.chart.song_duration:.1f}", "mono", MUTED, pos=(width - 190, 45))
            mode_label = "TRIAL" if self.trial_active else ("TUTORIAL" if self.tutorial_active else self.chart.difficulty.label)
            mode_color = YELLOW if self.trial_active else (GREEN if self.tutorial_active else CYAN)
            self.text(mode_label, "mono", mode_color, pos=(width - 150, 75))
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
        else:
            self._draw_judgment_feedback()
        if time.perf_counter() < self.combo_banner_until:
            self.text(self.combo_banner, "title", MAGENTA, center=(width // 2, height // 2 - 75))
        if not counting_down and not self.game_paused:
            self.text("ESC：一時停止メニュー", "small", MUTED, pos=(24, height - 35))
        if self.game_paused:
            self.panel(pygame.Rect(width // 2 - 205, height // 2 - 130, 410, 260), (25, 35, 58), 16)
            self.text("PAUSED", "h1", YELLOW, center=(width // 2, height // 2 - 90))
            self.button("再開  [ESC]", pygame.Rect(width // 2 - 160, height // 2 - 48, 320, 42), self.toggle_pause, accent=GREEN)
            self.button("リトライ  [R]", pygame.Rect(width // 2 - 160, height // 2 + 6, 320, 42), self.retry_game, accent=CYAN)
            self.button("チュートリアルへ  [Q]" if self.tutorial_active else ("区間設定へ  [Q]" if self.practice_active else "楽曲選択へ  [Q]"), pygame.Rect(width // 2 - 160, height // 2 + 60, 320, 42), self.return_to_practice_setup if self.practice_active else self.return_to_song_select, accent=MUTED)

    def _result_grade_color(self, rank: str) -> tuple[int, int, int]:
        return {"S+": YELLOW, "S": CYAN, "A": GREEN, "B": (120, 190, 255), "C": MUTED, "D": RED}.get(rank, CYAN)

    def _result_note_total(self, result: PlayResult) -> int:
        return sum(int(result.judgments.get(label, 0)) for label in ("PERFECT", "GREAT", "GOOD", "MISS"))

    def _is_full_combo_result(self, result: PlayResult) -> bool:
        return self._result_note_total(result) > 0 and int(result.judgments.get("MISS", 0)) == 0

    def _result_flags(self, result: PlayResult) -> list[tuple[str, tuple[int, int, int]]]:
        total = self._result_note_total(result)
        perfect = int(result.judgments.get("PERFECT", 0))
        flags: list[tuple[str, tuple[int, int, int]]] = []
        if total > 0 and perfect == total:
            flags.append(("ALL PERFECT!", YELLOW))
        if self._is_full_combo_result(result):
            flags.append(("FULL COMBO!", GREEN))
        last_ranking = self.profile.get("last_play_ranking", {})
        if isinstance(last_ranking, dict) and last_ranking.get("chart_key") == result.chart_hash:
            position = int(last_ranking.get("position", 0))
            if last_ranking.get("new_high_score"):
                delta = int(last_ranking.get("score_delta", 0))
                label = f"NEW HIGH SCORE! +{delta:,}" if delta > 0 else "NEW HIGH SCORE!"
                flags.append((label, CYAN))
            if 0 < position <= 3:
                flags.append((f"TOP {position} RANK IN!", MAGENTA))
            elif position > 0:
                flags.append((f"LOCAL RANK #{position}", MAGENTA))
        return flags

    def _result_badges(self) -> list[str]:
        badges = self.profile.get("last_play_badges", [])
        return [str(badge) for badge in badges] if isinstance(badges, list) else []

    def _result_song_title(self) -> str:
        if self.song_path is not None:
            return self.song_path.stem
        if self.analysis is not None and self.analysis.source_path:
            return Path(self.analysis.source_path).stem
        return "Unknown Track"

    def _draw_result_background(self, rank: str) -> None:
        width, height = self.size
        accent = self._result_grade_color(rank)
        for index in range(9):
            radius = 260 - index * 18
            alpha = max(8, 34 - index * 3)
            glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow, (*accent, alpha), (radius, radius), radius)
            self.surface.blit(glow, (width // 2 - radius, 72 - radius // 2))
        if rank in {"S+", "S", "A"}:
            now = time.perf_counter()
            colors = (YELLOW, CYAN, MAGENTA, GREEN, WHITE)
            for index in range(46 if rank == "S+" else 30):
                x = int((index * 97 + now * 36) % width)
                y = int(92 + ((index * 53 + now * 80) % 470))
                color = colors[index % len(colors)]
                pygame.draw.circle(self.surface, color, (x, y), 2 + index % 3)

    def _full_combo_media_files(self) -> list[Path]:
        folder = self.resource_path("assets/full_combo")
        if not folder.exists():
            return []
        return sorted(
            (path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in FULL_COMBO_MEDIA_EXTENSIONS),
            key=lambda path: path.name.casefold(),
        )

    def _load_full_combo_media_frames(self, max_width: int, max_height: int) -> list[pygame.Surface]:
        files = self._full_combo_media_files()
        if not files:
            return []
        cache_key = (tuple(str(path) for path in files), max_width, max_height)
        cached = self.full_combo_media_cache.get(cache_key)
        if cached is not None:
            return cached
        frames: list[pygame.Surface] = []
        for path in files[:48]:
            try:
                image = pygame.image.load(str(path)).convert_alpha()
            except pygame.error:
                continue
            scale = min(max_width / max(1, image.get_width()), max_height / max(1, image.get_height()), 1.0)
            if scale < 1.0:
                image = pygame.transform.smoothscale(image, (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale))))
            frames.append(image)
        self.full_combo_media_cache[cache_key] = frames
        return frames

    def _draw_full_combo_media(self, rect: pygame.Rect, result: PlayResult) -> None:
        if not self._is_full_combo_result(result):
            return
        self.panel(rect, (15, 24, 43), 16)
        pygame.draw.rect(self.surface, GREEN, rect, width=2, border_radius=16)
        self.text("FULL COMBO SPECIAL", "small", GREEN, center=(rect.centerx, rect.top + 26))
        frames = self._load_full_combo_media_frames(rect.width - 36, rect.height - 78)
        if frames:
            index = int(time.perf_counter() * 10) % len(frames)
            frame = frames[index]
            self.surface.blit(frame, frame.get_rect(center=(rect.centerx, rect.centery + 18)))
            if len(frames) > 1:
                self.text(f"FRAME {index + 1}/{len(frames)}", "small", MUTED, center=(rect.centerx, rect.bottom - 18))
            else:
                self.text("assets/full_combo", "small", MUTED, center=(rect.centerx, rect.bottom - 18))
            return
        mascot = self.selected_mascot
        if mascot is None:
            self.text("ADD IMAGE TO assets/full_combo", "small", YELLOW, center=rect.center)
            return
        base = self._mascot_surface(mascot, rect.height - 92)
        if base is None:
            self.text("ADD IMAGE TO assets/full_combo", "small", YELLOW, center=rect.center)
            return
        pulse = 1.0 + 0.045 * math.sin(time.perf_counter() * math.tau * 1.4)
        sprite = pygame.transform.rotozoom(base, 0, pulse)
        sprite.set_alpha(238)
        self.surface.blit(sprite, sprite.get_rect(center=(rect.centerx, rect.centery + 22)))
        self.text("画像を置くまではマスコットで代替表示", "small", MUTED, center=(rect.centerx, rect.bottom - 18))

    def _draw_result_mascot(self, rect: pygame.Rect, result: PlayResult) -> None:
        mascot = self.selected_mascot
        if mascot is None or self.mascot_mode_key == "off":
            return
        target_height = int(rect.height * (0.88 if result.rank in {"S+", "S"} else 0.76))
        base = self._mascot_surface(mascot, target_height)
        if base is None:
            return
        pulse = 1.0 + (0.035 * math.sin(time.perf_counter() * math.tau * 1.2) if result.rank in {"S+", "S", "A"} else 0.0)
        sprite = pygame.transform.rotozoom(base, 0, pulse)
        sprite.set_alpha(235)
        self.surface.blit(sprite, sprite.get_rect(midbottom=(rect.centerx, rect.bottom - 16)))
        self.text(mascot.name, "small", MUTED, center=(rect.centerx, rect.bottom - 4))

    def _wrap_result_dialogue(self, value: str, max_width: int, max_lines: int = 2) -> list[str]:
        font = self.fonts["small"]
        lines: list[str] = []
        current = ""
        for character in value:
            candidate = current + character
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = character
                if len(lines) == max_lines:
                    break
            else:
                current = candidate
        if current and len(lines) < max_lines:
            lines.append(current)
        consumed = "".join(lines)
        if len(consumed) < len(value) and lines:
            while lines[-1] and font.size(lines[-1] + "…")[0] > max_width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        return lines

    def _draw_result_mascot_dialogue(self, rect: pygame.Rect, result: PlayResult) -> None:
        mascot = self.selected_mascot
        if mascot is None or self.mascot_mode_key == "off":
            return
        accent = self._result_grade_color(result.rank)
        self.panel(rect, (20, 31, 53), 12)
        pygame.draw.rect(self.surface, accent, rect, width=2, border_radius=12)
        tail = ((rect.centerx - 12, rect.top), (rect.centerx + 12, rect.top), (rect.centerx, rect.top - 12))
        pygame.draw.polygon(self.surface, (20, 31, 53), tail)
        pygame.draw.lines(self.surface, accent, False, tail, 2)
        self.text(mascot.name, "small", accent, pos=(rect.left + 14, rect.top + 7))
        lines = self._wrap_result_dialogue(mascot_result_line(mascot.mascot_id, result.rank), rect.width - 28)
        for index, line in enumerate(lines):
            self.text(line, "small", WHITE, pos=(rect.left + 14, rect.top + 29 + index * 18))

    def _draw_result_reward_preview(self, rect: pygame.Rect) -> None:
        self.panel(rect, PANEL_DARK, 10)
        self.text("REWARD", "small", MAGENTA, pos=(rect.left + 14, rect.top + 12))
        unlocked_lookup = {reward.name: reward for reward in self.gallery_rewards()}
        reward = unlocked_lookup.get(self.newly_unlocked[0]) if self.newly_unlocked else None
        if reward is not None:
            self.text("NEW UNLOCKED", "small", YELLOW, pos=(rect.left + 14, rect.top + 36))
            preview = self._load_scaled_reward(reward, rect.width - 36, rect.height - 82)
            if preview is not None:
                self.surface.blit(preview, preview.get_rect(center=(rect.centerx, rect.centery + 18)))
            self.text(Path(reward.name).stem, "small", WHITE, center=(rect.centerx, rect.bottom - 18))
            return
        status = self.draw_reward_progress(pygame.Rect(rect.left + 14, rect.top + 42, rect.width - 28, 72), compact=True)
        if status.next_reward is not None:
            self.text("次の画像まであと少し", "small", MUTED, center=(rect.centerx, rect.bottom - 28))

    def save_result_screenshot(self) -> None:
        if not self.session:
            self.error = "保存できるリザルトがありません。"
            return
        output_dir = self.paths.root / "screenshots" / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        result = self.session.result()
        title = "".join(char if char.isalnum() or char in "-_" else "_" for char in self._result_song_title())[:36] or "result"
        lane_label = f"{chart_lane_count(self.chart) if self.chart else self.active_lane_count}lane"
        filename = f"AutoBeat5_{title}_{lane_label}_{result.rank}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        pygame.image.save(self.surface, str(output_dir / filename))
        self.message = f"リザルト画像を保存しました: {output_dir / filename}"

    def draw_result(self) -> None:
        if not self.session:
            self.set_screen("title")
            return
        result = self.session.result()
        width, height = self.size
        self._draw_result_background(result.rank)
        accent = self._result_grade_color(result.rank)
        song_title = self._result_song_title()
        difficulty = self.chart.difficulty.label if self.chart else ""

        self.text("RESULT", "h1", WHITE, pos=(54, 34))
        self.text(f"{song_title}  /  {difficulty}  /  {chart_lane_count(self.chart) if self.chart else self.active_lane_count} LANE", "small", MUTED, pos=(54, 74))
        self.text("Sで画像保存", "small", CYAN, pos=(width - 170, 42))

        hero = pygame.Rect(54, 118, 430, 420)
        self.panel(hero, (16, 24, 42), 18)
        pygame.draw.rect(self.surface, accent, hero, width=2, border_radius=18)
        self.text(result.rank, "title", accent, center=(hero.centerx, hero.top + 78))
        self.text(f"SCORE {result.score:07d}", "h1", WHITE, center=(hero.centerx, hero.top + 152))
        self.text(f"ACCURACY {result.accuracy:.2f}%", "body", CYAN, center=(hero.centerx, hero.top + 204))
        self.text(f"MAX COMBO {result.max_combo}", "body", YELLOW, center=(hero.centerx, hero.top + 240))

        y = hero.top + 286
        for label, color in self._result_flags(result)[:4]:
            self.panel(pygame.Rect(hero.left + 38, y, hero.width - 76, 34), (26, 42, 68), 8)
            self.text(label, "body", color, center=(hero.centerx, y + 17))
            y += 42
        badges = self._result_badges()[:3]
        if badges:
            self.text("TITLE", "small", MUTED, center=(hero.centerx, hero.bottom - 68))
            self.text(" / ".join(badges), "small", WHITE, center=(hero.centerx, hero.bottom - 42))

        stats = pygame.Rect(520, 118, 350, 300)
        self.panel(stats, PANEL, 14)
        labels = ("PERFECT", "GREAT", "GOOD", "MISS")
        max_count = max(1, *(int(result.judgments.get(label, 0)) for label in labels))
        for index, label in enumerate(labels):
            count = int(result.judgments.get(label, 0))
            row_y = stats.top + 32 + index * 62
            color = JUDGMENT_COLORS[Judgment(label)]
            self.text(label, "small", color, pos=(stats.left + 24, row_y))
            self.text(str(count), "mono", WHITE, pos=(stats.right - 74, row_y - 2))
            bar = pygame.Rect(stats.left + 24, row_y + 26, stats.width - 48, 10)
            pygame.draw.rect(self.surface, (45, 60, 88), bar, border_radius=5)
            pygame.draw.rect(self.surface, color, pygame.Rect(bar.left, bar.top, max(4, int(bar.width * count / max_count)), bar.height), border_radius=5)

        self._draw_result_reward_preview(pygame.Rect(520, 440, 350, 112))
        mascot_rect = pygame.Rect(900, 118, 300, 420)
        if self._is_full_combo_result(result):
            self._draw_full_combo_media(mascot_rect, result)
        else:
            self.panel(mascot_rect, (13, 20, 34), 16)
            self._draw_result_mascot(mascot_rect, result)
        self._draw_result_mascot_dialogue(pygame.Rect(900, 552, 300, 72), result)

        if self.chart_is_pending:
            self.panel(pygame.Rect(width // 2 - 385, height - 150, 770, 42), (44, 61, 92), 10)
            self.text("試作候補をプレイしました。どちらを残しますか？", "body", YELLOW, center=(width // 2, height - 129))
            self.button("採用・保存 [A]", pygame.Rect(width // 2 - 350, height - 96, 220, 40), self.adopt_pending_chart, accent=GREEN)
            self.button("以前を残す [D]", pygame.Rect(width // 2 - 110, height - 96, 220, 40), self.discard_pending_chart, accent=MAGENTA)
            self.button("画像保存 [S]", pygame.Rect(width // 2 + 130, height - 96, 220, 40), self.save_result_screenshot, accent=CYAN)
        else:
            button_y = height - 86
            compact = width < 1392
            actions = [
                ("もう一度 [ENTER/R]", "もう一度", 210, 170, self.start_game, GREEN),
                ("難易度変更 [D]", "難易度変更", 210, 160, self.return_to_difficulty, CYAN),
                ("ランキング [L]", "ランキング", 180, 160, self.open_ranking, MAGENTA),
                ("ギャラリー [G]", "ギャラリー", 180, 160, lambda: self.set_screen("gallery"), YELLOW),
                ("画像保存 [S]", "画像保存", 180, 160, self.save_result_screenshot, CYAN),
                ("曲選択 [ESC]", "曲選択", 160, 150, self.return_to_song_select, MUTED),
                ("設定", "設定", 100, 100, self.open_result_settings, CYAN),
            ]
            x = 50
            for label, short_label, normal_width, compact_width, action, accent in actions:
                button_width = compact_width if compact else normal_width
                self.button(short_label if compact else label, pygame.Rect(x, button_y, button_width, 42), action, accent=accent)
                x += button_width + 12

    def open_result_settings(self) -> None:
        self.set_screen("settings")

    def draw_unlock(self) -> None:
        width, height = self.size
        self.heading("NEW UNLOCK", "新しい遊び方・コレクションが解放されました")
        self.text("解放済み", "h1", MAGENTA, center=(width // 2, 172))
        for index, item_id in enumerate(self.newly_unlocked[:3]):
            y = 228 + index * 62
            self.panel(pygame.Rect(width // 2 - 290, y - 16, 580, 48), (24, 39, 66), 10)
            self.text(self._unlocked_notification_label(item_id), "body", YELLOW if item_id.startswith("lane.") else CYAN, center=(width // 2, y))
            self.text(self._unlocked_notification_detail(item_id), "small", MUTED, center=(width // 2, y + 20))
        if len(self.newly_unlocked) > 3:
            self.text(f"+{len(self.newly_unlocked) - 3} more", "small", MUTED, center=(width // 2, 424))
        unlocked_lookup = {reward.name: reward for reward in self.gallery_rewards()}
        reward_id = next((item for item in self.newly_unlocked if item in unlocked_lookup), None)
        first_reward = unlocked_lookup.get(reward_id) if reward_id else None
        if first_reward is not None:
            preview = self._load_scaled_reward(first_reward, 260, 140)
            if preview is not None:
                self.surface.blit(preview, preview.get_rect(center=(width // 2, 450)))
        self.draw_reward_progress(pygame.Rect(width // 2 - 280, 505, 560, 76), compact=True)
        self.button("ギャラリーで見る", pygame.Rect(width // 2 - 170, height - 118, 340, 42), lambda: self.set_screen("gallery"), accent=MAGENTA)
        self.button("リザルトを見る", pygame.Rect(width // 2 - 170, height - 66, 340, 38), lambda: self.set_screen("result"), accent=CYAN)

    def draw_gallery(self) -> None:
        width, height = self.size
        rewards = self.gallery_rewards()
        page_size = 8
        page_count = max(1, math.ceil(len(rewards) / page_size))
        self.gallery_page = max(0, min(self.gallery_page, page_count - 1))
        status = self.reward_status()
        next_text = "全画像を購入済み" if status.next_reward is None else f"次: {Path(status.next_reward.name).stem} まで {status.remaining_score:,} BP"
        self.heading("GALLERY", f"所持 {int(self.profile.get('wallet_score', 0)):,} BP  ·  所有 {status.unlocked_count}/{status.reward_count}  ·  {next_text}")
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
                required = "価格未設定" if reward.required_score is None else f"{reward.required_score:,} BP"
                self.text(Path(reward.name).stem, "small", WHITE if reward.unlocked else MUTED, center=(rect.centerx, rect.bottom - 35))
                self.text(required, "small", MUTED, center=(rect.centerx, rect.bottom - 16))
                self.buttons.append((rect, lambda selected=reward: self.open_reward(selected)))
        if page_count > 1:
            self.button("← 前へ", pygame.Rect(width // 2 - 220, height - 72, 180, 40), lambda: setattr(self, "gallery_page", max(0, self.gallery_page - 1)), accent=MAGENTA)
            self.button("次へ →", pygame.Rect(width // 2 + 40, height - 72, 180, 40), lambda: setattr(self, "gallery_page", min(page_count - 1, self.gallery_page + 1)), accent=MAGENTA)
        self.button("報酬を管理  [M]", pygame.Rect(width - 250, height - 72, 205, 40), self.open_reward_manager, accent=YELLOW)
        self.button("ショップ  [B]", pygame.Rect(215, height - 72, 170, 40), self.open_shop, accent=GREEN)
        self.button("タイトルへ", pygame.Rect(45, height - 72, 150, 40), lambda: self.set_screen("title"), accent=MUTED)

    def draw_shop(self) -> None:
        width, height = self.size
        items = self.shop_items()
        self._clamp_shop_position()
        balance = int(self.profile.get("wallet_score", 0))
        self.heading("BEAT SHOP", f"所持  {balance:,} BP  ・  通常プレイのスコアがBEAT POINTになります")
        list_rect = pygame.Rect(70, 150, 720, SHOP_VISIBLE_ROWS * SHOP_ROW_HEIGHT + 16)
        preview_rect = pygame.Rect(830, 150, 380, 422)
        self.panel(list_rect)
        self.panel(preview_rect, PANEL_DARK, 10)
        if not items:
            self.text("購入できるアイテムはまだありません。", "body", MUTED, center=list_rect.center)
            selected = None
        else:
            start = self.shop_scroll_index
            selected = items[self.shop_selected_index]
            for index in range(start, min(len(items), start + SHOP_VISIBLE_ROWS)):
                item = items[index]
                row = pygame.Rect(list_rect.left + 12, list_rect.top + 8 + (index - start) * SHOP_ROW_HEIGHT, list_rect.width - 34, SHOP_ROW_HEIGHT - 6)
                active = index == self.shop_selected_index
                self.panel(row, PANEL if active else PANEL_DARK, 7)
                pygame.draw.rect(self.surface, CYAN if active else (48, 63, 91), row, width=2 if active else 1, border_radius=7)
                self.text(item.category, "small", MAGENTA if item.category == "REWARD" else CYAN, pos=(row.left + 14, row.top + 8))
                self.text(item.name, "body", WHITE if item.available else MUTED, pos=(row.left + 120, row.top + 13))
                if item.owned:
                    status, color = "OWNED", GREEN
                elif not item.available:
                    status, color = "NO ASSET", RED
                else:
                    status, color = f"{item.price:,} BP", YELLOW
                self.text(status, "small", color, pos=(row.right - 132, row.top + 17))
                self.buttons.append((row, lambda selected_index=index: self._select_shop_item(selected_index)))
        self.text("PREVIEW", "small", MUTED, pos=(preview_rect.left + 18, preview_rect.top + 16))
        if selected is not None:
            self._draw_shop_preview(selected, pygame.Rect(preview_rect.left + 24, preview_rect.top + 48, preview_rect.width - 48, 275))
            self.text(selected.name, "body", WHITE, center=(preview_rect.centerx, preview_rect.bottom - 74))
            detail = "購入済み" if selected.owned else ("素材待ち" if not selected.available else f"価格  {selected.price:,} BP")
            self.text(detail, "small", GREEN if selected.owned else YELLOW, center=(preview_rect.centerx, preview_rect.bottom - 42))
        label = "購入済み" if selected and selected.owned else ("購入を確定 [ENTER]" if selected and self.shop_confirmation_id == selected.item_id else "購入する [ENTER]")
        self.button(label, pygame.Rect(width // 2 - 180, height - 78, 360, 42), self.activate_shop_purchase, accent=GREEN)
        self.button("タイトルへ [ESC]", pygame.Rect(45, height - 70, 190, 40), lambda: self.set_screen("title"), accent=MUTED)

    def _select_shop_item(self, index: int) -> None:
        self.shop_selected_index = index
        self.shop_confirmation_id = None
        self._clamp_shop_position()

    def _draw_shop_preview(self, item: ShopItem, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.surface, (10, 16, 29), rect, border_radius=8)
        image = None
        if item.mascot_id:
            mascot = find_mascot(self.mascot_catalog, item.mascot_id)
            if mascot is not None:
                image = self._mascot_surface(mascot, rect.height - 24)
        elif item.asset_path is not None:
            image = self._load_scaled_reward(RewardImage(item.asset_path.name, item.asset_path, item.price, item.owned), rect.width - 24, rect.height - 24)
        if image is None:
            self.text("NO PREVIEW", "small", MUTED, center=rect.center)
            return
        preview = image.copy()
        if not item.owned:
            preview.set_alpha(105)
        self.surface.blit(preview, preview.get_rect(center=rect.center))
        if not item.owned:
            self.text("LOCKED", "body", WHITE, center=rect.center)

    def draw_reward_manager(self) -> None:
        """報酬の必要スコア・画像有無・解放状況を一覧で確認する画面。"""
        width, height = self.size
        entries = self.reward_manager_entries()
        self._clamp_reward_manager_position()
        visible_rows = self._reward_manager_visible_rows()
        status = self.reward_status()
        next_text = "購入候補はありません" if status.next_reward is None else f"次の候補: {Path(status.next_reward.name).stem}（あと {status.remaining_score:,} BP）"
        self.heading("REWARD MANAGER", f"所持 {int(self.profile.get('wallet_score', 0)):,} BP  ・  所有 {status.unlocked_count}/{status.reward_count}  ・  {next_text}")
        self.draw_reward_progress(pygame.Rect(95, 140, width - 190, 70), compact=True)

        list_rect = pygame.Rect(95, 232, width - 190, visible_rows * REWARD_MANAGER_ROW_HEIGHT + 16)
        self.panel(list_rect)
        if not entries:
            self.text("報酬がありません。rewards フォルダへ画像を入れ、reward_config.json に価格を設定してください。", "body", MUTED, center=list_rect.center)
        else:
            start = self.reward_manager_scroll_index
            end = min(len(entries), start + visible_rows)
            for index in range(start, end):
                item = entries[index]
                row = pygame.Rect(list_rect.left + 12, list_rect.top + 10 + (index - start) * REWARD_MANAGER_ROW_HEIGHT, list_rect.width - 38, REWARD_MANAGER_ROW_HEIGHT - 5)
                selected = index == self.reward_manager_selected_index
                self.panel(row, (37, 57, 88) if selected else PANEL_DARK, 6)
                pygame.draw.rect(self.surface, YELLOW if selected else (54, 71, 103), row, width=2 if selected else 1, border_radius=6)

                preview_rect = pygame.Rect(row.left + 10, row.top + 7, 44, 38)
                if item.exists:
                    preview = self._load_scaled_reward(RewardImage(item.name, item.path, item.required_score, item.unlocked), preview_rect.width, preview_rect.height)
                    if preview is not None:
                        self.surface.blit(preview, preview.get_rect(center=preview_rect.center))
                    else:
                        self.text("!", "body", RED, center=preview_rect.center)
                else:
                    pygame.draw.rect(self.surface, (70, 45, 55), preview_rect, border_radius=4)
                    self.text("?", "body", RED, center=preview_rect.center)

                self.text(Path(item.name).stem, "small", WHITE, pos=(row.left + 68, row.top + 10))
                required_text = "価格設定なし" if item.required_score is None else f"{item.required_score:,} BP"
                self.text(required_text, "small", MUTED, pos=(row.left + 340, row.top + 10))

                if not item.exists:
                    label, color, detail = "MISSING FILE", RED, "画像を追加してください"
                elif item.required_score is None:
                    label, color, detail = "NO PRICE", YELLOW, "priceを追加してください"
                elif item.unlocked:
                    label, color, detail = "OWNED", GREEN, "クリックで表示"
                else:
                    label, color, detail = "SHOP", MUTED, f"あと {int(item.remaining_score or 0):,} BP"
                self.text(label, "small", color, pos=(row.left + 535, row.top + 10))
                self.text(detail, "small", color if label == "LOCKED" else MUTED, pos=(row.left + 710, row.top + 10))
                self.buttons.append((row, lambda selected_index=index: self.select_reward_manager_entry(selected_index)))

            if len(entries) > visible_rows:
                track = pygame.Rect(list_rect.right - 16, list_rect.top + 10, 6, list_rect.height - 20)
                pygame.draw.rect(self.surface, PANEL_DARK, track, border_radius=3)
                thumb_height = max(26, int(track.height * visible_rows / len(entries)))
                max_scroll = len(entries) - visible_rows
                progress = self.reward_manager_scroll_index / max_scroll if max_scroll else 0.0
                thumb_top = track.top + int((track.height - thumb_height) * progress)
                pygame.draw.rect(self.surface, YELLOW, pygame.Rect(track.left, thumb_top, track.width, thumb_height), border_radius=3)

        self.text(f"{self.reward_manager_scroll_index + 1 if entries else 0}-{min(len(entries), self.reward_manager_scroll_index + visible_rows)} / {len(entries)}", "small", MUTED, center=(width // 2, height - 115))
        self.button("画像フォルダの場所  [F]", pygame.Rect(80, height - 72, 235, 40), self.show_reward_folder, accent=CYAN)
        self.button("設定ファイルの場所  [C]", pygame.Rect(330, height - 72, 235, 40), self.show_reward_config, accent=YELLOW)
        self.button("ギャラリーへ  [ESC]", pygame.Rect(width - 310, height - 72, 230, 40), lambda: self.set_screen("gallery"), accent=MAGENTA)

    def draw_gallery_preview(self) -> None:
        width, height = self.size
        reward = self.selected_reward
        if reward is None or not reward.unlocked:
            self.set_screen("gallery")
            return
        self.heading("GALLERY PREVIEW", Path(reward.name).stem)
        self.panel(pygame.Rect(80, 145, width - 160, height - 255))
        image = self._load_scaled_reward(reward, width - 220, height - 350)
        if image:
            self.surface.blit(image, image.get_rect(center=(width // 2, height // 2 - 10)))
        else:
            self.text("画像を読み込めませんでした。", "body", RED, center=(width // 2, height // 2))
        if reward.required_score is not None:
            self.text(f"購入価格: {reward.required_score:,} BP", "small", MUTED, center=(width // 2, height - 95))
        self.button("ギャラリーへ戻る", pygame.Rect(width // 2 - 160, height - 65, 320, 42), lambda: self.set_screen("gallery"), accent=MAGENTA)

    def _brighten(self, color: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
        return tuple(max(0, min(255, channel + amount)) for channel in color)

    def _draw_note_cap(self, rect: pygame.Rect, color: tuple[int, int, int], *, skin: str | None = None, lane_index: int | None = None) -> None:
        skin = skin or self.note_skin_key
        if skin == "glow":
            glow = pygame.Surface((rect.width + 22, rect.height + 22), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*color, 70), glow.get_rect(), border_radius=12)
            self.surface.blit(glow, (rect.left - 11, rect.top - 11), special_flags=pygame.BLEND_PREMULTIPLIED)
            pygame.draw.rect(self.surface, self._brighten(color, 24), rect, border_radius=8)
            pygame.draw.rect(self.surface, (245, 252, 255), rect.inflate(-8, -10), border_radius=5)
            return
        if skin == "crystal":
            points = [(rect.left + rect.width // 2, rect.top - 3), (rect.right, rect.centery), (rect.left + rect.width // 2, rect.bottom + 3), (rect.left, rect.centery)]
            pygame.draw.polygon(self.surface, self._brighten(color, -18), points)
            pygame.draw.polygon(self.surface, self._brighten(color, 70), points, width=2)
            pygame.draw.line(self.surface, (245, 252, 255), (rect.left + rect.width // 2, rect.top + 2), (rect.left + rect.width // 2, rect.bottom - 2), 1)
            return
        if skin == "arcade":
            pygame.draw.rect(self.surface, self._brighten(color, -30), rect, border_radius=2)
            pygame.draw.rect(self.surface, (245, 252, 255), rect, width=3, border_radius=2)
            pygame.draw.line(self.surface, self._brighten(color, 60), (rect.left + 5, rect.top + 5), (rect.right - 5, rect.top + 5), 2)
            return
        if skin == "minimal":
            pygame.draw.line(self.surface, self._brighten(color, 45), (rect.left + 4, rect.centery), (rect.right - 4, rect.centery), 5)
            pygame.draw.line(self.surface, (245, 252, 255), (rect.left + 9, rect.centery), (rect.right - 9, rect.centery), 1)
            return
        if skin == "pixel":
            block = pygame.Rect(rect.left, rect.top + 1, rect.width, rect.height - 2)
            pygame.draw.rect(self.surface, self._brighten(color, -12), block)
            pygame.draw.rect(self.surface, self._brighten(color, 52), block, width=2)
            px = max(5, rect.height // 3)
            pygame.draw.rect(self.surface, (245, 252, 255), pygame.Rect(block.left + 5, block.top + 4, px, px))
            pygame.draw.rect(self.surface, self._brighten(color, -46), pygame.Rect(block.right - px - 5, block.bottom - px - 4, px, px))
            return
        if skin == "heart":
            radius = max(5, rect.height // 2)
            pygame.draw.circle(self.surface, color, (rect.centerx - radius // 2, rect.centery - 2), radius)
            pygame.draw.circle(self.surface, color, (rect.centerx + radius // 2, rect.centery - 2), radius)
            pygame.draw.polygon(self.surface, color, [(rect.left + 3, rect.centery + 2), (rect.right - 3, rect.centery + 2), (rect.centerx, rect.bottom + 8)])
            pygame.draw.circle(self.surface, self._brighten(color, 70), (rect.centerx - radius // 2, rect.centery - 3), radius, width=2)
            return
        if skin == "star":
            points = []
            outer = max(rect.width, rect.height) * 0.48
            inner = outer * 0.46
            for i in range(10):
                angle = -math.pi / 2 + i * math.pi / 5
                radius = outer if i % 2 == 0 else inner
                points.append((rect.centerx + math.cos(angle) * radius, rect.centery + math.sin(angle) * radius))
            pygame.draw.polygon(self.surface, color, points)
            pygame.draw.polygon(self.surface, self._brighten(color, 75), points, width=2)
            return
        if skin == "diamond":
            points = [(rect.centerx, rect.top - 6), (rect.right, rect.centery), (rect.centerx, rect.bottom + 6), (rect.left, rect.centery)]
            pygame.draw.polygon(self.surface, color, points)
            pygame.draw.polygon(self.surface, (245, 252, 255), points, width=2)
            return
        if skin == "ribbon_hold":
            pygame.draw.polygon(self.surface, self._brighten(color, -18), [(rect.left - 8, rect.top + 3), (rect.left, rect.centery), (rect.left - 8, rect.bottom - 3), (rect.right + 8, rect.bottom - 3), (rect.right, rect.centery), (rect.right + 8, rect.top + 3)])
            pygame.draw.rect(self.surface, self._brighten(color, 40), rect, border_radius=7)
            pygame.draw.line(self.surface, (245, 252, 255), (rect.left + 8, rect.centery), (rect.right - 8, rect.centery), 1)
            return
        if skin == "neon_line":
            pygame.draw.rect(self.surface, self._brighten(color, 45), rect, width=2, border_radius=6)
            pygame.draw.line(self.surface, color, (rect.left + 5, rect.centery), (rect.right - 5, rect.centery), 3)
            return
        if skin == "accessible":
            pygame.draw.rect(self.surface, color, rect, border_radius=5)
            pygame.draw.rect(self.surface, (245, 252, 255), rect, width=3, border_radius=5)
            if lane_index is not None:
                self.text(str(lane_index + 1), "small", (10, 14, 24), center=rect.center)
            return
        pygame.draw.rect(self.surface, color, rect, border_radius=7)

    def _draw_hold_rail(self, rect: pygame.Rect, color: tuple[int, int, int], *, skin: str | None = None) -> None:
        skin = skin or self.note_skin_key
        if skin in {"minimal", "neon_line"}:
            pygame.draw.line(self.surface, self._brighten(color, -10), (rect.centerx, rect.top), (rect.centerx, rect.bottom), 4 if skin == "minimal" else 6)
            pygame.draw.line(self.surface, self._brighten(color, 55), (rect.centerx, rect.top), (rect.centerx, rect.bottom), 1)
            return
        if skin == "ribbon_hold":
            ribbon = pygame.Surface((rect.width + 24, rect.height), pygame.SRCALPHA)
            points = []
            for i in range(0, rect.height + 8, 8):
                wave = math.sin(i / 13.0) * 5
                points.append((12 + rect.width * 0.25 + wave, i))
            for i in range(rect.height, -8, -8):
                wave = math.sin(i / 13.0) * 5
                points.append((12 + rect.width * 0.75 + wave, i))
            pygame.draw.polygon(ribbon, (*self._brighten(color, -22), 165), points)
            pygame.draw.lines(ribbon, (*self._brighten(color, 65), 220), False, points[: max(2, len(points)//2)], 2)
            self.surface.blit(ribbon, (rect.left - 12, rect.top))
            return
        alpha = 115 if skin in {"glow", "crystal"} else 190
        rail = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(rail, (*self._brighten(color, -35), alpha), rail.get_rect(), border_radius=8)
        self.surface.blit(rail, rect.topleft)

    def _draw_note_preview_panel(self, rect: pygame.Rect, now: float) -> None:
        self.panel(rect, (14, 22, 38), 12)
        self.text("NOTE PREVIEW", "small", MUTED, pos=(rect.left + 14, rect.top + 12))
        self.text(f"{self.note_theme_label} / {self.note_skin_label}", "small", CYAN, pos=(rect.left + 14, rect.top + 36))
        stage = pygame.Rect(rect.left + 16, rect.top + 66, rect.width - 32, rect.height - 86)
        pygame.draw.rect(self.surface, (10, 16, 29), stage, border_radius=10)
        lanes = min(5, self.active_lane_count)
        lane_width = max(34, stage.width // lanes)
        line_y = stage.bottom - 30
        for lane in range(lanes):
            x = stage.left + lane * lane_width
            lane_rect = pygame.Rect(x, stage.top + 8, lane_width - 2, line_y - stage.top - 8)
            pygame.draw.rect(self.surface, (16, 25, 43), lane_rect)
            color = self.lane_color(lane)
            pygame.draw.line(self.surface, tuple(channel // 3 for channel in color), (x, lane_rect.top), (x, line_y), 1)
            y = stage.top + 42 + lane * 18
            cap = pygame.Rect(x + 5, y, lane_width - 12, 14)
            if lane == 1:
                rail = pygame.Rect(cap.centerx - 7, y + 12, 14, max(38, line_y - y - 22))
                self._draw_hold_rail(rail, color)
                self._draw_note_cap(cap, color, lane_index=lane)
                end_cap = pygame.Rect(cap.left, min(line_y - 18, y + 72), cap.width, 14)
                self._draw_note_cap(end_cap, color, lane_index=lane)
            else:
                self._draw_note_cap(cap, color, lane_index=lane)
        pygame.draw.line(self.surface, WHITE, (stage.left + 6, line_y), (stage.right - 6, line_y), 2)
        _, description = NOTE_SKINS[self.note_skin_key]
        self.text(description, "small", MUTED, center=(rect.centerx, rect.bottom - 17))

    def _draw_settings_mascot_preview(self, rect: pygame.Rect, now: float) -> None:
        self.panel(rect, (14, 22, 38), 12)
        self.text("MASCOT PREVIEW", "small", MUTED, pos=(rect.left + 14, rect.top + 12))
        self.text(self.mascot_mode_label, "small", CYAN, pos=(rect.left + 14, rect.top + 36))
        mascot = self.selected_mascot
        intensity = MASCOT_MODES[self.mascot_mode_key][1]
        stage = pygame.Rect(rect.left + 18, rect.top + 70, rect.width - 36, rect.height - 92)
        pygame.draw.rect(self.surface, (10, 16, 29), stage, border_radius=10)
        pygame.draw.line(self.surface, (43, 58, 86), (stage.left + 12, stage.bottom - 20), (stage.right - 12, stage.bottom - 20), 2)
        if mascot is None:
            self.text("NO ASSET", "small", RED, center=stage.center)
            return
        if intensity <= 0.0:
            self.text(mascot.name, "small", WHITE, center=(stage.centerx, stage.centery - 10))
            self.text("OFF", "small", MUTED, center=(stage.centerx, stage.centery + 18))
            return
        target_height = max(80, min(stage.height - 18, int(stage.width * 0.95)))
        target_height = round(target_height * mascot.scale)
        base = self._mascot_surface(mascot, target_height)
        if base is None:
            self.text("LOAD ERROR", "small", RED, center=stage.center)
            return
        pulse = (0.5 + 0.5 * math.sin(now * math.tau * 1.4)) * intensity
        sway = math.sin(now * math.tau * 0.75) * intensity
        sprite = pygame.transform.rotozoom(base, sway * 1.2, 1.0 + pulse * 0.035)
        rect_sprite = sprite.get_rect(midbottom=(stage.centerx, stage.bottom - 16 - int(pulse * 8)))
        if rect_sprite.top < stage.top + 6:
            scale = (stage.height - 28) / max(1, sprite.get_height())
            sprite = pygame.transform.smoothscale(sprite, (max(1, int(sprite.get_width() * scale)), max(1, int(sprite.get_height() * scale))))
            rect_sprite = sprite.get_rect(midbottom=(stage.centerx, stage.bottom - 16 - int(pulse * 8)))
        self.surface.blit(sprite, rect_sprite)
        self.text(mascot.name, "small", WHITE, center=(rect.centerx, rect.bottom - 18))


    def _setting_display_value(self, index: int, value: str) -> tuple[str, bool]:
        if index == 2 and not self.profile.get("tutorial_completed", False):
            return "CLASSIC  LOCKED", False
        if index in {6, 7, 8} and not self.profile.get("tutorial_completed", False):
            return f"{value}  LOCKED", False
        if index in {13, 14} and not self.profile.get("tutorial_completed", False):
            return "STANDARD  LOCKED", False
        if index == 5:
            locked_count = sum(1 for lane_count in LANE_COUNT_OPTIONS if not self.is_lane_mode_unlocked(lane_count))
            if locked_count:
                return f"{value}  LOCK {locked_count}", True
        if index == 19 and self.mascot_catalog:
            unlocked_count = sum(1 for mascot in self.mascot_catalog if self.is_mascot_available(mascot.mascot_id))
            if unlocked_count < len(self.mascot_catalog):
                return f"{value}  {unlocked_count}/{len(self.mascot_catalog)}", True
        return value, True

    def _settings_unlock_hint(self) -> str:
        if self.settings_selection == 2 and not self.profile.get("tutorial_completed", False):
            return self._locked_tutorial_setting_message("効果音タイプ")
        if self.settings_selection in {6, 7, 8} and not self.profile.get("tutorial_completed", False):
            return self._locked_tutorial_setting_message("背景設定")
        if self.settings_selection == 13 and not self.profile.get("tutorial_completed", False):
            return self._locked_tutorial_setting_message("ノーツ配色")
        if self.settings_selection == 14 and not self.profile.get("tutorial_completed", False):
            return self._locked_tutorial_setting_message("ノーツデザイン")
        if self.settings_selection == 5:
            locked = [self.lane_unlock_message(lane_count) for lane_count in LANE_COUNT_OPTIONS if not self.is_lane_mode_unlocked(lane_count)]
            return " / ".join(locked[:2])
        if self.settings_selection == 19 and self.mascot_catalog:
            locked = [mascot for mascot in self.mascot_catalog if not self.is_mascot_available(mascot.mascot_id)]
            if locked:
                mascot = min(locked, key=lambda item: self.mascot_unlock_requirement(item.mascot_id))
                return f"LOCKED: {mascot.name} はBEAT SHOPで購入できます"
        return ""

    def _settings_rows(self) -> list[tuple[str, str]]:
        windows = self.settings["judgment_windows_ms"]
        mascot = self.selected_mascot
        mascot_name = mascot.name if mascot else "NO ASSET"
        return [
            ("音楽音量", f"{self.settings['music_volume'] * 100:.0f}%"),
            ("効果音音量", f"{self.settings['sfx_volume'] * 100:.0f}%"),
            ("効果音タイプ", self.sfx_theme_label),
            ("ノーツ速度", f"{self.settings['note_speed']:.0f}"),
            ("プレイ表示", self.playfield_mode_label),
            ("レーン数", self.lane_count_label),
            ("背景モード", self.background_mode_label),
            ("背景画像", self.background_image_label()),
            ("背景透明度", f"{self.background_opacity * 100:.0f}%"),
            ("Timing Offset", f"{self.settings['timing_offset_ms']} ms"),
            ("判定幅 PERFECT", f"{windows['perfect']} ms"),
            ("判定幅 GREAT", f"{windows['great']} ms"),
            ("判定幅 GOOD", f"{windows['good']} ms"),
            ("ノーツ配色", self.note_theme_label),
            ("ノーツデザイン", self.note_skin_label),
            ("フルスクリーン", "ON" if self.settings["fullscreen"] else "OFF"),
            ("解像度", f"{self.settings['resolution'][0]} x {self.settings['resolution'][1]}"),
            ("入力タイミング測定", "ENTER"),
            ("マスコット演出", self.mascot_mode_label),
            ("マスコット", mascot_name),
            ("レーン視点", self.lane_view_label),
            ("描画品質", "軽量" if self.low_graphics_quality else "標準"),
        ]

    def _setting_row_has_choices(self, index: int) -> bool:
        if index in {2, 4, 5, 6, 8, 13, 14, 15, 16, 18, 20, 21}:
            return True
        if index == 7:
            return bool(self.packaged_background_files() or self.settings.get("background_image"))
        if index == 19:
            return len(self.mascot_catalog) > 1
        return False

    def draw_settings(self) -> None:
        width, height = self.size
        compact = width < 1120 or height < 650
        self.heading("SETTINGS", "↑↓で項目選択、←→で変更。背景画像は Enter で選択")
        rows = self._settings_rows()
        if compact:
            panel = pygame.Rect(40, 120, width - 80, max(300, height - 180))
            self.panel(panel)
            column_gap = 18
            column_width = (panel.width - 40 - column_gap) // 2
            rows_per_column = math.ceil(len(rows) / 2)
            row_step = 28 if height < 680 else 30
            for index, (name, value) in enumerate(rows):
                column = index // rows_per_column
                row_index = index % rows_per_column
                x = panel.left + 20 + column * (column_width + column_gap)
                y = panel.top + 14 + row_index * row_step
                rect = pygame.Rect(x, y, column_width, 24)
                selected = index == self.settings_selection
                value, available = self._setting_display_value(index, value)
                if selected:
                    self.panel(rect, (44, 61, 92), 6)
                    pygame.draw.rect(self.surface, CYAN, rect, width=1, border_radius=6)
                self.text(name, "small", pos=(rect.left + 10, rect.top + 3))
                value_x = rect.left + max(145, rect.width // 2 - 6)
                value_color = (CYAN if selected else WHITE) if available else MUTED
                if self._setting_row_has_choices(index):
                    self.text("◁", "small", MUTED if selected else (82, 101, 135), pos=(value_x - 24, rect.top + 3))
                    self.text(value, "small", value_color, pos=(value_x, rect.top + 3))
                    right_x = min(rect.right - 22, value_x + max(56, self.fonts["small"].size(value)[0] + 12))
                    self.text("▷", "small", MUTED if selected else (82, 101, 135), pos=(right_x, rect.top + 3))
                else:
                    self.text(value, "small", value_color, pos=(value_x, rect.top + 3))
                self.buttons.append((rect, lambda selected_index=index: setattr(self, "settings_selection", selected_index)))
            key_y = panel.top + 14 + rows_per_column * row_step + 18
            self.text("KEY CONFIG", "small", YELLOW, pos=(panel.left + 20, key_y))
            active_keys = self.active_lane_keys
            active_names = self.active_lane_names
            key_gap = 8
            key_width = max(72, min(150, (panel.width - 40 - key_gap * (len(active_keys) - 1)) // len(active_keys)))
            for lane, name in enumerate(active_names):
                x = panel.left + 20 + lane * (key_width + key_gap)
                rect = pygame.Rect(x, key_y + 27, key_width, 28)
                self.panel(rect, (52, 46, 73) if self.key_capture_lane == lane else PANEL_DARK, 8)
                self.text(f"{name}: {active_keys[lane].upper()}", "small", center=rect.center)
                self.buttons.append((rect, lambda selected=lane: setattr(self, "key_capture_lane", selected)))
            hint = self._settings_unlock_hint()
            if hint:
                self.text(hint, "small", YELLOW, center=(width // 2, height - 92))
            self.button("設定を保存", pygame.Rect(width // 2 - 155, height - 54, 310, 36), self.persist_settings, accent=GREEN)
        else:
            panel = pygame.Rect(width // 2 - 390, 125, 780, 545)
            self.panel(panel)
            rows_per_column = math.ceil(len(rows) / 2)
            column_gap = 24
            column_width = (720 - column_gap) // 2
            row_step = 31
            for index, (name, value) in enumerate(rows):
                column = index // rows_per_column
                row_index = index % rows_per_column
                x = width // 2 - 360 + column * (column_width + column_gap)
                y = 138 + row_index * row_step
                rect = pygame.Rect(x, y, column_width, 25)
                selected = index == self.settings_selection
                value, available = self._setting_display_value(index, value)
                if selected:
                    self.panel(rect, (44, 61, 92), 6)
                    pygame.draw.rect(self.surface, CYAN, rect, width=1, border_radius=6)
                self.text(name, "small", pos=(rect.left + 12, rect.top + 3))
                value_color = (CYAN if selected else WHITE) if available else MUTED
                value_x = rect.left + 178
                if self._setting_row_has_choices(index):
                    self.text("◁", "small", MUTED if selected else (82, 101, 135), pos=(value_x - 24, rect.top + 3))
                    self.text(value, "small", value_color, pos=(value_x, rect.top + 3))
                    right_x = min(rect.right - 20, value_x + max(58, self.fonts["small"].size(value)[0] + 13))
                    self.text("▷", "small", MUTED if selected else (82, 101, 135), pos=(right_x, rect.top + 3))
                else:
                    self.text(value, "small", value_color, pos=(value_x, rect.top + 3))
                self.buttons.append((rect, lambda selected_index=index: setattr(self, "settings_selection", selected_index)))
            key_y = 138 + rows_per_column * row_step + 28
            self.text("KEY CONFIG", "small", YELLOW, pos=(width // 2 - 360, key_y))
            active_keys = self.active_lane_keys
            active_names = self.active_lane_names
            key_gap = 8
            key_width = max(82, min(150, (720 - key_gap * (len(active_keys) - 1)) // len(active_keys)))
            start_x = width // 2 - (key_width * len(active_keys) + key_gap * (len(active_keys) - 1)) // 2
            for lane, name in enumerate(active_names):
                x = start_x + lane * (key_width + key_gap)
                rect = pygame.Rect(x, key_y + 26, key_width, 29)
                self.panel(rect, (52, 46, 73) if self.key_capture_lane == lane else PANEL_DARK, 8)
                self.text(f"{name}: {active_keys[lane].upper()}", "small", center=rect.center)
                self.buttons.append((rect, lambda selected=lane: setattr(self, "key_capture_lane", selected)))
            preview_space = width - (width // 2 + 390) - 35
            preview_width = min(230, preview_space)
            if preview_width >= 180:
                preview_rect = pygame.Rect(width - preview_width - 25, 180, preview_width, 330)
                if self.settings_selection in {13, 14}:
                    self._draw_note_preview_panel(preview_rect, time.perf_counter())
                else:
                    self._draw_settings_mascot_preview(preview_rect, time.perf_counter())
            hint = self._settings_unlock_hint()
            if hint:
                self.text(hint, "small", YELLOW, center=(width // 2, 604))
            self.button("設定を保存", pygame.Rect(width // 2 - 175, 625, 350, 38), self.persist_settings, accent=GREEN)
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
        self.display_surface = pygame.display.set_mode((int(width), int(height)), flags)
        self.surface = self._create_render_surface((int(width), int(height)))

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
            if not self.profile.get("tutorial_completed", False):
                self.message = self._locked_tutorial_setting_message("効果音タイプ")
                return
            themes = list(SFX_THEMES)
            current_theme = self.sfx_theme_key
            current_index = themes.index(current_theme)
            self.settings["sfx_theme"] = themes[(current_index + direction) % len(themes)]
            self._rebuild_feedback_sounds()
            self.preview_sfx_theme()
        elif index == 3:
            self.settings["note_speed"] = max(250, min(1200, float(self.settings["note_speed"]) + 25 * direction))
        elif index == 4:
            modes = list(PLAYFIELD_MODES)
            current_mode = self.playfield_mode_key
            current_index = modes.index(current_mode)
            self.settings["playfield_mode"] = modes[(current_index + direction) % len(modes)]
        elif index == 5:
            current_index = LANE_COUNT_OPTIONS.index(self.active_lane_count)
            candidate = LANE_COUNT_OPTIONS[(current_index + direction) % len(LANE_COUNT_OPTIONS)]
            if not self.is_lane_mode_unlocked(candidate):
                self.message = self.lane_unlock_message(candidate)
                return
            self.settings["lane_count"] = candidate
            self.key_capture_lane = None
            self._normalize_lane_runtime_settings()
        elif index == 6:
            if not self.profile.get("tutorial_completed", False):
                self.message = self._locked_tutorial_setting_message("背景設定")
                return
            modes = list(BACKGROUND_MODES)
            current_mode = self.background_mode_key
            current_index = modes.index(current_mode)
            self.settings["background_mode"] = modes[(current_index + direction) % len(modes)]
        elif index == 7:
            if not self.profile.get("tutorial_completed", False):
                self.message = self._locked_tutorial_setting_message("背景画像")
                return
            self.cycle_background_image(direction)
        elif index == 8:
            if not self.profile.get("tutorial_completed", False):
                self.message = self._locked_tutorial_setting_message("背景透明度")
                return
            self.settings["background_opacity"] = max(0.05, min(0.65, round(self.background_opacity + 0.05 * direction, 2)))
        elif index == 9:
            self.settings["timing_offset_ms"] = max(-200, min(200, int(self.settings["timing_offset_ms"]) + 5 * direction))
        elif index == 10:
            windows["perfect"] = max(15, min(windows["great"] - 5, int(windows["perfect"]) + 5 * direction))
        elif index == 11:
            windows["great"] = max(windows["perfect"] + 5, min(windows["good"] - 5, int(windows["great"]) + 5 * direction))
        elif index == 12:
            windows["good"] = max(windows["great"] + 5, min(250, int(windows["good"]) + 5 * direction))
        elif index == 13:
            if not self.profile.get("tutorial_completed", False):
                self.message = self._locked_tutorial_setting_message("ノーツ配色")
                return
            themes = list(NOTE_THEMES)
            current_theme = self.note_theme_key
            current_index = themes.index(current_theme)
            self.settings["note_theme"] = themes[(current_index + direction) % len(themes)]
        elif index == 14:
            if not self.profile.get("tutorial_completed", False):
                self.message = self._locked_tutorial_setting_message("ノーツデザイン")
                return
            skins = list(NOTE_SKINS)
            current_skin = self.note_skin_key
            current_index = skins.index(current_skin)
            self.settings["note_skin"] = skins[(current_index + direction) % len(skins)]
        elif index == 15:
            self.settings["fullscreen"] = not self.settings["fullscreen"]
            self._apply_display_settings()
        elif index == 16:
            current = tuple(self.settings["resolution"])
            try:
                resolution_index = RESOLUTION_PRESETS.index(current)
            except ValueError:
                resolution_index = 0
            resolution_index = (resolution_index + direction) % len(RESOLUTION_PRESETS)
            self.settings["resolution"] = list(RESOLUTION_PRESETS[resolution_index])
            if not self.settings["fullscreen"]:
                self._apply_display_settings()
        elif index == 18:
            modes = list(MASCOT_MODES)
            current_mode = self.mascot_mode_key
            current_index = modes.index(current_mode)
            self.settings["mascot_mode"] = modes[(current_index + direction) % len(modes)]
        elif index == 19 and self.mascot_catalog:
            mascot_ids = [mascot.mascot_id for mascot in self.mascot_catalog]
            selected = self.selected_mascot or self.mascot_catalog[0]
            current_index = mascot_ids.index(selected.mascot_id)
            candidate = mascot_ids[(current_index + direction) % len(mascot_ids)]
            if not self.is_mascot_available(candidate):
                self.message = f"{candidate.upper()} はBEAT SHOPで購入できます。"
                return
            self.settings["mascot_id"] = candidate
        elif index == 20:
            modes = list(LANE_VIEW_MODES)
            current_view = self.lane_view_key
            current_index = modes.index(current_view)
            self.settings["lane_view"] = modes[(current_index + direction) % len(modes)]
        elif index == 21:
            self.settings["graphics_quality"] = "standard" if self.low_graphics_quality else "low"
        self.message = "設定を変更しました。保存してください。"

    def persist_settings(self) -> None:
        try:
            save_settings(self.paths, self.settings)
            self.message = "設定を保存しました。"
            self.error = ""
        except ValueError as error:
            self.error = str(error)

    def exit_app(self) -> None:
        pygame.mouse.set_visible(True)
        self.audio.stop()
        self.running = False

    def set_screen(self, screen: str) -> None:
        if screen != "game":
            self._reset_lane_input_state()
        self.screen = screen
        self.error = ""
        self.key_capture_lane = None

    def draw_overlay(self) -> None:
        width, _ = self.size
        if self.screen == "select":
            message = self.error or self.message
            if message:
                self.text(self._playlist_label(message, "small", width - 100), "small", RED if self.error else GREEN, center=(width // 2, self.size[1] - 94))
            return
        if self.message:
            self.text(self.message, "small", GREEN, center=(width // 2, 125))
        if self.error:
            self.panel(pygame.Rect(width // 2 - 430, 124, 860, 44), (82, 31, 43), 8)
            self.text(self.error, "small", RED, center=(width // 2, 146))

    def _update_mouse_cursor(self, *, moved: bool = False) -> None:
        active = self.screen == "game" and self.session is not None and not self.game_paused and getattr(self, "_cursor_window_focused", True)
        session = self.session if active else None
        if session is not getattr(self, "_cursor_game_session", None):
            self._cursor_game_session = session
            self._cursor_visible_until = 0.0
        now = time.perf_counter()
        if active and moved:
            self._cursor_visible_until = now + 2.0
        visible = not active or now < getattr(self, "_cursor_visible_until", 0.0)
        if pygame.mouse.get_visible() != visible:
            pygame.mouse.set_visible(visible)

    def draw(self) -> None:
        if self.screen != "title":
            self._title_scene = None
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
            "practice_setup": self.draw_practice_setup,
            "practice_result": self.draw_practice_result,
            "trial_result": self.draw_trial_result,
            "ranking": self.draw_ranking,
            "game": self.draw_game,
            "result": self.draw_result,
            "unlock": self.draw_unlock,
            "gallery": self.draw_gallery,
            "shop": self.draw_shop,
            "reward_manager": self.draw_reward_manager,
            "gallery_preview": self.draw_gallery_preview,
            "settings": self.draw_settings,
            "calibration": self.draw_calibration,
        }[self.screen]()
        if self.screen not in {"title", "game", "calibration"}:
            self.draw_overlay()
        self._update_mouse_cursor()
        self._present()

    def key_event(self, event: pygame.event.Event) -> None:
        key = pygame.key.name(event.key).lower()
        game_lane: int | None = None
        lane_was_down = False
        if self.screen == "game" and self.session:
            game_lane = self._lane_from_key_name(key)
            if game_lane is not None:
                lane_was_down = game_lane in self._lane_keys_down
                self._lane_keys_down.add(game_lane)
        if self.key_capture_lane is not None:
            active_keys = self.active_lane_keys
            if key in active_keys:
                self.error = "同じキーを複数レーンには割り当てられません。"
            elif key not in {"escape", "return"}:
                active_keys[self.key_capture_lane] = key
                self.settings["lane_keys"][str(self.active_lane_count)] = active_keys
                if self.active_lane_count == 5:
                    self.settings["keys"] = list(active_keys)
                self.key_capture_lane = None
                self.message = "キーを変更しました。保存してください。"
            return
        if self.screen == "title":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.open_playlist("normal")
            elif event.key == pygame.K_p:
                self.open_playlist("practice")
            elif event.key == pygame.K_t:
                self.set_screen("tutorial")
            elif event.key == pygame.K_g:
                self.set_screen("gallery")
            elif event.key == pygame.K_b:
                self.open_shop()
            elif event.key == pygame.K_s:
                self.set_screen("settings")
        elif self.screen == "select":
            if event.key == pygame.K_UP:
                self.move_playlist_selection(-1)
            elif event.key == pygame.K_DOWN:
                self.move_playlist_selection(1)
            elif event.key == pygame.K_PAGEUP:
                self.move_playlist_selection(-self._playlist_visible_rows())
            elif event.key == pygame.K_PAGEDOWN:
                self.move_playlist_selection(self._playlist_visible_rows())
            elif event.key == pygame.K_HOME:
                self.playlist_selected_index = 0
                self._clamp_playlist_position()
            elif event.key == pygame.K_END:
                self.playlist_selected_index = max(0, len(self.playlist_entries()) - 1)
                self._clamp_playlist_position()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_current_playlist_entry()
            elif event.key == pygame.K_i:
                self.choose_file()
            elif event.key == pygame.K_TAB or event.key == pygame.K_RIGHT:
                self.cycle_library_folder(1)
            elif event.key == pygame.K_LEFT:
                self.cycle_library_folder(-1)
            elif event.key == pygame.K_n:
                self.create_library_folder()
            elif event.key == pygame.K_m:
                self.move_selected_playlist_song_to_current_folder()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("title")
        elif self.screen == "library":
            if event.key == pygame.K_UP:
                self.move_library_selection(-1)
            elif event.key == pygame.K_DOWN:
                self.move_library_selection(1)
            elif event.key == pygame.K_PAGEUP:
                self.move_library_selection(-self._library_visible_rows())
            elif event.key == pygame.K_PAGEDOWN:
                self.move_library_selection(self._library_visible_rows())
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
                if self.chart and self.chart.metadata.get("tutorial_optional"):
                    self.retry_game()
                elif self.tutorial_step_index == len(self.current_tutorial_steps()) - 1:
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
        elif self.screen == "practice_setup":
            step = 1.0 if event.mod & pygame.KMOD_SHIFT else 0.1
            if event.key == pygame.K_LEFT:
                self.adjust_practice_boundary("start", -step)
            elif event.key == pygame.K_RIGHT:
                self.adjust_practice_boundary("start", step)
            elif event.key == pygame.K_a:
                self.adjust_practice_boundary("end", -step)
            elif event.key == pygame.K_d:
                self.adjust_practice_boundary("end", step)
            elif event.key == pygame.K_l:
                self.practice_loop = not self.practice_loop
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_practice()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("select")
        elif self.screen == "practice_result":
            if event.key == pygame.K_r:
                self.start_practice()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self.set_screen("practice_setup")
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("title")
        elif self.screen == "trial_result":
            if event.key == pygame.K_ESCAPE:
                self.return_to_song_select()
        elif self.screen == "chart_summary":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_game()
            elif event.key == pygame.K_r:
                self.regenerate_chart()
            elif event.key == pygame.K_LEFT and self.chart_candidates:
                self.move_chart_candidate(-1)
            elif event.key == pygame.K_RIGHT and self.chart_candidates:
                self.move_chart_candidate(1)
            elif event.key == pygame.K_a and self.chart_is_pending:
                self.adopt_pending_chart()
            elif event.key == pygame.K_d and self.chart_is_pending:
                self.discard_pending_chart()
            elif event.key == pygame.K_l and not self.chart_is_pending:
                self.open_ranking()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("difficulty")
        elif self.screen == "ranking":
            if event.key == pygame.K_LEFT:
                self.move_ranking_lane_count(-1)
            elif event.key == pygame.K_RIGHT:
                self.move_ranking_lane_count(1)
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("chart_summary")
        elif self.screen == "result" and self.chart_is_pending:
            if event.key == pygame.K_a:
                self.adopt_pending_chart()
            elif event.key == pygame.K_d:
                self.discard_pending_chart()
            elif event.key == pygame.K_s:
                self.save_result_screenshot()
        elif self.screen == "result":
            if event.key in (pygame.K_RETURN, pygame.K_r):
                self.start_game()
            elif event.key == pygame.K_d:
                self.return_to_difficulty()
            elif event.key == pygame.K_l:
                self.open_ranking()
            elif event.key == pygame.K_g:
                self.set_screen("gallery")
            elif event.key == pygame.K_s:
                self.save_result_screenshot()
            elif event.key == pygame.K_ESCAPE:
                self.return_to_song_select()
        elif self.screen == "settings":
            if event.key == pygame.K_UP:
                self.settings_selection = (self.settings_selection - 1) % len(self._settings_rows())
            elif event.key == pygame.K_DOWN:
                self.settings_selection = (self.settings_selection + 1) % len(self._settings_rows())
            elif event.key == pygame.K_LEFT:
                self.adjust_setting(-1)
            elif event.key == pygame.K_RIGHT:
                self.adjust_setting(1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.settings_selection == 7:
                if not self.profile.get("tutorial_completed", False):
                    self.message = self._locked_tutorial_setting_message("背景画像")
                else:
                    self.choose_background_file()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.settings_selection in (2, 4, 5, 6, 13, 14, 15, 16, 18, 19, 20):
                self.adjust_setting(1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.settings_selection == 17:
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
            elif event.key == pygame.K_m:
                self.open_reward_manager()
            elif event.key == pygame.K_b:
                self.open_shop()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("title")
        elif self.screen == "shop":
            if event.key == pygame.K_UP:
                self.move_shop_selection(-1)
            elif event.key == pygame.K_DOWN:
                self.move_shop_selection(1)
            elif event.key == pygame.K_PAGEUP:
                self.move_shop_selection(-SHOP_VISIBLE_ROWS)
            elif event.key == pygame.K_PAGEDOWN:
                self.move_shop_selection(SHOP_VISIBLE_ROWS)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.activate_shop_purchase()
            elif event.key == pygame.K_ESCAPE:
                self.shop_confirmation_id = None
                self.set_screen("title")
        elif self.screen == "reward_manager":
            if event.key == pygame.K_UP:
                self.move_reward_manager_selection(-1)
            elif event.key == pygame.K_DOWN:
                self.move_reward_manager_selection(1)
            elif event.key == pygame.K_PAGEUP:
                self.move_reward_manager_selection(-self._reward_manager_visible_rows())
            elif event.key == pygame.K_PAGEDOWN:
                self.move_reward_manager_selection(self._reward_manager_visible_rows())
            elif event.key == pygame.K_HOME:
                self.reward_manager_selected_index = 0
                self._clamp_reward_manager_position()
            elif event.key == pygame.K_END:
                self.reward_manager_selected_index = max(0, len(self.reward_manager_entries()) - 1)
                self._clamp_reward_manager_position()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.select_reward_manager_entry(self.reward_manager_selected_index)
            elif event.key == pygame.K_f:
                self.show_reward_folder()
            elif event.key == pygame.K_c:
                self.show_reward_config()
            elif event.key == pygame.K_ESCAPE:
                self.set_screen("gallery")
        elif self.screen == "gallery_preview":
            if event.key == pygame.K_ESCAPE:
                self.set_screen("gallery")
        elif self.screen == "game":
            if self.countdown_active:
                if event.key == pygame.K_ESCAPE:
                    self.return_to_practice_setup() if self.practice_active else self.return_to_song_select()
                return
            if self.game_paused:
                if event.key == pygame.K_ESCAPE:
                    self.toggle_pause()
                elif event.key == pygame.K_r:
                    self.retry_game()
                elif event.key == pygame.K_q:
                    self.return_to_practice_setup() if self.practice_active else self.return_to_song_select()
            elif event.key == pygame.K_ESCAPE:
                self.toggle_pause()
            else:
                if self.practice_active and event.key == pygame.K_l:
                    self.practice_loop = not self.practice_loop
                    self.message = f"ループを{'ON' if self.practice_loop else 'OFF'}にしました。"
                    return
                if self.practice_active and event.key == pygame.K_q:
                    self.return_to_practice_setup()
                    return
                lane = game_lane
                if lane is None:
                    return
                if lane_was_down or lane in self._resume_blocked_lanes:
                    return
                self._play_feedback(self._press_active_lane(lane, self.gameplay_time()), lane)
        elif event.key == pygame.K_ESCAPE:
            self.set_screen("title")

    def key_up_event(self, event: pygame.event.Event) -> None:
        if self.screen != "game" or not self.session:
            return
        key = pygame.key.name(event.key).lower()
        lane = self._lane_from_key_name(key)
        if lane is None:
            return
        self._lane_keys_down.discard(lane)
        if lane in self._resume_blocked_lanes:
            self._resume_blocked_lanes.discard(lane)
            for source_lane in self.active_to_source_lanes(lane):
                self.session.held_lanes.discard(source_lane)
            return
        if self.game_paused:
            for source_lane in self.active_to_source_lanes(lane):
                self.session.held_lanes.discard(source_lane)
            return
        self._play_feedback(self._release_active_lane(lane, self.gameplay_time()), lane)

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
                self.screen = "tutorial" if self.tutorial_active else ("practice_setup" if self.practice_active else "difficulty")
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
        if self.trial_active:
            limit_hits_mid_song = self.analysis is not None and float(self.analysis.duration) > TRIAL_PLAY_LIMIT_SECONDS
            if limit_hits_mid_song and current_time >= self.trial_end_time - TRIAL_FADE_SECONDS:
                fade_remaining = max(0.0, self.trial_end_time - current_time)
                fade_ratio = min(1.0, fade_remaining / TRIAL_FADE_SECONDS)
                self.audio.set_volume(float(self.settings["music_volume"]) * fade_ratio)
                self.trial_fade_started = True
            if current_time >= self.trial_end_time - 0.01:
                self.audio.stop()
                self.finish_game()
                return
        if self.practice_active and current_time >= self.practice_end - 0.01:
            self.audio.stop()
            if self.practice_loop:
                self.practice_round += 1
                self.start_practice(countdown=False)
            else:
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
                elif event.type == pygame.WINDOWFOCUSLOST:
                    self._cursor_window_focused = False
                    self._handle_game_focus_lost()
                    self._update_mouse_cursor()
                elif event.type == pygame.WINDOWFOCUSGAINED:
                    self._cursor_window_focused = True
                elif event.type == pygame.MOUSEMOTION:
                    if event.rel != (0, 0):
                        self._update_mouse_cursor(moved=True)
                elif event.type == pygame.MOUSEWHEEL and self.screen == "select":
                    self.scroll_playlist(-event.y)
                elif event.type == pygame.MOUSEWHEEL and self.screen == "library":
                    self.scroll_library(-event.y)
                elif event.type == pygame.MOUSEWHEEL and self.screen == "reward_manager":
                    self.scroll_reward_manager(-event.y)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    for rect, action in self.buttons:
                        if rect.collidepoint(self._to_logical_point(event.pos)):
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
        pygame.mouse.set_visible(True)
        self.persist_settings()
        pygame.quit()


def main() -> None:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    AutoBeatApp().run()


if __name__ == "__main__":
    main()
