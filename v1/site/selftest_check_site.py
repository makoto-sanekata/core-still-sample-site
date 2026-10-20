#!/usr/bin/env python3
"""check_site.py が「本当に鳴る」ことの確認（検査器の自己検査）。

site/ と fixtures/ を一時フォルダへ丸ごとコピーし、わざと壊した版を作って check_site.py にかける。
壊した版が「終了コード1」かつ「想定したメッセージ」で落ちなければ、この自己検査が失敗する。
本物のファイルには一切触らない。

使い方（core-still のルートから）:
    python3 30-build/demo/site/selftest_check_site.py
"""
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")

SITE_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SITE_DIR.parent / "fixtures"

Edit = Callable[[str], str]


def replace_once(old: str, new: str) -> Edit:
    """old を new に1回だけ置き換える。old が無ければ自己検査自体を失敗させる。"""
    def edit(text: str) -> str:
        if old not in text:
            raise ValueError(f"壊す対象が見つかりません: {old}")
        return text.replace(old, new, 1)
    return edit


def replace_all(old: str, new: str) -> Edit:
    """old を new にすべて置き換える（同じ言葉が複数箇所にあるとき、全部消して初めて「無い」状態にする）。"""
    def edit(text: str) -> str:
        if old not in text:
            raise ValueError(f"壊す対象が見つかりません: {old}")
        return text.replace(old, new)
    return edit


def regex_remove(pattern: str) -> Edit:
    def edit(text: str) -> str:
        result, count = re.subn(pattern, "", text, count=1, flags=re.S)
        if count == 0:
            raise ValueError(f"壊す対象が見つかりません: {pattern}")
        return result
    return edit


def regex_replace(pattern: str, replacement: str) -> Edit:
    def edit(text: str) -> str:
        result, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
        if count == 0:
            raise ValueError(f"壊す対象が見つかりません: {pattern}")
        return result
    return edit


def edit_inside_reality() -> Edit:
    """「本番では／この見本では」の注記の、説明文（dd）をすべて空にする（ラベルだけ残す）。"""
    def edit(text: str) -> str:
        match = re.search(r'<aside class="reality".*?</aside>', text, flags=re.S)
        if match is None:
            raise ValueError("注記（aside.reality）が見つかりません")
        emptied = re.sub(r"<dd>.*?</dd>", "<dd></dd>", match.group(0), flags=re.S)
        return text[:match.start()] + emptied + text[match.end():]
    return edit


def append_before(marker: str, addition: str) -> Edit:
    return replace_once(marker, addition + marker)


