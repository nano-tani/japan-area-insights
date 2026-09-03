# 地理粒度拡張設計 v1.0

## 1. 目的

現在の東京都23区単位の比較を壊さず、将来的に次の粒度を同じサイト・同じデータ基盤で扱えるようにする。

- 区（ward）
- 駅エリア（station_area）
- 町丁目（neighborhood）
- 250mメッシュ（mesh250）

設計上の最重要方針は、すべての粒度に同じ100点スコアを無理に適用しないことと、位置精度が低いデータを細かい地域へ推測配分しないことである。

## 2. 結論

公開上の階層は次を基本とする。

```text
東京都23区
  ├─ 区
  │   ├─ 町丁目
  │   └─ 250mメッシュ地図
  └─ 駅エリア（区境をまたいでよい独立した比較単位）
```

駅エリアは区の子要素として固定しない。駅から1km圏は複数区にまたがることがあるため、駅エリアは独立した `geo_unit` とし、250mメッシュとの対応で範囲を定義する。

### スコア方針

| 粒度 | 総合100点 | ランキング | 主用途 |
|---|---|---|---|
| 区 | する | する | 都内全体比較 |
| 駅エリア | 条件付きでする | する | 物件探索・駅比較 |
| 町丁目 | 将来検討。初期は個別指標中心 | 条件付き | 住む場所の比較 |
| 250mメッシュ | しない | しない | 地図レイヤー・局所分析 |

250mメッシュでは、将来人口、施設アクセス、駅アクセス、地価ポイントなどを個別レイヤーとして表示する。取引件数不足や位置精度不足を理由に総合点は出さない。

## 3. 既存DBとの互換性

現在の `areas.area_id` は東京都23区の市区町村コードとして使用している。この意味は変更しない。

既存テーブルを一度に汎用化すると、現在動いている区スコア、公開JSON、GitHub Actionsを壊しやすいため、次の方式を採用する。

1. `areas` と既存の `area_*` テーブルは区単位の互換レイヤーとして維持する。
2. 新しい地理単位は `geo_units` 系テーブルへ追加する。
3. 生データはできるだけ位置情報・原典コードを保持する。
4. 新しい粒度の集計結果は `geo_metrics` / `geo_scores` に保存する。
5. 区のスコア移行は最後に行い、当面は現在の `area_scores` を正とする。

## 4. 新しい地理モデル

### 4.1 geo_units

すべての比較・表示単位を表す。

```sql
CREATE TABLE geo_units (
    geo_id TEXT PRIMARY KEY,
    geo_type TEXT NOT NULL,
    canonical_code TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_geo_id TEXT,
    primary_area_id TEXT,
    prefecture_code TEXT,
    latitude REAL,
    longitude REAL,
    radius_m INTEGER,
    definition_version TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (parent_geo_id) REFERENCES geo_units(geo_id),
    FOREIGN KEY (primary_area_id) REFERENCES areas(area_id),
    UNIQUE (geo_type, canonical_code, definition_version)
);
```

`geo_type` は初期段階では次のみ許可する。

- `ward`
- `station_area`
- `neighborhood`
- `mesh250`

`primary_area_id` は画面上の代表区を示す補助値であり、駅エリアの範囲制約には使用しない。

### 4.2 geo_unit_meshes

地理単位を250mメッシュの集合として定義する。

```sql
CREATE TABLE geo_unit_meshes (
    geo_id TEXT NOT NULL,
    mesh_id TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    method TEXT NOT NULL,
    distance_m REAL,
    PRIMARY KEY (geo_id, mesh_id),
    FOREIGN KEY (geo_id) REFERENCES geo_units(geo_id)
);
```

用途は次の通り。

- 区: XKT013の `SHICODE` で所属する全メッシュ
- 駅エリア: 駅中心から指定半径内のメッシュ
- 町丁目: 行政界ポリゴンとの包含または交差メッシュ
- 250mメッシュ: 自分自身1件

初期実装では `weight=1.0` の中心点包含方式でよい。町丁目の境界精度を上げる段階で面積按分用の `weight` を利用する。

### 4.3 geo_metrics

地理単位ごとの計算済み指標を保存する。

```sql
CREATE TABLE geo_metrics (
    geo_id TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    period TEXT NOT NULL,
    value REAL,
    sample_size INTEGER,
    source_id INTEGER,
    metric_version TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (geo_id, metric_key, period, metric_version),
    FOREIGN KEY (geo_id) REFERENCES geo_units(geo_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
```

例:

- `price_change_5y`
- `population_change_5y`
- `future_population_2045_ratio`
- `facilities_per_10k`
- `stations_per_100k`
- `lines_count`
- `ridership_per_capita`
- `transaction_count_5y`

`sample_size` を必須に近い扱いとし、スコア可否判定に使う。

### 4.4 geo_scores

新しい粒度のスコアを保存する。

