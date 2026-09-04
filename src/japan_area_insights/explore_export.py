from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .analysis_schema import ensure_analysis_schema
from .db import connect


THEMES = [
    {
        "key": "market",
        "label": "価格・不動産",
        "description": "地価・取引価格・取引量から街の市場を探す",
        "metrics": [
            "core.price_score",
            "market.land_price_median",
            "market.median_unit_price",
            "market.transaction_count",
        ],
    },
    {
        "key": "people",
        "label": "人口・将来",
        "description": "将来人口・自然増減・世帯構成から探す",
        "metrics": [
            "core.future_population_score",
            "people.retention_2045",
            "demographics.natural_change",
            "household.single_household_share",
        ],
    },
    {
        "key": "housing",
        "label": "住宅",
        "description": "持ち家・借家・築年構成から住宅ストックを見る",
        "metrics": [
            "housing2023.owner_occupied_share",
            "housing2023.rental_share",
            "housing2023.pre1980_share",
            "housing2023.post2011_share",
        ],
    },
    {
        "key": "economy",
        "label": "仕事・経済",
        "description": "所得・従業者・昼夜人口から街の働く力を見る",
        "metrics": [
            "economy.taxable_income_per_taxpayer",
            "economy.day_night_population_ratio",
            "economy.employees",
            "economy.establishments",
        ],
    },
    {
        "key": "life",
        "label": "生活・子育て",
        "description": "生活利便性と人口構成をまとめて見る",
        "metrics": [
            "core.convenience_score",
            "people.child_share",
            "people.elderly_share",
            "core.transport_score",
        ],
    },
    {
        "key": "mobility",
        "label": "交通・移動",
        "description": "交通利便性・昼夜人口・人口動向から探す",
        "metrics": [
            "core.transport_score",
            "economy.day_night_population_ratio",
            "core.population_score",
            "core.transaction_score",
        ],
    },
    {
        "key": "urban",
        "label": "都市・開発",
        "description": "用途地域・人口集中・容積率から都市構造を見る",
        "metrics": [
            "urban.zoning_mesh_share",
            "urban.did_mesh_share",
            "market.transaction_far_median",
            "market.land_price_median",
        ],
    },
    {
        "key": "resilience",
        "label": "防災・地形",
        "description": "洪水・液状化・高潮・土砂の人口曝露を確認する",
        "metrics": [
            "hazard.flood_population_share",
            "hazard.liquefaction_population_share",
            "hazard.storm_surge_population_share",
            "hazard.sediment_population_share",
        ],
    },
]


CORE_METRICS = {
    "core.total_score": ("総合評価", "点", "higher", "total_score"),
    "core.price_score": ("価格動向", "点", "higher", "price_score"),
    "core.population_score": ("人口動向", "点", "higher", "population_score"),
    "core.future_population_score": ("将来人口", "点", "higher", "future_population_score"),
    "core.convenience_score": ("生活利便性", "点", "higher", "convenience_score"),
    "core.transport_score": ("交通利便性", "点", "higher", "transport_score"),
    "core.transaction_score": ("取引活性度", "点", "higher", "transaction_score"),
}

EXPOSURE_METRICS = {
    "hazard.flood_population_share": ("洪水人口曝露", "%", "lower", "flood"),
    "hazard.liquefaction_population_share": ("液状化人口曝露", "%", "lower", "liquefaction"),
    "hazard.storm_surge_population_share": ("高潮人口曝露", "%", "lower", "storm_surge"),
    "hazard.sediment_population_share": ("土砂災害人口曝露", "%", "lower", "sediment_disaster"),
    "urban.zoning_mesh_share": ("用途地域指定メッシュ率", "%", "neutral", "zoning"),
    "urban.did_mesh_share": ("人口集中地区メッシュ率", "%", "neutral", "densely_inhabited_district"),
}

CUSTOM_METRICS = {
    "people.retention_2045": ("2045年人口維持率", "%", "higher"),
}

