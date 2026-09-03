from __future__ import annotations

from typing import Any, Callable, Mapping

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

DAY_NIGHT_ID = "0003454499"
ECONOMIC_CENSUS_ID = "0004005689"


def _code(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(str(label).strip()):
            return code
    return None


def _seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO dataset_catalog(
            dataset_key, provider, api_id, category, title, source_vintage,
            granularity, refresh_mode, enabled, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_key) DO UPDATE SET api_id=excluded.api_id,title=excluded.title,notes=excluded.notes
        """,
        [
            ("estat_census_daynight_2020", "政府統計の総合窓口 e-Stat", DAY_NIGHT_ID, "economy", "2020年国勢調査 昼夜間人口比率", "2020", "municipality", "extended", 1, "男女・年齢総数"),
            ("estat_economic_census_2021", "政府統計の総合窓口 e-Stat", ECONOMIC_CENSUS_ID, "economy", "2021年経済センサス 活動調査", "2021", "municipality", "extended", 1, "全産業・経営組織総数"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO metric_definitions(
            metric_key, category, label, unit, direction, granularity,
            source_dataset_key, min_sample_size, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        [
            ("economy.day_night_population_ratio", "economy", "昼夜間人口比率", "%", "neutral", "ward", "estat_census_daynight_2020", 1, "昼間人口÷夜間人口×100。100超は昼間流入型、100未満は流出型の傾向"),
            ("economy.establishments", "economy", "事業所数", "事業所", "higher", "ward", "estat_economic_census_2021", 1, "2021年経済センサスの全産業事業所数"),
            ("economy.employees", "economy", "従業者数", "人", "higher", "ward", "estat_economic_census_2021", 1, "2021年経済センサスの男女計従業者数"),
            ("economy.employees_per_establishment", "economy", "1事業所当たり従業者数", "人/事業所", "neutral", "ward", "estat_economic_census_2021", 1, "従業者数÷事業所数"),
        ],
    )


def _total_filters(classes: Mapping[str, Mapping[str, str]], keep: set[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for dim_id, mapping in classes.items():
        if dim_id in keep:
            continue
        code = _code(mapping, lambda label: label in {"総数", "総数（男女計）", "男女計"})
        if code is None:
            code = _code(mapping, lambda label: label.startswith("総数"))
        if code is None and len(mapping) == 1:
            code = next(iter(mapping))
        if code is not None:
            filters[_filter_name(dim_id)] = code
    return filters


def fetch_day_night(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(DAY_NIGHT_ID)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    params: dict[str, Any] = {_filter_name(area_dim): ",".join(area_ids), "metaGetFlg": "Y", "cntGetFlg": "N"}
    params.update(_total_filters(classes, {area_dim}))
    payload = client.get_stats_data_all(DAY_NIGHT_ID, params, max_rows=2000)
    source_id = _source_id(conn, title="2020年国勢調査 昼夜間人口比率", dataset_id=DAY_NIGHT_ID, payload=payload)
    written = 0
    for value in _values(payload):
        area_id = str(value.get(f"@{area_dim}") or "")
        number = _number(value.get("$"))
        if area_id not in area_ids or number is None:
            continue
        upsert_metric(
            conn,
            geo_id=f"ward:{area_id}",
            metric_key="economy.day_night_population_ratio",
            period="2020",
            value=number,
            sample_size=1,
            source_id=source_id,
            metric_version=METRIC_VERSION,
            quality_grade="A",
            source_year="2020",
            notes="2020年国勢調査 1-1-2 / 男女・年齢総数",
        )
        written += 1
    return written


def fetch_economic_census(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(ECONOMIC_CENSUS_ID)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)

    item_dim = None
    item_codes: dict[str, str] = {}
    for dim_id, mapping in classes.items():
        establishments = _code(mapping, lambda label: label == "事業所数")
        employees = _code(mapping, lambda label: label in {"従業者数_男女計", "従業者数（男女計）", "従業者数 男女計"})
        if establishments and employees:
            item_dim = dim_id
            item_codes = {establishments: "economy.establishments", employees: "economy.employees"}
            break
    if item_dim is None:
        raise ValueError("could not identify economic census item dimension")

    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(item_dim): ",".join(item_codes),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }
    for dim_id, mapping in classes.items():
        if dim_id in {area_dim, item_dim}:
            continue
        code = _code(mapping, lambda label: label == "全産業")
        if code is None:
            code = _code(mapping, lambda label: label.startswith("全産業"))
        if code is None:
            code = _code(mapping, lambda label: label in {"総数", "総数（男女計）", "男女計"})
        if code is None and len(mapping) == 1:
            code = next(iter(mapping))
        if code:
            params[_filter_name(dim_id)] = code

    payload = client.get_stats_data_all(ECONOMIC_CENSUS_ID, params, max_rows=5000)
    source_id = _source_id(conn, title="2021年経済センサス 活動調査", dataset_id=ECONOMIC_CENSUS_ID, payload=payload)
    saved: dict[tuple[str, str], float] = {}
    written = 0
    for value in _values(payload):
        area_id = str(value.get(f"@{area_dim}") or "")
        item_code = str(value.get(f"@{item_dim}") or "")
        number = _number(value.get("$"))
        metric_key = item_codes.get(item_code)
        if area_id not in area_ids or metric_key is None or number is None:
            continue
        upsert_metric(
            conn,
            geo_id=f"ward:{area_id}",
            metric_key=metric_key,
            period="2021",
            value=number,
            sample_size=1,
            source_id=source_id,
            metric_version=METRIC_VERSION,
            quality_grade="A",
            source_year="2021",
            notes="2021年経済センサス 活動調査 9-2 / 全産業・経営組織総数",
        )
        saved[(area_id, metric_key)] = number
        written += 1
    for area_id in area_ids:
        establishments = saved.get((area_id, "economy.establishments"))
        employees = saved.get((area_id, "economy.employees"))
        if establishments and employees is not None and establishments > 0:
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key="economy.employees_per_establishment",
                period="2021",
                value=round(employees / establishments, 3),
                sample_size=1,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade="A",
                source_year="2021",
                notes="従業者数÷事業所数",
            )
            written += 1
    return written


def fetch_structure_metrics(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    _seed(conn)
    return fetch_day_night(client, conn, area_ids) + fetch_economic_census(client, conn, area_ids)
