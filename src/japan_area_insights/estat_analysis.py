from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .sources.estat import BASE_URL, EStatClient

MIGRATION_IN_ID = "0004044293"
MIGRATION_OUT_ID = "0004044294"
SSDS_ECONOMY_ID = "0000020103"
SSDS_ADMIN_ID = "0000020104"
METRIC_VERSION = "detail-v1"

SSDS_METRICS = {
    SSDS_ECONOMY_ID: {
        "C120110": "economy.taxable_income",
        "C120120": "economy.income_taxpayers",
    },
    SSDS_ADMIN_ID: {
        "D2201": "economy.fiscal_strength_index",
        "D2211": "economy.real_debt_service_ratio",
        "D2212": "economy.future_burden_ratio",
    },
}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "...", "X", "x"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _meta_class_objects(meta: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    root = meta.get("GET_META_INFO", {}).get("METADATA_INF", {})
    class_inf = root.get("CLASS_INF", {}) or {}
    return _list(class_inf.get("CLASS_OBJ"))


def _data_class_objects(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    statistical = payload.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
    return _list((statistical.get("CLASS_INF", {}) or {}).get("CLASS_OBJ"))


def _class_map(objects: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for obj in objects:
        dim_id = str(obj.get("@id") or "")
        if not dim_id:
            continue
        result[dim_id] = {
            str(item.get("@code")): str(item.get("@name") or "")
            for item in _list(obj.get("CLASS"))
            if item.get("@code") is not None
        }
    return result


def _dimension_name_map(objects: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    return {str(obj.get("@id")): str(obj.get("@name") or "") for obj in objects if obj.get("@id")}


def _filter_name(dim_id: str) -> str:
    if not dim_id:
        raise ValueError("empty e-Stat dimension id")
    return "cd" + dim_id[0].upper() + dim_id[1:]


def _dimension_containing_codes(classes: Mapping[str, Mapping[str, str]], codes: Iterable[str]) -> str:
    wanted = set(map(str, codes))
    best: tuple[int, str] | None = None
    for dim_id, mapping in classes.items():
        overlap = len(wanted.intersection(mapping.keys()))
        if overlap and (best is None or overlap > best[0]):
            best = (overlap, dim_id)
    if best is None:
        raise ValueError(f"e-Stat metadata does not contain requested codes: {sorted(wanted)[:5]}")
    return best[1]


def _dimension_matching_labels(
    classes: Mapping[str, Mapping[str, str]],
    predicates: Iterable[Callable[[str], bool]],
) -> str | None:
    checks = list(predicates)
    for dim_id, mapping in classes.items():
        labels = list(mapping.values())
        if all(any(check(label) for label in labels) for check in checks):
            return dim_id
    return None


def _code_by_label(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(label):
            return code
    return None


def _values(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    statistical = payload.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
    return _list((statistical.get("DATA_INF", {}) or {}).get("VALUE"))


def _year_from_label(label: str) -> int:
    matches = re.findall(r"(?:19|20)\d{2}", label)
    return max(map(int, matches)) if matches else -1


def _source_id(conn, *, title: str, dataset_id: str, payload: Mapping[str, Any]) -> int:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    cursor = conn.execute(
        """
        INSERT INTO data_sources(
            source_name, dataset_id, source_url, terms_url,
            published_at, fetched_at, raw_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"政府統計の総合窓口 e-Stat / {title}",
            dataset_id,
            f"https://www.e-stat.go.jp/stat-search/database?statdisp_id={dataset_id}",
            "https://www.e-stat.go.jp/terms-of-use",
            None,
            datetime.now(timezone.utc).isoformat(),
            hashlib.sha256(raw).hexdigest(),
        ),
    )
    return int(cursor.lastrowid)


def fetch_ssds_metrics(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    written = 0
    saved: dict[tuple[str, str], tuple[float, str, int]] = {}

    for stats_id, metric_map in SSDS_METRICS.items():
        meta = client.get_meta_info(stats_id)
        meta_objects = _meta_class_objects(meta)
        classes = _class_map(meta_objects)
        area_dim = _dimension_containing_codes(classes, area_ids)
        indicator_dim = _dimension_containing_codes(classes, metric_map.keys())
        params = {
            _filter_name(area_dim): ",".join(area_ids),
            _filter_name(indicator_dim): ",".join(metric_map.keys()),
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
        }
        payload = client.get_stats_data_all(stats_id, params, max_rows=50000)
        data_classes = _class_map(_data_class_objects(payload))
        source_id = _source_id(
            conn,
            title="社会・人口統計体系",
            dataset_id=stats_id,
            payload=payload,
        )
        # Determine a likely time dimension by names/codes in the returned cube.
        time_dim = _dimension_matching_labels(
            data_classes,
            [lambda label: _year_from_label(label) > 0],
        )
        candidates: dict[tuple[str, str], list[tuple[int, str, float]]] = {}
        for value in _values(payload):
            area_id = str(value.get(f"@{area_dim}") or "")
            indicator = str(value.get(f"@{indicator_dim}") or "")
            number = _number(value.get("$"))
            if area_id not in area_ids or indicator not in metric_map or number is None:
                continue
            time_code = str(value.get(f"@{time_dim}") or "") if time_dim else ""
            time_label = data_classes.get(time_dim or "", {}).get(time_code, time_code or "latest")
            candidates.setdefault((area_id, indicator), []).append((_year_from_label(time_label), time_label, number))

        for (area_id, indicator), rows in candidates.items():
            _, period, number = max(rows, key=lambda row: row[0])
            metric_key = metric_map[indicator]
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key=metric_key,
                period=period,
                value=number,
                sample_size=1,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade="A",
                source_year=period,
                notes=f"e-Stat {stats_id} / {indicator}",
            )
            saved[(area_id, metric_key)] = (number, period, source_id)
            written += 1

    # Useful derived value that remains traceable to the two original SSDS cells.
    for area_id in area_ids:
        income = saved.get((area_id, "economy.taxable_income"))
        taxpayers = saved.get((area_id, "economy.income_taxpayers"))
        if income and taxpayers and taxpayers[0] not in (0, None):
            period = max(income[1], taxpayers[1])
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key="economy.taxable_income_per_taxpayer",
                period=period,
                value=round(income[0] / taxpayers[0], 3),
                sample_size=1,
                source_id=income[2],
                metric_version=METRIC_VERSION,
                quality_grade="A",
                source_year=period,
                notes="C120110 課税対象所得 ÷ C120120 所得割納税義務者数",
            )
            written += 1
    return written


def _migration_filters(meta: Mapping[str, Any], area_ids: list[str], ages: list[str]) -> tuple[dict[str, Any], str, str]:
    objects = _meta_class_objects(meta)
    classes = _class_map(objects)
    area_dim = _dimension_containing_codes(classes, area_ids)
    age_dim = _dimension_matching_labels(
        classes,
        [lambda label: "20" in label and "29" in label, lambda label: "30" in label and "39" in label],
    )
    if age_dim is None:
        raise ValueError("could not identify migration age dimension")

    wanted_age_codes = [
        code for code, label in classes[age_dim].items()
        if any(target in label.replace(" ", "") for target in ages)
    ]
    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(age_dim): ",".join(wanted_age_codes),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }

    # Collapse non-target dimensions to totals so a 100M-cell source cube becomes
    # a few hundred cells.  Keep the table item dimension if it has one member.
    for dim_id, mapping in classes.items():
        if dim_id in {area_dim, age_dim}:
            continue
        labels = list(mapping.values())
        code: str | None = None
        if any("総数（前住地" in label or "総数(前住地" in label for label in labels):
            code = _code_by_label(mapping, lambda label: "総数" in label and "前住地" in label)
        elif any("総数（現住地" in label or "総数(現住地" in label for label in labels):
            code = _code_by_label(mapping, lambda label: "総数" in label and "現住地" in label)
        elif {"男", "女"}.issubset(set(labels)) or ("男" in labels and "女" in labels):
            code = _code_by_label(mapping, lambda label: label == "総数")
        elif any(label == "移動者" for label in labels):
            code = _code_by_label(mapping, lambda label: label == "移動者")
        elif any("2025年" in label for label in labels):
            code = _code_by_label(mapping, lambda label: "2025年" in label)
        elif len(mapping) == 1:
            code = next(iter(mapping))
        if code:
            params[_filter_name(dim_id)] = code
    return params, area_dim, age_dim


def _migration_values(payload: Mapping[str, Any], area_dim: str, age_dim: str) -> dict[str, dict[str, float]]:
    classes = _class_map(_data_class_objects(payload))
    result: dict[str, dict[str, float]] = {}
    for value in _values(payload):
        area_id = str(value.get(f"@{area_dim}") or "")
        age_code = str(value.get(f"@{age_dim}") or "")
        age_label = classes.get(age_dim, {}).get(age_code, age_code)
        number = _number(value.get("$"))
        if area_id and number is not None:
            result.setdefault(area_id, {})[age_label] = number
    return result


def _age_value(row: Mapping[str, float], *tokens: str) -> float:
    for label, value in row.items():
        compact = label.replace(" ", "").replace("　", "")
        if all(token in compact for token in tokens):
            return float(value)
    return 0.0


def fetch_migration_metrics(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    age_labels = ["総数", "0～9歳", "20～29歳", "30～39歳"]
    payloads: dict[str, Any] = {}
    parsed: dict[str, dict[str, dict[str, float]]] = {}
    source_ids: dict[str, int] = {}
    for stats_id, direction in ((MIGRATION_IN_ID, "in"), (MIGRATION_OUT_ID, "out")):
        meta = client.get_meta_info(stats_id)
        params, area_dim, age_dim = _migration_filters(meta, area_ids, age_labels)
        payload = client.get_stats_data_all(stats_id, params, max_rows=20000)
        payloads[direction] = payload
        parsed[direction] = _migration_values(payload, area_dim, age_dim)
        source_ids[direction] = _source_id(
            conn,
            title="住民基本台帳人口移動報告",
            dataset_id=stats_id,
            payload=payload,
        )

    written = 0
    for area_id in area_ids:
        inbound = parsed.get("in", {}).get(area_id, {})
        outbound = parsed.get("out", {}).get(area_id, {})
        in_total = _age_value(inbound, "総数")
        out_total = _age_value(outbound, "総数")
        in_0_9 = _age_value(inbound, "0", "9")
        out_0_9 = _age_value(outbound, "0", "9")
        in_20 = _age_value(inbound, "20", "29")
        out_20 = _age_value(outbound, "20", "29")
        in_30 = _age_value(inbound, "30", "39")
        out_30 = _age_value(outbound, "30", "39")
        values = {
            "migration.in_total": (in_total, source_ids.get("in")),
            "migration.out_total": (out_total, source_ids.get("out")),
            "migration.net_total": (in_total - out_total, source_ids.get("in")),
            "migration.net_20_39": ((in_20 + in_30) - (out_20 + out_30), source_ids.get("in")),
            "migration.net_0_9": (in_0_9 - out_0_9, source_ids.get("in")),
        }
        for metric_key, (number, source_id) in values.items():
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key=metric_key,
                period="2025",
                value=number,
                sample_size=1,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade="A",
                source_year="2025",
                notes="住民基本台帳人口移動報告。移動者（外国人含む）の総数。",
            )
            written += 1
    return written


def fetch_extended_estat(client: EStatClient, conn, area_ids: list[str]) -> int:
    return fetch_ssds_metrics(client, conn, area_ids) + fetch_migration_metrics(client, conn, area_ids)
