#!/usr/bin/env python3
"""check_site_v2.py をわざと壊して鳴ることを確かめる。まず無傷で合格→3種の破壊でそれぞれ失敗。"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK = HERE / "check_site_v2.py"
PUBLIC = HERE / "public"


def run(root: Path) -> int:
    return subprocess.run([sys.executable, str(CHECK), str(root)], capture_output=True, text=True).returncode


def mutate(tmp: Path, rel: str, old: str, new: str) -> None:
    f = tmp / rel
    s = f.read_text(encoding="utf-8")
    if old not in s:
        raise RuntimeError(f"置換元がありません: {rel} {old!r}")
    f.write_text(s.replace(old, new, 1), encoding="utf-8")


CASES = [
    ("noindex削除", "index.html", '<meta name="robots" content="noindex,nofollow">', ""),
    ("「90分」挿入", "pay/index.html", "60分（案）", "90分"),
    ("内部リンク切れ", "index.html", 'href="/flow/"', 'href="/nowhere/"'),
    ("analytics.js挿入", "index.html", '<script src="/assets/core.js"></script>',
     '<script src="/assets/analytics.js"></script><script src="/assets/core.js"></script>'),
    ("core.cssを外す", "flow/index.html", '<link rel="stylesheet" href="/assets/core.css">', ""),
    ("インラインscript挿入", "board/index.html", '<script src="/assets/core.js"></script>',
     '<script>alert(1)</script><script src="/assets/core.js"></script>'),
    ("プライバシーリンク削除", "flow/index.html", '<a href="/privacy/">Privacy</a>', ""),
    ("公式連絡先の文を削除", "after/index.html", "お支払い先をメールやLINEで変更することはありません", "（削除）"),
    ("ほかのサイトを埋め込む", "index.html", 'src="https://www.google.com/maps?', 'src="https://evil.example/?'),
    ("Accessセクション削除", "index.html", '<h2 class="section-title">場所</h2>', '<h2 class="section-title">ばしょ</h2>'),
    ("まだ迷うをLINEへ戻す", "index.html", '<a class="hero-link" href="#report">', '<a class="hero-link" href="https://lin.ee/69OHrO3">'),
    ("構造化データを壊す", "index.html", '"@type": "ExerciseGym",', '"@type": "ExerciseGym"'),
    ("特商法リンク削除", "flow/index.html", '<a href="/law/">Law</a>', ""),
    ("メニューにBoardを戻す", "flow/index.html", '<a href="/after/">After</a>\n', '<a href="/after/">After</a>\n    <a href="/board/">Board</a>\n'),
    ("ノリさん向け注記を消す", "admin/index.html", 'class="nori-only"', 'class="x"'),
    ("7日後の条件を消す", "after/index.html", "まだ申し込んでいない", "（削除）"),
    ("CSPヘッダー削除", "_headers", "Content-Security-Policy:", "X-Removed:"),
    ("枠埋め込み禁止を外す", "_headers", "X-Frame-Options: DENY", "X-Frame-Options: SAMEORIGIN"),
]


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix="selftest_v2_", dir=os.environ.get("TMPDIR")))
    failed = False
    try:
        clean = base / "clean"
        shutil.copytree(PUBLIC, clean)
        rc = run(clean)
        print(f"無傷コピー: 終了コード {rc}（期待 0）")
        failed |= rc != 0
        for label, rel, old, new in CASES:
            d = base / label.replace("「", "").replace("」", "")
            shutil.copytree(PUBLIC, d)
            mutate(d, rel, old, new)
            rc = run(d)
            ok = rc == 1
            print(f"{label}: 終了コード {rc}（期待 1） {'鳴った' if ok else '鳴らなかった!'}")
            failed |= not ok
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("セルフテスト:", "失敗" if failed else "合格")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
