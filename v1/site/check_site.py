#!/usr/bin/env python3
"""見本サイト（site/public）の検査。1コマンドで全部見る。落ちたら終了コード1。

使い方（core-still のルートから）:
    python3 30-build/demo/site/check_site.py

正典は 30-build/demo/2026-10-17-demo-spec.md（第2・3・6章）と fixtures/demo-data.json。
外部ライブラリは使わない（標準ライブラリだけ）。
"""
import json
import logging
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")

SITE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = SITE_DIR / "public"
FIXTURES_PATH = SITE_DIR.parent / "fixtures" / "demo-data.json"
CSS_PATH = PUBLIC_DIR / "assets" / "style.css"

PAGES = ["index.html", "guide/index.html", "flow/index.html", "pay/index.html", "after/index.html",
         "owner/index.html", "admin/index.html"]
PAGES_WITH_LINE_BUTTON = ["index.html", "guide/index.html", "flow/index.html", "after/index.html"]
PAGES_WITH_CONTACT_LINK = ["index.html", "flow/index.html"]
LINKED_PAGES_FROM_GUIDE = ["/", "/flow/", "/pay/", "/after/", "/owner/", "/admin/"]
AFTER_PATH = "/after/"
# 設計書11章：ノリさん1人が初めて開く人、という視点で全ページにそろえる部品
REGION_CLASSES = ("reality", "feedback", "next-step", "route")  # 本番と見本の注記／感想の欄／次へ／見る順番
REALITY_LABELS = ("本番では", "この見本では")
FEEDBACK_TEXT = "好き／嫌／分からないを、そのまま誠さんに送ってください。"
PAGES_WITHOUT_REALITY = {"guide/index.html"}  # 入口のページは、注記ではなく「見方」そのものを書いている
NEXT_STEPS = {  # ページごとの「次へ」の行き先（どのページからも次に行く場所が1つ見える）
    "index.html": "/flow/",
    "guide/index.html": "/",
    "flow/index.html": "/pay/",
    "pay/index.html": "/after/",
    "after/index.html": "/owner/",
    "owner/index.html": "/admin/",
    "admin/index.html": "/guide/#decide",
}
GUIDE_ROUTE_ANCHORS = ["#customer", "#owner", "#decide"]  # 「A お客さまとして／B ノリさんとして／C 決めてほしいこと」
CONTACT_HREF_RE = re.compile(r"(?i)^(mailto|tel|sms):")
NAV_CLASSES = ("site-nav", "footer-nav")  # 上（ヘッダー）と下（フッター）のリンク欄
CHOOSE_TEXT = "選んでください"  # 設計書10章②：無料相談とアセスメントのどちらを入口にするか、サイトに書く

LINE_ADD_PLACEHOLDER = "{{LINE_ADD_URL}}"
ALLOWED_PLACEHOLDERS = {"LINE_ADD_URL", "SITE_URL"}
ROBOTS_META = "noindex,nofollow"
PAY_BOX_TEXT = "ここにカード払いの画面が出ます（見本・実際には決済されません）"
SENT_TEXT = "送信しました（見本）"
AUTO_NOTE = "自動で入ります（見本）"
NONE_MARK = "—"

# 設計書 第3章の表（この値だけを使う）
ALLOWED_COLORS = {"#0A0A0A", "#1A1A1C", "#FFFFFF", "#F7F7F8", "#6B6B70", "#E8E8EA", "#B8BCC2"}
SPEC_CSS_STRINGS = [
    '"Times New Roman", "Hiragino Mincho ProN", serif',
    '"Helvetica Neue", "Inter", "Hiragino Kaku Gothic ProN", sans-serif',
    "clamp(24px, 5vw, 80px)",
    "1240px",
]
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
FORBIDDEN_TAGS = {"form", "input", "textarea", "select"}
URL_ATTR_TAGS = {"script", "link", "img", "iframe", "source", "video", "audio", "embed", "object", "track"}
MEDICAL_WORDS = ["治る", "治す", "治療", "診断", "必ず痩せ", "痩せる", "病気", "症状"]
UNREPLACED_MARKERS = [r"\[\[.*?\]\]", r"\$\{.*?\}", r"\bTODO\b", r"\bFIXME\b", r"(?i)lorem ipsum"]

DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?")
SLOT_LABEL_RE = re.compile(r"\d{1,2}/\d{1,2}（[月火水木金土日]）\d{1,2}:\d{2}")
CUSTOMER_NAME_RE = re.compile(r"見本 [一-龥ぁ-んァ-ヶ]+")
PRICE_RE = re.compile(r"[0-9０-９][0-9０-９,，.]*\s*円|[¥￥]")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"0\d{1,4}-\d{1,4}-\d{3,4}")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
# 統合役が {{LINE_ADD_URL}} を差し替えたあとの公式LINEのURLも合格にする
LINE_URL_RE = re.compile(r"https://(lin\.ee|line\.me)/\S+")

Fixtures = dict[str, Any]


def squash(text: str) -> str:
    """空白をすべて除く（改行・<br>で分かれた文を同じ文として比べるため）。"""
    return re.sub(r"\s+", "", text)


class PageParser(HTMLParser):
    """HTMLから、検査に要る情報（タグ・文字・表・帯）だけを集める。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []  # (タグ名, 属性) を出てきた順に
        self.chunks: list[str] = []        # 文字のかたまり（スクリプト・スタイルは除く）
        self.title = ""
        self.body_first: tuple[str, dict[str, str]] | None = None  # <body>直下の最初の要素
        self.band_texts: list[str] = []    # 「見本」の帯の中の文字
        self.main_chunks: list[str] = []   # <main>の中の文字（フッターの注記に隠れた欠落を見逃さないため）
        self.tables: list[dict[str, Any]] = []  # {"caption", "headers", "rows"}
        self.nav_links: dict[str, list[str]] = {}  # <nav class="...">ごとのリンク先
        self.main_hrefs: list[str] = []    # <main>の中の<a>のリンク先（上下のリンク欄を除く）
        self.region_texts: dict[str, list[str]] = {c: [] for c in REGION_CLASSES}  # 注記・感想・次への文字
        self.region_counts: dict[str, int] = {c: 0 for c in REGION_CLASSES}        # その部品が何個あるか
        self.region_hrefs: dict[str, list[str]] = {c: [] for c in REGION_CLASSES}  # その部品の中の<a>のリンク先
        self.lists: list[list[str]] = []   # 箇条書き（ol・ul）ごとの、各項目の文字
        self._list_stack: list[list[str]] = []
        self._item: list[str] | None = None
        self._region_depth: dict[str, int] = {c: 0 for c in REGION_CLASSES}
        self._nav_class = ""
        self._skip = 0
        self._main_depth = 0
        self._in_title = False
        self._after_body = False
        self._band_depth = 0
        self._table: dict[str, Any] | None = None
        self._in_caption = False
        self._row: list[tuple[str, str, str | None]] | None = None
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v if v is not None else "") for k, v in attrs}
        self.tags.append((tag, attr_map))
        if self._after_body and tag != "body":
            self.body_first = (tag, attr_map)
            self._after_body = False
        if tag == "body":
            self._after_body = True
        if tag == "nav":
            self._nav_class = attr_map.get("class", "")
        elif tag == "a" and self._nav_class:
            self.nav_links.setdefault(self._nav_class, []).append(attr_map.get("href", ""))
        if tag in VOID_TAGS:
            return
        if self._band_depth:
            self._band_depth += 1
        elif "sample-band" in attr_map.get("class", "").split():
            self._band_depth = 1
        if self._main_depth:
            self._main_depth += 1
        elif tag == "main":
            self._main_depth = 1
        if tag == "a" and self._main_depth:
            self.main_hrefs.append(attr_map.get("href", ""))
        self._open_regions(tag, attr_map)
        self._open_structure(tag, attr_map)

    def _open_regions(self, tag: str, attrs: dict[str, str]) -> None:
        """注記（reality）・感想（feedback）・次へ（next-step）の中にいる間、文字を別に集める。"""
        classes = attrs.get("class", "").split()
        for region in REGION_CLASSES:
            if self._region_depth[region]:
                self._region_depth[region] += 1
            elif region in classes:
                self._region_depth[region] = 1
                self.region_counts[region] += 1
        if tag == "a":
            for region, depth in self._region_depth.items():
                if depth:
                    self.region_hrefs[region].append(attrs.get("href", ""))

    def _open_structure(self, tag: str, attrs: dict[str, str]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "table":
            self._table = {"caption": "", "headers": [], "rows": []}
        elif tag == "caption":
            self._in_caption = True
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = {"tag": tag, "label": attrs.get("data-label"), "parts": []}
        elif tag in ("ol", "ul"):
            self._list_stack.append([])
        elif tag == "li" and self._list_stack:
            self._item = []

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if self._band_depth:
            self._band_depth -= 1
        if self._main_depth:
            self._main_depth -= 1
        if tag == "nav":
            self._nav_class = ""
        for region in REGION_CLASSES:
            if self._region_depth[region]:
                self._region_depth[region] -= 1
        if tag in ("script", "style"):
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "caption":
            self._in_caption = False
        elif tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == "li" and self._item is not None and self._list_stack:
            self._list_stack[-1].append("".join(self._item).strip())
            self._item = None
        elif tag in ("ol", "ul") and self._list_stack:
            self.lists.append(self._list_stack.pop())

    def _close_cell(self) -> None:
        if self._cell is None or self._row is None:
            return
        text = "".join(self._cell["parts"]).strip()
        self._row.append((self._cell["tag"], text, self._cell["label"]))
        self._cell = None

    def _close_row(self) -> None:
        table, row = self._table, self._row
        self._row = None
        if table is None or not row:
            return
        if all(cell[0] == "th" for cell in row):
            table["headers"] = [cell[1] for cell in row]
        else:
            table["rows"].append(row)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        self.chunks.append(text)
        if self._in_title:
            self.title += text
        if self._band_depth:
            self.band_texts.append(text)
        if self._main_depth:
            self.main_chunks.append(text)
        for region, depth in self._region_depth.items():
            if depth:
                self.region_texts[region].append(text)
        if self._in_caption and self._table is not None:
            self._table["caption"] += text
        if self._cell is not None:
            self._cell["parts"].append(text)
        if self._item is not None:
            self._item.append(text)


class Page:
    """1ページ分の生HTMLと、その解析結果。"""

    def __init__(self, name: str, raw: str) -> None:
        self.name = name
        self.raw = raw
        parser = PageParser()
        parser.feed(raw)
        parser.close()
        self.p = parser
        self.squashed = squash("".join(parser.chunks))
        self.main_squashed = squash("".join(parser.main_chunks))

    def hrefs(self) -> list[str]:
        return [attrs["href"] for tag, attrs in self.p.tags if tag == "a" and "href" in attrs]


Pages = dict[str, Page]


def load_pages() -> tuple[Pages, list[str]]:
    """全ページを読む。読めないページは errors に積む（他の検査は続ける）。"""
    pages: Pages = {}
    errors: list[str] = []
    for name in PAGES:
        try:
            pages[name] = Page(name, (PUBLIC_DIR / name).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            logging.error("%s を読めません: %s", name, exc)
            errors.append(f"{name}: 読めません（{exc}）")
    return pages, errors


# ---------------------------------------------------------------- 各検査
# 各検査は「問題の文章のリスト」を返す。空なら合格。引数は (pages, fx) でそろえる。

def check_band_noindex_viewport(pages: Pages, _fx: Fixtures) -> list[str]:
    """全ページに「見本」の帯・noindexのmeta・viewportがある。"""
    errors = []
    for name, page in pages.items():
        first = page.p.body_first
        if not first or first[0] != "div" or "sample-band" not in first[1].get("class", "").split():
            errors.append(f"{name}: <body>の最初の要素が「見本」の帯（div.sample-band）ではありません")
        elif "見本" not in "".join(page.p.band_texts):
            errors.append(f"{name}: 帯の中に「見本」の文字がありません")
        if "見本" not in page.p.title:
            errors.append(f"{name}: <title>に「見本」がありません")
        metas = {a.get("name"): a.get("content", "") for t, a in page.p.tags if t == "meta" and a.get("name")}
        if metas.get("robots") != ROBOTS_META:
            errors.append(f'{name}: <meta name="robots" content="{ROBOTS_META}"> がありません')
        if "width=device-width" not in metas.get("viewport", ""):
            errors.append(f"{name}: viewport のmetaがありません")
    return errors


def is_external(url: str) -> bool:
    return bool(re.match(r"(?i)(https?:)?//", url.strip()))


def is_line_add_link(href: str) -> bool:
    """LINE追加ボタンのリンク：目印のまま、または差し替え後の公式LINEのURL。"""
    return href == LINE_ADD_PLACEHOLDER or bool(LINE_URL_RE.fullmatch(href))


def is_allowed_link(href: str, contact: str) -> bool:
    """外へ出てよい<a>：本物の問い合わせ窓口と、公式LINEのURLだけ。"""
    return href == contact or bool(LINE_URL_RE.fullmatch(href))


def check_no_external(pages: Pages, fx: Fixtures) -> list[str]:
    """外部のscript・link・img等が無い。外へ出る<a>は問い合わせ窓口と公式LINEだけ。"""
    errors = []
    contact = fx["business"]["contact_url"]
    for name, page in pages.items():
        for tag, attrs in page.p.tags:
            if tag == "script" and "src" in attrs:
                errors.append(f"{name}: <script src> は置けません（インラインのみ）: {attrs['src']}")
            if tag in URL_ATTR_TAGS:
                for key in ("src", "href", "data", "poster"):
                    if is_external(attrs.get(key, "")):
                        errors.append(f"{name}: 外部URLを読み込む<{tag}>があります: {attrs[key]}")
            if tag == "a" and is_external(attrs.get("href", "")) and not is_allowed_link(attrs["href"], contact):
                errors.append(f"{name}: 問い合わせ窓口・公式LINE以外の外部リンク: {attrs['href']}")
            if tag == "style" or "style" in attrs:
                errors.append(f"{name}: <style>・style属性は使いません（共通CSSだけ）")
        if re.search(r"(?i)url\(\s*['\"]?(https?:)?//|@import|gtag\(|googletagmanager|google-analytics", page.raw):
            errors.append(f"{name}: 外部読み込み・アクセス解析らしき記述があります")
    return errors


def check_no_form(pages: Pages, _fx: Fixtures) -> list[str]:
    """<form>・<input>などの入力欄が無い。"""
    errors = []
    for name, page in pages.items():
        for tag, attrs in page.p.tags:
            if tag in FORBIDDEN_TAGS:
                errors.append(f"{name}: <{tag}> があります（入力欄は置かない）")
            if "contenteditable" in attrs:
                errors.append(f"{name}: contenteditable があります（入力欄は置かない）")
    return errors


def added_point_strings(fx: Fixtures) -> dict[str, list[str]]:
    """設計書10章「追加の6点」の文字（fixturesの新しいキー）を、出るべきページごとに集める。"""
    free, follow, proposal = fx["free_consult"], fx["follow_ups"], fx["after_proposal"]
    referral, survey = fx["referral"], fx["survey"]
    email = fx["email_collection"]
    apply_, nudge, question = proposal["apply"], proposal["nudge"], proposal["question"]
    return {
        "guide": [free["decision_note"], email["where"], email["later_option"]],
        "flow": [
            free["name"], free["duration"], free["price_label"], free["summary"], free["decision_note"],
            *[slot["label"] for slot in free["slots"]], CHOOSE_TEXT,
            follow["intro"], *[t for item in follow["items"] for t in (item["when"], item["title"], item["text"])],
            referral["when"], referral["title"], referral["text"], referral["loop_note"],
            survey["question"], *survey["options"], survey["note"],
            email["title"], email["why"], email["where"], email["owner"], email["purpose"], email["later_option"],
        ],
        "pay": [
            *fx["pay_rules"].values(),
            email["where"], *email["form_fields"], email["purpose"], email["payers"], email["not_collected"],
        ],
        "after": [
            apply_["title"], *apply_["steps"], apply_["note"],
            nudge["when"], nudge["text"], question["title"], question["text"],
        ],
    }


def fixture_strings(fx: Fixtures) -> dict[str, list[str]]:
    """fixtures から、ページごとに「必ず表示されるべき文字」を作る。"""
    biz, menus, flow = fx["business"], fx["menus"], fx["flow"]
    added = added_point_strings(fx)
    menu_texts = [text for m in menus for text in (m["name"], m["duration"], m["price_label"], m["summary"])]
    day, report = fx["owner_day"], fx["report_sample"]
    names = {c["id"]: c["name"] for c in fx["customers"]}
    return {
        "index.html": [biz["slogan"], biz["area"], *menu_texts],
        "guide/index.html": [biz["line_account_name"], menus[0]["price_label"], *added["guide"]],
        "flow/index.html": [*menu_texts, *[t for s in flow for t in (s["title"], s["text"])], *added["flow"]],
        "pay/index.html": [menus[0]["name"], menus[0]["duration"], menus[0]["price_label"],
                           fx["slots"][0]["label"], PAY_BOX_TEXT, flow[1]["text"], *added["pay"]],
        "after/index.html": added["after"],
        "owner/index.html": [
            day["date"], day["morning"]["title"], *day["morning"]["items"],
            day["evening"]["title"], day["evening"]["note"], names[day["evening"]["customer_id"]],
            day["monday"]["title"], day["monday"]["week_of"], SENT_TEXT,
            report["date"], report["title"], *report["measure"], report["analyze"], *report["optimize"], report["next"],
        ],
        "admin/index.html": [],
    }


def monday_stats_string(fx: Fixtures) -> str:
    """月曜の数字カードに、この順で出るべき文字列（週の数字そのまま）。"""
    week = next(w for w in fx["weekly"] if w["week_of"] == fx["owner_day"]["monday"]["week_of"])
    entries = "".join(f"入口：{k}{v}件" for k, v in week["by_entry"].items())
    return f"新しい予約{week['new_bookings']}件アセスメント{week['assessments']}件契約{week['contracts']}件{entries}"


def check_fixture_texts(pages: Pages, fx: Fixtures) -> list[str]:
    """fixtures の名前・日時・料金表記・文面が、各ページに出ている。"""
    errors = []
    expected = fixture_strings(fx)
    for name, page in pages.items():
        # 見本の注記はフッター（全ページ）、それ以外は<main>の中に出ているべき
        # （フッターの注記に「〇〇,〇〇〇円」があるため、本文の欠落がフッターに隠れないようにする）
        for text in [fx["label"], fx["note"]]:
            if squash(text) not in page.squashed:
                errors.append(f"{name}: fixtures の文字が見つかりません: {text}")
        for text in expected.get(name, []):
            if squash(text) not in page.main_squashed:
                errors.append(f"{name}: 本文（main）に fixtures の文字が見つかりません: {text}")
    owner = pages.get("owner/index.html")
    if owner and squash(monday_stats_string(fx)) not in owner.main_squashed:
        errors.append(f"owner/index.html: 月曜の数字がfixturesと違います（期待: {monday_stats_string(fx)}）")
    if owner and not any("data-send" in a for t, a in owner.p.tags if t == "button"):
        errors.append("owner/index.html: ［送る］ボタン（button[data-send]）がありません")
    return errors


def check_expected_lists(pages: Pages, fx: Fixtures) -> list[str]:
    """短い項目名（お名前・メールアドレス・Instagram…）は他の文に紛れて通ってしまうので、箇条書きの中身そのものを比べる。"""
    email, survey, free = fx["email_collection"], fx["survey"], fx["free_consult"]
    expected = [
        ("pay/index.html", email["form_fields"], "予約・お申し込みでうかがう項目"),
        ("flow/index.html", survey["options"], "「何で知りましたか」の選択肢"),
        ("flow/index.html", [slot["label"] for slot in free["slots"]], "無料相談の枠の例"),
    ]
    errors = []
    for name, items, what in expected:
        page = pages.get(name)
        if page and items not in page.p.lists:
            errors.append(f"{name}: {what}の箇条書きがfixturesと違います（期待: {items}）")
    return errors


def check_links_and_buttons(pages: Pages, fx: Fixtures) -> list[str]:
    """LINE追加ボタン・問い合わせ窓口リンク・歩き方の行き先がある。"""
    errors = []
    contact = fx["business"]["contact_url"]
    for name in PAGES_WITH_LINE_BUTTON:
        if name in pages and not any(is_line_add_link(h) for h in pages[name].hrefs()):
            errors.append(f"{name}: LINE追加ボタン（href={LINE_ADD_PLACEHOLDER}）がありません")
    for name in PAGES_WITH_CONTACT_LINK:
        if name in pages and contact not in pages[name].hrefs():
            errors.append(f"{name}: 問い合わせ窓口（{contact}）へのリンクがありません")
    guide = pages.get("guide/index.html")
    for href in LINKED_PAGES_FROM_GUIDE:
        if guide and href not in guide.p.main_hrefs:
            errors.append(f"guide/index.html: 本文（手順の一覧）に {href} へのリンクがありません")
    for name, page in pages.items():
        for nav_class in NAV_CLASSES:
            if AFTER_PATH not in page.p.nav_links.get(nav_class, []):
                errors.append(f"{name}: {nav_class}（上下のリンク欄）に {AFTER_PATH} へのリンクがありません")
    return errors


def check_page_parts(name: str, page: Page) -> list[str]:
    """1ページ分：冒頭の注記・終わりの「次へ」と感想の欄。"""
    parser = page.p
    errors = []
    if name not in PAGES_WITHOUT_REALITY:
        reality = squash("".join(parser.region_texts["reality"]))
        enough = len(reality) > sum(len(label) for label in REALITY_LABELS) + 20  # ラベルだけで中身が空、を落とす
        if parser.region_counts["reality"] != 1 or not enough or any(squash(l) not in reality for l in REALITY_LABELS):
            errors.append(f"{name}: 冒頭に「本番では／この見本では」の注記（aside.reality）が1つ、中身つきで必要です")
    if squash(FEEDBACK_TEXT) not in squash("".join(parser.region_texts["feedback"])):
        errors.append(f"{name}: ページの終わりの感想の欄（.feedback）に「{FEEDBACK_TEXT}」が必要です")
    expected = NEXT_STEPS.get(name)
    next_hrefs = parser.region_hrefs["next-step"]
    if parser.region_counts["next-step"] != 1 or next_hrefs != [expected]:
        errors.append(f"{name}: 「次へ」（a.next-step）は1つで、行き先は {expected} です（今: {next_hrefs}）")
    return errors


def check_viewpoint_parts(pages: Pages, _fx: Fixtures) -> list[str]:
    """設計書11章：全ページにそろえる部品と、入口（見方）の道しるべがある。"""
    errors = []
    for name, page in pages.items():
        errors.extend(check_page_parts(name, page))
    guide = pages.get("guide/index.html")
    if guide and guide.p.region_hrefs["route"] != GUIDE_ROUTE_ANCHORS:
        errors.append(f"guide/index.html: 「見る順番」（ol.route）のリンクは {GUIDE_ROUTE_ANCHORS} の順にそろえます"
                      f"（今: {guide.p.region_hrefs['route']}）")
    return errors


def done_mark(flag: bool) -> str:
    return "済" if flag else "未"


def expected_admin_tables(fx: Fixtures) -> list[tuple[list[str], list[list[str]]]]:
    """管理表の4つの表。見出しと各行の文字を fixtures から組み立てる。"""
    names = {c["id"]: c["name"] for c in fx["customers"]}
    menus = {m["id"]: m["name"] for m in fx["menus"]}
    customers = [[c["name"], c["entry"], c["status"],
                  f"{c['week']}週目" if c["week"] is not None else NONE_MARK,
                  c["next"] or NONE_MARK, c["heard_from"], c["auto_contact"], c["email_status"]] for c in fx["customers"]]
    bookings = [[b["datetime"], names[b["customer_id"]], menus[b["menu_id"]],
                 done_mark(b["prepaid"]), done_mark(b["reminder_sent"]), b["payment_status"]] for b in fx["bookings"]]
    sales = [[s["date"], names[s["customer_id"]], s["item"], s["amount_label"], s["method"]] for s in fx["sales"]]
    entry_keys = list(fx["weekly"][0]["by_entry"].keys())
    weekly = [[w["week_of"], str(w["new_bookings"]), str(w["assessments"]), str(w["contracts"]),
               *[str(w["by_entry"][k]) for k in entry_keys]] for w in fx["weekly"]]
    return [
        (["名前", "入口", "状態", "90日の何週目", "次回", "何で知りましたか", "次の自動連絡", "メールアドレス"], customers),
        (["日時", "お客さま", "メニュー", "事前払い", "リマインド送信済み", "支払い状況"], bookings),
        (["入金日", "お客さま", "内容", "金額", "決済方法"], sales),
        (["週のはじまり", "新しい予約", "アセスメント", "契約", *[f"入口：{k}" for k in entry_keys]], weekly),
    ]


def check_admin_tables(pages: Pages, fx: Fixtures) -> list[str]:
    """/admin/ の表が fixtures と、見出し・行数・各セルまで一致する。"""
    page = pages.get("admin/index.html")
    if page is None:
        return []
    errors = []
    expected = expected_admin_tables(fx)
    tables = page.p.tables
    if len(tables) != len(expected):
        return [f"admin/index.html: 表が{len(tables)}個です（期待: {len(expected)}個）"]
    for i, (table, (headers, rows)) in enumerate(zip(tables, expected), start=1):
        if table["headers"] != headers:
            errors.append(f"admin 表{i}: 見出しが違います {table['headers']} ≠ {headers}")
        if table["caption"] != fx["label"]:
            errors.append(f"admin 表{i}: 表の頭に「{fx['label']}」がありません")
        if [[c[1] for c in row] for row in table["rows"]] != rows:
            errors.append(f"admin 表{i}: 行の中身がfixturesと違います（行数 {len(table['rows'])} / 期待 {len(rows)}）")
        if any([c[2] for c in row] != headers for row in table["rows"]):
            errors.append(f"admin 表{i}: スマホ表示用の data-label が見出しと違います")
    if page.main_squashed.count(squash(AUTO_NOTE)) != len(expected):
        errors.append(f"admin/index.html: 「{AUTO_NOTE}」が各表の見出し下に{len(expected)}つ必要です")
    return errors


def allowed_dates(fx: Fixtures) -> tuple[set[str], set[str]]:
    """fixtures に出てくる日付・日時・枠の表記すべて。"""
    dump = json.dumps(fx, ensure_ascii=False)
    found = set(DATETIME_RE.findall(dump))
    found |= {token.split(" ")[0] for token in found}
    return found, set(SLOT_LABEL_RE.findall(dump))


def check_no_invented_data(pages: Pages, fx: Fixtures) -> list[str]:
    """知らない名前・日時・金額・連絡先が無い（fixtures以外を作っていない）。"""
    errors = []
    names = [c["name"] for c in fx["customers"]]
    dates, labels = allowed_dates(fx)
    for name, page in pages.items():
        for chunk in page.p.chunks:
            for found in CUSTOMER_NAME_RE.findall(chunk):
                if not any(found.startswith(n) for n in names):
                    errors.append(f"{name}: fixturesに無いお客さま名: {found}")
            for token in DATETIME_RE.findall(chunk):
                if token not in dates:
                    errors.append(f"{name}: fixturesに無い日付・日時: {token}")
            for token in SLOT_LABEL_RE.findall(chunk):
                if token not in labels:
                    errors.append(f"{name}: fixturesに無い予約枠の表記: {token}")
            errors.extend(f"{name}: 具体的な金額は置けません: {token}" for token in PRICE_RE.findall(chunk))
        # メール様・電話様の文字列は、見える文字だけでなく属性（hrefなど）も含めて生のHTMLぜんぶを見る
        for rule, what in ((EMAIL_RE, "メールアドレス"), (PHONE_RE, "電話番号")):
            errors.extend(f"{name}: {what}は置けません: {token}" for token in rule.findall(page.raw))
        errors.extend(f"{name}: 連絡先リンク（mailto・tel）は置けません: {attrs['href']}"
                      for tag, attrs in page.p.tags if tag == "a" and CONTACT_HREF_RE.match(attrs.get("href", "")))
        errors.extend(f"{name}: 医療の言い方は使いません: {w}" for w in MEDICAL_WORDS if w in page.squashed)
    return errors


def check_placeholders(pages: Pages, _fx: Fixtures) -> list[str]:
    """{{LINE_ADD_URL}} と {{SITE_URL}} 以外の未置換の目印が無い。"""
    errors = []
    for name, page in pages.items():
        for found in PLACEHOLDER_RE.findall(page.raw):
            if found not in ALLOWED_PLACEHOLDERS:
                errors.append(f"{name}: 未置換の目印 {{{{{found}}}}}")
        for pattern in UNREPLACED_MARKERS:
            errors.extend(f"{name}: 未置換らしき記述: {m.group(0)}" for m in re.finditer(pattern, page.raw))
    return errors


def check_css(_pages: Pages, _fx: Fixtures) -> list[str]:
    """共通CSSが設計書 第3章の色・書体・余白だけを使い、外部を読み込まない。"""
    try:
        css = CSS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logging.error("CSS を読めません: %s", exc)
        return [f"assets/style.css: 読めません（{exc}）"]
    errors = []
    for color in re.findall(r"#[0-9A-Fa-f]{3,8}\b", css):
        if color.upper() not in ALLOWED_COLORS:
            errors.append(f"assets/style.css: 表にない色 {color}")
    if re.search(r"(?i)\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(", css):
        errors.append("assets/style.css: rgb()/hsl()等の色指定は使いません（表の16進だけ）")
    if re.search(r"(?i)@import|@font-face|url\(", css):
        errors.append("assets/style.css: @import・@font-face・url() は使いません（外部読み込みなし）")
    errors.extend(f"assets/style.css: 設計書の値が見つかりません: {s}" for s in SPEC_CSS_STRINGS if s not in css)
    return errors


def resolve_internal(href: str) -> Path:
    """/flow/ → public/flow/index.html のようにファイルへ直す。"""
    path = href.split("#")[0].split("?")[0]
    target = PUBLIC_DIR / path.lstrip("/")
    return target / "index.html" if path.endswith("/") or target.is_dir() else target


def check_internal_links(pages: Pages, _fx: Fixtures) -> list[str]:
    """サイト内のリンク・CSSの参照先と、ページ内リンク（#…）の行き先が実在する。"""
    errors = []
    for name, page in pages.items():
        ids = {attrs["id"] for _, attrs in page.p.tags if "id" in attrs}
        for tag, attrs in page.p.tags:
            href = attrs.get("href", "") if tag in ("a", "link") else ""
            if href.startswith("#") and len(href) > 1 and href[1:] not in ids:
                errors.append(f"{name}: ページ内リンクの行き先（id）がありません: {href}")
            if not href.startswith("/") or href.startswith("//") or "{{" in href:
                continue
            if not resolve_internal(href).is_file():
                errors.append(f"{name}: リンク先がありません: {href}")
    return errors


