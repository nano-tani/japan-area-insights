from __future__ import annotations

from typing import Any, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .estat_analysis import (
    METRIC_VERSION,
    _class_map,
    _data_class_objects,
    _filter_name,
    _meta_class_objects,
    _number,
    _source_id,
    _values,
)
from .sources.estat import EStatClient

CENSUS_COMMUTING_ID = "0003454527"

FLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS commuting_flows (
    ward_area_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    counterpart_code TEXT NOT NULL,
    counterpart_name TEXT,
    flow_type TEXT NOT NULL,
    year INTEGER NOT NULL,
    count REAL NOT NULL,
    source_id INTEGER,
    PRIMARY KEY (ward_area_id,direction,counterpart_code,flow_type,year),
    FOREIGN KEY (ward_area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_commuting_flows_ward ON commuting_flows(ward_area_id,direction,count DESC);
"""

DEFINITIONS = [
    ("mobility.outbound_count", "mobility", "区外への通勤・通学流出", "人", "neutral", "ward", "estat_census_2020_commuting", 1, "常住地から他市区町村へ通勤・通学する人数。取得できたODセルの合計。"),
    ("mobility.inbound_count", "mobility", "区外からの通勤・通学流入", "人", "neutral", "ward", "estat_census_2020_commuting", 1, "他市区町村から当該区へ通勤・通学する人数。取得できたODセルの合計。"),
    ("mobility.net_inflow", "mobility", "通勤・通学純流入", "人", "neutral", "ward", "estat_census_2020_commuting", 1, "流入人数−流出人数。"),
    ("mobility.top_outbound_destination_share", "mobility", "最大流出先シェア", "%", "neutral", "ward", "estat_census_2020_commuting", 1, "区外流出のうち最大の通勤・通学先が占める比率。"),
    ("mobility.top_inbound_origin_share", "mobility", "最大流入元シェア", "%", "neutral", "ward", "estat_census_2020_commuting", 1, "区外流入のうち最大の常住地が占める比率。"),
    ("mobility.tokyo23_outbound_share", "mobility", "流出先の東京23区内比率", "%", "neutral", "ward", "estat_census_2020_commuting", 1, "区外への通勤・通学流出のうち相手先が東京23区の比率。"),
    ("mobility.tokyo23_inbound_share", "mobility", "流入元の東京23区内比率", "%", "neutral", "ward", "estat_census_2020_commuting", 1, "区外からの通勤・通学流入のうち相手元が東京23区の比率。"),
]


def ensure_commuting_schema(conn) -> None:
    ensure_analysis_schema(conn)
    conn.executescript(FLOW_SCHEMA)
    conn.execute(
        """
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES ('estat_census_2020_commuting','政府統計の総合窓口 e-Stat',?,'mobility',
                '2020年国勢調査 通勤・通学の市区町村間流動','2020','municipality_od','extended',1,
                'ODセルを区の流入・流出として保存。特殊地域・不詳は相手先コードとして残し、23区内比率からは除外。')
        ON CONFLICT(dataset_key) DO UPDATE SET api_id=excluded.api_id,title=excluded.title,notes=excluded.notes
        """,
        (CENSUS_COMMUTING_ID,),
    )
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        DEFINITIONS,
    )


def _norm(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("　", "").replace("・", "").strip()


def _mapping(obj: Mapping[str, Any]) -> dict[str, str]:
    classes = obj.get("CLASS") or []
    if isinstance(classes, Mapping):
        classes = [classes]
    return {str(row.get("@code")): str(row.get("@name") or row.get("@code")) for row in classes if isinstance(row, Mapping)}


def _identify_od_dimensions(meta: Any, area_ids: list[str]) -> tuple[str, str, dict[str, str], dict[str, str]] | None:
    objects = _meta_class_objects(meta)
    candidates: list[tuple[int, str, str, dict[str, str]]] = []
    for obj in objects:
        dim_id = str(obj.get("@id") or "")
        name = str(obj.get("@name") or "")
        mapping = _mapping(obj)
        overlap = sum(area_id in mapping for area_id in area_ids)
        if overlap:
            candidates.append((overlap, dim_id, name, mapping))
    if len(candidates) < 2:
        return None
    origin = next((row for row in candidates if "常住" in row[2]), None)
    destination = next((row for row in candidates if "従業" in row[2] or "通学" in row[2]), None)
    if origin and destination and origin[1] != destination[1]:
        return origin[1], destination[1], origin[3], destination[3]
    candidates.sort(reverse=True)
    first, second = candidates[0], candidates[1]
    return first[1], second[1], first[3], second[3]


def _preferred_code(mapping: Mapping[str, str]) -> str | None:
    labels = [(str(code), _norm(label)) for code, label in mapping.items()]
    priorities = (
        "総数",
        "15歳以上就業者通学者",
        "就業者通学者",
        "従業者通学者",
        "人口",
    )
    for wanted in priorities:
        for code, label in labels:
            if label == wanted:
                return code
    for wanted in ("就業者", "通学者"):
        for code, label in labels:
            if wanted in label and "総数" in label:
                return code
    if len(mapping) == 1:
        return str(next(iter(mapping)))
    return None


def _build_filters(classes: Mapping[str, Mapping[str, str]], keep: set[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for dim_id, mapping in classes.items():
        if dim_id in keep:
            continue
        code = _preferred_code(mapping)
        if code:
            filters[_filter_name(dim_id)] = code
    return filters


def _parse_flow_rows(
    payload: Any,
    *,
    ward_dim: str,
    counterpart_dim: str,
    ward_ids: set[str],
    counterpart_names: Mapping[str, str],
    direction: str,
    source_id: int,
) -> list[dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for value in _values(payload):
        ward = str(value.get(f"@{ward_dim}") or "")
        counterpart = str(value.get(f"@{counterpart_dim}") or "")
        count = _number(value.get("$"))
        if ward not in ward_ids or not counterpart or count is None or count <= 0:
            continue
        # Same-municipality cells are not external flows and are omitted from this table.
        if counterpart == ward:
            continue
        key = (ward, counterpart)
        result[key] = {
            "ward_area_id": ward,
            "direction": direction,
            "counterpart_code": counterpart,
            "counterpart_name": counterpart_names.get(counterpart),
            "flow_type": "work_school",
            "year": 2020,
            "count": float(count),
            "source_id": source_id,
        }
    return list(result.values())


def fetch_census_commuting_flows(client: EStatClient, conn, area_ids: list[str]) -> int:
    """Fetch 2020 Census OD flows for the target wards.

    Metadata varies across Census tables, so the two municipality dimensions are
    detected by labels/code overlap. If the table layout changes, this function
    returns zero instead of aborting the rest of the extended e-Stat refresh.
    """
    ensure_commuting_schema(conn)
    try:
        meta = client.get_meta_info(CENSUS_COMMUTING_ID)
        identified = _identify_od_dimensions(meta, area_ids)
        if not identified:
            print("Census commuting: could not identify two municipality dimensions; skipped")
            return 0
        origin_dim, destination_dim, origin_names, destination_names = identified
        classes = _class_map(_meta_class_objects(meta))
        base_filters = _build_filters(classes, {origin_dim, destination_dim})

        outbound_params = {
            **base_filters,
            _filter_name(origin_dim): ",".join(area_ids),
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
        }
        outbound_payload = client.get_stats_data_all(CENSUS_COMMUTING_ID, outbound_params, max_rows=150000)
        source_id = _source_id(
            conn,
            title="2020年国勢調査 通勤・通学市区町村間流動",
            dataset_id=CENSUS_COMMUTING_ID,
            payload=outbound_payload,
        )
        outbound = _parse_flow_rows(
            outbound_payload,
            ward_dim=origin_dim,
            counterpart_dim=destination_dim,
            ward_ids=set(area_ids),
            counterpart_names=destination_names,
            direction="outbound",
            source_id=source_id,
        )

        inbound_params = {
            **base_filters,
            _filter_name(destination_dim): ",".join(area_ids),
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
        }
        inbound_payload = client.get_stats_data_all(CENSUS_COMMUTING_ID, inbound_params, max_rows=150000)
        inbound = _parse_flow_rows(
            inbound_payload,
            ward_dim=destination_dim,
            counterpart_dim=origin_dim,
            ward_ids=set(area_ids),
            counterpart_names=origin_names,
            direction="inbound",
            source_id=source_id,
        )
    except Exception as exc:
        print(f"Census commuting: skipped after metadata/API mismatch: {exc}")
        return 0

    conn.execute("DELETE FROM commuting_flows WHERE ward_area_id IN (%s) AND year=2020" % ",".join("?" for _ in area_ids), tuple(area_ids))
    flows = outbound + inbound
    if flows:
        conn.executemany(
            """
            INSERT INTO commuting_flows(
                ward_area_id,direction,counterpart_code,counterpart_name,flow_type,year,count,source_id
            ) VALUES (
                :ward_area_id,:direction,:counterpart_code,:counterpart_name,:flow_type,:year,:count,:source_id
            )
            ON CONFLICT(ward_area_id,direction,counterpart_code,flow_type,year) DO UPDATE SET
                counterpart_name=excluded.counterpart_name,count=excluded.count,source_id=excluded.source_id
            """,
            flows,
        )

    written = 0
    tokyo23 = set(area_ids)
    for area_id in area_ids:
        out_rows = [row for row in outbound if row["ward_area_id"] == area_id]
        in_rows = [row for row in inbound if row["ward_area_id"] == area_id]
        out_total = sum(float(row["count"]) for row in out_rows)
        in_total = sum(float(row["count"]) for row in in_rows)
        out_top = max((float(row["count"]) for row in out_rows), default=0.0)
        in_top = max((float(row["count"]) for row in in_rows), default=0.0)
        out_23 = sum(float(row["count"]) for row in out_rows if row["counterpart_code"] in tokyo23)
        in_23 = sum(float(row["count"]) for row in in_rows if row["counterpart_code"] in tokyo23)
        values = {
            "mobility.outbound_count": out_total,
            "mobility.inbound_count": in_total,
            "mobility.net_inflow": in_total - out_total,
            "mobility.top_outbound_destination_share": out_top / out_total * 100.0 if out_total else None,
            "mobility.top_inbound_origin_share": in_top / in_total * 100.0 if in_total else None,
            "mobility.tokyo23_outbound_share": out_23 / out_total * 100.0 if out_total else None,
            "mobility.tokyo23_inbound_share": in_23 / in_total * 100.0 if in_total else None,
        }
        for key, number in values.items():
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key=key,
                period="2020",
                value=round(number, 3) if number is not None else None,
                sample_size=len(out_rows) if "outbound" in key else len(in_rows),
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade="A" if flows else "D",
                source_year="2020",
                notes="2020年国勢調査の市区町村間通勤・通学OD。区外セルのみ集計。",
            )
            written += 1
    return written
