# AutoBeat 5 Variable Lane Mode Specification

## Purpose

AutoBeat 5 currently uses a fixed 5-lane play style. Variable lane modes add a lower-stress entry point for beginners and a higher-ceiling option for advanced players while keeping the current 5-lane experience intact.

The goal is to support three lane counts:

| Mode | Target Player | Default Keys | Positioning |
| --- | --- | --- | --- |
| 3 LANE | New players, casual play, small keyboards | D / Space / K | left / center / right |
| 5 LANE | Standard AutoBeat 5 | D / F / Space / J / K | current layout |
| 7 LANE | Advanced players, challenge charts | S / D / F / Space / J / K / L | wider hand spread |

5 LANE remains the default and must remain compatible with existing generated charts and saved scores.

## Implementation Status

Phase 1 is implemented in the app layer. The settings screen can switch `3 LANE` / `5 LANE` / `7 LANE`, each lane count keeps its own key profile, and the play screen derives lane count, lane width, key labels, hit flashes, hold sparks, and key input from the active setting. Existing 5-lane generated charts are temporarily remapped into the selected display lane count so they remain playable during this transition.

Phase 2 is also implemented for generated charts. `ChartGenerator.generate()` accepts `lane_count`, generated chart metadata records `lane_count` / `lane_mode`, chart cache files are saved under `charts/<music_hash>/<lane_count>lane/<difficulty>.json`, 5 LANE still falls back to the legacy cache path, chart summaries show lane count, and ranking keys use `<music_hash>:<difficulty>:<lane_count>lane` with 5 LANE legacy ranking fallback.

Phase 3 is implemented for polish. The generator applies lane-count-specific tuning, tutorials branch into 3/5/7-lane lesson charts, playlist/library BEST text prefers the currently selected lane mode, and result/ranking screens show lane count explicitly.

Phase 4 is implemented for release-facing clarity. Difficulty selection shows the active lane mode and its BEST score, chart summary shows lane-mode comparison, ranking shows 3/5/7 lane best tabs for the current difficulty, practice/trial/result screens carry lane labels, and saved result screenshots include the lane mode in the filename.

Phase 5 is implemented for direct ranking review. The ranking screen now has clickable 3/5/7 lane tabs, and LEFT/RIGHT cycles between lane-specific ranking records without leaving the screen.

Phase 6 is implemented for chart QA visibility. The chart summary now reports lane usage, maximum lane concentration, and a compact quality memo so generated charts with lane bias or high density are easier to spot before playtesting.

Remaining future work: deeper playtest-driven chart tuning, manual playtest notes across several songs, and stronger unlock/DLC presentation for lane-related cosmetics once the game economy is finalized.

## Player-Facing Behavior

### Settings

Add a new setting row: `レーン数`.

- Choices: `3 LANE`, `5 LANE`, `7 LANE`
- Default: `5 LANE`
- Changing lane count changes the active key layout and future chart generation.
- Existing key configuration should become lane-count-specific.
- If a player switches from 5 LANE to 3 LANE and back, their 5-lane key bindings should still be preserved.

Recommended default key profiles:

| Lane Count | Keys |
| ---: | --- |
| 3 | `D`, `Space`, `K` |
| 5 | `D`, `F`, `Space`, `J`, `K` |
| 7 | `S`, `D`, `F`, `Space`, `J`, `K`, `L` |

### Difficulty Selection

Difficulty remains BEGINNER / EASY / NORMAL / HARD / EXPERT.
Lane count is orthogonal to difficulty.

Example identities:

- EASY + 3 LANE: fewer lanes and simpler hand movement
- EASY + 5 LANE: current easy style
- EASY + 7 LANE: wide layout, still low density
- HARD + 7 LANE: advanced chart with higher lane variety

### Chart Summary

The chart summary must show lane count clearly.

Recommended header:

```text
EASY ・ 5 LANE ・ 確定譜面 ・ 生成候補 1
```

