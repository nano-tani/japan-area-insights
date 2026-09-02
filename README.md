# japan-area-insights

公的データを中心に、日本の街を価格・人口・将来人口・生活環境・交通・取引活性度などから比較するプロジェクトです。

## MVP

最初の対象は東京都23区です。

- データ取得・正規化・計算: Python + SQLite
- 公開: 静的HTML/CSS/JavaScript + 生成済みJSON
- 公開基盤: GitHub Pages
- AI: 説明文生成だけに使用し、スコア計算には使用しない
- 災害リスク: 総合点に混ぜず別表示

公開サイト側にAPIキーは置きません。公的APIはPython/GitHub Actions側で取得し、加工済みJSONだけを公開します。

## 開発

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e .[dev]
python scripts/init_db.py
python scripts/seed_areas.py
python scripts/build_site.py
pytest
```

生成物は `web/data/` に出力されます。

## 公的データ

### 不動産取引価格

不動産情報ライブラリ XIT001 を使用します。

```bash
python scripts/fetch_reinfolib_transactions.py --from-year 2021 --to-year 2026
```

### 地価公示・都道府県地価調査

不動産情報ライブラリ XPT002 を使用します。

```bash
python scripts/fetch_land_prices.py --from-year 2021 --to-year 2026
```

### 人口・世帯

e-Statの令和7年国勢調査速報集計を使用します。

- 表1-1 `0004050397`: 2025年人口
- 表1-2 `0004050417`: 2020年組替人口・世帯、2025年世帯、5年間増減率

```bash
python scripts/fetch_population.py
```

### 250mメッシュ将来人口

不動産情報ライブラリ XKT013 を使用します。国土数値情報「250mメッシュ別将来推計人口（R6国政局推計）」と同じデータを、東京23区のタイル範囲から取得します。

```bash
python scripts/fetch_future_population.py
```

CSV ZIPを直接取り込む `scripts/import_future_population.py` も予備経路として残しています。

### スコアと公開JSON

```bash
python scripts/compute_scores.py
python scripts/build_site.py
pytest
```

現時点の `v0.2` では、価格動向・人口動向・将来人口・取引活性度を相対評価できます。生活利便性と交通利便性が未実装のため、総合100点は意図的に算出しません。

## GitHub Actionsで実データを更新する

Repository Settings → Secrets and variables → Actions に次のRepository secretsを登録します。

- `REINFOLIB_API_KEY`: 不動産情報ライブラリのAPIキー
- `ESTAT_APP_ID`: e-StatのアプリケーションID

登録後、Actions → `Refresh public data` → `Run workflow` を実行します。

このWorkflowは、23区の取引価格・地価・2025年国勢調査速報・250m将来人口を取得し、SQLiteで集計・採点した後、`web/data/` の加工済みJSONだけをmainへ保存してGitHub Pagesへ公開します。秘密情報とSQLite本体は保存しません。

通常のPages公開は、すでに `web/data/` が存在する場合はそのスナップショットを使用します。そのためコード更新のたびに高コストな公的API取得を繰り返しません。

## ディレクトリ

- `src/japan_area_insights/`: データベース・計算・出力処理
- `scripts/`: 実行用スクリプト
- `database/`: SQLite（Git管理外）
- `web/`: GitHub Pagesで公開する静的サイト
- `docs/`: 仕様・データ出典
- `tests/`: 計算ロジックのテスト

## 注意

このサイトは投資助言を目的としません。スコアは対象地域内の相対評価であり、不動産価格の上昇や投資収益を保証するものではありません。
