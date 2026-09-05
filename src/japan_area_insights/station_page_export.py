from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .page_quality import station_page_quality
from .site_config import SITE_DESCRIPTION, SITE_NAME, absolute_url, station_path, station_url

FACILITY_LABELS = {
    "school": "学校",
    "childcare": "保育園・幼稚園等",
    "medical": "医療機関",
    "library": "図書館",
    "public_facility": "公共施設",
}
SCORE_COMPONENTS = (
    ("価格動向", "price_score", 20),
    ("人口動向（推計）", "population_score", 20),
    ("将来人口", "future_population_score", 20),
    ("生活利便性", "convenience_score", 15),
    ("交通利便性", "transport_score", 15),
    ("取引活性度", "transaction_score", 10),
)


@dataclass(frozen=True)
class StationPageExportStats:
    generated_count: int
    indexable_count: int
    noindex_count: int


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value: Any, digits: int = 0) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if digits <= 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}".rstrip("0").rstrip(".")


def _metric(detail: Mapping[str, Any], key: str) -> Any:
    return ((detail.get("metrics") or {}).get(key) or {}).get("value")


def _future(detail: Mapping[str, Any], year: int) -> Mapping[str, Any] | None:
    return next((row for row in detail.get("future_population", []) or [] if int(row.get("year") or 0) == year), None)


def _safe_url(value: Any) -> str | None:
    text = str(value or "").strip()
    parsed = urlparse(text)
    return text if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _station_name(detail: Mapping[str, Any]) -> str:
    name = str(detail.get("name") or "").strip()
    return name if name.endswith("駅") else f"{name}駅"


def _score_bar(label: str, value: Any, maximum: int) -> str:
    try:
        numeric = float(value)
        width = max(0.0, min(100.0, numeric / maximum * 100.0))
        shown = _number(numeric, 1)
    except (TypeError, ValueError):
        width = 0.0
        shown = "—"
    return (
        '<div class="station-score-row">'
        f'<div><span>{escape(label)}</span><strong>{shown} / {maximum}</strong></div>'
        f'<div class="station-score-track"><i style="width:{width:.2f}%"></i></div>'
        '</div>'
    )


def _population_rows(detail: Mapping[str, Any]) -> str:
    rows = []
    for row in detail.get("future_population", []) or []:
        year = int(row.get("year") or 0)
        if year not in {2025, 2030, 2035, 2040, 2045}:
            continue
        rows.append(
            "<tr>"
            f"<th>{year}年</th>"
            f"<td>{_number(row.get('projected_population'))}人</td>"
            f"<td>{_number(row.get('retention_rate'), 1)}%</td>"
            "</tr>"
        )
    return "".join(rows) or '<tr><td colspan="3">将来人口データ未生成</td></tr>'


def _transaction_rows(detail: Mapping[str, Any]) -> str:
    rows = (detail.get("transactions") or [])[-5:]
    if not rows:
        return '<div class="station-empty">駅指定取引データ未生成</div>'
    return "".join(
        '<div class="station-data-row">'
        f'<span>{int(row.get("year") or 0)}年 / {_number(row.get("transaction_count"))}件</span>'
        f'<strong>{_number(row.get("median_unit_price"))}円/㎡</strong>'
        '</div>'
        for row in reversed(rows)
    )


def _source_rows(detail: Mapping[str, Any]) -> str:
    rows: list[str] = []
    seen: set[tuple[str, str]] = set()
    for source in detail.get("sources", []) or []:
        name = str(source.get("source_name") or "公的データ")
        dataset = str(source.get("dataset_id") or "")
        key = (name, dataset)
        if key in seen:
            continue
        seen.add(key)
        url = _safe_url(source.get("source_url"))
        label = f"{escape(name)}{f' / {escape(dataset)}' if dataset else ''}"
        rows.append(
            f'<li><a href="{escape(url, quote=True)}" target="_blank" rel="noreferrer">{label}</a></li>'
            if url else f"<li>{label}</li>"
        )
    return "".join(rows) or "<li>公開スナップショットに出典情報がありません。</li>"