# (説明, 壊すファイル, 壊し方, 出力に含まれるべき文字)
MUTATIONS: list[tuple[str, str, Edit, str]] = [
    ("帯を1ページ消す", "public/flow/index.html", regex_remove(r'<div class="sample-band".*?</div>\n'), "flow/index.html: <body>の最初の要素"),
    ("帯から「見本」の文字を消す", "public/pay/index.html", regex_replace(r'<div class="sample-band".*?</div>\n', '<div class="sample-band" role="note">お知らせ</div>\n'), "帯の中に「見本」の文字がありません"),
    ("noindexのmetaを消す", "public/pay/index.html", regex_remove(r'<meta name="robots"[^>]*>\n'), "pay/index.html: <meta name=\"robots\""),
    ("viewportを消す", "public/owner/index.html", regex_remove(r'<meta name="viewport"[^>]*>\n'), "owner/index.html: viewport"),
    ("<form>を足す", "public/guide/index.html", append_before("</main>", "<form></form>"), "<form> があります"),
    ("<input>を足す", "public/guide/index.html", append_before("</main>", '<input type="text">'), "<input> があります"),
    ("外部scriptを足す", "public/index.html", append_before("</body>", '<script src="https://example.com/a.js"></script>'), "<script src>"),
    ("外部imgを足す", "public/index.html", append_before("</main>", '<img src="https://example.com/a.png" alt="">'), "外部URLを読み込む<img>"),
    ("外部フォントを足す", "public/index.html", append_before("</head>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">'), "外部URLを読み込む<link>"),
    ("解析タグを足す", "public/index.html", append_before("</body>", "<script>gtag('config','G-XXXX');</script>"), "アクセス解析らしき記述"),
    ("知らないお客さまを作る", "public/admin/index.html", replace_once("見本 一郎", "見本 次郎"), "fixturesに無いお客さま名: 見本 次郎"),
    ("日時を1つ書き換える", "public/admin/index.html", replace_once("2026-11-06 07:30", "2026-11-06 07:45"), "fixturesに無い日付・日時"),
    ("管理表の行を1つ消す", "public/admin/index.html", regex_remove(r'<tr><td data-label="名前">見本 直子</td>.*?</tr>\n'), "行の中身がfixturesと違います"),
    ("具体的な金額を書く", "public/flow/index.html", replace_once("〇〇,〇〇〇円", "9,800円"), "具体的な金額は置けません"),
    ("本文の料金表記を消す（フッターに残っていても落ちる）", "public/pay/index.html", replace_once("<dd>〇〇,〇〇〇円</dd>", "<dd></dd>"), "本文（main）に fixtures の文字が見つかりません: 〇〇,〇〇〇円"),
    ("流れの文を1つ消す", "public/flow/index.html", replace_once("カードで先にお支払い。当日の現金のやり取りはありません。", ""), "fixtures の文字が見つかりません"),
    ("知らない目印を残す", "public/index.html", replace_once("https://lin.ee/69OHrO3", "{{LINE_URL}}"), "未置換の目印 {{LINE_URL}}"),
    ("LINE追加ボタンの目印を消す", "public/flow/index.html", replace_once('href="https://lin.ee/69OHrO3"', 'href="/"'), "flow/index.html: LINE追加ボタン"),
    ("メールアドレスを書く", "public/index.html", replace_once("渋谷</dd>", "渋谷 info@example.com</dd>"), "メールアドレスは置けません"),
    ("医療の言い方を書く", "public/index.html", replace_once("計測し、分析し、最適化する。", "必ず痩せる。計測し、分析し、最適化する。"), "医療の言い方は使いません"),
    ("style属性を足す", "public/index.html", replace_once('<h1>', '<h1 style="color:red">'), "style属性は使いません"),
    ("リンク先を壊す", "public/guide/index.html", replace_once('href="/flow/"', 'href="/flowx/"'), "リンク先がありません: /flowx/"),
    ("CSSに表にない色を足す", "public/assets/style.css", replace_once("a { color: inherit; }", "a { color: #FF0000; }"), "表にない色 #FF0000"),
    ("CSSにrgba()を足す", "public/assets/style.css", replace_once("a { color: inherit; }", "a { color: rgba(0,0,0,.5); }"), "rgb()/hsl()等の色指定"),
    ("CSSに外部フォントを足す", "public/assets/style.css", replace_once("*, *::before", '@import url("https://fonts.googleapis.com/css2");\n*, *::before'), "@import・@font-face・url()"),
    ("robots.txtの全拒否を消す", "public/robots.txt", replace_once("Disallow: /", "Disallow:"), "robots.txt:"),
    ("_headersのnoindexを消す", "public/_headers", replace_once("X-Robots-Tag: noindex, nofollow", "X-Frame-Options: DENY"), "_headers:"),
    # ---- 設計書10章「追加の6点」で足した中身 ----
    ("新ページ /after/ に<form>を足す", "public/after/index.html", append_before("</main>", "<form></form>"), "after/index.html: <form> があります"),
    ("新ページ /after/ の帯を消す", "public/after/index.html", regex_remove(r'<div class="sample-band".*?</div>\n'), "after/index.html: <body>の最初の要素"),
    ("/after/ のLINEボタンを外す", "public/after/index.html", replace_once('href="https://lin.ee/69OHrO3"', 'href="/flow/"'), "after/index.html: LINE追加ボタン"),
    ("/after/ の声かけの文を消す", "public/after/index.html", replace_once("急がなくて大丈夫です。", ""), "本文（main）に fixtures の文字が見つかりません: レポートはご覧いただけましたか"),
    ("上（ヘッダー）の /after/ リンクを消す", "public/owner/index.html", regex_remove(r'      <a href="/after/">提案のあと</a>\n(?=      <a href="/guide/">ノリさんへ：見方</a>\n    </nav>)'), "owner/index.html: site-nav（上下のリンク欄）に /after/"),
    ("下（フッター）の /after/ リンクを消す", "public/pay/index.html", regex_remove(r'      <a href="/after/">提案のあと</a>\n(?=      <a href="/owner/">)'), "pay/index.html: footer-nav（上下のリンク欄）に /after/"),
    ("歩き方の一覧から /after/ へのリンクを外す", "public/guide/index.html", replace_once('href="/after/">提案のあとを開く', 'href="/flow/">提案のあとを開く'), "guide/index.html: 本文（手順の一覧）に /after/ へのリンクがありません"),
    ("flowの「選んでください」を消す", "public/flow/index.html", replace_all("選んでください", "お考えください"), "本文（main）に fixtures の文字が見つかりません: 選んでください"),
    ("flowの無料相談の枠を書き換える", "public/flow/index.html", replace_once("11/6（金）12:30", "11/6（金）13:30"), "fixturesに無い予約枠の表記: 11/6（金）13:30"),
    ("flowの自動連絡（7日後）を書き換える", "public/flow/index.html", replace_once("追加の7日後", "追加の8日後"), "本文（main）に fixtures の文字が見つかりません: 追加の7日後"),
    ("flowの「何で知りましたか」の選択肢を消す", "public/flow/index.html", replace_once("<li>Instagram</li>", ""), "本文（main）に fixtures の文字が見つかりません: Instagram"),
    ("flowのページ内リンクの行き先を壊す", "public/flow/index.html", replace_once('id="entrance"', 'id="entranc"'), "ページ内リンクの行き先（id）がありません: #entrance"),
    ("payの仮押さえの文を消す", "public/pay/index.html", replace_once("予約から24時間は、枠を仮押さえします。", ""), "本文（main）に fixtures の文字が見つかりません: 予約から24時間は"),
    ("ownerの朝の要点の新しい行を消す", "public/owner/index.html", regex_remove(r'              <li>新しい友だち 1人（Google から）。まだ予約はありません</li>\n'), "本文（main）に fixtures の文字が見つかりません: 新しい友だち 1人"),
    ("adminの新しい列の見出しを消す", "public/admin/index.html", replace_once("<th>何で知りましたか</th>", ""), "admin 表1: 見出しが違います"),
    ("adminの「何で知りましたか」の値を書き換える", "public/admin/index.html", replace_once("Instagram", "Facebook"), "admin 表1: 行の中身がfixturesと違います"),
    ("adminの支払い状況を書き換える", "public/admin/index.html", replace_once("未払い（期限 11/3 9:00）", "未払い（期限 11/3 12:00）"), "admin 表2: 行の中身がfixturesと違います"),
    # ---- 設計書11章「ノリさんが初めて開く人の視点」＋メールの集め方で足した中身 ----
    ("flowの冒頭の「本番では／この見本では」を消す", "public/flow/index.html", regex_remove(r'    <aside class="reality".*?</aside>\n'), "flow/index.html: 冒頭に「本番では／この見本では」の注記"),
    ("payの注記の中身を空にする（ラベルだけ残す）", "public/pay/index.html", edit_inside_reality(), "pay/index.html: 冒頭に「本番では／この見本では」の注記"),
    ("indexの注記を2つにする", "public/index.html", append_before("</main>", '<aside class="reality"><dl><div><dt>本番では</dt><dd>ふたつめの注記をわざと足した、長めの文です。</dd></div></dl></aside>'), "index.html: 冒頭に「本番では／この見本では」の注記"),
    ("ownerの感想の文を書き換える", "public/owner/index.html", replace_once("そのまま誠さんに送ってください", "そのまま教えてください"), "owner/index.html: ページの終わりの感想の欄"),
    ("indexの感想の欄を消す", "public/index.html", regex_remove(r'  <section class="section section--tint feedback">.*?</section>\n'), "index.html: ページの終わりの感想の欄"),
    ("guideの感想の欄を消す", "public/guide/index.html", regex_remove(r'  <section class="section section--tint feedback">.*?</section>\n'), "guide/index.html: ページの終わりの感想の欄"),
    ("adminの「次へ」の行き先を変える", "public/admin/index.html", replace_once('class="next-step" href="/guide/#decide"', 'class="next-step" href="/guide/"'), "admin/index.html: 「次へ」"),
    ("afterの「次へ」を消す", "public/after/index.html", regex_remove(r'  <section class="section wrap tail">.*?</section>\n'), "after/index.html: 「次へ」"),
    ("flowの「次へ」を2つにする", "public/flow/index.html", append_before("</main>", '<a class="next-step" href="/pay/">もうひとつ</a>'), "flow/index.html: 「次へ」"),
    ("guideの道しるべ（C 決めてほしいこと）を外す", "public/guide/index.html", replace_once('<a href="#decide"><span class="route__no">C</span>決めてほしいこと</a>', "決めてほしいこと"), "guide/index.html: 「見る順番」（ol.route）のリンク"),
    ("guideの行き先（id=decide）を壊す", "public/guide/index.html", replace_once('id="decide"', 'id="decid"'), "ページ内リンクの行き先（id）がありません: #decide"),
    ("guideの「決めてほしいこと」の文を消す", "public/guide/index.html", replace_once("有料アセスメントの手前に置くか、並べるか、置かないか、ノリさんが選んでください。", ""), "本文（main）に fixtures の文字が見つかりません: 有料アセスメントの手前に"),
    ("payの「健康のことは聞かない」の文を消す", "public/pay/index.html", replace_once("既往歴・服薬などの健康のことは、この画面では聞きません（別の場所で、同意のうえ分けて扱います）。", ""), "本文（main）に fixtures の文字が見つかりません: 既往歴・服薬などの健康のことは"),
    ("payの「うかがう項目」からメールアドレスを消す", "public/pay/index.html", replace_once("<li><p>メールアドレス</p></li>\n        ", ""), "pay/index.html: 予約・お申し込みでうかがう項目の箇条書きがfixturesと違います"),
    ("payの項目の見本に<input>を足す", "public/pay/index.html", replace_once("<li><p>お名前</p></li>", '<li><p>お名前</p><input type="text"></li>'), "pay/index.html: <input> があります"),
    ("payにmailtoリンクを足す", "public/pay/index.html", append_before("</main>", '<a href="mailto:test">メールする</a>'), "pay/index.html: 連絡先リンク（mailto・tel）は置けません"),
    ("payに実在風のメールアドレスを書く", "public/pay/index.html", replace_once("<li><p>お名前</p>", "<li><p>お名前 taro@example.com</p>"), "pay/index.html: メールアドレスは置けません"),
    ("flowの名簿の説明（why）を消す", "public/flow/index.html", replace_once("メールアドレスも集めておくと、LINEと別に、ノリさん自身の名簿が残ります。", ""), "本文（main）に fixtures の文字が見つかりません: LINEの友だちだけだと"),
    ("flowの「あとで考える方法」の文を消す", "public/flow/index.html", replace_once("本番に進むと決まってから考えます。", ""), "本文（main）に fixtures の文字が見つかりません: LINEの画面の中で1タップ"),
    ("flowの「何で知りましたか」の箇条書きを1つ減らす", "public/flow/index.html", replace_once("<li>その他</li>", ""), "flow/index.html: 「何で知りましたか」の選択肢の箇条書きがfixturesと違います"),
    ("adminのメールアドレス列の見出しを消す", "public/admin/index.html", replace_once("<th>メールアドレス</th>", ""), "admin 表1: 見出しが違います"),
    ("adminのメールアドレス列の値を書き換える", "public/admin/index.html", replace_once("入力済み（ダミー）", "入力済み"), "admin 表1: 行の中身がfixturesと違います"),
]

# ページを1枚まるごと消した場合（説明, 消すページ）
PAGE_REMOVALS: list[tuple[str, str]] = [
    ("ページを1枚消す（owner）", "owner/index.html"),
    ("新ページ /after/ を消す", "after/index.html"),
]


def copy_site(tmp_root: Path) -> Path:
    """site/ と fixtures/ を、本物と同じ相対配置で一時フォルダへコピーする。"""
    site_copy = tmp_root / "site"
    shutil.copytree(SITE_DIR, site_copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(FIXTURES_DIR, tmp_root / "fixtures")
    return site_copy


def run_check(site_copy: Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(site_copy / "check_site.py")], capture_output=True, text=True, check=False)
    return result.returncode, result.stdout + result.stderr


def run_mutation(description: str, rel_path: str, edit: Edit, expected: str) -> bool:
    """壊した版を作って検査にかけ、想定どおり落ちたらTrue。"""
    with tempfile.TemporaryDirectory() as tmp:
        site_copy = copy_site(Path(tmp))
        target = site_copy / rel_path
        try:
            target.write_text(edit(target.read_text(encoding="utf-8")), encoding="utf-8")
        except (OSError, ValueError) as exc:
            logging.error("%s: 壊せませんでした: %s", description, exc)
            print(f"NG  {description}: 壊せませんでした（{exc}）")
            return False
        code, output = run_check(site_copy)
    detected = code == 1 and expected in output
    print(f"{'OK ' if detected else 'NG '} {description} → 終了コード{code}" + ("" if detected else f"（想定メッセージ「{expected}」が出ていません）"))
    return detected


def run_missing_page(description: str, page: str) -> bool:
    """ページが1枚まるごと無い場合も落ちる。"""
    with tempfile.TemporaryDirectory() as tmp:
        site_copy = copy_site(Path(tmp))
        (site_copy / "public" / page).unlink()
        code, output = run_check(site_copy)
    detected = code == 1 and f"{page}: 読めません" in output
    print(f"{'OK ' if detected else 'NG '} {description} → 終了コード{code}")
    return detected


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        code, output = run_check(copy_site(Path(tmp)))
    if code != 0:
        print(f"NG  壊していないコピーが合格しません（終了コード{code}）\n{output}")
        return 1
    print("OK  壊していないコピーは合格（終了コード0）")
    results = [run_mutation(*m) for m in MUTATIONS] + [run_missing_page(*r) for r in PAGE_REMOVALS]
    missed = results.count(False)
    if missed:
        print(f"\nFAIL: {missed} 件の「わざと壊した版」を検査が見逃した／壊せなかった")
        return 1
    print(f"\nPASS: わざと壊した {len(results)} 通りすべてで check_site.py が落ちた")
    return 0


if __name__ == "__main__":
    sys.exit(main())
