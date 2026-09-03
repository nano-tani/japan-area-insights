from __future__ import annotations

from typing import Any

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

SOCIAL_TABLES = {
    "0000020205": {
        "dataset_key": "estat_ssds_education",
        "category": "education",
        "title": "社会・人口統計体系 E 教育",
        "metrics": {
            "E9101": ("education.graduates_total", "最終学歴人口（卒業者総数）", "人", "neutral"),
            "E9106": ("education.university_graduates", "大学・大学院卒業人口", "人", "higher"),
        },
    },
    "0000020206": {
        "dataset_key": "estat_ssds_labor",
        "category": "labor",
        "title": "社会・人口統計体系 F 労働",
        "metrics": {
            "F1101": ("labor.labor_force", "労働力人口", "人", "neutral"),
            "F1102": ("labor.employed", "就業者数", "人", "higher"),
        },
    },
    "0000020207": {
        "dataset_key": "estat_ssds_culture",
        "category": "culture",
        "title": "社会・人口統計体系 G 文化・スポーツ",
        "metrics": {
            "G1201": ("culture.community_centers", "公民館数", "施設", "neutral"),
            "G1401": ("culture.libraries", "図書館数", "施設", "neutral"),
        },
    },
    "0000020208": {
        "dataset_key": "estat_ssds_housing",
        "category": "housing",
        "title": "社会・人口統計体系 H 居住",
        "metrics": {
            "H1100": ("housing.total_housing", "総住宅数", "戸", "neutral"),
            "H110202": ("housing.vacant_housing", "空き家数", "戸", "lower"),
        },
    },
    "0000020209": {
        "dataset_key": "estat_ssds_health",
        "category": "health",
        "title": "社会・人口統計体系 I 健康・医療",
        "metrics": {
            "I5101": ("health.hospitals", "病院数", "施設", "neutral"),
            "I5102": ("health.clinics", "一般診療所数", "施設", "neutral"),
            "I5211": ("health.hospital_beds", "病院病床数", "床", "higher"),
            "I6101": ("health.medical_doctors", "医療施設医師数", "人", "higher"),
        },
    },
    "0000020210": {
        "dataset_key": "estat_ssds_welfare",
        "category": "welfare",
        "title": "社会・人口統計体系 J 福祉・社会保障",
        "metrics": {
            "J2301": ("welfare.elderly_facilities", "老人福祉施設数", "施設", "neutral"),
        },
    },
}

DERIVED_DEFINITIONS = [
    ("education.university_graduate_share", "education", "大学・大学院卒業者比率", "%", "higher", "ward", "estat_ssds_education", 1, "最終学歴人口（卒業者総数）に占める大学・大学院卒業人口"),
    ("labor.employed_share_of_labor_force", "labor", "労働力人口に占める就業者比率", "%", "higher", "ward", "estat_ssds_labor", 1, "就業者数÷労働力人口。一般的な就業率とは定義が異なる"),
    ("housing.vacancy_rate", "housing", "空き家率", "%", "lower", "ward", "estat_ssds_housing", 1, "空き家数÷総住宅数"),
    ("health.hospital_beds_per_10k", "health", "人口1万人当たり病院病床数", "床/万人", "higher", "ward", "estat_ssds_health", 1, "病院病床数÷最新人口×1万人"),
    ("health.doctors_per_10k", "health", "人口1万人当たり医療施設医師数", "人/万人", "higher", "ward", "estat_ssds_health", 1, "医療施設医師数÷最新人口×1万人"),
]


def _seed_catalog(conn) -> None:
    dataset_rows = [
        (
            spec["dataset_key"],
            "政府統計の総合窓口 e-Stat",
            stats_id,
            spec["category"],
            spec["title"],
            "年度次",
            "municipality",
            "extended",
            1,
            "市区町村データ / 基礎データ（廃置分合処理済）",
        )
        for stats_id, spec in SOCIAL_TABLES.items()
    ]
    conn.executemany(
        """
        INSERT INTO dataset_catalog(
            dataset_key, provider, api_id, category, title, source_vintage,
            granularity, refresh_mode, enabled, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_key) DO UPDATE SET
          api_id=excluded.api_id, title=excluded.title, notes=excluded.notes
        """,
        dataset_rows,
    )
    metric_rows = []
    for spec in SOCIAL_TABLES.values():
        for metric_key, label, unit, direction in spec["metrics"].values():
            metric_rows.append(
                (metric_key, spec["category"], label, unit, direction, "ward", spec["dataset_key"], 1, spec["title"])
            )
    metric_rows.extend(DERIVED_DEFINITIONS)
    conn.executemany(
        """
        INSERT INTO metric_definitions(
            metric_key, category, label, unit, direction, granularity,
            source_dataset_key, min_sample_size, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric_key) DO UPDATE SET
          category=excluded.category, label=excluded.label, unit=excluded.unit,
          direction=excluded.direction, source_dataset_key=excluded.source_dataset_key,
          description=excluded.description
        """,
        metric_rows,
    )