Summary should include lane count in chart identity and generated metadata so users know what they are about to play.

### Gameplay Screen

The playfield should derive lane width and key labels from the active chart lane count instead of assuming 5.

Layout rules:

- 3 LANE should not simply leave large empty gaps inside the note field. The field can be narrower so notes feel centered and easy to read.
- 5 LANE should visually match the current game as closely as possible.
- 7 LANE should use a wider field where possible, but preserve side space for judgment panel and mascot when screen width allows.
- On small resolutions, 7 LANE may reduce mascot/cutin priority before shrinking note readability too far.

Suggested width policy at logical 1280x720:

| Lane Count | Field Width Target | Notes |
| ---: | ---: | --- |
| 3 | 450-520px | centered, large notes |
| 5 | current 620px+ | existing feel |
| 7 | 760-860px | narrower lanes but still readable |

### Tutorial

Initial implementation may keep tutorial fixed at 5 LANE.
Later, tutorial can branch by lane count:

- 3 LANE tutorial for first-time players
- 5 LANE standard tutorial
- 7 LANE challenge introduction

Do not block variable lane implementation on tutorial branching.

## Data Model

### Settings

Current settings use a single `keys` list of length 5. Replace or migrate to lane-count-specific key profiles.

Proposed settings shape:

```json
{
  "lane_count": 5,
  "lane_keys": {
    "3": ["d", "space", "k"],
    "5": ["d", "f", "space", "j", "k"],
    "7": ["s", "d", "f", "space", "j", "k", "l"]
  }
}
```

Compatibility rule:

- If old `keys` exists and `lane_keys["5"]` is missing, copy old `keys` into `lane_keys["5"]`.
- Keep reading `keys` for one migration cycle, but new saves should write `lane_keys` and `lane_count`.
- A helper should expose `active_lane_keys` so UI/gameplay code does not directly inspect raw settings.

### Chart

Current chart notes use `lane` values `0` to `4`. The chart must record lane count.

Proposed chart metadata for backward compatibility:

```json
{
  "metadata": {
    "lane_count": 5,
    "lane_mode": "5lane"
  }
}
```

Compatibility rule:

- Missing `metadata.lane_count` means `5`.
- Notes are valid only when `0 <= lane < lane_count`.

A future schema version may promote `lane_count` to a top-level field, but metadata is safer for the first migration because it does not break existing `Chart.from_dict` readers.

## Cache and Ranking Identity

Lane count changes the game surface enough that generated charts, scores, and rankings must not mix across lane modes.

### Chart File Path

Current path:

```text
charts/<music_hash>/<difficulty>.json
```

Recommended path after migration:

```text
charts/<music_hash>/<lane_count>lane/<difficulty>.json
```

Backward compatibility:

- For 5 LANE only, if `charts/<hash>/5lane/<difficulty>.json` is missing, read the old `charts/<hash>/<difficulty>.json`.
- When saving after migration, write to the new lane-specific path.
- Do not overwrite old files automatically until migration has been tested.

### Ranking Key

Current key:

```text
<music_hash>:<difficulty>
```

Recommended key:

```text
<music_hash>:<difficulty>:<lane_count>lane
```

Backward compatibility:

- Existing keys without lane suffix are treated as 5 LANE records.
- Song cards can show only active lane-count records at first.
- A later UI can show per-lane tabs or compact labels.

## Chart Generation

The generator must accept `lane_count` as an input:

```python
ChartGenerator().generate(analysis, difficulty, variant=0, lane_count=5)
```

The seed should include lane count:

```text
<music_hash>:<difficulty>:<lane_count>:<variant>
```

This prevents a 3-lane chart and a 7-lane chart from accidentally sharing generation identity.

### Frequency Band Mapping

Analysis currently produces 5 band-energy values. Keep the analyzer unchanged initially and remap those 5 bands to N lanes.

3 LANE mapping:

| Source | Lane |
| --- | ---: |
| low + low-mid | 0 |
| mid / percussion / downbeat | 1 |
| high-mid + high | 2 |

