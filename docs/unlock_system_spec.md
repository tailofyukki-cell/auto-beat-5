# AutoBeat 5 Unlock System Specification

## Purpose

AutoBeat 5の解放システムは、プレイを続ける理由を作りつつ、初心者には遊びやすい入口を、上級者には挑戦先を自然に渡すための仕組みである。

初期リリースでは、すべてを最初から選ばせるのではなく、標準体験を `5 LANE` に絞る。プレイ結果と累積スコアに応じて、`3 LANE`、`7 LANE`、マスコット、ご褒美画像、将来のDLCアイテムを順番に解放する。

## Design Goals

- 初回プレイヤーに選択肢を出しすぎず、まず標準の5レーンで遊んでもらう。
- 低ランクが続くプレイヤーには、挫折する前に練習向けの3レーンを解放する。
- 高ランクを取れるプレイヤーには、腕試しとして7レーンを解放する。
- マスコットとご褒美画像は、通常プレイで貯めたBEAT POINTを消費して購入するコレクション要素にする。
- リリース用ZIPでは、未解放の素材も同梱するがゲーム内ではロック状態で見せる。
- DLCはフォルダ追加でマスコットやご褒美画像を増やせる構造にする。

## Current Implementation Status

現在、以下を実装済み。

- 新規プロフィールには `lane.5` と `mascot.rhythm` を初期解放として保存する。
- `5 LANE` の低ランク継続または高MISS率継続で `lane.3` を解放する。
- `5 LANE` のSランク以上、またはAランク以上の複数回達成で `lane.7` を解放する。
- マスコットは `rhythm` を初期解放にし、他キャラはBEAT SHOPで購入する。
- 効果音タイプ、背景設定、ノーツ配色はチュートリアル完了で現在同梱されている基本分を解放する。
- 設定画面では未解放レーン・未解放マスコット・未解放テーマを選択不可にし、LOCKED表示と条件ヒントを出す。
- リザルト後の解放通知は、レーン、マスコット、ご褒美画像をまとめて表示する。
- ご褒美画像は `rewards/locked/` から検出し、解放後に `rewards/unlocked/` へコピーする。

## Deferred Work

実プレイでの譜面品質チューニングは一旦保留する。

保留理由:

- 現在はレーン数、ランキング、譜面概要などの土台整備を優先している。
- 譜面品質は実音源での人間プレイ評価が必要で、自動テストだけでは判断しきれない。
- 解放システム導入後に、3/5/7レーンそれぞれのプレイログを見ながら調整する方が効率が良い。

再開条件:

- 代表的な複数ジャンルのテスト曲が用意されている。
- 3/5/7レーンの解放導線が実装済みである。
- 各レーンのプレイ結果、ミス率、ランク分布を確認できる。

## Unlock Categories

| Category | 初期状態 | 解放条件 | 備考 |
| --- | --- | --- | --- |
| lane_mode.5 | 解放済み | 初期解放 | 標準体験 |
| lane_mode.3 | ロック | 低ランク・高MISS率の継続 | 練習向けとして肯定的に見せる |
| lane_mode.7 | ロック | 高ランク達成 | 上級者向けチャレンジ |
| mascot | 1体のみ解放 | BEAT POINTを消費して購入 | 設定画面で選択 |
| reward_image | 0点画像のみ解放 | BEAT POINTを消費して購入 | ギャラリーで閲覧 |
| background | 標準背景のみ解放 | チュートリアル完了、追加分はDLC | 任意画像もチュートリアル後に選択可能 |
| note_theme | 標準のみ解放 | チュートリアル完了、追加分はDLC | 将来拡張 |
| sfx_theme | 標準のみ解放 | チュートリアル完了、追加分はDLC | 試聴可能にする |

## Lane Mode Unlock Rules

### Initial State

初回起動時は `5 LANE` のみ解放する。

設定画面には `3 LANE` / `5 LANE` / `7 LANE` を表示してよいが、未解放のものは選択不可にする。
未解放表示は `LOCKED` と条件説明を出す。