```sql
CREATE TABLE geo_scores (
    geo_id TEXT NOT NULL,
    calculation_date TEXT NOT NULL,
    peer_group TEXT NOT NULL,
    price_score REAL,
    population_score REAL,
    future_population_score REAL,
    convenience_score REAL,
    transport_score REAL,
    transaction_score REAL,
    total_score REAL,
    confidence TEXT NOT NULL,
    data_completeness REAL,
    score_version TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    eligibility_reason TEXT,
    PRIMARY KEY (geo_id, calculation_date, score_version),
    FOREIGN KEY (geo_id) REFERENCES geo_units(geo_id)
);
```

`peer_group` を必ず保持する。区と駅を同じ母集団で順位付けしてはいけない。

例:

- `tokyo23:ward`
- `tokyo23:station_area:r1000`
- `tokyo23:neighborhood`

## 5. ID設計

人間向け名称を主キーにしない。名称変更・同名駅・表記揺れに耐えられるIDを使う。

推奨形式:

```text
ward:13113
station:<group_code>:r1000:v1
neighborhood:<official_code>:v1
mesh250:<mesh_id>
```

駅は XKT015 のグループコードを基本識別子とする。同じ駅名でも別駅扱いになるケースを名称で統合しない。

駅エリアの半径や定義を変えた場合、同じIDを上書きせず `definition_version` を上げる。

## 6. 駅エリアの定義

### 初期仕様

- 比較用半径: 1,000m
- 駅中心: XKT015の駅座標
- 範囲: 駅中心から1,000m以内に中心点を持つ250mメッシュ
- 東京23区境界外のメッシュ: MVPの駅比較では除外
- 区境をまたぐ場合: 両区の対象メッシュを含める

1kmを初期値とする理由は、500mより人口・施設・取引のサンプルが安定しやすく、徒歩圏としても説明しやすいため。

将来は表示用に500m圏を追加してよいが、スコア定義は混在させない。

## 7. データごとの細分化可否

| データ | 区 | 駅1km | 町丁目 | 250m |
|---|---|---|---|---|
| 将来人口 XKT013 | ◎ | ◎ | ◎ | ◎ |
| 学校・保育・医療・図書館・公共施設 | ◎ | ◎ | ◎ | ◎ |
| 駅・乗降客数 XKT015 | ◎ | ◎ | ◎ | ◎ |
| 地価公示 XPT002 | ◎ | ○ | ○ | 点データ表示 |
| 取引価格 XIT001 | ◎ | ◎（駅指定集計） | △ | × |
| 取引価格ポイント XPT001 | ◎ | ○ | △ | × |
| 国勢調査人口 | ◎ | 将来対応 | 将来対応 | 将来対応 |

### 取引価格に関する重要制約

XIT001は駅コードで検索できるため、駅単位の取引集計には利用できる。

一方、XPT001のポイントは実際の物件位置ではなく「対象不動産の最寄り駅のポイント」である。したがって、XPT001の座標を物件所在地とみなして町丁目や250mメッシュへ割り当ててはいけない。

また XIT001 の `DistrictCode` はデータ更新時に変更される可能性があり、過去との継続性が保証されていないため、町丁目の恒久IDとして直接利用しない。

## 8. スコア適格性

### 8.1 区

現在のv0.3を維持する。

### 8.2 駅エリア

初期の総合点表示条件を次とする。

- 6構成項目がすべて算出可能
- 直近5完了年の取引件数が30件以上
- 価格指標に利用できる年が3年以上
- 将来人口の2025年・2045年が取得可能
- 駅エリア内人口が0ではない

条件未達の場合は、算出可能な個別指標のみ表示して `総合点: データ不足` とする。

信頼度は区とは別基準にする。駅の取引件数を区の閾値と直接比較しない。

### 8.3 町丁目

初期リリースでは総合100点を出さない。

理由:

- 取引位置の精度に制約がある
- 地価公示点が存在しない町丁目が多い
- 人口境界データの整備が必要

まずは人口・将来人口・施設・交通・地価ポイントの個別表示から開始する。

### 8.4 250mメッシュ

総合点・ランキングを禁止する。

表示可能な例:

- 2025人口
- 2045人口
- 2045/2025人口維持率
- 500m以内施設数
- 最寄駅距離
- 最寄駅乗降客数
- 周辺地価公示点

## 9. 価格データの扱い

細分化後は区平均だけでなく、元の地価ポイントを保持する必要がある。

将来追加するテーブル例:

```sql
CREATE TABLE land_price_points (
    point_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    area_id TEXT NOT NULL,
    price_classification INTEGER NOT NULL,
    price REAL NOT NULL,
    latitude REAL,
    longitude REAL,
    mesh_id TEXT,
    source_id INTEGER,
    PRIMARY KEY (point_id, year, price_classification)
);
```

