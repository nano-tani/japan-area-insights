from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from .page_quality import station_page_quality
from .site_config import SITE_DESCRIPTION, SITE_NAME, absolute_url


@dataclass(frozen=True)
class ThemePageStats:
    generated_pages: int
    ranked_stations: int


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _metric(detail: Mapping[str, Any], key: str) -> float | None:
    value = ((detail.get("metrics") or {}).get(key) or {}).get("value")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _score(detail: Mapping[str, Any], key: str, maximum: float) -> float | None:
    value = detail.get(key)
    try:
        if value is None:
            return None
        return max(0.0, min(100.0, float(value) / maximum * 100.0))
    except (TypeError, ValueError):
        return None


def _mesh_summary(data_dir: Path, code: str) -> Mapping[str, Any]:
    path = data_dir / "map" / "station" / code / "mesh250.json"
    if not path.exists():
        return {}
    try:
        return _json(path).get("summary") or {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _quake_probability(detail: Mapping[str, Any], mesh_summary: Mapping[str, Any]) -> float | None:
    direct = _metric(detail, "seismic_30y_6lower_probability")
    if direct is not None:
        return direct
    value = ((mesh_summary.get("seismic") or {}).get("earthquake_probability_30y_6lower_population_weighted"))
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safety_score(detail: Mapping[str, Any], mesh_summary: Mapping[str, Any]) -> tuple[float | None, int]:
    risks: list[float] = []
    flood = _metric(detail, "hazard_flood_population_share")
    quake = _quake_probability(detail, mesh_summary)
    for value in (flood, quake):
        if value is not None:
            risks.append(max(0.0, min(100.0, value)))
    if not risks:
        return None, 0
    return 100.0 - mean(risks), len(risks)


def _station_rows(data_dir: Path) -> list[dict[str, Any]]:
    station_dir = data_dir / "geo" / "station"
    rows: list[dict[str, Any]] = []
    if not station_dir.exists():
        return rows
    for path in sorted(station_dir.glob("*.json")):
        detail = _json(path)
        if not station_page_quality(detail).indexable:
            continue
        code = str(detail.get("station_code") or "").strip()
        if not code:
            continue
        mesh_summary = _mesh_summary(data_dir, code)
        future = _score(detail, "future_population_score", 20)
        price = _score(detail, "price_score", 20)
        convenience = _score(detail, "convenience_score", 15)
        transport = _score(detail, "transport_score", 15)
        safety, safety_sources = _safety_score(detail, mesh_summary)
        rows.append(
            {
                "code": code,
                "name": str(detail.get("name") or code),
                "ward": str(detail.get("primary_ward_name") or ""),
                "confidence": str(detail.get("confidence") or "—"),
                "future": future,
                "price": price,
                "daily": mean([value for value in (convenience, transport) if value is not None]) if any(value is not None for value in (convenience, transport)) else None,
                "safety": safety,
                "safety_sources": safety_sources,
                "retention": _metric(detail, "future_population_retention_2045"),
                "price_change": _metric(detail, "transaction_unit_price_change"),
                "flood": _metric(detail, "hazard_flood_population_share"),
                "quake": _quake_probability(detail, mesh_summary),
            }
        )
    return rows


def _rank(rows: list[dict[str, Any]], theme: str) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in rows:
        score: float | None = None
        if theme == "future-population" and row["future"] is not None:
            score = row["future"]
        elif theme == "price-and-future" and row["price"] is not None and row["future"] is not None:
            score = (row["price"] + row["future"]) / 2
        elif theme == "future-and-safety" and row["future"] is not None and row["safety"] is not None:
            score = row["future"] * 0.6 + row["safety"] * 0.4
        if score is None:
            continue
        ranked.append({**row, "theme_score": score})
    return sorted(ranked, key=lambda item: (-item["theme_score"], item["name"], item["code"]))[:20]


THEMES = {
    "future-population": {
        "kicker": "FUTURE POPULATION",
        "title": "2045年まで人口を維持しやすい駅",
        "description": "東京23区の駅中心1km圏について、2045年までの将来人口を公的データから比較します。",
        "method": "将来人口スコアを100換算して順位化。2045/2025人口維持率は実数値を併記します。",
    },
    "price-and-future": {
        "kicker": "PRICE × FUTURE",
        "title": "価格動向と将来人口を両方見る駅",
        "description": "価格の動きだけでも人口だけでもなく、東京23区の駅1km圏を価格動向と2045年までの将来人口から比較します。",
        "method": "価格動向スコアと将来人口スコアをそれぞれ100換算し、50%ずつで参考指数を算出します。",
    },
    "future-and-safety": {
        "kicker": "FUTURE × HAZARD",
        "title": "将来人口と水害・地震を一緒に見る駅",
        "description": "東京23区の駅1km圏について、2045年までの人口維持と洪水曝露・地震確率を同じ画面で比較します。",
        "method": "将来人口60%と、水害曝露・震度6弱以上確率を低いほど高評価にした参考値40%を合成。取得できる防災項目だけで計算します。",
    },
}


def _row_metrics(theme: str, row: Mapping[str, Any]) -> str:
    if theme == "future-population":
        items = (("2045 / 2025人口", row.get("retention"), "%"), ("信頼度", row.get("confidence"), ""))
    elif theme == "price-and-future":
        items = (("2045 / 2025人口", row.get("retention"), "%"), ("取引単価変化", row.get("price_change"), "%"), ("信頼度", row.get("confidence"), ""))
    else:
        items = (("2045 / 2025人口", row.get("retention"), "%"), ("洪水曝露人口", row.get("flood"), "%"), ("30年 震度6弱以上", row.get("quake"), "%"))
    html = []
    for label, value, unit in items:
        shown = escape(str(value)) if isinstance(value, str) else _number(value, 1)
        html.append(f'<span><small>{escape(label)}</small><strong>{shown}{unit if shown != "—" else ""}</strong></span>')
    return "".join(html)


def _ranking_page(theme: str, rows: list[dict[str, Any]]) -> str:
    meta = THEMES[theme]
    canonical = absolute_url(f"ranking/{theme}/")
    cards = []
    for index, row in enumerate(rows, 1):
        station_name = row["name"] if str(row["name"]).endswith("駅") else f'{row["name"]}駅'
        cards.append(
            '<article class="theme-ranking-row">'
            f'<div class="theme-ranking-rank"><span>#{index}</span><strong>{_number(row["theme_score"], 1)}</strong><small>参考指数</small></div>'
            f'<div class="theme-ranking-main"><p>{escape(row["ward"])}</p><h2><a href="../../station/{escape(row["code"], quote=True)}/">{escape(station_name)}</a></h2>'
            f'<div class="theme-ranking-metrics">{_row_metrics(theme, row)}</div></div>'
            '</article>'
        )
    body = "".join(cards) or '<div class="station-empty">必要な公開データがまだ揃っていません。</div>'
    return f'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(meta["title"])}ランキング | {SITE_NAME}</title>
  <meta name="description" content="{escape(meta["description"], quote=True)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canonical, quote=True)}">
  <link rel="stylesheet" href="../../styles.css">
  <link rel="stylesheet" href="../../polish.css">
  <link rel="stylesheet" href="../../navigation.css?v=20260905-5">
  <link rel="stylesheet" href="../../station-page.css?v=20260905-1">
  <link rel="stylesheet" href="../../station-theme-ranking.css?v=20260905-1">
</head>
<body class="station-page theme-ranking-page">
  <header class="site-header"><a class="brand" href="../../">{SITE_NAME} <span>BETA</span></a><nav class="site-nav" aria-label="主要ナビゲーション"><a href="../../#recommend">おすすめから探す</a><a href="../../stations.html" aria-current="page">街・駅名から探す</a><a href="../../#discover">条件で探す</a></nav></header>
  <main>
    <nav class="station-breadcrumb" aria-label="パンくず"><a href="../../">{SITE_NAME}</a><span>›</span><a href="../">テーマ別ランキング</a><span>›</span><strong>{escape(meta["title"])}</strong></nav>
    <section class="theme-ranking-hero"><p class="eyebrow">{escape(meta["kicker"])}</p><h1>{escape(meta["title"])}</h1><p>{escape(meta["description"])}</p></section>
    <div class="theme-ranking-method"><strong>計算方法</strong><span>{escape(meta["method"])}</span></div>
    <section class="theme-ranking-list" aria-label="ランキング">{body}</section>
    <div class="station-notice"><strong>順位の読み方</strong><span>参考指数は東京23区内の公開データを同じルールで並べるための比較値です。住みやすさ・安全性・将来の資産価値を保証するものではありません。個別物件は住所単位の公式情報も確認してください。</span></div>
  </main>
  <footer><p>{escape(SITE_DESCRIPTION)}</p><p><a href="https://github.com/nano-tani/japan-area-insights" target="_blank" rel="noreferrer">計算方法・出典 →</a></p></footer>
</body>
</html>'''


def _ranking_index() -> str:
    cards = "".join(
        f'<a class="theme-index-card" href="./{slug}/"><span>{escape(meta["kicker"])}</span><strong>{escape(meta["title"])}</strong><p>{escape(meta["description"])}</p></a>'
        for slug, meta in THEMES.items()
    )
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>テーマ別に駅を探す | {SITE_NAME}</title><meta name="description" content="東京23区の駅を、将来人口、価格動向、防災データの組み合わせから探せるテーマ別ランキング。"><meta name="robots" content="index,follow"><link rel="canonical" href="{absolute_url('ranking/')}"><link rel="stylesheet" href="../styles.css"><link rel="stylesheet" href="../polish.css"><link rel="stylesheet" href="../navigation.css?v=20260905-5"><link rel="stylesheet" href="../station-page.css?v=20260905-1"><link rel="stylesheet" href="../station-theme-ranking.css?v=20260905-1"></head><body class="station-page theme-ranking-page"><header class="site-header"><a class="brand" href="../">{SITE_NAME} <span>BETA</span></a><nav class="site-nav" aria-label="主要ナビゲーション"><a href="../#recommend">おすすめから探す</a><a href="../stations.html" aria-current="page">街・駅名から探す</a><a href="../#discover">条件で探す</a></nav></header><main><nav class="station-breadcrumb" aria-label="パンくず"><a href="../">{SITE_NAME}</a><span>›</span><strong>テーマ別ランキング</strong></nav><section class="theme-ranking-hero"><p class="eyebrow">DECISION THEMES</p><h1>テーマ別に駅を探す</h1><p>総合点だけで決めず、将来人口・価格・防災という目的別の切り口から候補駅を探します。</p></section><div class="theme-index-grid">{cards}</div></main><footer><p>{escape(SITE_DESCRIPTION)}</p><p><a href="https://github.com/nano-tani/japan-area-insights" target="_blank" rel="noreferrer">計算方法・出典 →</a></p></footer></body></html>'''


def export_station_theme_pages(output_dir: str | Path) -> ThemePageStats:
    data_dir = Path(output_dir)
    web_root = data_dir.parent
    ranking_root = web_root / "ranking"
    ranking_root.mkdir(parents=True, exist_ok=True)
    rows = _station_rows(data_dir)
    total_ranked = 0
    (ranking_root / "index.html").write_text(_ranking_index(), encoding="utf-8")
    generated = 1
    for theme in THEMES:
        ranked = _rank(rows, theme)
        total_ranked += len(ranked)
        target = ranking_root / theme
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(_ranking_page(theme, ranked), encoding="utf-8")
        generated += 1
    return ThemePageStats(generated_pages=generated, ranked_stations=total_ranked)