def check_robots_and_headers(_pages: Pages, _fx: Fixtures) -> list[str]:
    """robots.txt は全拒否、_headers は全パスに X-Robots-Tag: noindex。"""
    try:
        robots = (PUBLIC_DIR / "robots.txt").read_text(encoding="utf-8").splitlines()
        headers = (PUBLIC_DIR / "_headers").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logging.error("robots.txt / _headers を読めません: %s", exc)
        return [f"robots.txt / _headers が読めません（{exc}）"]
    errors = []
    robots = [line.strip() for line in robots]
    if "User-agent: *" not in robots or "Disallow: /" not in robots:
        errors.append("robots.txt: 「User-agent: *」と「Disallow: /」が必要です")
    rules = [line for line in headers if line.strip() and not line.lstrip().startswith("#")]
    if not any(url == "/*" and re.match(r"^[ \t]+X-Robots-Tag:\s*noindex", value) for url, value in zip(rules, rules[1:])):
        errors.append("_headers: 「/*」の次の行に、インデントして X-Robots-Tag: noindex が必要です")
    return errors


CHECKS: list[tuple[str, Callable[[Pages, Fixtures], list[str]]]] = [
    ("帯・noindex・viewport", check_band_noindex_viewport),
    ("外部script/link/img・解析なし", check_no_external),
    ("<form>/<input>なし", check_no_form),
    ("fixturesの文字が出ている", check_fixture_texts),
    ("箇条書きの中身", check_expected_lists),
    ("ボタン・リンク", check_links_and_buttons),
    ("全ページの注記・次へ・感想・見る順番", check_viewpoint_parts),
    ("管理表の中身", check_admin_tables),
    ("知らない名前・日時・金額なし", check_no_invented_data),
    ("未置換の目印なし", check_placeholders),
    ("共通CSSの色・書体", check_css),
    ("サイト内リンクの実在", check_internal_links),
    ("robots.txt・_headers", check_robots_and_headers),
]