### 3 LANE Unlock

3レーンは「救済」ではなく、`RELAX MODE` または `PRACTICE FRIENDLY` のような練習向けモードとして見せる。

推奨条件:

- `5 LANE` で `C` ランク以下を3回記録する。
- または `5 LANE` でMISS率25%以上のプレイを3回記録する。

どちらかを満たした時点で解放する。

解放メッセージ案:

```text
3 LANE MODE 解放
少ないキーで曲に慣れられる練習向けモードです
```

### 7 LANE Unlock

7レーンは上級者向けの挑戦モードとして見せる。

推奨条件:

- `5 LANE` で `S` ランク以上を1回記録する。
- または `5 LANE` で `A` ランク以上を3回記録する。

どちらかを満たした時点で解放する。

解放メッセージ案:

```text
7 LANE MODE 解放
より広いレーンで高難度の譜面に挑戦できます
```

### Lane Lock Behavior

未解放レーンを選ぼうとした場合:

- 選択は変更しない。
- 短いロック音を鳴らす。
- 画面下部に条件を表示する。

例:

```text
3 LANEは、5 LANEでC以下を3回またはMISS率25%以上を3回で解放されます
7 LANEは、5 LANEでS以上を1回またはA以上を3回で解放されます
```

## Currency And Score Economy

### Currency Name

内部的には既存の `lifetime_score` を使う。
プレイヤー向けには `TOTAL SCORE` または `スター` のような名称にできるが、初期実装では追加通貨を作らず累積スコアをそのまま使う。

### Spend Or Threshold

通常プレイで獲得したスコアと同額を `wallet_score`（表示名: BEAT POINT）へ加算する。
BEAT SHOPでマスコットまたはご褒美画像を購入すると、価格分を残高から消費して永続解放する。
購入は確認を含む二段階操作とし、購入済みアイテムへの二重支払いは発生しない。
練習・お試し・チュートリアルのスコアはBEAT POINTへ加算しない。

旧プロフィールは初回移行時に `lifetime_score` と同額のBEAT POINTを受け取る。
旧方式ですでに条件到達していたアイテムは購入済みとして維持し、再ロックしない。

推奨データ:

```json
{
  "lifetime_score": 123456,
  "wallet_score": 23456,
  "wallet_initialized": true,
  "shop_migrated": true,
  "unlocked_items": ["lane.5", "mascot.rhythm", "reward.reward_001"],
  "unlock_stats": {
    "five_lane_low_rank_count": 2,
    "five_lane_high_miss_count": 1,
    "five_lane_a_or_better_count": 2,
    "five_lane_s_or_better_count": 0
  }
}
```

## Cosmetic Unlock Rules

### Mascots

初期解放は1体のみ。候補は現在の標準キャラである `rhythm` または `cute` のどちらかに統一する。

推奨:

- 初期マスコット: `rhythm`
- 既存の追加マスコット: BEAT SHOPで順次購入
- DLCマスコット: DLCカタログ読み込み後、条件に応じて解放

設定画面では、未解放マスコットも小さなシルエットまたは鍵表示で存在だけ見せる。
ただし、画像を完全に見せすぎると解放報酬感が弱くなるため、未解放時は暗くして名前と条件だけ表示する。

### Tutorial-Cleared Themes

効果音タイプ、背景設定、ノーツ配色は、初回プレイ前に選択肢を増やしすぎないため、初期状態では標準のみ選択可能にする。

チュートリアルを最後までクリアすると、同梱されている基本テーマをまとめて解放する。

- `sfx.*`: 現在同梱されている効果音タイプ
- `background.*`: VISUALIZER / IMAGE / OFF / custom image
- `note_theme.*`: 現在同梱されているノーツ配色

将来DLCで追加するテーマも同じID体系を使う。例: `sfx.neon_pack_hit`、`background.neon_stage`、`note_theme.gold_live`。
DLC追加分は、DLCカタログ側で `unlock_type: tutorial_completed`、`score_threshold`、または `initial` を選べるようにする。

