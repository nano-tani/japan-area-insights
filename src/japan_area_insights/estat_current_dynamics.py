from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .estat_analysis import (
    METRIC_VERSION,
    _class_map,
    _dimension_containing_codes,
    _filter_name,
    _meta_class_objects,
    _number,
    _source_id,
    _values,
)
from .sources.estat import EStatClient

VITAL_STATS_CODE = "00450011"
VITAL_YEAR = 2024


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _norm(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("　", "").replace(",", "，").strip()


def _code(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(_norm(label)):
            return str(code)
    return None


def _year(label: Any) -> int:
    years = re.findall(r"(?:19|20)\d{2}", str(label or ""))
    return max(map(int, years)) if years else -1


def _preferred_code(mapping: Mapping[str, str], year: int | None = None) -> str | None:
    totals = {"総数", "計", "総計", "男女計", "総数（男女計）", "総数(男女計)", "全数", "全体"}
    code = _code(mapping, lambda label: label in totals)
    if code:
        return code
    code = _code(mapping, lambda label: label.startswith("総数"))
    if code:
        return code
    if year is not None:
        for code, label in mapping.items():
            if _year(label) == year:
                return str(code)
    if len(mapping) == 1:
        return str(next(iter(mapping)))
    return None


def _table_entries(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    root = payload.get("GET_STATS_LIST", {}).get("DATALIST_INF", {}) or {}
    rows = root.get("TABLE_INF") or root.get("LIST_INF") or []
    return [row for row in _list(rows) if isinstance(row, Mapping)]


def _entry_id(entry: Mapping[str, Any]) -> str | None:
    value = entry.get("@id") or entry.get("id")
    if value:
        return str(value)
    for key in ("TABLE_INF", "TITLE_SPEC", "STATISTICS_NAME_SPEC"):
        nested = entry.get(key)
        if isinstance(nested, Mapping):
            value = nested.get("@id") or nested.get("id")
            if value:
                return str(value)
    return None


def discover_vital_table(client: EStatClient, kind: str, year: int = VITAL_YEAR) -> str:
    if kind not in {"birth", "death"}:
        raise ValueError(kind)
    keywords = ("出生数", "市区町村", "出生の場所") if kind == "birth" else ("死亡数", "市区町村", "年齢")
    for search_word in (" AND ".join(keywords), f"{keywords[0]} AND 市区町村", keywords[0]):
        payload = client.get_stats_list(
            {"statsCode": VITAL_STATS_CODE, "surveyYears": str(year), "searchWord": search_word, "limit": 100}
        )
        candidates: list[tuple[int, str]] = []
        for entry in _table_entries(payload):
            stats_id = _entry_id(entry)
            if not stats_id:
                continue
            text = json.dumps(entry, ensure_ascii=False)
            score = sum(token in text for token in keywords)
            if "市区町村別" in text:
                score += 1
            if str(year) in text:
                score += 1
            candidates.append((score, stats_id))
        if candidates:
            score, stats_id = max(candidates, key=lambda row: row[0])
            if score >= 2:
                return stats_id
    raise RuntimeError(f"could not discover {year} vital-statistics table for {kind}")


def _fetch_totals(client: EStatClient, conn, stats_id: str, area_ids: list[str], title: str) -> tuple[dict[str, float], int]:
    meta = client.get_meta_info(stats_id)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    params: dict[str, Any] = {_filter_name(area_dim): ",".join(area_ids), "metaGetFlg": "Y", "cntGetFlg": "N"}
    for dim_id, mapping in classes.items():
        if dim_id == area_dim:
            continue
        code = _preferred_code(mapping, VITAL_YEAR)
        if code is None:
            raise ValueError(f"cannot select total/year for {stats_id} dimension {dim_id}")
        params[_filter_name(dim_id)] = code
    payload = client.get_stats_data_all(stats_id, params, max_rows=5000)
    source_id = _source_id(conn, title=title, dataset_id=stats_id, payload=payload)
    values: dict[str, float] = {}
    for row in _values(payload):
        area_id = str(row.get(f"@{area_dim}") or "")
        number = _number(row.get("$"))
        if area_id in area_ids and number is not None:
            values[area_id] = number
    return values, source_id


def _reference_population(conn, area_id: str) -> tuple[float | None, int | None]:
    row = conn.execute(
        """SELECT year,population FROM population
           WHERE area_id=? AND population IS NOT NULL AND population>0
           ORDER BY ABS(year-?),year DESC LIMIT 1""",
        (area_id, VITAL_YEAR),
    ).fetchone()
    if row is None:
        return None, None
    return float(row["population"]), int(row["year"])


def _seed(conn, birth_id: str, death_id: str) -> None:
    conn.executemany(
        """INSERT INTO dataset_catalog(
               dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes
           ) VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(dataset_key) DO UPDATE SET api_id=excluded.api_id,title=excluded.title,notes=excluded.notes""",
        [
            ("estat_vital_birth_2024", "政府統計の総合窓口 e-Stat", birth_id, "demographics", "2024人口動態統計 出生", "2024", "municipality", "extended", 1, "確定数・市区町村総数"),
            ("estat_vital_death_2024", "政府統計の総合窓口 e-Stat", death_id, "demographics", "2024人口動態統計 死亡", "2024", "municipality", "extended", 1, "確定数・市区町村・性年齢総数"),
        ],
    )
    definitions = [
        ("demographics.vital_births", "demographics", "出生数", "人", "neutral", "ward", "estat_vital_birth_2024", 1, "人口動態統計確定数の出生数"),
        ("demographics.vital_deaths", "demographics", "死亡数", "人", "neutral", "ward", "estat_vital_death_2024", 1, "人口動態統計確定数の死亡数"),
        ("demographics.natural_change", "demographics", "出生死亡差", "人", "higher", "ward", "estat_vital_birth_2024", 1, "出生数－死亡数"),
        ("demographics.births_per_1000_reference", "demographics", "出生数（人口千人あたり参考）", "人/千人", "neutral", "ward", "estat_vital_birth_2024", 1, "最も近い利用可能人口年を分母にした参考値"),
        ("demographics.deaths_per_1000_reference", "demographics", "死亡数（人口千人あたり参考）", "人/千人", "neutral", "ward", "estat_vital_death_2024", 1, "最も近い利用可能人口年を分母にした参考値"),
        ("demographics.natural_change_per_1000_reference", "demographics", "出生死亡差（人口千人あたり参考）", "人/千人", "higher", "ward", "estat_vital_birth_2024", 1, "最も近い利用可能人口年を分母にした参考値"),
    ]
    conn.executemany(
        """INSERT INTO metric_definitions(
               metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description
           ) VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description""",
        definitions,
    )


def _write(conn, area_id: str, key: str, value: float | None, source_id: int, *, quality: str = "A", estimate: bool = False, source_year: str = "2024", note: str = "") -> int:
    upsert_metric(
        conn,
        geo_id=f"ward:{area_id}", metric_key=key, period="2024", value=round(value, 3) if value is not None else None,
        sample_size=1, source_id=source_id, metric_version=METRIC_VERSION, quality_grade=quality,
        source_year=source_year, is_estimate=estimate, notes=note,
    )
    return 1


def fetch_vital_dynamics(client: EStatClient, conn, area_ids: list[str]) -> int:
    birth_id = discover_vital_table(client, "birth")
    death_id = discover_vital_table(client, "death")
    _seed(conn, birth_id, death_id)
    births, birth_source = _fetch_totals(client, conn, birth_id, area_ids, "2024人口動態統計 出生")
    deaths, death_source = _fetch_totals(client, conn, death_id, area_ids, "2024人口動態統計 死亡")
    derived_source = _source_id(
        conn,
        title="2024人口動態統計 出生・死亡（派生）",
        dataset_id=f"vital:2024:{birth_id}:{death_id}",
        payload={"birth_stats_id": birth_id, "death_stats_id": death_id},
    )

    written = 0
    for area_id in area_ids:
        birth = births.get(area_id)
        death = deaths.get(area_id)
        natural = birth - death if birth is not None and death is not None else None
        written += _write(conn, area_id, "demographics.vital_births", birth, birth_source, note="人口動態統計確定数")
        written += _write(conn, area_id, "demographics.vital_deaths", death, death_source, note="人口動態統計確定数")
        written += _write(conn, area_id, "demographics.natural_change", natural, derived_source, note="出生数－死亡数")
        population, population_year = _reference_population(conn, area_id)
        for key, numerator, source_id in (
            ("demographics.births_per_1000_reference", birth, birth_source),
            ("demographics.deaths_per_1000_reference", death, death_source),
            ("demographics.natural_change_per_1000_reference", natural, derived_source),
        ):
            value = numerator / population * 1000.0 if numerator is not None and population else None
            written += _write(
                conn, area_id, key, value, source_id,
                quality="B", estimate=True,
                source_year=f"2024/pop:{population_year}" if population_year else "2024",
                note=(f"分母は{population_year}年人口。年次が一致しない場合があるため参考値。" if population_year else "人口分母なし。"),
            )
    return written


def fetch_current_dynamics(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    try:
        return fetch_vital_dynamics(client, conn, area_ids)
    except Exception as exc:
        print(f"warning: skipped 2024 vital dynamics: {exc}")
        return 0
