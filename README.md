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

## ディレクトリ

- `src/japan_area_insights/`: データベース・計算・出力処理
- `scripts/`: 実行用スクリプト
- `database/`: SQLite（Git管理外）
- `web/`: GitHub Pagesで公開する静的サイト
- `docs/`: 仕様・データ出典
- `tests/`: 計算ロジックのテスト

## 注意

このサイトは投資助言を目的としません。スコアは対象地域内の相対評価であり、不動産価格の上昇や投資収益を保証するものではありません。