### Reward Images

ご褒美画像は現在の `rewards/reward_config.json` を使う。

初期実装では以下の方針にする。

- `price: 0` の画像だけ初期解放。
- それ以外はギャラリーでロック表示。
- BEAT SHOPで購入後、ギャラリーから閲覧できる。
- ZIP内には画像を含めるが、ゲーム内閲覧は解放済みのみ許可する。
- ロック済み画像は `rewards/locked/` に置き、Windowsでは隠し属性を付ける。
- 解放済み画像は `rewards/unlocked/` にコピーし、ユーザーがエクスプローラーから見られるようにする。

### DLC Items

DLCは将来 `dlc/<pack_id>/catalog.json` を読む。
DLC側も通常アイテムと同じ `price` を持てる。

DLC追加例:

```json
{
  "id": "mascot.neon_star",
  "category": "mascot",
  "display_name": "NEON STAR",
  "asset": "mascots/neon_star.png",
  "price": 250000,
  "pack_id": "neon_pack_01"
}
```

安全ルール:

- DLC内のパスはDLCフォルダ配下の相対パスのみ許可する。
- 絶対パス、`..`、巨大ファイル、不正拡張子は無視する。
- 壊れたDLCがあってもゲーム本体は起動を継続する。

## Release ZIP Behavior

リリース用ZIPには以下を含める。

```text
AutoBeat5/
├─ AutoBeat5.exe
├─ assets/
│  └─ mascots/
├─ rewards/
│  ├─ reward_config.json
│  ├─ locked/           # 隠し属性。解放前画像の置き場
│  │  └─ *.png / *.webp
│  └─ unlocked/         # 解放後にコピーされる表示用フォルダ
├─ docs/
│  └─ AutoBeat5_User_Guide.pdf
└─ dlc/                 # 初期リリースでは空でもよい
```

ZIP同梱時のルール:

- マスコット画像やご褒美画像は配布物に含める。
- ご褒美画像は原則 `rewards/locked/` に入れる。
- `rewards/locked/` はWindowsで隠し属性を付ける。これは秘匿ではなく、解放前の雰囲気を作るための演出である。
- 解放時に `rewards/unlocked/` へ画像をコピーし、ユーザーがエクスプローラーから直接見られるようにする。
- 未解放アイテムはゲーム内でロック状態にする。
- ユーザーが隠しファイル表示をONにすれば解放前画像を見られるが、それは許容する。
- 本当に秘匿したい素材は、初期ZIPに含めず後日DLCとして配布する。

## User Interface

### Settings Screen

設定画面で選べる項目は、解放状態を持つ。

表示例:

```text
レーン数        ◁ 5 LANE ▷
マスコット      ◁ RHYTHM ▷
効果音タイプ    ◁ CLASSIC ▷
```

未解放時:

```text
レーン数        ◁ 3 LANE LOCKED ▷
条件: 5 LANEでC以下をあと1回
```

未解放項目にカーソルがある時は、プレビュー欄に条件を表示する。

### Result Screen

リザルト画面は解放の一番気持ちいい場所なので、通知を強めに出す。

表示例:

```text
NEW UNLOCK
7 LANE MODE
Sランク達成で新しい挑戦が開放されました
```

複数解放された場合は、最大3件まで強調表示し、それ以上は `+2 more` のようにまとめる。

### Gallery And Reward Manager

ギャラリーではロック済み画像を鍵付きカードとして表示する。

- 解放済み: サムネイル表示、クリックで拡大。
- 未解放: 暗いサムネイルまたは鍵アイコン、必要スコア表示。
- ファイル欠損: `MISSING FILE` 表示。
- 設定なし画像: `NO SCORE RULE` 表示。

## Data Model

### Profile

既存の `profile.json` に以下を追加する。

