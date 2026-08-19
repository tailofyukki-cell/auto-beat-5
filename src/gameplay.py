"""音源時計の時刻差だけでノーツ判定するゲームコア。"""
from __future__ import annotations

from dataclasses import dataclass, field

from models import Chart, Judgment, Note, NoteType, PlayResult


@dataclass(frozen=True, slots=True)
class JudgmentWindows:
    perfect: float = 0.045
    great: float = 0.090
    good: float = 0.140

    @classmethod
    def from_ms(cls, raw: dict[str, object]) -> "JudgmentWindows":
        return cls(
            perfect=float(raw.get("perfect", 45)) / 1000,
            great=float(raw.get("great", 90)) / 1000,
            good=float(raw.get("good", 140)) / 1000,
        )

    def judge(self, difference: float) -> Judgment:
        absolute = abs(difference)
        if absolute <= self.perfect:
            return Judgment.PERFECT
        if absolute <= self.great:
            return Judgment.GREAT
        if absolute <= self.good:
            return Judgment.GOOD
        return Judgment.MISS


BASE_SCORE = {
    Judgment.PERFECT: 1000,
    Judgment.GREAT: 800,
    Judgment.GOOD: 500,
    Judgment.MISS: 0,
}
JUDGMENT_ORDER = {
    Judgment.PERFECT: 3,
    Judgment.GREAT: 2,
    Judgment.GOOD: 1,
    Judgment.MISS: 0,
}


@dataclass(slots=True)
class NoteState:
    note: Note
    judged: Judgment | None = None  # ノーツ単位で統合した最終判定
    start_judgment: Judgment | None = None  # 長押しSTARTの内部評価
    pressed_at: float | None = None
    released_at: float | None = None
    active_hold: bool = False

    @property
    def complete(self) -> bool:
        return self.judged is not None


@dataclass(slots=True)
class GameSession:
    chart: Chart
    windows: JudgmentWindows
    timing_offset: float = 0.0
    score: int = 0
    combo: int = 0
    max_combo: int = 0
    states: list[NoteState] = field(init=False)
    judgment_counts: dict[str, int] = field(default_factory=lambda: {judgment.value: 0 for judgment in Judgment})
    latest_judgment: Judgment | None = None
    held_lanes: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.chart.sort()
        self.states = [NoteState(note) for note in self.chart.notes]

    def _add_judgment(self, judgment: Judgment) -> None:
        """ノーツの最終判定をスコア・コンボ・リザルトへ一度だけ反映する。"""
        self.latest_judgment = judgment
        self.judgment_counts[judgment.value] += 1
        if judgment is Judgment.MISS:
            self.combo = 0
            return
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)
        combo_bonus = min(1.50, 1.0 + self.combo / 1000)
        self.score += round(BASE_SCORE[judgment] * combo_bonus)

    def _resolve(self, state: NoteState, judgment: Judgment) -> Judgment:
        if state.judged is None:
            state.judged = judgment
            state.active_hold = False
            self._add_judgment(judgment)
        return state.judged

    @staticmethod
    def _worse(left: Judgment, right: Judgment) -> Judgment:
        return left if JUDGMENT_ORDER[left] <= JUDGMENT_ORDER[right] else right

    def _nearest_unjudged(self, lane: int, time: float) -> NoteState | None:
        candidates = [
            state
            for state in self.states
            if state.note.lane == lane and state.judged is None and not state.active_hold and abs(state.note.time - time) <= self.windows.good
        ]
        return min(candidates, key=lambda state: abs(state.note.time - time), default=None)

    def press(self, lane: int, audio_time: float) -> Judgment | None:
        """キー押下時のSTART判定。長押しは終端まで内部評価を保留する。"""
        time = audio_time + self.timing_offset
        self.held_lanes.add(lane)
        state = self._nearest_unjudged(lane, time)
        if state is None:
            return None
        judgment = self.windows.judge(time - state.note.time)
        state.pressed_at = time
        self.latest_judgment = judgment
        if state.note.kind is NoteType.HOLD:
            state.start_judgment = judgment
            state.active_hold = judgment is not Judgment.MISS
            if judgment is Judgment.MISS:
                self._resolve(state, Judgment.MISS)
            return judgment
        self._resolve(state, judgment)
        return judgment

    def release(self, lane: int, audio_time: float) -> Judgment | None:
        """長押しのRELEASEを評価し、START/HOLD/RELEASEを一つの最終判定へ統合する。"""
        time = audio_time + self.timing_offset
        self.held_lanes.discard(lane)
        active = next((state for state in self.states if state.note.lane == lane and state.active_hold), None)
        if active is None:
            return None
        active.released_at = time
        end_time = active.note.end_time or active.note.time
        release_judgment = self.windows.judge(time - end_time)
        if time < end_time - self.windows.good:
            release_judgment = Judgment.MISS
        start_judgment = active.start_judgment or Judgment.MISS
        final = self._worse(start_judgment, release_judgment)
        self._resolve(active, final)
        return final

    def tick(self, audio_time: float) -> list[Judgment]:
        """未入力MISSと長押しのHOLD/終了を処理する。"""
        time = audio_time + self.timing_offset
        emitted: list[Judgment] = []
        for state in self.states:
            if state.judged is not None:
                continue
            if not state.active_hold and time > state.note.time + self.windows.good:
                self._resolve(state, Judgment.MISS)
                emitted.append(Judgment.MISS)
            elif state.active_hold:
                end_time = state.note.end_time or state.note.time
                if state.note.lane not in self.held_lanes and time < end_time - self.windows.good:
                    self._resolve(state, Judgment.MISS)
                    emitted.append(Judgment.MISS)
                elif time > end_time + self.windows.good:
                    # 終端を過ぎても押し続けている場合、START評価をそのまま最終評価へ統合する。
                    final = state.start_judgment or Judgment.MISS
                    self._resolve(state, final)
                    emitted.append(final)
        return emitted

    @property
    def finished(self) -> bool:
        return all(state.complete for state in self.states)

    def result(self) -> PlayResult:
        total = len(self.states)
        weighted = (
            self.judgment_counts[Judgment.PERFECT.value] * 1.0
            + self.judgment_counts[Judgment.GREAT.value] * 0.8
            + self.judgment_counts[Judgment.GOOD.value] * 0.5
        )
        accuracy = 0.0 if total == 0 else weighted / total * 100
        rank = "S" if accuracy >= 95 else "A" if accuracy >= 88 else "B" if accuracy >= 75 else "C" if accuracy >= 60 else "D"
        return PlayResult(
            score=self.score,
            max_combo=self.max_combo,
            judgments=dict(self.judgment_counts),
            accuracy=round(accuracy, 2),
            rank=rank,
            chart_hash=f"{self.chart.music_hash}:{self.chart.difficulty.value}",
        )
