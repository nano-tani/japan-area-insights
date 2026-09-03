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

## 地理粒度拡張

区より細かい分析は、区・駅エリア・町丁目・250mメッシュを同一基盤で扱う方針です。駅エリアは区境をまたげる独立した比較単位とし、250mメッシュには無理に総合点を付けません。

全体設計: [`docs/AREA_GRANULARITY_DESIGN.md`](docs/AREA_GRANULARITY_DESIGN.md)

### Phase A: 地理基盤

Phase Aは実装済みです。既存の区単位DBを壊さず、次の汎用テーブルを追加しています。

- `geo_units`: 区・駅エリア・町丁目・250mメッシュの共通マスタ
- `geo_unit_meshes`: 各地理単位を250mメッシュ集合で定義
- `geo_metrics`: 粒度別の計算済み指標
- `geo_scores`: 粒度別・比較母集団別のスコア

XKT013の将来人口を取得した後に次を実行すると、23区と250mメッシュを新しい地理モデルへ同期します。

```bash
python scripts/sync_geo_units.py
```

同期処理は、区を `ward:<市区町村コード>`、250mメッシュを `mesh250:<メッシュコード>` として登録し、XKT013の `SHICODE` に基づく区→メッシュ対応を保存します。250mメッシュの中心座標もメッシュコードから再現して保持します。

### Phase B: 駅エリア

Phase BではXKT015の駅グループコードごとに駅中心1km圏を生成します。駅エリアは区境をまたぐことができ、1km以内に中心点を持つ250mメッシュの集合として管理します。

詳細設計: [`docs/STATION_AREA_DESIGN.md`](docs/STATION_AREA_DESIGN.md)

```bash
python scripts/sync_station_areas.py
python scripts/fetch_station_transactions.py --from-year 2021 --to-year 2026
python scripts/compute_station_scores.py
python scripts/build_site.py
```

駅の価格・取引活性度は、物件位置を1km圏へ推測配分せず、不動産情報ライブラリXIT001を駅グループコードで検索して取得します。駅ページは `web/stations.html`、公開JSONは `web/data/geo/` と `web/data/rankings/station.json` に生成します。

駅スコアは区スコアとは別の比較母集団です。駅の人口動向v0.1は、細粒度の2025年国勢調査実績を未導入のため、XKT013の2020年人口→2025年推計人口の変化を暫定利用し、画面上も「人口動向（推計）」と明記します。

## 開発

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -e .[dev]
python scripts/init_db.py
python scripts/seed_areas.py
python scripts/sync_geo_units.py
python scripts/sync_station_areas.py
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

駅エリアでは同じXIT001を `station=<駅グループコード>` で取得します。標準では当年途中を除外し、完了年までを取得します。

```bash
python scripts/fetch_station_transactions.py --from-year 2021 --to-year 2026
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
python scripts/sync_geo_units.py
```

CSV ZIPを直接取り込む `scripts/import_future_population.py` も予備経路として残しています。

### 生活利便施設

不動産情報ライブラリの国土数値情報APIを使用します。

- XKT006: 学校
- XKT007: 保育園・幼稚園等
- XKT010: 医療機関
- XKT017: 図書館
- XKT018: 市区町村役場・集会施設等

```bash
python scripts/fetch_facilities.py
```

生活利便性は、各カテゴリの施設数を人口で割った「1万人あたり施設数」を相対評価し、各カテゴリの順位を均等に合成します。区スコアは23区内、駅スコアは駅1km圏同士で別々に順位付けします。

XKT006の幼稚園・こども園はXKT007と重複しやすいため、学校カテゴリから除外します。XKT017は元データ上、大学図書館等を含む可能性があるため、個々の施設が一般利用可能であることまでは意味しません。

### 交通

不動産情報ライブラリ XKT015「駅別乗降客数」を使用します。

```bash
python scripts/fetch_transport.py
```

区の交通利便性は次の3指標を23区内で相対評価し、均等に合成します。

- 人口10万人あたり駅数
- 区内の路線数
- 駅別乗降客数 ÷ 人口

駅エリアも同じ3系統を使いますが、対象は駅中心1km圏であり、人口にはXKT013の2025年推計人口を使います。

駅の区への割当は、駅座標を約250mの4分の1地域メッシュへ変換し、XKT013の `MESH_ID` → `SHICODE` 対応を利用します。行政界付近の駅では、厳密な境界ポリゴンによる判定と異なる場合があります。

### スコアと公開JSON

```bash
python scripts/compute_scores.py
python scripts/compute_station_scores.py
python scripts/build_site.py
pytest
```

区の `v0.3` 総合100点は次の6項目で構成します。

- 価格動向: 20点
- 人口動向: 20点
- 将来人口: 20点
- 生活利便性: 15点
- 交通利便性: 15点
- 取引活性度: 10点

各項目は同じ粒度・同じ比較母集団の中で相対評価します。必要な6項目のどれかが欠ける場合は、欠損を0点扱いせず総合点を算出しません。

駅の `station-v0.1` も100点構成ですが、区とは入力指標・適格条件・peer groupが異なります。駅総合点は、6項目完備、直近5完了年の取引30件以上、価格3年以上などの条件を満たす場合だけ表示します。

## GitHub Actionsで実データを更新する

Repository Settings → Secrets and variables → Actions に次のRepository secretsを登録します。

- `REINFOLIB_API_KEY`: 不動産情報ライブラリのAPIキー
- `ESTAT_APP_ID`: e-StatのアプリケーションID

登録後、Actions → `Refresh public data` → `Run workflow` を実行します。

このWorkflowは、23区の取引価格・地価・2025年国勢調査速報・250m将来人口・生活利便施設・駅/乗降客数を取得し、地理基盤と駅1km圏を同期します。その後、駅グループコード別XIT001取引履歴を取得し、区スコア・駅スコア・公開JSONを生成してGitHub Pagesへ公開します。秘密情報とSQLite本体は保存しません。

駅指定XIT001は駅数×年数のAPIリクエストが必要なため、通常の区データ更新より時間がかかります。Workflowのタイムアウトは180分に設定しています。

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
