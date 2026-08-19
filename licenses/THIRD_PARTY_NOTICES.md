# AutoBeat 5 — Third-Party Notices

AutoBeat 5 は以下の第三者ソフトウェアを利用します。配布版を公開・販売する前に、使用した各依存関係の**バージョン固有のライセンス本文**と、PyInstaller生成物に含まれるバイナリのライセンスを再確認してください。本通知は法的助言ではありません。

| コンポーネント | 用途 | ライセンス | 配布時の対応 | 参照 |
|---|---|---|---|---|
| Pygame | 2D描画、入力、音源再生 | LGPL 2.1 | 配布物にライセンス本文と著作権表示を同梱する。 | [Pygame LGPL][1] |
| librosa | BPM、beat、onset、周波数解析 | ISC | 著作権表示と許諾文を同梱する。 | [librosa LICENSE][2] |
| NumPy | 数値処理 | BSD 3-Clause | 使用バージョンのNOTICE/LICENSEを同梱する。 | [NumPy license][3] |
| SciPy | 信号処理の依存関係 | BSD 3-Clause | 使用バージョンのNOTICE/LICENSEを同梱する。 | [SciPy license][4] |
| SoundFile / libsndfile | 音源ファイル読込の依存経路 | BSD 3-Clause / LGPL系ライブラリを含む場合がある | バンドル内容と動的ライブラリを確認し、該当するライセンス文を同梱する。 | [SoundFile license][5] |
| scikit-learn | librosaの依存関係 | BSD 3-Clause | 使用バージョンのNOTICE/LICENSEを同梱する。 | [scikit-learn license][6] |
| Numba / llvmlite | librosaの高速処理依存関係 | BSD系 | 使用バージョンのNOTICE/LICENSEを同梱する。 | [Numba license][7] |
| PyInstaller | 実行ファイル生成 | GPL-2.0 with bootloader exception | ビルドツールとしてのライセンスとブートローダー例外を確認する。 | [PyInstaller license][8] |

ゲームに読み込ませる音楽ファイルは、ユーザー自身が所有または利用許諾を得たものに限られます。AutoBeat 5 は市販曲その他の音源を同梱・再配布しません。

[1]: https://www.pygame.org/docs/LGPL.txt "Pygame LGPL"
[2]: https://github.com/librosa/librosa/blob/main/LICENSE.md "librosa ISC License"
[3]: https://github.com/numpy/numpy/blob/main/LICENSE.txt "NumPy License"
[4]: https://github.com/scipy/scipy/blob/main/LICENSE.txt "SciPy License"
[5]: https://github.com/bastibe/python-soundfile/blob/master/LICENSE "SoundFile License"
[6]: https://github.com/scikit-learn/scikit-learn/blob/main/COPYING "scikit-learn License"
[7]: https://github.com/numba/numba/blob/main/LICENSE "Numba License"
[8]: https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt "PyInstaller License"
