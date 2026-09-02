# japan-area-insights

公的データを中心に、日本の街を価格・人口・将来人口・生活環境・交通・取引活性度などから比較するプロジェクトです。

## MVP

最初の対象は東京都23区です。

- データ取得・正規化・計算: Python + SQLite
- 公開: 静的HTML/CSS/JavaScript + 生成済みJSON
- 公開基盤: GitHub Pages
- AI: 説明文生成だけに使用し、スコア計算には使用しない
- 災害リスク: 総合点に混ぜず別表示

公開サイト側にAPIキーは置きません。公的APIはPython側で取得し、加工済みJSONだけを公開します。

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

## 公的データの取得

国土交通省「不動産情報ライブラリ」のAPIキーと、e-StatのアプリケーションIDを環境変数へ設定します。秘密情報はリポジトリへコミットしません。

PowerShell:

```powershell
$env:REINFOLIB_API_KEY="発行されたAPIキー"
$env:ESTAT_APP_ID="発行されたアプリケーションID"
```

macOS / Linux:

```bash
export REINFOLIB_API_KEY="発行されたAPIキー"
export ESTAT_APP_ID="発行されたアプリケーションID"
```

### 不動産取引価格

```bash
python scripts/fetch_reinfolib_transactions.py --from-year 2021 --to-year 2025
```

XIT001から取引明細、平方メートル単価の平均・中央値、取引件数を保存します。

### 地価公示・都道府県地価調査

```bash
python scripts/fetch_land_prices.py --from-year 2020 --to-year 2026
```

XPT002を東京23区の範囲で取得し、市区ごとの平均地価と前年比・3年・5年変化率を保存します。

### 2025年国勢調査速報

```bash
python scripts/fetch_population.py
```

e-Statの令和7年国勢調査速報集計、表1-1（0004050397）と表1-2（0004050417）から2025年人口・世帯数・5年間増減率と、組替済み2020年人口・世帯数を保存します。

### 250mメッシュ将来人口

国土数値情報の「250mメッシュ別将来推計人口（R6国政局推計）」から東京都CSV ZIP `250m_mesh_suikei_2024_csv_13.zip` を取得し、次を実行します。

```bash
python scripts/import_future_population.py path/to/250m_mesh_suikei_2024_csv_13.zip
```

2020年から2070年までの5年刻みの推計人口を、250mメッシュ単位でSQLiteへ保存します。公開JSONでは23区単位へ集約します。

### スコアと公開JSON

```bash
python scripts/compute_scores.py
python scripts/build_site.py
pytest
```

現時点の `v0.2` では、価格動向・人口動向・将来人口・取引活性度を相対評価できます。生活利便性と交通利便性が未実装のため、総合100点は意図的に算出しません。未実装項目を0点扱いして見かけだけの総合点を作ることはしません。

## ディレクトリ

- `src/japan_area_insights/`: データベース・計算・出力処理
- `scripts/`: 実行用スクリプト
- `database/`: SQLite（Git管理外）
- `web/`: GitHub Pagesで公開する静的サイト
- `docs/`: 仕様・データ出典
- `tests/`: 計算ロジックのテスト

## 注意

このサイトは投資助言を目的としません。スコアは対象地域内の相対評価であり、不動産価格の上昇や投資収益を保証するものではありません。