def _latest_population(conn, area_id: str) -> float | None:
    row = conn.execute(
        "SELECT population FROM population WHERE area_id=? AND population IS NOT NULL ORDER BY year DESC LIMIT 1",
        (area_id,),
    ).fetchone()
    return float(row["population"]) if row and row["population"] is not None else None


def fetch_social_metrics(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    _seed_catalog(conn)
    written = 0
    saved: dict[tuple[str, str], tuple[float, str, int]] = {}

    for stats_id, spec in SOCIAL_TABLES.items():
        meta = client.get_meta_info(stats_id)
        classes = _class_map(_meta_class_objects(meta))
        area_dim = _dimension_containing_codes(classes, area_ids)
        codes = list(spec["metrics"].keys())
        indicator_dim = _dimension_containing_codes(classes, codes)
        payload = client.get_stats_data_all(
            stats_id,
            {
                _filter_name(area_dim): ",".join(area_ids),
                _filter_name(indicator_dim): ",".join(codes),
                "metaGetFlg": "Y",
                "cntGetFlg": "N",
            },
            max_rows=100000,
        )
        data_classes = _class_map(_data_class_objects(payload))
        time_candidates = [
            dim_id for dim_id, mapping in data_classes.items()
            if any(_year_from_label(label) > 0 for label in mapping.values())
        ]
        time_dim = "time" if "time" in time_candidates else (time_candidates[0] if time_candidates else None)
        source_id = _source_id(conn, title=spec["title"], dataset_id=stats_id, payload=payload)
        candidates: dict[tuple[str, str], list[tuple[int, str, float]]] = {}
        for value in _values(payload):
            area_id = str(value.get(f"@{area_dim}") or "")
            code = str(value.get(f"@{indicator_dim}") or "")
            number = _number(value.get("$"))
            if area_id not in area_ids or code not in spec["metrics"] or number is None:
                continue
            time_code = str(value.get(f"@{time_dim}") or "") if time_dim else ""
            period = data_classes.get(time_dim or "", {}).get(time_code, time_code or "latest")
            candidates.setdefault((area_id, code), []).append((_year_from_label(period), period, number))

        for (area_id, code), rows in candidates.items():
            _, period, number = max(rows, key=lambda row: row[0])
            metric_key = spec["metrics"][code][0]
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
                notes=f"e-Stat {stats_id} / {code}",
            )
            saved[(area_id, metric_key)] = (number, period, source_id)
            written += 1

    for area_id in area_ids:
        derived: list[tuple[str, float, str, int, str]] = []
        graduates = saved.get((area_id, "education.graduates_total"))
        university = saved.get((area_id, "education.university_graduates"))
        if graduates and university and graduates[0] > 0:
            derived.append((
                "education.university_graduate_share",
                university[0] / graduates[0] * 100.0,
                max(university[1], graduates[1]),
                university[2],
                "E9106÷E9101",
            ))
        labor = saved.get((area_id, "labor.labor_force"))
        employed = saved.get((area_id, "labor.employed"))
        if labor and employed and labor[0] > 0:
            derived.append((
                "labor.employed_share_of_labor_force",
                employed[0] / labor[0] * 100.0,
                max(labor[1], employed[1]),
                employed[2],
                "F1102÷F1101",
            ))
        housing = saved.get((area_id, "housing.total_housing"))
        vacant = saved.get((area_id, "housing.vacant_housing"))
        if housing and vacant and housing[0] > 0:
            derived.append((
                "housing.vacancy_rate",
                vacant[0] / housing[0] * 100.0,
                max(housing[1], vacant[1]),
                vacant[2],
                "H110202÷H1100",
            ))
        population = _latest_population(conn, area_id)
        beds = saved.get((area_id, "health.hospital_beds"))
        doctors = saved.get((area_id, "health.medical_doctors"))
        if population and population > 0 and beds:
            derived.append(("health.hospital_beds_per_10k", beds[0] / population * 10000.0, beds[1], beds[2], "I5211÷最新人口×10000"))
        if population and population > 0 and doctors:
            derived.append(("health.doctors_per_10k", doctors[0] / population * 10000.0, doctors[1], doctors[2], "I6101÷最新人口×10000"))

        for metric_key, value, period, source_id, note in derived:
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key=metric_key,
                period=period,
                value=round(value, 3),
                sample_size=1,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade="A",
                source_year=period,
                notes=note,
            )
            written += 1
    return written
