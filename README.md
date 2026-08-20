# AutoBeat 5

**AutoBeat 5** は、ユーザーが選んだ音楽ファイルを解析し、5レーンの縦スクロール譜面を生成してプレイするWindows向け音楽ゲームです。低音は左側のD/F、高音は右側のJ/K、強いリズムはSpaceへ優先的に割り当て、単純なBPM同期のランダム譜面ではなく、onset・周波数帯・リズム強度・持続区間を組み合わせて譜面を作ります。

> **音源の利用条件:** 読み込む音楽は、プレイヤー自身が所有するか、適法に利用できるファイルに限ってください。本作は音楽ファイルを同梱・再配布しません。

## 機能

| 領域 | 実装内容 |
|---|---|
| 入力 | D / F / Space / J / K を初期値とする5レーン。設定画面で重複しない任意キーへ変更可能。 |
| 楽曲 | MP3 / WAV / OGG / FLAC を選択し、解析結果と曲ファイルのSHA-256をキャッシュ。解析済みの最大20曲はローカルライブラリーから再選択できる。 |
| 解析 | BPM・beat・局所BPM・小節頭候補・onset・HPSSによる打楽器/持続音分離・帯域別エネルギーを抽出。失敗時は画面に理由を示す。 |
| 譜面 | BEGINNER / EASY / NORMAL / HARD / EXPERTの5段階。通常・同時押し・長押し・連打的な交互入力を扱う。 |
| プレイ | 時刻差によるPERFECT / GREAT / GOOD / MISS、長押しのSTART/HOLD/RELEASE内部評価、コンボ、スコア、Timing Offset、一時停止、リザルト。 |
| 演出 | 判定音、50 / 100 / 500 COMBOバナー、一時停止中の再開・リトライ・選曲へ戻る操作。 |
| プレイ可能性 | 同一レーン間隔、同時押し数、同じ手の長押し衝突、片手への過度な入力集中、長押し始点の重複ノーツを検査・補正。 |
| ご褒美 | 累積スコアに基づく外部画像フォルダの解放とギャラリー。PNG / JPEG / WebP対応。サムネイル、未解放の鍵表示、拡大プレビューを備える。 |
| チュートリアル | 曲ファイルを必要としないメトロノーム型の4段階練習。中央レーン、5レーン、長押し、基本パターンを順に学べる。 |
| デモ曲 | 制作者が`demo_songs`フォルダへ置いたMP3 / WAV / OGG / FLACを、選曲画面の`DEMO SONGS`から読み込める。体験版では事前解析済みキャッシュと全難易度譜面を同梱する。 |
| 保存 | 設定、成績、プレイ履歴、解析済み楽曲、画像解放、解析・譜面キャッシュをローカル保存。 |

## 操作

| 画面 | 操作 |
|---|---|
| タイトル | **Enter / Space** でプレイ画面へ。**T**でチュートリアル、Gでギャラリー、Sで設定。 |
| チュートリアル | **Enter / Space**で開始。メトロノーム音に合わせてD / F / Space / J / Kを押す。Escで課題一覧へ戻る。 |
| 楽曲選択 | ボタンから音源を選択すると解析を開始。`demo_songs`内のデモ曲は`DEMO SONGS`として表示される。 |
| 難易度選択 | **↑ / ↓** で難易度を選択し、**Enter / Space** で開始。 |
| プレイ中 | 設定した5キーで演奏。**Esc**で一時停止・再開。 |
| 設定 | **↑ / ↓**で項目を選び、**← / →**で音量、ノーツ速度、Timing Offset、判定幅、フルスクリーン、解像度を変更。キーコンフィグの枠をクリックしてから任意キーを押す。 |

## 譜面生成の考え方

譜面は同じ音源ファイル・難易度・生成器バージョンに対して決定論的に生成されます。まずonsetの強度と広帯域トランジェントから演奏候補を選び、帯域別の強さでレーンを割り当てます。強い低域はD/F、強い高域はJ/K、強い広帯域のリズムはSpaceを優先します。複数帯域が同時に強い場合は難易度に応じて同時押しにし、持続区間はNORMAL以上で長押し候補になります。連続onsetは難易度の許す最小間隔に従って連打的な配置として残されます。

