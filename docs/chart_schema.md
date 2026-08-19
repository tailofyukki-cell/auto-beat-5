# AutoBeat 5 譜面データ仕様

## 目的

譜面は、解析結果とは独立して再生・共有・再検証できるJSONファイルとして保存します。保存先は`charts/<music_hash>/<difficulty>.json`です。音源そのものは含めず、SHA-256ハッシュと参照パスだけをメタデータに残します。

## トップレベル構造

| フィールド | 型 | 必須 | 説明 |
|---|---|---:|---|
| `version` | integer | はい | 譜面データ形式の版。初版は`1`。 |
| `music_hash` | string | はい | 元音源ファイルのSHA-256。 |
| `difficulty` | string | はい | `beginner`、`easy`、`normal`、`hard`、`expert`のいずれか。 |
| `seed` | integer | はい | 決定論的な生成を追跡するシード。 |
| `song_duration` | number | はい | 楽曲長（秒）。 |
| `generator_version` | string | はい | 自動譜面生成器の版。 |
| `metadata` | object | はい | BPM、分析版、参照元などの補助情報。 |
| `notes` | array | はい | ノーツ配列。時刻、レーン順に並べる。 |

## ノーツ構造

| フィールド | 型 | 必須 | 説明 |
|---|---|---:|---|
| `time` | number | はい | 判定対象となる開始時刻（秒）。 |
| `lane` | integer | はい | `0`〜`4`。順にD、F、Space、J、Kへ対応。 |
| `kind` | string | はい | 初版は`tap`または`hold`。 |
| `end_time` | number / null | 条件付き | `hold`の場合のみ、開始より後の終了時刻（秒）。 |
| `source` | string | はい | `onset`または`sustain`など、生成根拠。 |
| `strength` | number | はい | 解析から得た相対強度。`0`〜`1.5`程度。 |
| `id` | string | はい | 保存時に決定される一意な識別子。 |

同時押しは、同じ`time`を持つ複数のノーツで表現します。連打は、短い時間間隔で連続する複数の`tap`ノーツとして表現します。これにより、専用の複合ノーツ型を増やさずに基本的な再生・判定を統一できます。

## 例

```json
{
  "version": 1,
  "music_hash": "a4c2...",
  "difficulty": "normal",
  "seed": 839182734,
  "song_duration": 182.46,
  "generator_version": "1.0",
  "metadata": {
    "bpm": 128.0,
    "algorithm": "frequency-onset-percussion-sustain-v1"
  },
  "notes": [
    {
      "time": 12.50000,
      "lane": 2,
      "kind": "tap",
      "end_time": null,
      "source": "onset",
      "strength": 0.91,
      "id": "00017-12.5000-2"
    },
    {
      "time": 13.00000,
      "lane": 0,
      "kind": "hold",
      "end_time": 14.25000,
      "source": "sustain",
      "strength": 0.60,
      "id": "00018-13.0000-0"
    },
    {
      "time": 13.00000,
      "lane": 4,
      "kind": "tap",
      "end_time": null,
      "source": "onset",
      "strength": 0.74,
      "id": "00019-13.0000-4"
    }
  ]
}
```

## 拡張規則

将来の追加ノーツは、既存フィールドを破壊せず`kind`と専用属性を追加します。新しいランタイムは未知の`kind`を安全に読み飛ばすか、明示的にエラーとして表示しなければなりません。形式変更時は`version`を上げ、旧版の移行器を追加します。