```json
{
  "unlocked_features": ["lane.5"],
  "unlocked_cosmetics": ["mascot.rhythm"],
  "unlock_stats": {
    "five_lane_low_rank_count": 0,
    "five_lane_high_miss_count": 0,
    "five_lane_a_or_better_count": 0,
    "five_lane_s_or_better_count": 0
  }
}
```

互換性:

- `unlocked_features` が存在しない場合は `lane.5` を自動追加する。
- 既存の `unlocked_rewards` は当面維持する。
- 将来は `unlocked_cosmetics` と `unlocked_rewards` を統合してもよいが、初期実装では無理に移行しない。

### Unlock Catalog

将来は `unlock_catalog.json` を導入する。

```json
{
  "version": 1,
  "items": [
    {
      "id": "lane.3",
      "category": "feature",
      "display_name": "3 LANE MODE",
      "unlock_type": "performance",
      "conditions": [
        { "metric": "five_lane_low_rank_count", "gte": 3 },
        { "metric": "five_lane_high_miss_count", "gte": 3 }
      ]
    },
    {
      "id": "mascot.cool",
      "category": "mascot",
      "display_name": "COOL",
      "unlock_type": "purchase",
      "price": 100000,
      "asset": "assets/mascots/cool.png"
    }
  ]
}
```

条件配列はOR扱いにする。
同一条件内でANDが必要になった場合は、将来 `all` / `any` 形式へ拡張する。

## Implementation Order

1. `profile.json` の互換初期化に `unlocked_features` と `unlock_stats` を追加する。
2. 5レーン以外のレーン選択にロック判定を入れる。
3. リザルト保存時に `unlock_stats` を更新する。
4. 3レーン・7レーンの解放判定とリザルト通知を追加する。
5. マスコットカタログに `price` または `unlock_id` を持たせる。
6. 設定画面で未解放マスコットをロック表示し、選択不可にする。
7. ご褒美画像を `rewards/locked/` から読み込み、解放時に `rewards/unlocked/` へコピーする。
8. `rewards/locked/` にWindows隠し属性を付ける。
9. ご褒美画像のロック表示をリリースZIP前提で再確認する。
10. `dlc/*/catalog.json` の読み込みを追加する。
11. release preflightでロック対象素材、DLCパス、安全な拡張子を検査する。
12. 操作説明PDFに解放システムの説明を追加する。

## Acceptance Criteria

- 新規プロフィールでは `5 LANE` のみ選択できる。
- 条件未達の `3 LANE` / `7 LANE` は設定画面でロック表示になる。
- チュートリアル未完了時は効果音タイプ、背景設定、ノーツ配色が標準以外へ変更できない。
- チュートリアル完了後、同梱済みの効果音タイプ、背景設定、ノーツ配色が選択できる。
- 5レーンで低ランク条件を満たすと3レーンが解放される。
- 5レーンで高ランク条件を満たすと7レーンが解放される。
- 解放時はリザルト画面で通知される。
- 初期マスコット以外はBEAT SHOPで購入するまで設定不可になる。
- ご褒美画像はZIPに入っていても未解放ならギャラリーで閲覧できない。
- ロック済みご褒美画像は `rewards/locked/` から検出される。
- 解放済みご褒美画像は `rewards/unlocked/` にコピーされ、エクスプローラーから見られる。
- DLCフォルダを追加しても、壊れたDLCは無視されゲームは起動する。
- 既存セーブデータは自動移行され、5レーンの既存プレイ体験は壊れない。

## Open Decisions

| Topic | Current Recommendation |
| --- | --- |
| 初期マスコット | `rhythm` を推奨。既存設定が `cute` の場合は互換を残す |
| スコアは消費するか | 通常スコアと同額のBEAT POINTを獲得し、ショップ購入時に消費する |
| 3レーン解放文言 | 救済ではなく練習向け・気軽さとして表現する |
| ZIP内素材の秘匿 | `rewards/locked/` を隠し属性にする演出ロック。完全秘匿はしない |
| 譜面品質チューニング | 一旦保留。解放システム後に実プレイ評価で再開 |
