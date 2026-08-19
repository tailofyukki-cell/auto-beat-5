"""AutoBeat 5のTiming Offsetキャリブレーションロジック。"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median


@dataclass(slots=True)
class CalibrationSession:
    """一定間隔のクリックに対する入力遅延をロバストに推定する。"""

    started_at: float
    interval_seconds: float = 0.5
    warmup_beats: int = 2
    sample_target: int = 10
    max_offset_ms: int = 200
    offsets_ms: list[float] = field(default_factory=list)
    emitted_beat: int = -1
    last_recorded_beat: int = -1

    def due_clicks(self, now: float) -> list[int]:
        """前回更新以降に鳴らすべきクリック番号を返す。"""
        if now < self.started_at:
            return []
        latest = int((now - self.started_at) // self.interval_seconds)
        clicks = list(range(self.emitted_beat + 1, latest + 1))
        if clicks:
            self.emitted_beat = latest
        return clicks

    def beat_time(self, beat_index: int) -> float:
        return self.started_at + beat_index * self.interval_seconds

    def record_press(self, now: float) -> float | None:
        """SPACE入力を最も近いクリックに対応付け、ウォームアップ後の偏差を保存する。"""
        beat_index = int(round((now - self.started_at) / self.interval_seconds))
        if beat_index < self.warmup_beats:
            return None
        offset_ms = (now - self.beat_time(beat_index)) * 1000.0
        if abs(offset_ms) > self.max_offset_ms:
            return None
        if beat_index <= self.last_recorded_beat:
            return None
        self.last_recorded_beat = beat_index
        self.offsets_ms.append(offset_ms)
        return offset_ms

    @property
    def complete(self) -> bool:
        return len(self.offsets_ms) >= self.sample_target

    @property
    def recommendation_ms(self) -> int | None:
        """外れ値に強い中央値を、ゲーム側で使う範囲へ丸めて返す。"""
        if len(self.offsets_ms) < max(3, self.sample_target // 2):
            return None
        return max(-self.max_offset_ms, min(self.max_offset_ms, int(round(median(self.offsets_ms)))))

    @property
    def latest_offset_ms(self) -> int | None:
        return int(round(self.offsets_ms[-1])) if self.offsets_ms else None

    @property
    def remaining_samples(self) -> int:
        return max(0, self.sample_target - len(self.offsets_ms))

    def summary(self) -> str:
        recommendation = self.recommendation_ms
        if recommendation is None:
            return "入力が不足しています。"
        sign = "+" if recommendation >= 0 else ""
        return f"推奨 Timing Offset: {sign}{recommendation} ms"
