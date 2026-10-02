"""Build the Japanese release manual from current game screenshots."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "user_manual" / "screenshots"
OUTPUT = ROOT / "docs" / "AutoBeat5_User_Guide.pdf"
PREVIEWS = ROOT / "artifacts" / "manual_pages"
FONT = ROOT / "fonts" / "NotoSansCJK-Regular.ttc"
SIZE = (1600, 900)
INK = (24, 34, 48)
MUTED = (83, 100, 118)
ACCENT = (0, 120, 157)

# Instructions are kept beside the screenshot they explain, not inside the game.
PAGES = [
    ("オトアソビ", "好きな曲を、遊ぼう。", "01_title", [
        "操作説明書 / 2026年9月10日版",
        "自分の音楽ファイルを読み込み、自動生成された譜面で遊ぶWindows用音楽ゲームです。",
        "まずはTUTORIALで基本操作を練習。曲を選んで遊ぶときはPLAY MUSICへ。",
        "画像は現行ソースのゲーム描画です。曲名・スコア・所持ポイントは説明用の例です。",
    ]),
    ("起動と最初の一曲", "ZIPは展開してから起動します", None, [
        "配布ZIPを新しいフォルダへすべて展開し、OtoasobiフォルダのOtoasobi.exeを起動します。ZIPの中から直接起動しないでください。",
        "同梱の説明書はOtoasobi_User_Guide.pdfです。既存データを引き継ぐため、保存先には旧名称が残ります。",
        "_internal・assets・rewards・demo_songsなどをEXEと一緒に保管してください。EXEだけの移動は避けます。",
        "基本の流れは、PLAY MUSIC → 曲の読込・選択 → 難易度 → 譜面概要 → プレイです。",
        "初回解析には時間がかかる場合があります。自分で利用する権利のある音楽ファイルを選んでください。",
        "終了するときはタイトル画面右下の「終了」、またはウィンドウの閉じるボタンを使います。",
    ]),
    ("曲を選ぶ・整理する", "PLAYLIST", "02_playlist", [
        "曲を読み込むと一覧から選べます。↑↓で選択、Enterで決定、Iで音楽ファイルを読み込みます。",
        "Nでフォルダ作成、Mは「選択曲をここへ移動」です。デモ曲は移動できません。フォルダはゲーム内の分類です。",
        "左右キーでフォルダを切り替えます。最後に開いたフォルダが次回の開始位置になります。",
        "曲の元ファイルを移動・削除すると再生できなくなる場合があります。必要なら読み込み直してください。",
    ]),
    ("譜面を選ぶ・試す", "譜面概要と生成候補", "03_chart_summary", [
        "BPM・曲の長さ・TAP/HOLD数・同時押し回数などを確認できます。NPSは1秒あたりのノーツ数です。",
        "「新しい候補」から作り直せます。比較候補は最大5個。候補がある場合は左右キーで切り替えます。",
        "試作候補には採用・破棄の操作があります。画面のボタン表示に従って選んでください。",
        "「お試しプレイ」はクリック専用。最大60秒で終了し、長い曲はフェードアウトします。短い曲は全曲を試せます。",
        "お試しプレイでは通常のスコア記録やBP獲得は行いません。通常プレイはEnterで開始します。",
    ]),
    ("ノーツの叩き方", "判定ラインに合うタイミングで入力", "04_gameplay", [
        "初期の5レーンは左から D / F / Space / J / K。画面下のキー表示を確認します。",
        "TAPはノーツが判定ラインに来たら押します。HOLDは先頭で押して保持し、終端に合わせて離します。",
        "同時押しは細い線でつながります。長押し中でも、別レーンの通常ノーツを叩けます。",
        "PERFECT・GREAT・GOOD・MISS、スコア、コンボを表示します。結果の精度や最大コンボも狙ってみましょう。",
    ]),
    ("奥から手前へ流れる3D表示", "SETTINGS → レーン視点", "10_perspective", [
        "レーン視点を切り替えると、通常の平面表示と奥行きのある表示を選べます。",
        "3D表示でも入力キーと判定のルールは同じです。ノーツの大きさは奥から手前へ変わります。",
        "レーン視点と「プレイ表示」は別項目です。見やすい組み合わせを選んでください。",
        "画面の動きが重い場合は平面表示へ戻し、解像度やマスコット演出も調整してください。",
    ]),
    ("一時停止・再開", "ESCで一時停止", "05_pause", [
        "演奏中にESCを押すと一時停止します。再開もESCです。",
        "一時停止中はRでリトライ、Qで曲選択へ戻れます。練習中は練習設定へ戻ります。",
        "再開時は画面のカウントダウンを待ちます。押しっぱなしのキーはいったん離してから入力してください。",
        "ウィンドウを切り替えた後は、ゲームをクリックして操作対象に戻してから再開してください。",
    ]),
    ("結果を見る・もう一度遊ぶ", "RESULT", "11_result", [
        "ランク、スコア、正確さ、最大コンボ、各判定数を確認できます。マスコットの一言にも注目。",
        "Enter / Rで再挑戦、Dで同じ曲の難易度変更、Lでランキング、Gでギャラリーへ移動します。",
        "Sで結果画像を保存できます。保存先はゲーム内のメッセージを確認してください。ESCで曲選択へ戻ります。",
        "通常プレイのスコアはBPになります。新しい解放があれば通知が表示されます。",
    ]),
    ("設定を変更する", "SETTINGS", "06_settings", [
        "↑↓で項目選択、←→で値を変更します。選択肢のある項目には左右の三角印が表示されます。",
        "音楽・効果音の音量、ノーツ速度、判定幅、表示、解像度などを変更できます。変更後は「設定を保存」。",
        "効果音タイプを切り替えると試聴できます。マスコットやノーツデザインはプレビューで確認できます。",
        "LOCKEDは未解放です。条件を確認してからチュートリアルや通常プレイ、ショップへ進んでください。",
    ]),
    ("背景・演出を自分好みに", "見やすさを優先して調整", None, [
        "背景モードでビジュアライザーや画像背景を選べます。「背景画像」でEnterを押すと画像を選択できます。",
        "「背景透明度」を調整し、ノーツと判定ラインが背景に埋もれない明るさにしてください。",
        "マスコットとマスコット演出を設定できます。50コンボ刻みのカットインやフルコンボ時の演出は、同梱・設定された素材によって変わります。",
        "ノーツ配色とノーツデザインは別項目です。見やすい配色・形状をプレビューで選んでください。",
        "小さい画面では解像度とフルスクリーンを調整します。3D表示が重い場合は通常表示へ戻す方法もあります。",
        "設定の選択肢は解放状態と追加コンテンツによって異なります。追加素材は提供元の導入手順に従ってください。",
    ]),
    ("入力タイミングを合わせる", "Timing Offsetの測定", "07_calibration", [
        "設定の「入力タイミング測定」を開き、クリック音に合わせてSpaceを押します。",
        "測定後に推奨値が出たらAまたはEnterで適用できます。Rで再測定、ESCで設定へ戻ります。",
        "普段遊ぶスピーカー・イヤホンで測定してください。出力先を変えると遅延が変わる場合があります。",
        "一定の音ズレはOffsetで調整します。処理落ちのような不規則な引っ掛かりは表示設定も見直してください。",
    ]),
    ("練習とレーン数", "苦手な部分から少しずつ", None, [
        "TUTORIALは音源なしで基本操作を練習する入口です。初期状態は5 LANEとRHYTHMマスコットです。",
        "PRACTICEでは曲と練習区間を選び、繰り返し練習できます。練習の成績は通常プレイの記録やBPとは別です。",
        "3 LANEは5 LANEでC以下を3回、またはMISS率25%以上を3回で解放。別々の累計条件です。",
        "7 LANEは5 LANEでS以上を1回、またはA以上を3回で解放します。解放後は設定で切り替えます。",
        "初期キー：3 LANE = D / Space / K、5 LANE = D / F / Space / J / K。",
        "7 LANE = S / D / F / Space / J / K / L。設定で変更している場合は画面下のキー表示を優先してください。",
    ]),
    ("BPでアイテムを購入", "BEAT SHOP", "12_shop", [
        "タイトルのSHOP、またはBでショップへ。通常プレイで獲得したBPを使います。",
        "項目を選び、価格・所持BPを確認。「購入する」の後に「購入を確定」で確定します。購入するとBPを消費します。",
        "OWNEDは購入済み、NO ASSETは素材がなく購入できない状態です。商品は同梱素材により変わります。",
        "マスコットやご褒美画像などを購入できます。購入したマスコットは設定から選択します。",
        "同梱の効果音・背景設定・ノーツ配色やデザインには、チュートリアルで解放される項目もあります。",
    ]),
    ("ご褒美画像を楽しむ", "GALLERY", "08_gallery", [
        "タイトルのGALLERYから所有画像を確認できます。未解放の画像はロックされています。",
        "解放済みの画像を選んで開きます。画像表示からはESCで一覧へ戻れます。",
        "ショップや報酬の一覧で購入・解放状況を確認できます。価格と条件は画面の表示を優先してください。",
        "未解放の素材は雰囲気を出すためのロックです。暗号化による完全な保護ではありません。",
    ]),
    ("保存場所・困ったとき", "データを残して安心して更新", None, [
        "販売用バッチで作ったRC1版の設定・スコアは、通常 %APPDATA%\\AutoBeat5_Release_RC1 に保存されます。開発版は %APPDATA%\\AutoBeat5 です。",
        "ご褒美画像は配布先の rewards/locked から、解放時に rewards/unlocked へコピーされます。エクスプローラーからも確認できます。",
        "更新時は古いフォルダに上書きせず新しい場所へ展開。事前にAppDataの保存データと解放済み画像をバックアップしてください。",
        "音が出ないときはWindowsの出力先とミキサー、ゲームの音楽・効果音の音量を確認します。",
        "曲が読み込めない場合は元ファイルの存在・利用可能な形式を確認し、別の曲でも試してください。",
        "不具合を報告するときは、画面画像・解像度・レーン数・難易度・表示モード・再現操作を添えると調査しやすくなります。",
    ]),
]


def font(size: int):
    return ImageFont.truetype(str(FONT), size)


def wrap(draw, text, face, width):
    line = ""
    for char in text:
        if line and draw.textlength(line + char, font=face) > width:
            yield line
            line = ""
        line += char
    if line:
        yield line


def render_page(entry, index):
    title, subtitle, screenshot, paragraphs = entry
    page = Image.new("RGB", SIZE, (249, 251, 253))
    draw = ImageDraw.Draw(page)
    draw.rectangle((0, 0, 1600, 10), fill=ACCENT)
    draw.text((54, 30), title, font=font(42), fill=INK)
    draw.text((56, 91), subtitle, font=font(24), fill=MUTED)
    if screenshot:
        path = SCREENSHOTS / f"{screenshot}.png"
        with Image.open(path) as original:
            shot = original.convert("RGB")
        shot.thumbnail((1000, 642), Image.Resampling.LANCZOS)
        x, y = 54 + (1000 - shot.width) // 2, 155 + (642 - shot.height) // 2
        page.paste(shot, (x, y))
        draw.rectangle((x - 1, y - 1, x + shot.width, y + shot.height), outline=(195, 207, 217), width=1)
        columns = [(1090, 155, 450, paragraphs)]
        face, spacing = font(23), 34
    else:
        middle = (len(paragraphs) + 1) // 2
        columns = [(60, 175, 690, paragraphs[:middle]), (835, 175, 690, paragraphs[middle:])]
        face, spacing = font(28), 44
    for x, y, width, texts in columns:
        for text in texts:
            draw.rectangle((x, y + 10, x + 5, y + 27), fill=ACCENT)
            for line in wrap(draw, text, face, width - 24):
                if y + spacing > 816:
                    raise ValueError(f"Text overflow on page {index}: {title}")
                draw.text((x + 22, y), line, font=face, fill=INK)
                y += spacing
            y += 24
    draw.line((54, 837, 1546, 837), fill=(202, 214, 222))
    draw.text((56, 850), "オトアソビ | 好きな曲を、遊ぼう。 | 操作説明書", font=font(18), fill=MUTED)
    draw.text((1430, 850), f"{index:02d} / {len(PAGES):02d}", font=font(18), fill=MUTED)
    return page


def build_pdf() -> Path:
    pages = [render_page(entry, index) for index, entry in enumerate(PAGES, 1)]
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for index, page in enumerate(pages, 1):
        page.save(PREVIEWS / f"page-{index:02d}.png")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(OUTPUT, save_all=True, append_images=pages[1:], resolution=120.0,
                  title="オトアソビ 操作説明書", author="オトアソビ", quality=90)
    return OUTPUT


if __name__ == "__main__":
    print(build_pdf())