def _json_ld(detail: Mapping[str, Any], canonical: str, title: str, description: str) -> str:
    station_name = _station_name(detail)
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": canonical,
                "url": canonical,
                "name": title,
                "description": description,
                "inLanguage": "ja",
                "about": {
                    "@type": "Place",
                    "name": station_name,
                    "geo": {
                        "@type": "GeoCoordinates",
                        "latitude": detail.get("latitude"),
                        "longitude": detail.get("longitude"),
                    },
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": absolute_url()},
                    {"@type": "ListItem", "position": 2, "name": "駅から探す", "item": absolute_url("stations.html")},
                    {"@type": "ListItem", "position": 3, "name": station_name, "item": canonical},
                ],
            },
        ],
    }
    return json.dumps(graph, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def build_station_page(detail: Mapping[str, Any]) -> str:
    quality = station_page_quality(detail)
    code = str(detail.get("station_code") or "")
    station_name = _station_name(detail)
    ward = str(detail.get("primary_ward_name") or "東京23区")
    canonical = station_url(code)
    pop2025 = _future(detail, 2025)
    pop2045 = _future(detail, 2045)
    retention = _metric(detail, "future_population_retention_2045")
    latest_price = _metric(detail, "transaction_unit_price_median_latest")
    price_change = _metric(detail, "transaction_unit_price_change")
    transaction_count = _metric(detail, "transaction_count_5y")
    nearby_lines = _metric(detail, "nearby_line_count")
    ridership = _metric(detail, "ridership_daily")
    title = f"{station_name}周辺の将来人口・暮らし・不動産データ | {SITE_NAME}"
    description = (
        f"{station_name}（{ward}）の駅中心1km圏を公的データで分析。2025年・2045年の将来人口、"
        "生活施設、交通、不動産取引の推移を確認できます。"
    )
    robots = "index,follow" if quality.indexable else "noindex,follow"
    lines = sorted({
        f"{str(row.get('operator_name') or '').strip()} {str(row.get('line_name') or '').strip()}".strip()
        for row in detail.get("lines", []) or []
        if str(row.get("operator_name") or row.get("line_name") or "").strip()
    })
    line_text = " / ".join(lines) or "路線データ未生成"
    score_rows = "".join(_score_bar(label, detail.get(key), maximum) for label, key, maximum in SCORE_COMPONENTS)
    facility_rows = "".join(
        '<div class="station-data-row">'
        f'<span>{escape(label)}</span><strong>{_number(_metric(detail, f"facility_{key}_count"))}施設</strong>'
        '</div>'
        for key, label in FACILITY_LABELS.items()
    )
    eligibility = (
        "総合点算出対象"
        if detail.get("eligibility") == "eligible"
        else str(detail.get("eligibility_reason") or "総合点の算出条件を満たしていません")
    )
    quality_note = "" if quality.indexable else (
        '<div class="station-notice"><strong>公開品質確認中</strong><span>このページは検索対象から外しています。データ更新後に再判定します。</span></div>'
    )
    ward_link = f"../../ward.html?id={escape(str(detail.get('primary_area_id') or ''), quote=True)}"

    return f'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description, quote=True)}">
  <meta name="robots" content="{robots}">
  <link rel="canonical" href="{escape(canonical, quote=True)}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{escape(title, quote=True)}">
  <meta property="og:description" content="{escape(description, quote=True)}">
  <meta property="og:url" content="{escape(canonical, quote=True)}">
  <link rel="stylesheet" href="../../styles.css">
  <link rel="stylesheet" href="../../polish.css">
  <link rel="stylesheet" href="../../navigation.css?v=20260905-5">
  <link rel="stylesheet" href="../../station-page.css?v=20260905-1">
  <script type="application/ld+json">{_json_ld(detail, canonical, title, description)}</script>
</head>
<body class="station-page">
  <header class="site-header">
    <a class="brand" href="../../">{SITE_NAME} <span>BETA</span></a>
    <nav class="site-nav" aria-label="主要ナビゲーション">
      <a href="../../#recommend">おすすめから探す</a>
      <a href="../../stations.html" aria-current="page">街・駅名から探す</a>
      <a href="../../#discover">条件で探す</a>
    </nav>
  </header>
  <main>
    <nav class="station-breadcrumb" aria-label="パンくず"><a href="../../">{SITE_NAME}</a><span>›</span><a href="../../stations.html">駅から探す</a><span>›</span><strong>{escape(station_name)}</strong></nav>
    <section class="station-page-hero">
      <div>
        <p class="eyebrow">STATION AREA / {escape(code)}</p>
        <h1>{escape(station_name)}<span>周辺の今と2045年</span></h1>
        <p class="lead">{escape(ward)}・駅中心約{_number(detail.get('radius_m') or 1000)}m。人口の将来像、生活施設、交通、不動産取引を同じページで確認します。</p>
        <div class="meta-row"><span>{escape(line_text)}</span><span>信頼度 {escape(str(detail.get('confidence') or '—'))}</span><span>データ基準 {escape(str(detail.get('calculation_date') or '—'))}</span></div>
      </div>
      <aside class="station-reference-score"><span>参考総合評価</span><strong>{_number(detail.get('total_score'), 1)}</strong><small>/ 100</small><p>{escape(eligibility)}</p></aside>
    </section>
    {quality_note}

    <section class="station-section" aria-labelledby="future-heading">
      <div class="station-section-head"><div><p class="section-kicker">NOW → 2045</p><h2 id="future-heading">将来人口を先に見る</h2></div><p>総合点より先に、駅1km圏の人口が今後どう変わるかを確認します。</p></div>
      <div class="station-key-grid">
        <article><span>2025年推計人口</span><strong>{_number(pop2025.get('projected_population') if pop2025 else None)}人</strong></article>
        <article><span>2045年推計人口</span><strong>{_number(pop2045.get('projected_population') if pop2045 else None)}人</strong></article>
        <article><span>2045 / 2025</span><strong>{_number(retention, 1)}%</strong></article>
        <article><span>1km圏メッシュ</span><strong>{_number(detail.get('mesh_count'))}個</strong></article>
      </div>
      <div class="station-table-wrap"><table><thead><tr><th>年</th><th>推計人口</th><th>2025年比</th></tr></thead><tbody>{_population_rows(detail)}</tbody></table></div>
      <p class="station-footnote">将来人口は250mメッシュを駅中心1km圏で集計した推計値です。将来の人口を保証するものではありません。</p>
    </section>

    <section class="station-section" aria-labelledby="market-heading">
      <div class="station-section-head"><div><p class="section-kicker">HOUSING MARKET</p><h2 id="market-heading">不動産取引の動き</h2></div><p>物件位置を1km圏へ推測せず、この駅のグループコードを条件に取得した取引だけを集計します。</p></div>
      <div class="station-key-grid station-key-grid-3">
        <article><span>直近単価中央値</span><strong>{_number(latest_price)}円/㎡</strong></article>
        <article><span>価格変化</span><strong>{_number(price_change, 1)}%</strong></article>
        <article><span>直近5完了年の取引</span><strong>{_number(transaction_count)}件</strong></article>
      </div>
      <div class="station-panel">{_transaction_rows(detail)}</div>
      <div class="station-notice"><strong>集計範囲に注意</strong><span>駅指定XIT001は「駅から1km以内の物件」を意味しません。駅コード検索で取得できた取引の傾向です。</span></div>
    </section>

    <section class="station-section station-two-col" aria-label="暮らしと交通">
      <div>
        <div class="station-section-head"><div><p class="section-kicker">DAILY LIFE</p><h2>生活施設</h2></div></div>
        <div class="station-panel">{facility_rows}</div>
      </div>
      <div>
        <div class="station-section-head"><div><p class="section-kicker">TRANSPORT</p><h2>交通</h2></div></div>
        <div class="station-panel">
          <div class="station-data-row"><span>1km圏の駅</span><strong>{_number(_metric(detail, 'nearby_station_count'))}駅</strong></div>
          <div class="station-data-row"><span>1km圏の路線</span><strong>{_number(nearby_lines)}路線</strong></div>
          <div class="station-data-row"><span>駅別乗降客数 合計</span><strong>{_number(ridership)}人/日</strong></div>
          <div class="station-data-row"><span>中心駅の路線</span><strong>{escape(line_text)}</strong></div>
        </div>
      </div>
    </section>

    <section class="station-section" aria-labelledby="score-heading">
      <div class="station-section-head"><div><p class="section-kicker">REFERENCE SCORE</p><h2 id="score-heading">参考スコアの内訳</h2></div><p>東京23区内の駅1km圏だけを母集団にした相対評価です。区スコアとは直接比較できません。</p></div>
      <div class="station-score-panel">{score_rows}</div>
    </section>

    <section class="station-section station-two-col" aria-label="関連ページと出典">
      <div>
        <div class="station-section-head"><div><p class="section-kicker">NEXT</p><h2>次に確認する</h2></div></div>
        <div class="station-link-panel">
          <a href="../../stations.html">別の駅を探す <span>→</span></a>
          <a href="{ward_link}">{escape(ward)}全体を見る <span>→</span></a>
        </div>
      </div>
      <div>
        <div class="station-section-head"><div><p class="section-kicker">SOURCES</p><h2>データ出典</h2></div></div>
        <ul class="station-source-list">{_source_rows(detail)}</ul>
      </div>
    </section>
  </main>
  <footer>
    <p><strong>広告について：</strong>本サイトではアフィリエイト広告を利用する場合があります。評価や比較結果は広告報酬の有無にかかわらず、公的データ等に基づきます。</p>
    <p>本サイトは住む場所を比較・検討するための参考情報で、特定地域への居住・購入・投資を推奨するものではありません。</p>
    <p><a href="https://github.com/nano-tani/japan-area-insights" target="_blank" rel="noreferrer">計算方法・出典 →</a></p>
  </footer>
</body>
</html>
'''


def _build_station_index(rows: list[Mapping[str, Any]]) -> str:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("primary_ward_name") or "その他"), []).append(row)
    sections = []
    for ward in sorted(grouped):
        links = "".join(
            f'<a href="./{escape(str(row.get("station_code") or ""), quote=True)}/"><strong>{escape(_station_name(row))}</strong><span>{_number(row.get("total_score"), 1)} / 100</span></a>'
            for row in sorted(grouped[ward], key=lambda item: (str(item.get("name") or ""), str(item.get("station_code") or "")))
        )
        sections.append(f'<section class="station-directory-group"><h2>{escape(ward)}</h2><div>{links}</div></section>')
    canonical = absolute_url("station/")
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>東京23区の駅一覧 | {SITE_NAME}</title><meta name="description" content="東京23区の駅1km圏データ一覧。駅ごとの将来人口・暮らし・交通・不動産取引を確認できます。"><link rel="canonical" href="{canonical}"><link rel="stylesheet" href="../styles.css"><link rel="stylesheet" href="../polish.css"><link rel="stylesheet" href="../navigation.css?v=20260905-5"><link rel="stylesheet" href="../station-page.css?v=20260905-1"></head><body class="station-page"><header class="site-header"><a class="brand" href="../">{SITE_NAME} <span>BETA</span></a><nav class="site-nav" aria-label="主要ナビゲーション"><a href="../#recommend">おすすめから探す</a><a href="../stations.html" aria-current="page">街・駅名から探す</a><a href="../#discover">条件で探す</a></nav></header><main><section class="station-page-hero station-directory-hero"><div><p class="eyebrow">STATION DIRECTORY</p><h1>東京23区の駅一覧<span>駅中心1km圏で比較</span></h1><p class="lead">{len(rows)}駅の公開ページから、将来人口・暮らし・交通・不動産取引を確認できます。</p></div></section>{''.join(sections)}</main><footer><p>{escape(SITE_DESCRIPTION)}</p><p><a href="https://github.com/nano-tani/japan-area-insights" target="_blank" rel="noreferrer">計算方法・出典 →</a></p></footer></body></html>'''


def export_station_pages(output_dir: str | Path) -> StationPageExportStats:
    data_dir = Path(output_dir)
    web_root = data_dir.parent
    index_path = data_dir / "geo" / "index.json"
    station_json_dir = data_dir / "geo" / "station"
    station_root = web_root / "station"
    station_root.mkdir(parents=True, exist_ok=True)

    for child in station_root.iterdir():
        if child.is_dir() and child.name.isdigit():
            shutil.rmtree(child)

    if not index_path.exists():
        (station_root / "index.html").write_text(_build_station_index([]), encoding="utf-8")
        return StationPageExportStats(0, 0, 0)

    payload = _json(index_path)
    generated_rows: list[dict[str, Any]] = []
    indexable = 0
    noindex = 0
    for summary in payload.get("station_areas", []) or []:
        code = str(summary.get("station_code") or "").strip()
        detail_path = station_json_dir / f"{code}.json"
        if not code or not detail_path.exists():
            continue
        detail = _json(detail_path)
        quality = station_page_quality(detail)
        page_dir = station_root / code
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(build_station_page(detail), encoding="utf-8")
        generated_rows.append(detail)
        if quality.indexable:
            indexable += 1
        else:
            noindex += 1

    (station_root / "index.html").write_text(_build_station_index(generated_rows), encoding="utf-8")
    return StationPageExportStats(len(generated_rows), indexable, noindex)
