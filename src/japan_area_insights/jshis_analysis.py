from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric

METRIC_VERSION = "detail-v1"
GROUND_VERSION = "V4"
HAZARD_VERSION = "Y2024"

JSHIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS mesh_seismic_metrics (
    mesh_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    ground_version TEXT,
    microtopography_code TEXT,
    microtopography_name TEXT,
    avs REAL,
    arv REAL,
    avs_eb REAL,
    avs_ref REAL,
    hazard_version TEXT,
    t30_i45_ps REAL,
    t30_i50_ps REAL,
    t30_i55_ps REAL,
    t30_i60_ps REAL,
    t30_p03_si REAL,
    t30_p06_si REAL,
    t30_p03_sv REAL,
    t30_p06_sv REAL,
    source_ground_id INTEGER,
    source_hazard_id INTEGER,
    fetched_at TEXT,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_ground_id) REFERENCES data_sources(source_id),
    FOREIGN KEY (source_hazard_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_mesh_seismic_area ON mesh_seismic_metrics(area_id);
"""

DATASETS = [
    (
        "jshis_surface_ground_v4",
        "防災科学技術研究所 J-SHIS（地震ハザードステーション）",
        "J-SHIS:sstrct:V4",
        "seismic",
        "表層地盤250mメッシュ V4",
        "V4",
        "mesh250",
        "extended",
        1,
        "250mメッシュの代表値。微地形区分、AVS30、地震動増幅率等。",
    ),
    (
        "jshis_pshm_y2024",
        "防災科学技術研究所 J-SHIS（地震ハザードステーション）",
        "J-SHIS:pshm:Y2024:AVR:TTL_MTTL",
        "seismic",
        "確率論的地震動予測地図 Y2024",
        "Y2024",
        "mesh250",
        "extended",
        1,
        "確率論的地震動予測モデル。地点の将来を保証するものではない。",
    ),
]

DEFINITIONS = [
    ("seismic.ground_coverage", "seismic", "表層地盤データ取得率", "%", "higher", "ward", "jshis_surface_ground_v4", 1, "2025人口がある250mメッシュのうちJ-SHIS表層地盤を取得できた比率"),
    ("seismic.hazard_coverage", "seismic", "地震ハザードデータ取得率", "%", "higher", "ward", "jshis_pshm_y2024", 1, "2025人口がある250mメッシュのうちJ-SHIS確率論的地震ハザードを取得できた比率"),
    ("seismic.avs_median", "seismic", "AVS30中央値", "m/s", "neutral", "ward", "jshis_surface_ground_v4", 1, "表層30mの平均S波速度（AVS30）の250mメッシュ中央値"),
    ("seismic.arv_median", "seismic", "地震動増幅率中央値", "倍", "neutral", "ward", "jshis_surface_ground_v4", 1, "工学的基盤から地表への最大速度増幅率ARVの250mメッシュ中央値"),
    ("seismic.t30_i45_population_weighted_probability", "seismic", "今後30年 震度5弱以上確率", "%", "neutral", "ward", "jshis_pshm_y2024", 1, "J-SHIS確率を2025年推計人口で加重平均した参考値"),
    ("seismic.t30_i50_population_weighted_probability", "seismic", "今後30年 震度5強以上確率", "%", "neutral", "ward", "jshis_pshm_y2024", 1, "J-SHIS確率を2025年推計人口で加重平均した参考値"),
    ("seismic.t30_i55_population_weighted_probability", "seismic", "今後30年 震度6弱以上確率", "%", "neutral", "ward", "jshis_pshm_y2024", 1, "J-SHIS確率を2025年推計人口で加重平均した参考値"),
    ("seismic.t30_i60_population_weighted_probability", "seismic", "今後30年 震度6強以上確率", "%", "neutral", "ward", "jshis_pshm_y2024", 1, "J-SHIS確率を2025年推計人口で加重平均した参考値"),
    ("seismic.t30_p03_si_population_weighted", "seismic", "30年超過確率3% 計測震度", "震度", "neutral", "ward", "jshis_pshm_y2024", 1, "30年間の超過確率3%に対応する計測震度を2025人口で加重平均"),
    ("seismic.t30_p06_si_population_weighted", "seismic", "30年超過確率6% 計測震度", "震度", "neutral", "ward", "jshis_pshm_y2024", 1, "30年間の超過確率6%に対応する計測震度を2025人口で加重平均"),
    ("seismic.t30_p03_sv_population_weighted", "seismic", "30年超過確率3% 地表最大速度", "cm/s", "neutral", "ward", "jshis_pshm_y2024", 1, "30年間の超過確率3%に対応する地表最大速度を2025人口で加重平均"),
    ("seismic.t30_p06_sv_population_weighted", "seismic", "30年超過確率6% 地表最大速度", "cm/s", "neutral", "ward", "jshis_pshm_y2024", 1, "30年間の超過確率6%に対応する地表最大速度を2025人口で加重平均"),
]


def ensure_jshis_schema(conn) -> None:
    ensure_analysis_schema(conn)
    conn.executescript(JSHIS_SCHEMA)
    conn.executemany(
        """
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,source_vintage=excluded.source_vintage,notes=excluded.notes
        """,
        DATASETS,
    )
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        DEFINITIONS,
    )


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _first_properties(payload: Any) -> Mapping[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    features = payload.get("features")
    if isinstance(features, list) and features:
        first = features[0]
        if isinstance(first, Mapping):
            props = first.get("properties")
            if isinstance(props, Mapping):
                return props
    props = payload.get("properties")
    return props if isinstance(props, Mapping) else None


def normalize_ground_payload(payload: Any) -> dict[str, Any] | None:
    props = _first_properties(payload)
    if not props:
        return None
    return {
        "microtopography_code": str(props.get("JCODE") or "") or None,
        "microtopography_name": str(props.get("JNAME") or "") or None,
        "avs": _number(props.get("AVS")),
        "arv": _number(props.get("ARV")),
        "avs_eb": _number(props.get("AVS_EB")),
        "avs_ref": _number(props.get("AVS_REF")),
    }


def normalize_hazard_payload(payload: Any) -> dict[str, Any] | None:
    props = _first_properties(payload)
    if not props:
        return None
    return {
        "t30_i45_ps": _number(props.get("T30_I45_PS")),
        "t30_i50_ps": _number(props.get("T30_I50_PS")),
        "t30_i55_ps": _number(props.get("T30_I55_PS")),
        "t30_i60_ps": _number(props.get("T30_I60_PS")),
        "t30_p03_si": _number(props.get("T30_P03_SI")),
        "t30_p06_si": _number(props.get("T30_P06_SI")),
        "t30_p03_sv": _number(props.get("T30_P03_SV")),
        "t30_p06_sv": _number(props.get("T30_P06_SV")),
    }


def upsert_mesh_seismic(
    conn,
    *,
    mesh_id: str,
    area_id: str,
    ground: Mapping[str, Any] | None,
    hazard: Mapping[str, Any] | None,
    source_ground_id: int | None,
    source_hazard_id: int | None,
    ground_version: str = GROUND_VERSION,
    hazard_version: str = HAZARD_VERSION,
) -> None:
    ensure_jshis_schema(conn)
    values = {
        "mesh_id": mesh_id,
        "area_id": area_id,
        "ground_version": ground_version if ground else None,
        "microtopography_code": ground.get("microtopography_code") if ground else None,
        "microtopography_name": ground.get("microtopography_name") if ground else None,
        "avs": ground.get("avs") if ground else None,
        "arv": ground.get("arv") if ground else None,
        "avs_eb": ground.get("avs_eb") if ground else None,
        "avs_ref": ground.get("avs_ref") if ground else None,
        "hazard_version": hazard_version if hazard else None,
        "t30_i45_ps": hazard.get("t30_i45_ps") if hazard else None,
        "t30_i50_ps": hazard.get("t30_i50_ps") if hazard else None,
        "t30_i55_ps": hazard.get("t30_i55_ps") if hazard else None,
        "t30_i60_ps": hazard.get("t30_i60_ps") if hazard else None,
        "t30_p03_si": hazard.get("t30_p03_si") if hazard else None,
        "t30_p06_si": hazard.get("t30_p06_si") if hazard else None,
        "t30_p03_sv": hazard.get("t30_p03_sv") if hazard else None,
        "t30_p06_sv": hazard.get("t30_p06_sv") if hazard else None,
        "source_ground_id": source_ground_id if ground else None,
        "source_hazard_id": source_hazard_id if hazard else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    conn.execute(
        """
        INSERT INTO mesh_seismic_metrics(
            mesh_id,area_id,ground_version,microtopography_code,microtopography_name,
            avs,arv,avs_eb,avs_ref,hazard_version,
            t30_i45_ps,t30_i50_ps,t30_i55_ps,t30_i60_ps,
            t30_p03_si,t30_p06_si,t30_p03_sv,t30_p06_sv,
            source_ground_id,source_hazard_id,fetched_at
        ) VALUES (
            :mesh_id,:area_id,:ground_version,:microtopography_code,:microtopography_name,
            :avs,:arv,:avs_eb,:avs_ref,:hazard_version,
            :t30_i45_ps,:t30_i50_ps,:t30_i55_ps,:t30_i60_ps,
            :t30_p03_si,:t30_p06_si,:t30_p03_sv,:t30_p06_sv,
            :source_ground_id,:source_hazard_id,:fetched_at
        )
        ON CONFLICT(mesh_id) DO UPDATE SET
            area_id=excluded.area_id,
            ground_version=COALESCE(excluded.ground_version,mesh_seismic_metrics.ground_version),
            microtopography_code=COALESCE(excluded.microtopography_code,mesh_seismic_metrics.microtopography_code),
            microtopography_name=COALESCE(excluded.microtopography_name,mesh_seismic_metrics.microtopography_name),
            avs=COALESCE(excluded.avs,mesh_seismic_metrics.avs),
            arv=COALESCE(excluded.arv,mesh_seismic_metrics.arv),
            avs_eb=COALESCE(excluded.avs_eb,mesh_seismic_metrics.avs_eb),
            avs_ref=COALESCE(excluded.avs_ref,mesh_seismic_metrics.avs_ref),
            hazard_version=COALESCE(excluded.hazard_version,mesh_seismic_metrics.hazard_version),
            t30_i45_ps=COALESCE(excluded.t30_i45_ps,mesh_seismic_metrics.t30_i45_ps),
            t30_i50_ps=COALESCE(excluded.t30_i50_ps,mesh_seismic_metrics.t30_i50_ps),
            t30_i55_ps=COALESCE(excluded.t30_i55_ps,mesh_seismic_metrics.t30_i55_ps),
            t30_i60_ps=COALESCE(excluded.t30_i60_ps,mesh_seismic_metrics.t30_i60_ps),
            t30_p03_si=COALESCE(excluded.t30_p03_si,mesh_seismic_metrics.t30_p03_si),
            t30_p06_si=COALESCE(excluded.t30_p06_si,mesh_seismic_metrics.t30_p06_si),
            t30_p03_sv=COALESCE(excluded.t30_p03_sv,mesh_seismic_metrics.t30_p03_sv),
            t30_p06_sv=COALESCE(excluded.t30_p06_sv,mesh_seismic_metrics.t30_p06_sv),
            source_ground_id=COALESCE(excluded.source_ground_id,mesh_seismic_metrics.source_ground_id),
            source_hazard_id=COALESCE(excluded.source_hazard_id,mesh_seismic_metrics.source_hazard_id),
            fetched_at=excluded.fetched_at
        """,
        values,
    )


def _median(values: Iterable[float | None]) -> float | None:
    vals = sorted(float(value) for value in values if value is not None)
    if not vals:
        return None
    n = len(vals)
    if n % 2:
        return round(vals[n // 2], 3)
    return round((vals[n // 2 - 1] + vals[n // 2]) / 2.0, 3)


def _coverage_grade(share: float) -> str:
    if share >= 95:
        return "A"
    if share >= 80:
        return "B"
    if share >= 50:
        return "C"
    return "D"


def _weighted(rows: list[Mapping[str, Any]], key: str, *, probability: bool = False) -> tuple[float | None, int]:
    usable = [row for row in rows if row.get(key) is not None and float(row.get("population_2025") or 0) > 0]
    total_weight = sum(float(row["population_2025"]) for row in usable)
    if total_weight <= 0:
        return None, len(usable)
    value = sum(float(row[key]) * float(row["population_2025"]) for row in usable) / total_weight
    if probability:
        value *= 100.0
    return round(value, 3), len(usable)


def compute_ward_seismic_metrics(conn) -> int:
    ensure_jshis_schema(conn)
    written = 0
    areas = conn.execute("SELECT area_id FROM areas ORDER BY area_id").fetchall()
    for area in areas:
        area_id = str(area["area_id"])
        rows = [dict(row) for row in conn.execute(
            """
            SELECT fp.mesh_id,fp.projected_population AS population_2025,msm.*
            FROM future_population fp
            LEFT JOIN mesh_seismic_metrics msm ON msm.mesh_id=fp.mesh_id
            WHERE fp.area_id=? AND fp.year=2025 AND fp.projected_population>0
            ORDER BY fp.mesh_id
            """,
            (area_id,),
        ).fetchall()]
        total = len(rows)
        if not total:
            continue
        ground_rows = [row for row in rows if row.get("ground_version")]
        hazard_rows = [row for row in rows if row.get("hazard_version")]
        ground_share = len(ground_rows) / total * 100.0
        hazard_share = len(hazard_rows) / total * 100.0
        source_ground_ids = [int(row["source_ground_id"]) for row in ground_rows if row.get("source_ground_id") is not None]
        source_hazard_ids = [int(row["source_hazard_id"]) for row in hazard_rows if row.get("source_hazard_id") is not None]
        source_ground_id = max(source_ground_ids) if source_ground_ids else None
        source_hazard_id = max(source_hazard_ids) if source_hazard_ids else None

        metric_values: list[tuple[str, float | None, int, int | None, str, str]] = [
            ("seismic.ground_coverage", round(ground_share, 3), len(ground_rows), source_ground_id, _coverage_grade(ground_share), GROUND_VERSION),
            ("seismic.hazard_coverage", round(hazard_share, 3), len(hazard_rows), source_hazard_id, _coverage_grade(hazard_share), HAZARD_VERSION),
            ("seismic.avs_median", _median(row.get("avs") for row in ground_rows), len(ground_rows), source_ground_id, _coverage_grade(ground_share), GROUND_VERSION),
            ("seismic.arv_median", _median(row.get("arv") for row in ground_rows), len(ground_rows), source_ground_id, _coverage_grade(ground_share), GROUND_VERSION),
        ]
        for key, probability in (
            ("t30_i45_ps", True), ("t30_i50_ps", True), ("t30_i55_ps", True), ("t30_i60_ps", True),
            ("t30_p03_si", False), ("t30_p06_si", False), ("t30_p03_sv", False), ("t30_p06_sv", False),
        ):
            value, sample = _weighted(hazard_rows, key, probability=probability)
            metric_values.append((
                f"seismic.{key}_population_weighted" if not probability else f"seismic.{key.replace('_ps','')}_population_weighted_probability",
                value,
                sample,
                source_hazard_id,
                _coverage_grade(hazard_share),
                HAZARD_VERSION,
            ))

        for metric_key, value, sample, source_id, grade, source_year in metric_values:
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key=metric_key,
                period=source_year,
                value=value,
                sample_size=sample,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade=grade,
                source_year=source_year,
                is_estimate=1,
                notes="防災科学技術研究所J-SHIS。250m代表値/確率論モデルであり、個別地点の安全性や将来の発生を保証しません。",
            )
            written += 1
    return written


def ground_type_distribution(conn, area_id: str) -> list[dict[str, Any]]:
    ensure_jshis_schema(conn)
    rows = conn.execute(
        """
        SELECT msm.microtopography_code,msm.microtopography_name,
               COUNT(*) AS mesh_count,
               SUM(COALESCE(fp.projected_population,0)) AS population_2025
        FROM future_population fp
        JOIN mesh_seismic_metrics msm ON msm.mesh_id=fp.mesh_id
        WHERE fp.area_id=? AND fp.year=2025 AND msm.microtopography_name IS NOT NULL
        GROUP BY msm.microtopography_code,msm.microtopography_name
        ORDER BY population_2025 DESC,mesh_count DESC,microtopography_name
        """,
        (area_id,),
    ).fetchall()
    total_pop = sum(float(row["population_2025"] or 0) for row in rows)
    return [
        {
            "code": row["microtopography_code"],
            "name": row["microtopography_name"],
            "mesh_count": int(row["mesh_count"]),
            "population_2025": round(float(row["population_2025"] or 0), 2),
            "population_share": round(float(row["population_2025"] or 0) / total_pop * 100.0, 3) if total_pop > 0 else None,
        }
        for row in rows
    ]