5 LANE mapping:

| Source Band | Lane |
| ---: | ---: |
| 0 | 0 |
| 1 | 1 |
| percussion / downbeat | 2 |
| 3 | 3 |
| 4 | 4 |

7 LANE mapping:

| Source | Lane Candidates |
| --- | --- |
| low | 0 / 1 |
| low-mid | 1 / 2 |
| percussion / downbeat | 3 |
| high-mid | 4 / 5 |
| high | 5 / 6 |

7 LANE should not simply increase simultaneous notes. It should primarily improve lane variety and left/right flow.

### Difficulty Rules by Lane Count

The same named difficulty should stay recognizable across lane modes, but physical complexity changes.

Recommended rule adjustments:

| Lane Count | Density | Chords | Holds | Notes |
| ---: | --- | --- | --- | --- |
| 3 | slightly lower | BEGINNER/EASY no chords, NORMAL max 2 | fewer overlapping holds | approachable |
| 5 | current | current | current | baseline |
| 7 | same or slightly higher for HARD/EXPERT | more spread, not more than current physical max without testing | avoid far jumps during holds | advanced readability |

The validator must use lane count for:

- lane bounds
- same-lane minimum gap
- max chord size
- hand-group conflict checks
- lane load balancing

Hand grouping proposal:

| Lane Count | Left Hand | Center | Right Hand |
| ---: | --- | --- | --- |
| 3 | lane 0 | lane 1 | lane 2 |
| 5 | lanes 0-1 | lane 2 | lanes 3-4 |
| 7 | lanes 0-2 | lane 3 | lanes 4-6 |

## Scoring

For the first implementation, keep score formulas unchanged within each lane mode.
Scores are separated by lane count, so direct fairness across 3/5/7 is not required.

Future option:

- Add a small lane-count badge on result cards.
- Avoid multiplying score by lane count at first; it can confuse players.

## UI and UX Risks

| Risk | Mitigation |
| --- | --- |
| 7 LANE becomes too cramped on 960x540 | Keep logical scaling, reduce mascot/cutin priority, enforce minimum lane width tests |
| Existing 5 LANE saves break | Missing lane_count means 5, old chart path fallback |
| Rankings look inconsistent | Treat old keys as 5lane, show active lane mode only |
| Key config becomes confusing | Store per-lane-count profiles and show only active count |
| Tutorial mismatch | Keep tutorial 5-lane initially and label it as standard tutorial |

## Implementation Order

1. Add lane-count constants and active key helpers.
2. Migrate settings from `keys` to `lane_keys`, keeping `keys` compatibility.
3. Update gameplay rendering and input handling to use `active_lane_count` and `active_lane_keys`.
4. Update chart loading/saving paths with 5-lane old-path fallback.
5. Add `lane_count` to chart metadata and chart summary display.
6. Update chart generator and validator to accept lane count.
7. Split ranking keys by lane count while reading old keys as 5 LANE.
8. Add settings UI row for `レーン数`.
9. Add tests for 3/5/7 rendering, input, generation, cache paths, ranking separation, and old-save compatibility.
10. Manual playtest 3 songs across 3/5/7 before shipping.

## Acceptance Criteria

- Existing 5-lane charts load and play without manual migration.
- New 3-lane charts contain only lanes 0-2.
- New 7-lane charts contain only lanes 0-6.
- Settings can switch 3/5/7 and preserve separate key profiles.
- Gameplay shows correct key labels and lane count.
- Chart summary shows lane count.
- Rankings do not mix lane counts.
- Trial play, practice, pause/resume, mascot, cutin, judgment panel, and background modes still work.
- All automated tests pass.

## Recommendation

Implement this as a phased feature rather than one large rewrite.
The safest first milestone is rendering/input/settings support while generation still defaults to 5 LANE internally. The second milestone should make generation and cache paths lane-aware. The third milestone should update rankings, result display, and tutorial polish.