区の `area_prices` は引き続き集計結果として使い、駅・町丁目・メッシュでは `land_price_points` から対象範囲を集計する。

## 10. 取引データの扱い

現在の `transactions` は区コードと地区名を保持している。細分化に備え、取得元の値を削らず保存する方向へ変更する。

駅エリアの取引集計は、位置推定ではなく XIT001 の `station` パラメータを使う方式を優先する。

これにより「駅から1km以内の物件」と「最寄駅がその駅の取引」は意味が異なるため、画面上も区別する。

推奨表示文言:

```text
取引価格: この駅を検索条件として取得できる取引データを集計
生活・人口: 駅から1km圏のメッシュを集計
```

異なる集計定義を隠して1つの位置範囲として見せない。

## 11. 集計パイプライン

```text
公的API
  ↓
正規化済み生データ
  ├─ transactions
  ├─ land_price_points
  ├─ future_population(mesh)
  ├─ facilities(coords)
  └─ stations(coords)
  ↓
250mメッシュ割当
  ↓
geo_units / geo_unit_meshes生成
  ↓
geo_metrics生成
  ↓
スコア適格性判定
  ↓
同一peer_group内で相対採点
  ↓
geo_scores
  ↓
静的JSON出力
```

AIはこのパイプラインへ入れない。AIは最終的な説明文生成だけに使用する。

## 12. 公開JSON設計

現在の `web/data/area/{area_id}.json` は互換性のため残す。

新設するパスは次を基本とする。

```text
web/data/geo/index.json
web/data/geo/ward/{geo_id}.json
web/data/geo/station/{geo_id}.json
web/data/geo/neighborhood/{geo_id}.json
web/data/map/ward/{area_id}/mesh250.json
web/data/rankings/ward.json
web/data/rankings/station.json
```

ブラウザへSQLiteを配布せず、今まで通り必要なJSONのみ公開する。

## 13. UI設計

### 区ページ

現在の区スコアを維持し、次を追加する。

- 区内の主要駅一覧
- 250mメッシュ地図
- 町丁目一覧（導入後）

### 駅ページ

表示順:

1. 駅名・路線
2. 駅エリア総合点（適格時のみ）
3. 価格
4. 人口・将来人口
5. 施設
6. 交通
7. 取引件数
8. 1km圏メッシュ地図
9. 出典・集計定義

### 250m地図

レイヤー切替方式とする。

- 将来人口
- 人口維持率
- 地価
- 施設
- 交通
- 災害リスク（将来）

異なる単位の数値を足し合わせた「メッシュ総合点」は作らない。

## 14. URL方針

静的サイトのため、実装方式はJSルーティングまたは生成HTMLのどちらでもよいが、論理URLは次を目標とする。

```text
/ward/13113
/station/<station-group-code>
/neighborhood/<official-code>
```

250mメッシュ単体ページは初期段階では作らず、地図選択時のパネル表示にする。

## 15. 段階導入

### Phase A: 地理基盤

- `geo_units`
- `geo_unit_meshes`
- `geo_metrics`
- `geo_scores`
- 区23件を `geo_units` にミラー
- XKT013から250mメッシュ単位を登録

公開画面は変更しない。

### Phase B: 駅エリア

- XKT015から駅 `geo_units` を生成
- 1km圏メッシュ対応を生成
- XIT001の駅指定取得を追加
- 駅指標・駅スコア
- 駅比較・駅ランキング

### Phase C: 250m地図

- 区ページにメッシュ地図
- 将来人口レイヤー
- 施設・交通レイヤー
- 地価ポイント表示

### Phase D: 町丁目

- 公式境界データ選定
- 町丁目 `geo_units`
- メッシュとの空間対応
- 個別指標表示
- 十分なデータがある場合のみスコア導入を再検討

## 16. 完成条件

地理粒度拡張の基盤完成条件は次とする。

- 既存23区ページ・v0.3スコアを壊さない
- 区・駅・町丁目・メッシュをID上で混同しない
- 駅エリアが区境をまたげる
- 同じ粒度同士だけでランキングする
- 取引位置を推測して250mメッシュへ配分しない
- 総合点が不適格な地域は欠損を0点扱いしない
- 集計定義・半径・スコア定義をバージョン管理する
- すべての公開指標から出典を追跡できる

## 17. 今回は行わないこと

この設計段階では次は実装しない。

- 町丁目境界データの最終選定
- 250mメッシュの総合スコア
- 民間店舗データ
- 物件単位の評価
- AIによるスコア補完
- 推測による取引位置の生成

## 18. 次の実装単位

最初の実装PRは **Phase A: 地理基盤** に限定する。

既存画面を変更せずDBとビルド側だけに新しい地理モデルを追加し、23区と250mメッシュが同じ `geo_units` 基盤上で表現できることをテストする。その後に駅エリア実装へ進む。
