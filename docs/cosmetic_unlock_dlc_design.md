# Cosmetic Unlock and DLC Design

## Goal

設定画面で選べる見た目・音まわりの項目を、将来的にスコア解放とリリース後DLC追加へ拡張できるようにする。
初期実装では通常設定として全項目を選択可能にし、データ形式だけを後からロック制御できる形へ寄せる。

## Cosmetic Categories

| Category | Current Examples | Storage | Unlock Target |
| --- | --- | --- | --- |
| background | VISUALIZER / IMAGE / OFF, packaged image, custom image | `assets/backgrounds/`, user-selected absolute path | チュートリアル完了、DLC追加背景 |
| mascot | `assets/mascots/manifest.json` entries | `assets/mascots/` | 初期はRHYTHM、以降はスコア/DLC |
| note_theme | built-in `NOTE_THEMES` | code now, manifest later | チュートリアル完了、DLC追加配色 |
| sfx_theme | built-in `SFX_THEMES` | code now, manifest or audio pack later | チュートリアル完了、DLC追加効果音 |
| playfield | built-in `PLAYFIELD_MODES` | code now | レーン表示モード |

## Unlock Model

将来は `cosmetics/catalog.json` のような共通カタログを追加する。
各アイテムは以下の形にする。

```json
{
  "id": "background.neon_grid",
  "category": "background",
  "display_name": "NEON GRID",
  "asset": "assets/backgrounds/neon_grid.png",
  "price": 50000,
  "dlc_pack": "base",
  "version": 1
}
```

購入残高は `profile["wallet_score"]` を使う。
`price` が未設定のものは購入不可、`0` のものは初期解放。
`unlock_type: tutorial_completed` のものはチュートリアル完了後に解放する。
DLCパックで追加されたアイテムも同じ条件で並べ、未所持DLCの項目は読み込まない。

## DLC Folder Proposal

リリース後に追加しやすいよう、将来は以下を読む。

```text
AutoBeat5/
├─ assets/
│  ├─ backgrounds/
│  └─ mascots/
└─ dlc/
   └─ pack_name/
      ├─ catalog.json
      ├─ backgrounds/
      ├─ mascots/
      └─ sfx/
```

DLCはフォルダ追加だけで反映する。
安全のため、`catalog.json` 内のパスはDLCフォルダ配下の相対パスのみ許可する。
絶対パスや `..` を含むパスは無視する。

## Current Step

現時点では以下を実装済み。

- プレイ背景モード: `VISUALIZER` / `IMAGE` / `OFF`
- 背景画像: `assets/backgrounds` の同梱画像を左右キーで切替、または設定画面の背景画像行で Enter/Space から任意画像を選択
- 背景透明度: 5%から65%まで5%刻み
- 画像背景は画面全体にカバー表示し、暗いレイヤーを重ねてノーツの視認性を優先

## Next Implementation Steps

1. `cosmetics/catalog.json` を導入し、背景・マスコット・SEテーマを共通アイテムとして列挙する。
2. 設定画面で未購入アイテムを表示する場合は、選択不可にしてBEAT SHOPへの案内を表示する。
3. `profile["unlocked_cosmetics"]` と `wallet_score` を使い、購入時に残高と解放状態を同時保存する。
4. `dlc/*/catalog.json` を読み込み、パック単位で追加アイテムをマージする。
5. リリース用preflightでDLC内の不正パス、欠損アセット、巨大画像を検査する。
