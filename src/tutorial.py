"""音源を必要としない、メトロノーム型チュートリアル用の固定譜面。"""
from __future__ import annotations

from dataclasses import dataclass

from models import Chart, Difficulty, Note, NoteType, normalize_lane_count

TUTORIAL_BPM = 120.0
TUTORIAL_BEAT_SECONDS = 60.0 / TUTORIAL_BPM


@dataclass(frozen=True, slots=True)
class TutorialStep:
    """一つの操作だけに焦点を当てた、短いチュートリアル課題。"""

    key: str
    title: str
    instruction: str
    notes: tuple[Note, ...]
    duration: float


def _tap(time: float, lane: int) -> Note:
    return Note(time=time, lane=lane, kind=NoteType.TAP, source="tutorial", strength=1.0)


def _hold(time: float, lane: int, end_time: float) -> Note:
    return Note(time=time, lane=lane, kind=NoteType.HOLD, end_time=end_time, source="tutorial", strength=1.0)


def tutorial_steps(lane_count: int = 5) -> tuple[TutorialStep, ...]:
    lane_count = normalize_lane_count(lane_count)
    center = lane_count // 2
    if lane_count == 3:
        return (
            TutorialStep(
                key="center-3lane",
                title="STEP 1 / 5  3レーン中央",
                instruction="クリック音に合わせて SPACE を4回押しましょう。",
                notes=(_tap(2.0, center), _tap(2.5, center), _tap(3.0, center), _tap(3.5, center)),
                duration=5.0,
            ),
            TutorialStep(
                key="lanes-3lane",
                title="STEP 2 / 5  3レーン",
                instruction="D・SPACE・K を順番に押しましょう。",
                notes=(_tap(2.0, 0), _tap(2.5, 1), _tap(3.0, 2), _tap(3.5, 1), _tap(4.0, 0), _tap(4.5, 1), _tap(5.0, 2)),
                duration=6.5,
            ),
            TutorialStep(
                key="chord-3lane",
                title="STEP 3 / 5  同時押し",
                instruction="線でつながる2つのノーツは、D と K を同時に押しましょう。",
                notes=tuple(_tap(time, lane) for time in (2.0, 3.0, 4.0, 5.0) for lane in (0, 2)),
                duration=6.5,
            ),
            TutorialStep(
                key="hold-3lane",
                title="STEP 4 / 5  3レーン長押し",
                instruction="D を押したまま、終端キャップで離しましょう。",
                notes=(_hold(2.0, 0, 4.0), _tap(5.0, 2), _tap(5.5, 1)),
                duration=7.0,
            ),
            TutorialStep(
                key="practice-3lane",
                title="STEP 5 / 5  3レーン練習",
                instruction="少ないレーンで、基本リズムを落ち着いて叩きましょう。",
                notes=(_tap(2.0, 1), _tap(2.5, 0), _tap(3.0, 2), _tap(3.5, 1), _tap(4.0, 0), _tap(4.5, 2), _tap(5.0, 1), _tap(5.5, 0), _tap(6.0, 2)),
                duration=8.0,
            ),
        )
    if lane_count == 7:
        return (
            TutorialStep(
                key="center-7lane",
                title="STEP 1 / 5  7レーン中央",
                instruction="クリック音に合わせて SPACE を4回押しましょう。",
                notes=(_tap(2.0, center), _tap(2.5, center), _tap(3.0, center), _tap(3.5, center)),
                duration=5.0,
            ),
            TutorialStep(
                key="lanes-7lane",
                title="STEP 2 / 5  7レーン",
                instruction="S・D・F・SPACE・J・K・L を順番に押しましょう。",
                notes=(_tap(2.0, 0), _tap(2.45, 1), _tap(2.9, 2), _tap(3.35, 3), _tap(3.8, 4), _tap(4.25, 5), _tap(4.7, 6), _tap(5.15, 5), _tap(5.6, 4), _tap(6.05, 3)),
                duration=7.5,
            ),
            TutorialStep(
                key="chord-7lane",
                title="STEP 3 / 5  同時押し",
                instruction="線でつながる2つのノーツは、F と J を同時に押しましょう。",
                notes=tuple(_tap(time, lane) for time in (2.0, 3.0, 4.0, 5.0) for lane in (2, 4)),
                duration=6.5,
            ),
            TutorialStep(
                key="hold-7lane",
                title="STEP 4 / 5  7レーン長押し",
                instruction="D を押したまま、反対側の J を叩いてみましょう。",
                notes=(_hold(2.0, 1, 4.0), _tap(3.0, 4), _tap(5.0, 6), _tap(5.5, 3)),
                duration=7.0,
            ),
            TutorialStep(
                key="practice-7lane",
                title="STEP 5 / 5  7レーン練習",
                instruction="広いレーンを目で追いながら、左右に流れるノーツを叩きましょう。",
                notes=(_tap(2.0, 3), _tap(2.45, 2), _tap(2.9, 4), _tap(3.35, 1), _tap(3.8, 5), _tap(4.25, 0), _tap(4.7, 6), _tap(5.15, 3), _tap(5.6, 2), _tap(6.05, 4), _tap(6.5, 3)),
                duration=8.5,
            ),
        )
    return (
        TutorialStep(
            key="center",
            title="STEP 1 / 5  中央レーン",
            instruction="クリック音に合わせて SPACE を4回押しましょう。",
            notes=(_tap(2.0, 2), _tap(2.5, 2), _tap(3.0, 2), _tap(3.5, 2)),
            duration=5.0,
        ),
        TutorialStep(
            key="lanes",
            title="STEP 2 / 5  5レーン",
            instruction="D・F・SPACE・J・K を順番に押しましょう。",
            notes=(_tap(2.0, 0), _tap(2.5, 1), _tap(3.0, 2), _tap(3.5, 3), _tap(4.0, 4), _tap(4.5, 3), _tap(5.0, 2), _tap(5.5, 1), _tap(6.0, 0)),
            duration=7.5,
        ),
        TutorialStep(
            key="chord",
            title="STEP 3 / 5  同時押し",
            instruction="線でつながる2つのノーツは、F と J を同時に押しましょう。",
            notes=tuple(_tap(time, lane) for time in (2.0, 3.0, 4.0, 5.0) for lane in (1, 3)),
            duration=6.5,
        ),
        TutorialStep(
            key="hold",
            title="STEP 4 / 5  長押しノーツ",
            instruction="F を押したまま、終端キャップで離しましょう。",
            notes=(_hold(2.0, 1, 4.0), _tap(5.0, 3), _tap(5.5, 2)),
            duration=7.0,
        ),
        TutorialStep(
            key="practice",
            title="STEP 5 / 5  基本の練習",
            instruction="クリック音を聞きながら、流れてくるノーツを叩きましょう。",
            notes=(_tap(2.0, 2), _tap(2.5, 1), _tap(3.0, 3), _tap(3.5, 0), _tap(4.0, 4), _tap(4.5, 2), _tap(5.0, 1), _tap(5.5, 3), _tap(6.0, 2), _tap(6.5, 0), _tap(7.0, 4)),
            duration=8.5,
        ),
    )