ALIASES = {
    "market": ["地価", "価格", "不動産", "取引", "マンション", "土地"],
    "people": ["人口", "将来人口", "出生", "死亡", "高齢化", "外国人", "世帯"],
    "housing": ["住宅", "持ち家", "借家", "築古", "新築"],
    "economy": ["所得", "経済", "仕事", "雇用", "事業所", "昼間人口"],
    "life": ["生活", "子育て", "学校", "保育", "病院", "医療", "福祉"],
    "mobility": ["交通", "駅", "鉄道", "通勤", "通学", "移動"],
    "urban": ["都市計画", "用途地域", "容積率", "開発", "DID"],
    "resilience": ["防災", "洪水", "液状化", "高潮", "津波", "土砂", "地震", "標高"],
}


def _latest_score(conn, area_id: str):
    return conn.execute(
        """
        SELECT * FROM area_scores WHERE area_id=?
        ORDER BY calculation_date DESC, rowid DESC LIMIT 1
        """,
        (area_id,),
    ).fetchone()


def _latest_detail_metric(conn, geo_id: str, metric_key: str):
    return conn.execute(
        """
        SELECT gm.value,gm.period,gm.sample_size,gm.metric_version,gm.calculated_at,
               mq.quality_grade,mq.source_year,mq.is_estimate,
               md.label,md.unit,md.direction,md.description
        FROM geo_metrics gm
        LEFT JOIN metric_quality mq
          ON mq.geo_id=gm.geo_id AND mq.metric_key=gm.metric_key
         AND mq.period=gm.period AND mq.metric_version=gm.metric_version
        LEFT JOIN metric_definitions md ON md.metric_key=gm.metric_key
        WHERE gm.geo_id=? AND gm.metric_key=? AND gm.metric_version='detail-v1'
        ORDER BY gm.calculated_at DESC, gm.period DESC LIMIT 1
        """,
        (geo_id, metric_key),
    ).fetchone()


def _exposure(conn, geo_id: str, layer_key: str):
    row = conn.execute(
        """
        SELECT period,population_share,exposed_mesh_count,total_mesh_count,
               exposed_population,total_population,calculated_at
        FROM geo_exposures
        WHERE geo_id=? AND layer_key=?
        ORDER BY CASE WHEN period='2025' THEN 0 ELSE 1 END, period DESC LIMIT 1
        """,
        (geo_id, layer_key),
    ).fetchone()
    if row is None:
        return None
    total_mesh = row["total_mesh_count"] or 0
    mesh_share = (
        float(row["exposed_mesh_count"] or 0) / float(total_mesh) * 100.0
        if total_mesh else None
    )
    return row, mesh_share


def _future_retention(conn, area_id: str) -> tuple[float | None, str | None]:
    rows = conn.execute(
        """
        SELECT year,SUM(projected_population) AS population
        FROM future_population WHERE area_id=? AND year IN (2025,2045)
        GROUP BY year
        """,
        (area_id,),
    ).fetchall()
    values = {int(row["year"]): row["population"] for row in rows}
    base = values.get(2025)
    future = values.get(2045)
    if base in (None, 0) or future is None:
        return None, None
    return round(float(future) / float(base) * 100.0, 3), "2045/2025"


def _metric_catalog(conn) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for key, (label, unit, direction, _) in CORE_METRICS.items():
        result[key] = {"key": key, "label": label, "unit": unit, "direction": direction, "kind": "core"}
    for key, (label, unit, direction, _) in EXPOSURE_METRICS.items():
        result[key] = {"key": key, "label": label, "unit": unit, "direction": direction, "kind": "exposure"}
    for key, (label, unit, direction) in CUSTOM_METRICS.items():
        result[key] = {"key": key, "label": label, "unit": unit, "direction": direction, "kind": "derived"}

    wanted = {key for theme in THEMES for key in theme["metrics"]}
    detail_keys = wanted - set(result)
    if detail_keys:
        placeholders = ",".join("?" for _ in detail_keys)
        for row in conn.execute(
            f"SELECT metric_key,label,unit,direction,description FROM metric_definitions WHERE metric_key IN ({placeholders})",
            tuple(sorted(detail_keys)),
        ):
            result[row["metric_key"]] = {
                "key": row["metric_key"],
                "label": row["label"],
                "unit": row["unit"],
                "direction": row["direction"] or "neutral",
                "description": row["description"],
                "kind": "detail",
            }
    for key in detail_keys:
        result.setdefault(key, {"key": key, "label": key, "unit": None, "direction": "neutral", "kind": "detail"})
    return result