生成後は、同じキーの極端な高速連打、難易度上限を超える同時押し、同じ手で重なる長押し、短時間に片手へ集中しすぎる入力を除去します。したがって、難易度を上げるとノーツ数だけでなく、反映する音情報の粒度と複合入力が増えます。

## チュートリアルとデモ曲

チュートリアルは音源ファイルを使わず、ゲーム内で生成するクリック音と固定譜面で動作します。音源の権利確認が不要なため、初回プレイに適しています。

制作者が自作したデモ曲を製品に同梱したい場合は、プロジェクト直下の`demo_songs\`へMP3 / WAV / OGG / FLACを追加してください。`python tools\prepare_demo_bundle.py`で解析キャッシュと全5難易度の譜面を生成してからビルドすると、体験版では初回解析なしで難易度選択へ進めます。ビルド時にフォルダごと`dist\AutoBeat5\demo_songs\`へコピーされ、選曲画面では最大3曲を`DEMO SONGS`として表示します。非音声ファイルは無視されます。配布前に、音源の著作権・原盤権・配信契約など、再配布に必要な権限を確認してください。

```text
demo_songs\
├─ README.txt
└─ your_demo_song.ogg
```

## ローカルデータとご褒美画像

初回起動時、Windowsでは通常`%APPDATA%\AutoBeat5\`へ設定とキャッシュを作成します。開発・検証では環境変数`AUTOBEAT_DATA_DIR`で保存先を変更できます。

```text
%APPDATA%\AutoBeat5\
├─ settings.json
├─ profile.json
├─ cache\<music_hash>.json
├─ charts\<music_hash>\beginner.json ... expert.json
└─ rewards\
   ├─ reward_config.json
   ├─ reward_001.png
   └─ reward_002.webp
```

`rewards/reward_config.json`では画像名と必要累積スコアを編集できます。ゲームの再ビルドは不要です。ギャラリーのサムネイルをクリックすると、解放済み画像を大きく表示できます。

```json
{
  "reward_001.png": { "required_score": 100000 },
  "reward_002.webp": { "required_score": 300000 }
}
```

## 開発環境での実行

Python 3.11以上を用意し、次の手順で起動します。

```powershell
python -m pip install -r requirements.txt
python main.py
```

macOS/Linuxでは動作確認に利用できますが、製品ターゲットはWindows 10 / 11です。

## Windows配布ビルド

Windows上で`build_windows.bat`をダブルクリックすると、依存関係を導入して`dist\AutoBeat5\AutoBeat5.exe`を生成します。ビルド成果物のフォルダ全体を配布してください。実行するユーザーはPythonや開発環境を別途インストールする必要がありません。

```text
AutoBeat5\
├─ AutoBeat5.exe
├─ _internal\
├─ demo_songs\        # 制作者のデモ曲、解析キャッシュ、全難易度譜面
├─ rewards\           # ご褒美画像と reward_config.json
├─ TRIAL_README.txt    # 体験版の起動・操作・利用条件
├─ docs\
└─ licenses\
```

初回公開前に、実機のWindows 10 / 11でMP3 / WAV / OGG / FLACの再生・解析、チュートリアルのクリック音・長押し操作、Timing Offset、デモ曲・ご褒美画像の読込を確認してください。署名なしのexeはWindowsの警告対象になる場合があるため、販売・継続配布ではコード署名も検討してください。

## テスト

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover -s tests -v
```

現時点では、解析特徴量の抽出、決定論的な難易度別生成、譜面キャッシュ、通常・長押し判定、同時押し上限、画面描画を自動テストします。人間が「曲を叩いている感覚」を評価するには、複数ジャンルの実音源による手動プレイテストも必要です。

## ライセンス

技術選定の主要な根拠は、[Pygame LGPL][1]、[librosa ISC License][2]、[Godot Engine License][3]、[Unity Plans & Pricing][4]にまとめています。AutoBeat 5の配布前には、`licenses/THIRD_PARTY_NOTICES.md`を読み、最終バイナリに含まれる依存関係のライセンス本文を確認・同梱してください。

[1]: https://www.pygame.org/docs/LGPL.txt "Pygame LGPL"
[2]: https://github.com/librosa/librosa/blob/main/LICENSE.md "librosa LICENSE"
[3]: https://godotengine.org/license/ "Godot Engine License"
[4]: https://unity.com/products "Unity Plans & Pricing"