TUTORIAL_STEPS: tuple[TutorialStep, ...] = tutorial_steps(5)


def optional_tutorial_steps(lane_count: int = 5) -> tuple[TutorialStep, ...]:
    lane_count = normalize_lane_count(lane_count)
    center = lane_count // 2
    left, right = center - 1, center + 1
    hold_notes = []
    for index, start in enumerate((3.0, 7.0, 11.0, 15.0)):
        held, other = (left, right) if index % 2 == 0 else (right, left)
        end = start + 1.5
        hold_notes.append(_hold(start, held, end))
        for anchor in (start, end):
            for offset, lane in ((-0.5, center), (-0.25, other),
                                 (0.25, other), (0.5, center)):
                hold_notes.append(_tap(anchor + offset, lane))
    pairs = [(0, lane_count - 1), (left, right), (left, center),
             (center, right), (0, center), (center, lane_count - 1)]
    if lane_count > 3:
        pairs.extend([(0, left), (right, lane_count - 1)])
    chords = tuple(_tap(2.0 + i * 0.5, lane)
                   for i, pair in enumerate(pairs * 3) for lane in pair)
    tap_patterns = (
        (left, right),
        tuple(range(lane_count)) + tuple(range(lane_count - 2, 0, -1)),
        (center, left, center, right),
        (left, left, right, right),
    )
    dense_taps = tuple(_tap(2.0 + (section * 16 + i) * 0.25, pattern[i % len(pattern)])
                       for section, pattern in enumerate(tap_patterns) for i in range(16))
    return (
        TutorialStep(f"optional-hold-dense-{lane_count}", "任意練習: 長押し前後の密集",
                     "長押しの開始と終了を意識して、前後の連打を叩きましょう。",
                     tuple(hold_notes), 19.0),
        TutorialStep(f"optional-chord-chain-{lane_count}", "任意練習: 連続同時押し",
                     "線でつながるノーツを同時に押し、次の組み合わせに備えましょう。",
                     chords, chords[-1].time + 2.0),
        TutorialStep(f"optional-tap-dense-{lane_count}", "任意練習: 単発ノーツの密集",
                     "左右交互・階段・中央との交互・2連打を、一定のリズムで叩きましょう。",
                     dense_taps, dense_taps[-1].time + 2.0),
    )


def build_tutorial_chart(step_index: int, lane_count: int = 5) -> Chart:
    """指定した課題を通常のGameSessionで扱える固定譜面へ変換する。"""
    basic_steps = tutorial_steps(lane_count)
    steps = basic_steps + optional_tutorial_steps(lane_count)
    lane_count = normalize_lane_count(lane_count)
    if not 0 <= step_index < len(steps):
        raise IndexError(f"tutorial step out of range: {step_index}")
    step = steps[step_index]
    chart = Chart(
        version=1,
        music_hash=f"tutorial:{step.key}",
        difficulty=Difficulty.BEGINNER,
        seed=step_index,
        song_duration=step.duration,
        notes=[Note.from_dict(note.to_dict()) for note in step.notes],
        generator_version="tutorial-1.0",
        metadata={
            "tutorial": True,
            "tutorial_optional": step_index >= len(basic_steps),
            "tutorial_step": step_index,
            "tutorial_title": step.title,
            "tutorial_instruction": step.instruction,
            "lane_count": lane_count,
            "lane_mode": f"{lane_count}lane",
            "bpm": TUTORIAL_BPM,
        },
    )
    chart.sort()
    return chart