def _add_percentiles(wards: list[dict], catalog: dict[str, dict]) -> None:
    keys = list(catalog)
    for key in keys:
        valid = [ward for ward in wards if ward["metrics"].get(key, {}).get("value") is not None]
        if not valid:
            continue
        ascending = sorted(valid, key=lambda ward: (float(ward["metrics"][key]["value"]), ward["area_id"]))
        count = len(ascending)
        for index, ward in enumerate(ascending):
            low_pct = round((index + 1) / count * 100.0, 1)
            high_pct = round((count - index) / count * 100.0, 1)
            ward["metrics"][key]["percentile_low"] = low_pct
            ward["metrics"][key]["percentile_high"] = high_pct
            direction = catalog[key].get("direction") or "neutral"
            if direction == "lower":
                ward["metrics"][key]["relative_percentile"] = low_pct
            else:
                ward["metrics"][key]["relative_percentile"] = high_pct


def export_explore_data(db_path: str | Path, output_dir: str | Path) -> None:
    output = Path(output_dir) / "explore"
    output.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        ensure_analysis_schema(conn)
        catalog = _metric_catalog(conn)
        areas = conn.execute(
            "SELECT area_id,prefecture_name,municipality_name FROM areas ORDER BY municipality_code"
        ).fetchall()
        wards: list[dict] = []
        wanted = {key for theme in THEMES for key in theme["metrics"]}

        for area in areas:
            area_id = str(area["area_id"])
            geo_id = f"ward:{area_id}"
            score = _latest_score(conn, area_id)
            metrics: dict[str, dict] = {}

            for key, (_, _, _, column) in CORE_METRICS.items():
                value = score[column] if score is not None else None
                metrics[key] = {
                    "value": value,
                    "period": score["calculation_date"] if score is not None else None,
                    "quality": score["confidence"] if score is not None else None,
                }

            for key in wanted - set(CORE_METRICS) - set(EXPOSURE_METRICS) - set(CUSTOM_METRICS):
                row = _latest_detail_metric(conn, geo_id, key)
                metrics[key] = {
                    "value": row["value"] if row is not None else None,
                    "period": row["period"] if row is not None else None,
                    "quality": row["quality_grade"] if row is not None else None,
                    "is_estimate": bool(row["is_estimate"]) if row is not None and row["is_estimate"] is not None else None,
                }

            retention, retention_period = _future_retention(conn, area_id)
            metrics["people.retention_2045"] = {
                "value": retention,
                "period": retention_period,
                "quality": "A" if retention is not None else None,
            }

            for key, (_, _, _, layer_key) in EXPOSURE_METRICS.items():
                value = _exposure(conn, geo_id, layer_key)
                if value is None:
                    metrics[key] = {"value": None, "period": None, "quality": None}
                    continue
                row, mesh_share = value
                metric_value = mesh_share if key.startswith("urban.") else row["population_share"]
                metrics[key] = {
                    "value": metric_value,
                    "period": row["period"],
                    "quality": "A",
                }

            wards.append(
                {
                    "area_id": area_id,
                    "prefecture_name": area["prefecture_name"],
                    "municipality_name": area["municipality_name"],
                    "confidence": score["confidence"] if score is not None else None,
                    "metrics": metrics,
                }
            )

        _add_percentiles(wards, catalog)

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "peer_group": "tokyo23:ward",
            "themes": [
                {**theme, "aliases": ALIASES.get(theme["key"], [])}
                for theme in THEMES
            ],
            "metric_catalog": catalog,
            "wards": wards,
            "notes": {
                "ranking": "各指標は東京23区内で比較します。指標ごとに利用可能な地域だけを母集団とします。",
                "hazard": "防災指標は総合100点には含めません。人口曝露率は250mメッシュ中心点との重なりによる集計です。",
            },
        }
        (output / "wards.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
