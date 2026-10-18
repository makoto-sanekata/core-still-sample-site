# CORE STILL 見本サイト（予約までの流れの案）

株式会社CORE STILL（代表 古川 巨久さん）のサイトをもとに、初めて来た方が初回予約まで進みやすい流れを試すために作った見本サイトです。公開は古川さんの了解を得ています。

- 公開中の見本：https://cs-sample-v2-3ed55e1b.makoto-net1210.workers.dev
- 本物のサイト：https://core-still.com/

## 見本であること

- 予約、支払い、自動のお知らせ、LINE配信、レポートの送信は動きません。画面と文面の見本です。
- お客さまの名前と数字は、すべて架空です。料金は〇〇,〇〇〇円の仮表示です。
- Guide・Board・Owner・Admin はノリさん向けの画面の見本で、本番ではお客さまに見せない想定です。
- `public/assets/core.css` と `core.js` は、本物のサイト（core-still.com）のデザインをそのまま使っています。

## 構成

- `public/` … 公開するファイル（静的HTML）
- `check_site_v2.py` … 見本の検査（見本の表示、noindex、金額表記、リンク切れ、セキュリティヘッダーなど）
- `selftest_check_site_v2.py` … 検査をわざと壊して、ちゃんと不合格になるかを確かめる

## 確かめ方

```bash
python3 check_site_v2.py
python3 selftest_check_site_v2.py
```

## 公開のしかた（Cloudflare Workers の静的アセット）

```bash
npx wrangler deploy --assets ./public --name <ワーカー名> --compatibility-date 2026-10-01
```
