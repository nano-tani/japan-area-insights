from __future__ import annotations

import re
from typing import Any, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .estat_analysis import (
    METRIC_VERSION,
    _class_map,
    _data_class_objects,
    _dimension_containing_codes,
    _filter_name,
    _meta_class_objects,
    _number,
    _source_id,
    _values,
    _year_from_label,
)
from .sources.estat import EStatClient

SSDS_TABLES = {
    "A": ("0000020101", "population_detail", "Ａ 人口・世帯"),
    "B": ("0000020102", "environment_detail", "Ｂ 自然環境"),
    "C": ("0000020103", "economy_detail", "Ｃ 経済基盤"),
    "D": ("0000020104", "administration_detail", "Ｄ 行政基盤"),
    "E": ("0000020205", "education_detail", "Ｅ 教育"),
    "F": ("0000020206", "labor_detail", "Ｆ 労働"),
    "G": ("0000020207", "culture_detail", "Ｇ 文化・スポーツ"),
    "H": ("0000020208", "housing_detail", "Ｈ 居住"),
    "I": ("0000020209", "health_detail", "Ｉ 健康・医療"),
    "J": ("0000020210", "welfare_detail", "Ｊ 福祉・社会保障"),
}


def _indicator_dimension(classes: Mapping[str, Mapping[str, str]], section: str) -> str:
    candidates: list[tuple[int, str]] = []
    pattern = re.compile(rf"^{re.escape(section)}\d+")
    for dim_id, mapping in classes.items():
        matches = sum(bool(pattern.match(str(code))) for code in mapping)
        if matches:
            candidates.append((matches, dim_id))
    if not candidates:
        raise ValueError(f"could not identify SSDS {section} indicator dimension")
    return max(candidates)[1]


def _time_dimension(classes: Mapping[str, Mapping[str, str]], excluded: set[str]) -> str | None:
    best: tuple[int, str] | None = None
    for dim_id, mapping in classes.items():
        if dim_id in excluded:
            continue
        year_labels = sum(_year_from_label(str(label)) > 0 for label in mapping.values())
        if year_labels and (best is None or year_labels > best[0]):
            best = (year_labels, dim_id)
    return best[1] if best else None


def _clean_label(code: str, label: str) -> str:
    text = str(label or "").strip()
    for prefix in (f"{code}_", f"{code} ", code):
        if text.startswith(prefix):
            text = text[len(prefix):].strip(" _")
            break
    return text or code


def _unit(value: Mapping[str, Any]) -> str | None:
    unit = value.get("@unit")
    if unit in (None, "", "-", "***"):
        return None
    return str(unit)


def _chunks(values: list[str], size: int = 40):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def fetch_ssds_full_catalog(client: EStatClient, conn, area_ids: list[str], *, batch_size: int = 40) -> int:
    """Store the latest usable numeric cell for every SSDS A-J indicator.

    The original indicator code is retained in the metric key. Existing curated
    metrics remain authoritative for their named summaries; this layer is a
    broad public-statistics catalog for detailed exploration, not scoring.
    """
    ensure_analysis_schema(conn)
    written = 0

    for section, (stats_id, category, title) in SSDS_TABLES.items():
        meta = client.get_meta_info(stats_id)
        classes = _class_map(_meta_class_objects(meta))
        area_dim = _dimension_containing_codes(classes, area_ids)
        indicator_dim = _indicator_dimension(classes, section)
        indicators = {
            str(code): str(label)
            for code, label in classes[indicator_dim].items()
            if re.match(rf"^{section}\d+", str(code))
        }
        if not indicators:
            continue

        dataset_key = f"estat_ssds_full_{section.lower()}"
        conn.execute(
            """
            INSERT INTO dataset_catalog(
                dataset_key,provider,api_id,category,title,source_vintage,
                granularity,refresh_mode,enabled,notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,notes=excluded.notes
            """,
            (
                dataset_key,"政府統計の総合窓口 e-Stat",stats_id,category,
                f"社会・人口統計体系 {title}","年度次","municipality","extended",1,
                "利用可能な数値指標を自動カタログ化。指標ごとに最新公表年が異なる。",
            ),
        )

        latest: dict[tuple[str, str], tuple[int, str, float, str | None, int]] = {}
        for codes in _chunks(list(indicators), max(1, batch_size)):
            params = {
                _filter_name(area_dim): ",".join(area_ids),
                _filter_name(indicator_dim): ",".join(codes),
                "metaGetFlg": "Y",
                "cntGetFlg": "N",
            }
            payload = client.get_stats_data_all(stats_id, params, max_rows=150000)
            data_classes = _class_map(_data_class_objects(payload))
            time_dim = _time_dimension(data_classes, {area_dim, indicator_dim})
            source_id = _source_id(conn, title=f"社会・人口統計体系 {title}", dataset_id=stats_id, payload=payload)
            for value in _values(payload):
                area_id = str(value.get(f"@{area_dim}") or "")
                indicator = str(value.get(f"@{indicator_dim}") or "")
                number = _number(value.get("$"))
                if area_id not in area_ids or indicator not in indicators or number is None:
                    continue
                time_code = str(value.get(f"@{time_dim}") or "") if time_dim else ""
                period = data_classes.get(time_dim or "", {}).get(time_code, time_code or "latest")
                year = _year_from_label(period)
                candidate = (year, period, number, _unit(value), source_id)
                previous = latest.get((area_id, indicator))
                if previous is None or candidate[0] > previous[0] or (candidate[0] == previous[0] and candidate[1] > previous[1]):
                    latest[(area_id, indicator)] = candidate

        for (area_id, indicator), (_, period, number, unit, source_id) in latest.items():
            metric_key = f"ssds.{section.lower()}.{indicator.lower()}"
            label = _clean_label(indicator, indicators[indicator])
            conn.execute(
                """
                INSERT INTO metric_definitions(
                    metric_key,category,label,unit,direction,granularity,
                    source_dataset_key,min_sample_size,description
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(metric_key) DO UPDATE SET
                    category=excluded.category,label=excluded.label,unit=excluded.unit,
                    source_dataset_key=excluded.source_dataset_key,description=excluded.description
                """,
                (
                    metric_key,category,label,unit,"neutral","ward",dataset_key,1,
                    f"社会・人口統計体系 {title} / {indicator}",
                ),
            )
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",metric_key=metric_key,period=period,
                value=number,sample_size=1,source_id=source_id,
                metric_version=METRIC_VERSION,quality_grade="A",source_year=period,
                notes=f"e-Stat {stats_id} / {indicator}. SSDSの指標ごとに原典統計・公表年が異なります。",
            )
            written += 1
        print(f"SSDS {section}: indicators={len(indicators)}, stored latest cells={sum(1 for area_id, _ in latest if area_id in area_ids)}")
    return written
