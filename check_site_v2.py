#!/usr/bin/env python3
"""見本サイト v2（site/public）の検査。落ちたら終了コード1。標準ライブラリのみ。

使い方: python3 check_site_v2.py [公開フォルダ]   （省略時は同じ階層の public）
"""
import json
import logging
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")

DEFAULT_PUBLIC = Path(__file__).resolve().parent / "public"
PAGES = ["law/index.html", "privacy/index.html", "index.html", "flow/index.html", "board/index.html", "guide/index.html",
         "pay/index.html", "after/index.html", "owner/index.html", "admin/index.html"]
LINE_URL = "https://lin.ee/69OHrO3"
ROBOTS_META = "noindex,nofollow"
FORBIDDEN_TAGS = {"form", "input", "textarea"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
GOOD_PRICE = "〇〇,〇〇〇円"
# 円つきの金額表記（数字・〇・◯・漢数字などで始まる）を拾う
YEN_RE = re.compile(r"[0-9０-９〇◯,，.]+\s*円|[¥￥]")
# flow の8段それぞれの受け皿の文（方針書4章）
FLOW_CATCH = [
    "確かめる場所",
    "追加してから10〜20日のあいだ",
    "相談翌日に1回「予約はこちら」",
    "「他の日時を相談する」でノリさんへ",
    "24時間の仮押さえ・12時間前のお知らせ・期限切れで自動キャンセル",
    "前日のお知らせ（場所・持ち物）",
    "送った日から7日後に1回だけ",
    "1の入口へ戻る",
]
STAGE_NAMES = ["入口", "友だち追加", "無料相談", "予約", "事前払い", "当日〜翌朝", "提案", "紹介"]


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.text: list[str] = []
        self.title = ""
        self.metas: list[dict[str, str]] = []
        self.hrefs: list[str] = []
        self.has_band = False
        self.first_section_hrefs: list[str] = []
        self._in_title = False
        self._skip = 0
        self._main = False
        self._section_depth = 0
        self._sections_seen = 0
        self._in_first = False
        self.stylesheets: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append((tag, a))
        if tag == "meta":
            self.metas.append(a)
        if tag == "link" and a.get("rel") == "stylesheet":
            self.stylesheets.append(a.get("href", ""))
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag == "title":
            self._in_title = True
        if tag in ("script", "style"):
            self._skip += 1
        if "sample-band" in a.get("class", "").split():
            self.has_band = True
        if tag == "main":
            self._main = True
        if tag == "section" and self._main:
            self._sections_seen += 1
            if self._sections_seen == 1:  # トップではこれがヒーロー
                self._in_first = True
        if tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
            if self._in_first:
                self.first_section_hrefs.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style"):
            self._skip -= 1
        if tag == "section" and self._in_first:
            self._in_first = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.text.append(data)


IFRAME_SRC_RE = re.compile(r'<iframe[^>]*\ssrc="([^"]+)"')
ALLOWED_IFRAME_PREFIX = "https://www.google.com/maps?"

OFFICIAL_TEXT = "お支払い先をメールやLINEで変更することはありません"

# _headers に必ず入っているべき守りのヘッダー（名前と要の値）
REQUIRED_HEADERS = [
    "X-Robots-Tag: noindex, nofollow",
    "Content-Security-Policy: default-src 'self'",
    "frame-ancestors 'none'",
    "X-Frame-Options: DENY",
    "X-Content-Type-Options: nosniff",
    "Referrer-Policy:",
    "Strict-Transport-Security:",
]


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def parse(path: Path) -> Parser:
    p = Parser()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def check_common(name: str, p: Parser, errors: list[str]) -> None:
    if not p.has_band:
        errors.append(f"{name}: 「見本」帯(sample-band)がありません")
    if not any(m.get("name") == "robots" and m.get("content") == ROBOTS_META for m in p.metas):
        errors.append(f"{name}: noindex,nofollow の meta がありません")
    if not p.title.strip().startswith("【見本】"):
        errors.append(f"{name}: title が【見本】で始まっていません")
    for tag, _ in p.tags:
        if tag in FORBIDDEN_TAGS:
            errors.append(f"{name}: 禁止タグ <{tag}> があります")
    text = "".join(p.text)
    if "90分" in text or "90分" in p.title:
        errors.append(f"{name}: 「90分」が残っています")
    for m in YEN_RE.finditer(text):
        # 〇〇,〇〇〇円 の一部ならOK（直前までさかのぼって確認）
        start = m.start()
        if not text[max(0, start - 0): m.end()].endswith(GOOD_PRICE) and m.group().strip() != GOOD_PRICE:
            errors.append(f"{name}: 〇〇,〇〇〇円 以外の金額表記: {m.group()!r}")
    if text.count("円") != text.count(GOOD_PRICE):
        errors.append(f"{name}: 「円」の数が 〇〇,〇〇〇円 の数と合いません")


def check_assets(root: Path, name: str, p: Parser, errors: list[str]) -> None:
    """core.css 読込・analytics 不在・core.js に fetch が無いことを確かめる。"""
    if "/assets/core.css" not in p.stylesheets:
        errors.append(f"{name}: assets/core.css を読み込んでいません")
    raw = (root / name).read_text(encoding="utf-8").lower()
    if "analytics" in raw or any("analytics" in x.lower() for x in p.scripts):
        errors.append(f"{name}: analytics が含まれています")


def check_links(root: Path, name: str, p: Parser, errors: list[str]) -> None:
    for href in p.hrefs:
        if re.match(r"^(https?:|mailto:|tel:)", href):
            continue
        base = href.split("#")[0]
        if href.startswith("#") or not base:
            if href.startswith("#") and f'id="{href[1:]}"' not in (root / name).read_text(encoding="utf-8"):
                errors.append(f"{name}: ページ内リンク先がありません {href}")
            continue
        rel = base.lstrip("/")
        target = root / rel if rel else root / "index.html"
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            errors.append(f"{name}: 内部リンク切れ {href}")


def run(root: Path) -> list[str]:
    errors: list[str] = []
    parsed: dict[str, Parser] = {}
    for name in PAGES:
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: ファイルがありません")
            continue
        p = parse(path)
        parsed[name] = p
        check_common(name, p, errors)
        check_links(root, name, p, errors)
        check_assets(root, name, p, errors)
        if "/board/" not in p.hrefs:
            errors.append(f"{name}: /board/ へのリンクがありません")

    # セキュリティ：インラインのscriptを置かない（CSPで禁止しているため、置くと動かなくなる）
    for name in PAGES:
        path = root / name
        if path.is_file() and "<script>" in path.read_text(encoding="utf-8"):
            errors.append(f"{name}: インラインの <script> があります（CSPで止まります）")
    # 本物のサイトの直し（10/18点検）を見本にも入れる：プライバシーポリシーへのリンクと「公式の連絡先」の固定文
    for name in PAGES:
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if 'href="/privacy/"' not in text:
            errors.append(f"{name}: プライバシーポリシー（/privacy/）へのリンクがありません")
        if OFFICIAL_TEXT not in text:
            errors.append(f"{name}: 「公式の連絡先」の固定文がありません")
    # 埋め込みは Googleマップだけ許す（ほかのサイトの枠を入れない）
    for name in PAGES:
        path = root / name
        if path.is_file():
            for src in IFRAME_SRC_RE.findall(path.read_text(encoding="utf-8")):
                if not src.startswith(ALLOWED_IFRAME_PREFIX):
                    errors.append(f"{name}: 許可していない埋め込み {src[:60]}")
    if '<h2 class="section-title">場所</h2>' not in (root / "index.html").read_text(encoding="utf-8"):
        errors.append("index.html: 場所（Access）のセクションがありません")
    # 検索対策：トップに店舗情報の構造化データ（JSON-LD）が入っていて、壊れていないこと
    top_html = (root / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', top_html, re.S)
    if not m:
        errors.append("index.html: 店舗情報の構造化データ（JSON-LD）がありません")
    else:
        try:
            ld = json.loads(m.group(1))
            if "address" not in ld or ld.get("@type") not in ("ExerciseGym", "LocalBusiness", "SportsActivityLocation"):
                errors.append("index.html: 構造化データに店舗の種類か住所がありません")
        except ValueError:
            errors.append("index.html: 構造化データのJSONが壊れています")
    # 出荷前の必須（軍配の評価 D-019）：特商法の表記へのリンクが全ページにあること、お客さんの言葉は枠だけ（作った声を入れない）
    for name in PAGES:
        path = root / name
        if path.is_file() and 'href="/law/"' not in path.read_text(encoding="utf-8"):
            errors.append(f"{name}: 特定商取引法の表記（/law/）へのリンクがありません")
    if 'id="voice"' not in top_html:
        errors.append("index.html: お客さんの言葉（#voice）の枠がありません")
    # PDFとの整合（10/18）：お客さま向けのメニューにノリさん向けの画面を出さない／ノリさん向けの画面に注記／7日後の声かけの条件を全ページで同じに
    for name in PAGES:
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        m_nav = re.search(r'<nav class="nav".*?</nav>', text, re.S)
        if m_nav and re.search(r'href="/(board|guide|owner|admin)/"', m_nav.group(0)):
            errors.append(f"{name}: お客さま向けのメニューにノリさん向けの画面があります")
        if name.split("/")[0] in ("board", "owner", "admin", "guide") and 'class="nori-only"' not in text:
            errors.append(f"{name}: ノリさん向けの画面の注記（nori-only）がありません")
    for name in ("flow/index.html", "after/index.html", "board/index.html"):
        if "まだ申し込んでいない" not in (root / name).read_text(encoding="utf-8"):
            errors.append(f"{name}: 7日後の声かけの条件（まだ申し込んでいない方だけ）がありません")
    # セキュリティ：守りのヘッダーが _headers にそろっていること
    headers = root / "_headers"
    header_text = headers.read_text(encoding="utf-8") if headers.is_file() else ""
    for required in REQUIRED_HEADERS:
        if required not in header_text:
            errors.append(f"_headers: {required} がありません")

    js = root / "assets" / "core.js"
    if not js.is_file():
        errors.append("assets/core.js がありません")
    elif "fetch(" in js.read_text(encoding="utf-8"):
        errors.append("assets/core.js に fetch( があります（外部送信の疑い）")
    for f in (root / "assets").glob("*"):
        if "analytics" in f.name.lower():
            errors.append(f"assets に analytics のファイルがあります: {f.name}")

    idx = parsed.get("index.html")
    if idx:
        # 入口3つ：予約・相談はLINE（2つ）、「まだ迷う」はLINEに入れずページ内のレポート見本へ
        n = sum(1 for h in idx.first_section_hrefs if h == LINE_URL)
        if n != 2:
            errors.append(f"index.html: ヒーロー（最初のセクション）の lin.ee ボタンが {n} 個（2個必要）")
        if "#report" not in idx.first_section_hrefs:
            errors.append("index.html: ヒーローに「まだ迷う → レポートの見本」（#report）がありません")
        if 'id="report"' not in (root / "index.html").read_text(encoding="utf-8"):
            errors.append("index.html: レポート見本のセクションに id=\"report\" がありません")
    flow = parsed.get("flow/index.html")
    if flow:
        t = squash("".join(flow.text))
        for i, phrase in enumerate(FLOW_CATCH, 1):
            if squash(phrase) not in t:
                errors.append(f"flow: 段{i}の受け皿の文がありません: {phrase}")
    board = parsed.get("board/index.html")
    if board:
        t = squash("".join(board.text))
        for i, name in enumerate(STAGE_NAMES, 1):
            if squash(f"段{i}") not in t or squash(name) not in t:
                errors.append(f"board: 段{i}（{name}）がありません")
        if "すべて架空" not in t:
            errors.append("board: 「すべて架空」の明記がありません")
    return errors


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_PUBLIC
    try:
        errors = run(root)
    except Exception as exc:  # 検査器自体の失敗も落とす
        logging.error("検査中に例外: %s", exc)
        return 1
    if errors:
        print("NG:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK: {len(PAGES)}ページ すべて合格 ({root})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
