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

STRUCTURE_TABLE = "0004019380"  # 6-2 annual, municipality, 2020+
USE_TABLE = "0004019381"        # 7-2 annual, municipality, 2020+

STRUCTURE_LABELS = {
    "wood": "木造",
    "src": "鉄骨鉄筋コンクリート造",
    "rc": "鉄筋コンクリート造",
    "steel": "鉄骨造",
}

USE_LABELS = {
    "residential": "居住専用",
    "semi_residential": "居住専用準住宅",
    "mixed_residential": "居住産業併用",
    "office": "情報通信業用建築物",
    "wholesale_retail": "卸売業，小売業用建築物",
    "finance": "金融業，保険業用建築物",
    "real_estate": "不動産業用建築物",
    "accommodation_food": "宿泊業，飲食サービス業用建築物",
    "education": "教育，学習支援業用建築物",
    "medical_welfare": "医療，福祉用建築物",
}


def _norm(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("　", "").replace(",", "，").strip()


def _code(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(_norm(label)):
            return str(code)
    return None


def _dimension(classes: Mapping[str, Mapping[str, str]], required: tuple[str, ...], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    wanted = [_norm(value) for value in required]
    best: tuple[int, str] | None = None
    for dim_id, mapping in classes.items():
        if dim_id in excluded:
            continue
        labels = [_norm(value) for value in mapping.values()]
        score = sum(any(label == token for label in labels) for token in wanted)
        if score and (best is None or score > best[0]):
            best = (score, dim_id)
    if not best:
        raise ValueError(f"building-start dimension not found: {required}")
    return best[1]


def _time_dimension(classes: Mapping[str, Mapping[str, str]], excluded: set[str]) -> str | None:
    best: tuple[int, str] | None = None
    for dim_id, mapping in classes.items():
        if dim_id in excluded:
            continue
        count = sum(_year_from_label(str(label)) > 0 for label in mapping.values())
        if count and (best is None or count > best[0]):
            best = (count, dim_id)
    return best[1] if best else None


def _total_code(mapping: Mapping[str, str]) -> str | None:
    return (
        _code(mapping, lambda label: label == "総計")
        or _code(mapping, lambda label: label == "計")
        or _code(mapping, lambda label: label == "総数")
    )


def _seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,notes=excluded.notes
        """,
        [
            ("estat_building_starts_structure", "政府統計の総合窓口 e-Stat", STRUCTURE_TABLE, "construction", "建築物着工統計 6-2 市区町村別・構造別", "2020年度以降", "municipality", "extended", 1, "API DBで利用可能な最新完了年度を採用。建築物の数・床面積。"),
            ("estat_building_starts_use", "政府統計の総合窓口 e-Stat", USE_TABLE, "construction", "建築物着工統計 7-2 市区町村別・用途別", "2020年度以降", "municipality", "extended", 1, "API DBで利用可能な最新完了年度を採用。用途別床面積。"),
        ],
    )
    definitions = [
        ("construction.building_count", "construction", "着工建築物数", "棟", "neutral", "ward", "estat_building_starts_structure", 1, "最新API完了年度の着工建築物数"),
        ("construction.floor_area", "construction", "着工床面積", "㎡", "neutral", "ward", "estat_building_starts_structure", 1, "最新API完了年度の着工床面積合計"),
        ("construction.floor_area_per_building", "construction", "1棟当たり着工床面積", "㎡/棟", "neutral", "ward", "estat_building_starts_structure", 1, "着工床面積÷着工建築物数"),
        ("construction.buildings_per_10k_population", "construction", "人口1万人当たり着工建築物", "棟/万人", "neutral", "ward", "estat_building_starts_structure", 1, "着工建築物数÷最新人口×1万人"),
        ("construction.floor_area_per_capita", "construction", "人口1人当たり着工床面積", "㎡/人", "neutral", "ward", "estat_building_starts_structure", 1, "着工床面積÷最新人口"),
        ("construction.floor_area_per_100_homes", "construction", "住宅100戸当たり着工床面積", "㎡/100戸", "neutral", "ward", "estat_building_starts_structure", 1, "着工床面積÷2023住宅数×100。住宅以外の建築を含むため開発量の参考値。"),
        ("construction.wood_floor_area_share", "construction", "木造着工床面積比率", "%", "neutral", "ward", "estat_building_starts_structure", 1, "全着工床面積に占める木造"),
        ("construction.src_floor_area_share", "construction", "SRC着工床面積比率", "%", "neutral", "ward", "estat_building_starts_structure", 1, "全着工床面積に占める鉄骨鉄筋コンクリート造"),
        ("construction.rc_floor_area_share", "construction", "RC着工床面積比率", "%", "neutral", "ward", "estat_building_starts_structure", 1, "全着工床面積に占める鉄筋コンクリート造"),
        ("construction.steel_floor_area_share", "construction", "鉄骨造着工床面積比率", "%", "neutral", "ward", "estat_building_starts_structure", 1, "全着工床面積に占める鉄骨造"),
        ("construction.residential_floor_area_share", "construction", "居住系着工床面積比率", "%", "neutral", "ward", "estat_building_starts_use", 1, "居住専用・準住宅・居住産業併用の床面積合計÷全用途"),
        ("construction.office_floor_area_share", "construction", "情報通信業用着工床面積比率", "%", "neutral", "ward", "estat_building_starts_use", 1, "全用途に占める情報通信業用建築物床面積"),
        ("construction.wholesale_retail_floor_area_share", "construction", "卸売・小売用着工床面積比率", "%", "neutral", "ward", "estat_building_starts_use", 1, "全用途に占める卸売・小売業用建築物床面積"),
        ("construction.accommodation_food_floor_area_share", "construction", "宿泊・飲食用着工床面積比率", "%", "neutral", "ward", "estat_building_starts_use", 1, "全用途に占める宿泊・飲食サービス業用建築物床面積"),
        ("construction.medical_welfare_floor_area_share", "construction", "医療・福祉用着工床面積比率", "%", "neutral", "ward", "estat_building_starts_use", 1, "全用途に占める医療・福祉用建築物床面積"),
    ]
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        definitions,
    )


def _latest_population(conn, area_id: str) -> float | None:
    row = conn.execute(
        "SELECT population FROM population WHERE area_id=? AND population IS NOT NULL ORDER BY year DESC LIMIT 1",
        (area_id,),
    ).fetchone()
    return float(row["population"]) if row and row["population"] is not None else None


def _housing_stock(conn, area_id: str) -> float | None:
    row = conn.execute(
        """
        SELECT value FROM geo_metrics
        WHERE geo_id=? AND metric_key='housing2023.total_housing' AND metric_version=?
        ORDER BY period DESC LIMIT 1
        """,
        (f"ward:{area_id}", METRIC_VERSION),
    ).fetchone()
    return float(row["value"]) if row and row["value"] is not None else None


def _write(conn, area_id: str, key: str, period: str, value: float | None, source_id: int, note: str) -> int:
    upsert_metric(
        conn,
        geo_id=f"ward:{area_id}",
        metric_key=key,
        period=period,
        value=round(value, 3) if value is not None else None,
        sample_size=1,
        source_id=source_id,
        metric_version=METRIC_VERSION,
        quality_grade="A",
        source_year=period,
        notes=note,
    )
    return 1


def _fetch_structure(client: EStatClient, conn, area_ids: list[str]) -> tuple[int, dict[str, tuple[str, float, float]]]:
    meta = client.get_meta_info(STRUCTURE_TABLE)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    item_dim = _dimension(classes, ("建築物の数", "床面積の合計"), {area_dim})
    structure_dim = _dimension(classes, ("木造", "鉄筋コンクリート造", "鉄骨造"), {area_dim, item_dim})
    item_codes = {
        "count": _code(classes[item_dim], lambda label: label == "建築物の数"),
        "area": _code(classes[item_dim], lambda label: label == "床面積の合計"),
    }
    total_structure = _total_code(classes[structure_dim])
    structure_codes = {slug: _code(classes[structure_dim], lambda label, wanted=_norm(name): label == wanted) for slug, name in STRUCTURE_LABELS.items()}
    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(item_dim): ",".join(code for code in item_codes.values() if code),
        _filter_name(structure_dim): ",".join(code for code in [total_structure, *structure_codes.values()] if code),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }
    payload = client.get_stats_data_all(STRUCTURE_TABLE, params, max_rows=20000)
    data_classes = _class_map(_data_class_objects(payload))
    time_dim = _time_dimension(data_classes, {area_dim, item_dim, structure_dim})
    source_id = _source_id(conn, title="建築物着工統計 6-2 市区町村別・構造別", dataset_id=STRUCTURE_TABLE, payload=payload)
    reverse_item = {code: name for name, code in item_codes.items() if code}
    reverse_structure = {code: slug for slug, code in structure_codes.items() if code}
    if total_structure:
        reverse_structure[total_structure] = "total"
    latest: dict[tuple[str, str, str], tuple[int, str, float]] = {}
    for row in _values(payload):
        area_id = str(row.get(f"@{area_dim}") or "")
        item = reverse_item.get(str(row.get(f"@{item_dim}") or ""))
        structure = reverse_structure.get(str(row.get(f"@{structure_dim}") or ""))
        number = _number(row.get("$"))
        if area_id not in area_ids or not item or not structure or number is None:
            continue
        time_code = str(row.get(f"@{time_dim}") or "") if time_dim else ""
        period = data_classes.get(time_dim or "", {}).get(time_code, time_code or "latest")
        year = _year_from_label(period)
        key = (area_id, item, structure)
        previous = latest.get(key)
        if previous is None or year > previous[0]:
            latest[key] = (year, period, number)

    written = 0
    totals: dict[str, tuple[str, float, float]] = {}
    for area_id in area_ids:
        total_count_row = latest.get((area_id, "count", "total"))
        total_area_row = latest.get((area_id, "area", "total"))
        if not total_count_row or not total_area_row:
            continue
        period = max(total_count_row[1], total_area_row[1])
        building_count = total_count_row[2]
        floor_area = total_area_row[2]
        totals[area_id] = (period, building_count, floor_area)
        population = _latest_population(conn, area_id)
        housing = _housing_stock(conn, area_id)
        values = {
            "construction.building_count": building_count,
            "construction.floor_area": floor_area,
            "construction.floor_area_per_building": floor_area / building_count if building_count else None,
            "construction.buildings_per_10k_population": building_count / population * 10000 if population else None,
            "construction.floor_area_per_capita": floor_area / population if population else None,
            "construction.floor_area_per_100_homes": floor_area / housing * 100 if housing else None,
        }
        for slug in STRUCTURE_LABELS:
            row = latest.get((area_id, "area", slug))
            values[f"construction.{slug}_floor_area_share"] = row[2] / floor_area * 100 if row and floor_area else None
        for key, value in values.items():
            written += _write(conn, area_id, key, period, value, source_id, "建築物着工統計6-2。API DBで利用可能な最新完了年度。住宅以外の建築物も含む。")
    return written, totals


def _fetch_use(client: EStatClient, conn, area_ids: list[str], totals: dict[str, tuple[str, float, float]]) -> int:
    meta = client.get_meta_info(USE_TABLE)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    item_dim = _dimension(classes, ("床面積の合計",), {area_dim})
    use_dim = _dimension(classes, ("居住専用", "居住産業併用"), {area_dim, item_dim})
    floor_item = _code(classes[item_dim], lambda label: label == "床面積の合計")
    total_use = _total_code(classes[use_dim])
    use_codes = {slug: _code(classes[use_dim], lambda label, wanted=_norm(name): label == wanted) for slug, name in USE_LABELS.items()}
    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(item_dim): floor_item,
        _filter_name(use_dim): ",".join(code for code in [total_use, *use_codes.values()] if code),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }
    payload = client.get_stats_data_all(USE_TABLE, params, max_rows=20000)
    data_classes = _class_map(_data_class_objects(payload))
    time_dim = _time_dimension(data_classes, {area_dim, item_dim, use_dim})
    source_id = _source_id(conn, title="建築物着工統計 7-2 市区町村別・用途別", dataset_id=USE_TABLE, payload=payload)
    reverse_use = {code: slug for slug, code in use_codes.items() if code}
    if total_use:
        reverse_use[total_use] = "total"
    latest: dict[tuple[str, str], tuple[int, str, float]] = {}
    for row in _values(payload):
        area_id = str(row.get(f"@{area_dim}") or "")
        use = reverse_use.get(str(row.get(f"@{use_dim}") or ""))
        number = _number(row.get("$"))
        if area_id not in area_ids or not use or number is None:
            continue
        time_code = str(row.get(f"@{time_dim}") or "") if time_dim else ""
        period = data_classes.get(time_dim or "", {}).get(time_code, time_code or "latest")
        year = _year_from_label(period)
        key = (area_id, use)
        previous = latest.get(key)
        if previous is None or year > previous[0]:
            latest[key] = (year, period, number)

    written = 0
    for area_id in area_ids:
        total_row = latest.get((area_id, "total"))
        denominator = total_row[2] if total_row else (totals.get(area_id, ("", 0, 0))[2] or None)
        period = total_row[1] if total_row else totals.get(area_id, ("latest", 0, 0))[0]
        def amount(slug: str) -> float | None:
            row = latest.get((area_id, slug))
            return row[2] if row else None
        residential_parts = [amount("residential"), amount("semi_residential"), amount("mixed_residential")]
        residential = sum(value for value in residential_parts if value is not None) if any(value is not None for value in residential_parts) else None
        values = {
            "construction.residential_floor_area_share": residential / denominator * 100 if residential is not None and denominator else None,
            "construction.office_floor_area_share": amount("office") / denominator * 100 if amount("office") is not None and denominator else None,
            "construction.wholesale_retail_floor_area_share": amount("wholesale_retail") / denominator * 100 if amount("wholesale_retail") is not None and denominator else None,
            "construction.accommodation_food_floor_area_share": amount("accommodation_food") / denominator * 100 if amount("accommodation_food") is not None and denominator else None,
            "construction.medical_welfare_floor_area_share": amount("medical_welfare") / denominator * 100 if amount("medical_welfare") is not None and denominator else None,
        }
        for key, value in values.items():
            written += _write(conn, area_id, key, period, value, source_id, "建築物着工統計7-2。API DBで利用可能な最新完了年度の用途別床面積。")
    return written


def fetch_building_starts(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    _seed(conn)
    written, totals = _fetch_structure(client, conn, area_ids)
    written += _fetch_use(client, conn, area_ids, totals)
    return written
