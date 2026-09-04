from __future__ import annotations

import re
from typing import Any, Iterable

from .analysis_schema import ensure_analysis_schema, upsert_metric

METRIC_VERSION = "detail-v1"

DEFINITIONS = [
    ("people.population_total", "people", "総人口（公的統計体系）", "人", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aから抽出した総人口"),
    ("people.child_population", "people", "15歳未満人口", "人", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの15歳未満人口"),
    ("people.child_share", "people", "15歳未満人口比率", "%", "neutral", "ward", "estat_ssds_full_a", 1, "15歳未満人口÷同じ公表期の総人口"),
    ("people.working_age_population", "people", "15～64歳人口", "人", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの15～64歳人口"),
    ("people.working_age_share", "people", "15～64歳人口比率", "%", "neutral", "ward", "estat_ssds_full_a", 1, "15～64歳人口÷同じ公表期の総人口"),
    ("people.elderly_population", "people", "65歳以上人口", "人", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの65歳以上人口"),
    ("people.elderly_share", "people", "65歳以上人口比率", "%", "neutral", "ward", "estat_ssds_full_a", 1, "65歳以上人口÷同じ公表期の総人口"),
    ("people.age75plus_population", "people", "75歳以上人口", "人", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの75歳以上人口"),
    ("people.age75plus_share", "people", "75歳以上人口比率", "%", "neutral", "ward", "estat_ssds_full_a", 1, "75歳以上人口÷同じ公表期の総人口"),
    ("people.foreign_population", "people", "外国人人口", "人", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの外国人人口"),
    ("people.foreign_share", "people", "外国人人口比率", "%", "neutral", "ward", "estat_ssds_full_a", 1, "外国人人口÷同じ公表期の総人口"),
    ("household.general_households", "household", "一般世帯数", "世帯", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの一般世帯数"),
    ("household.single_households", "household", "単独世帯数", "世帯", "neutral", "ward", "estat_ssds_full_a", 1, "社会・人口統計体系Aの単独世帯数"),
    ("household.single_household_share", "household", "単独世帯比率", "%", "neutral", "ward", "estat_ssds_full_a", 1, "単独世帯数÷同じ公表期の一般世帯数"),
]


def _norm(value: Any) -> str:
    text = str(value or "").replace(" ", "").replace("　", "").replace("〜", "～")
    text = re.sub(r"[（(].*?[）)]", "", text)
    return text.strip()


def _match(label: str, wanted: str) -> bool:
    label_n = _norm(label)
    wanted_n = _norm(wanted)
    return label_n == wanted_n or label_n.startswith(wanted_n)


def _seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        DEFINITIONS,
    )


def _latest_ssds_a(conn, area_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        """
        SELECT gm.metric_key,gm.period,gm.value,gm.source_id,
               md.label,md.unit
        FROM geo_metrics gm
        JOIN metric_definitions md ON md.metric_key=gm.metric_key
        WHERE gm.geo_id=? AND gm.metric_version=?
          AND md.category='population_detail' AND gm.metric_key LIKE 'ssds.a.%'
        ORDER BY gm.period DESC,gm.metric_key
        """,
        (f"ward:{area_id}", METRIC_VERSION),
    ).fetchall()]


def _find(rows: Iterable[dict[str, Any]], wanted: str, *, period: str | None = None) -> dict[str, Any] | None:
    candidates = [row for row in rows if _match(str(row.get("label") or ""), wanted)]
    if period is not None:
        exact = [row for row in candidates if str(row.get("period") or "") == period]
        if exact:
            return exact[0]
    return candidates[0] if candidates else None


def derive_population_profile(conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    _seed(conn)
    written = 0
    for area_id in area_ids:
        rows = _latest_ssds_a(conn, area_id)
        total = _find(rows, "総人口")
        if not total or total.get("value") in (None, 0):
            continue
        period = str(total["period"])
        total_value = float(total["value"])
        source_id = int(total["source_id"]) if total.get("source_id") is not None else None
        raw_map = {
            "people.population_total": total,
            "people.child_population": _find(rows, "15歳未満人口", period=period),
            "people.working_age_population": _find(rows, "15～64歳人口", period=period),
            "people.elderly_population": _find(rows, "65歳以上人口", period=period),
            "people.age75plus_population": _find(rows, "75歳以上人口", period=period),
            "people.foreign_population": _find(rows, "外国人人口", period=period),
            "household.general_households": _find(rows, "一般世帯数", period=period),
            "household.single_households": _find(rows, "単独世帯数", period=period),
        }
        for key, row in raw_map.items():
            value = float(row["value"]) if row and row.get("value") is not None else None
            upsert_metric(
                conn, geo_id=f"ward:{area_id}", metric_key=key, period=period,
                value=value, sample_size=1, source_id=(int(row["source_id"]) if row and row.get("source_id") is not None else source_id),
                metric_version=METRIC_VERSION, quality_grade="A", source_year=period,
                notes="社会・人口統計体系Aからラベルで抽出。原指標コードはSSDS全指標カタログで確認できます。",
            )
            written += 1

        for raw_key, share_key in (
            ("people.child_population", "people.child_share"),
            ("people.working_age_population", "people.working_age_share"),
            ("people.elderly_population", "people.elderly_share"),
            ("people.age75plus_population", "people.age75plus_share"),
            ("people.foreign_population", "people.foreign_share"),
        ):
            row = raw_map.get(raw_key)
            value = float(row["value"]) / total_value * 100.0 if row and row.get("value") is not None and total_value > 0 else None
            upsert_metric(
                conn, geo_id=f"ward:{area_id}", metric_key=share_key, period=period,
                value=round(value, 3) if value is not None else None, sample_size=1, source_id=source_id,
                metric_version=METRIC_VERSION, quality_grade="A", source_year=period,
                notes="同一公表期の人口指標から算出。",
            )
            written += 1

        general = raw_map.get("household.general_households")
        single = raw_map.get("household.single_households")
        household_share = (
            float(single["value"]) / float(general["value"]) * 100.0
            if general and single and general.get("value") not in (None, 0) and single.get("value") is not None
            else None
        )
        upsert_metric(
            conn, geo_id=f"ward:{area_id}", metric_key="household.single_household_share", period=period,
            value=round(household_share, 3) if household_share is not None else None, sample_size=1, source_id=source_id,
            metric_version=METRIC_VERSION, quality_grade="A", source_year=period,
            notes="単独世帯数÷一般世帯数。",
        )
        written += 1
    return written
