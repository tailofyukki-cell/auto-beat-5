"""AutoBeat 5で共有する譜面・解析・判定データモデル。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Difficulty(str, Enum):
    BEGINNER = "beginner"
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    EXPERT = "expert"

    @property
    def label(self) -> str:
        return self.value.upper()


class NoteType(str, Enum):
    TAP = "tap"
    HOLD = "hold"


class Judgment(str, Enum):
    PERFECT = "PERFECT"
    GREAT = "GREAT"
    GOOD = "GOOD"
    MISS = "MISS"


@dataclass(slots=True)
class Note:
    """一つの入力イベント。長押しはend_timeを持ち、同時押しは同時刻の複数Noteで表す。"""

    time: float
    lane: int
    kind: NoteType = NoteType.TAP
    end_time: float | None = None
    source: str = "onset"
    strength: float = 0.0
    id: str = ""

    def __post_init__(self) -> None:
        if self.lane not in range(5):
            raise ValueError(f"lane must be 0..4, got {self.lane}")
        if self.time < 0:
            raise ValueError("note time must be non-negative")
        if self.kind is NoteType.HOLD:
            if self.end_time is None or self.end_time <= self.time:
                raise ValueError("hold note requires end_time later than time")
        elif self.end_time is not None:
            raise ValueError("tap note cannot have end_time")

    @property
    def duration(self) -> float:
        return 0.0 if self.end_time is None else self.end_time - self.time

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Note":
        raw = dict(data)
        raw["kind"] = NoteType(raw.get("kind", NoteType.TAP.value))
        return cls(**raw)


@dataclass(slots=True)
class Chart:
    version: int
    music_hash: str
    difficulty: Difficulty
    seed: int
    song_duration: float
    notes: list[Note] = field(default_factory=list)
    generator_version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def sort(self) -> None:
        self.notes.sort(key=lambda note: (note.time, note.lane, note.kind.value))
        for index, note in enumerate(self.notes):
            note.id = f"{index:05d}-{note.time:.4f}-{note.lane}"

    def to_dict(self) -> dict[str, Any]:
        self.sort()
        return {
            "version": self.version,
            "music_hash": self.music_hash,
            "difficulty": self.difficulty.value,
            "seed": self.seed,
            "song_duration": self.song_duration,
            "generator_version": self.generator_version,
            "metadata": self.metadata,
            "notes": [note.to_dict() for note in self.notes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Chart":
        return cls(
            version=int(data.get("version", 1)),
            music_hash=str(data["music_hash"]),
            difficulty=Difficulty(data["difficulty"]),
            seed=int(data.get("seed", 0)),
            song_duration=float(data["song_duration"]),
            generator_version=str(data.get("generator_version", "1.0")),
            metadata=dict(data.get("metadata", {})),
            notes=[Note.from_dict(note) for note in data.get("notes", [])],
        )


@dataclass(slots=True)
class AnalysisResult:
    """JSON化できる軽量な解析結果。巨大な生スペクトログラムは保存しない。"""

    music_hash: str
    source_path: str
    duration: float
    sample_rate: int
    bpm: float
    beats: list[float]
    onsets: list[float]
    onset_strengths: list[float]
    band_energy: list[list[float]]
    percussive_strengths: list[float]
    sustained_segments: list[tuple[float, float, int]]
    local_bpms: list[tuple[float, float]] = field(default_factory=list)
    downbeats: list[float] = field(default_factory=list)
    analyzer_version: str = "1.1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisResult":
        raw = dict(data)
        raw["sustained_segments"] = [tuple(segment) for segment in raw.get("sustained_segments", [])]
        raw["local_bpms"] = [tuple(segment) for segment in raw.get("local_bpms", [])]
        raw["downbeats"] = list(raw.get("downbeats", []))
        return cls(**raw)


@dataclass(slots=True)
class PlayResult:
    score: int
    max_combo: int
    judgments: dict[str, int]
    accuracy: float
    rank: str
    chart_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


LANE_NAMES = ("D", "F", "SPACE", "J", "K")
DEFAULT_KEYS = ("d", "f", "space", "j", "k")
DIFFICULTY_ORDER = tuple(Difficulty)
"""譜面と画面の表示順。Difficultyの宣言順を5段階の難易度順とする。"""