def run_check(label: str, check: Callable[[Pages, Fixtures], list[str]], pages: Pages, fx: Fixtures) -> bool:
    """1つの検査を走らせて結果を表示する。合格ならTrue。"""
    try:
        errors = check(pages, fx)
    except Exception as exc:  # 検査自体の不具合も合格にしない
        logging.exception("検査 %s が途中で落ちました", label)
        errors = [f"検査が途中で落ちました: {type(exc).__name__}: {exc}"]
    print(f"{'NG' if errors else 'OK'}  {label}")
    for message in errors:
        print(f"      - {message}")
    return not errors


def main() -> int:
    try:
        fx = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logging.error("fixtures を読めません: %s", exc)
        return 1
    pages, load_errors = load_pages()
    print(f"検査対象: {len(pages)}/{len(PAGES)} ページ（{PUBLIC_DIR}）")
    failed = 0
    if load_errors:
        failed += 1
        print("NG  ページの読み込み")
        for message in load_errors:
            print(f"      - {message}")
    failed += sum(0 if run_check(label, check, pages, fx) else 1 for label, check in CHECKS)
    if failed:
        print(f"\nFAIL: {failed} 項目が不合格")
        return 1
    print(f"\nPASS: {len(CHECKS)} 項目すべて合格")
    return 0


if __name__ == "__main__":
    sys.exit(main())
