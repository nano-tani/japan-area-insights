from pathlib import Path

from japan_area_insights.analysis_export import export_analysis_data
from japan_area_insights.db import connect, initialize
from japan_area_insights.jshis_analysis import (
    compute_ward_seismic_metrics,
    ensure_jshis_schema,
    normalize_ground_payload,
    normalize_hazard_payload,
    upsert_mesh_seismic,
)
from japan_area_insights.ward_maps import build_ward_mesh_payload


def _seed(conn):
    conn.execute(
        "INSERT INTO areas(area_id,prefecture_code,municipality_code,prefecture_name,municipality_name) VALUES ('13101','13','13101','東京都','千代田区')"
    )
    conn.execute(
        """
        INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
        VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
        """
    )
    for mesh_id, pop2025, pop2045 in (
        ("5339461111", 100.0, 110.0),
        ("5339461112", 300.0, 330.0),
    ):
        conn.execute(
            "INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101',?,2025,?)",
            (mesh_id, pop2025),
        )
        conn.execute(
            "INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101',?,2045,?)",
            (mesh_id, pop2045),
        )


def test_normalize_jshis_payloads():
    ground = normalize_ground_payload({
        "features": [{"properties": {"JCODE": "10", "JNAME": "台地", "AVS": "350", "ARV": "1.25", "AVS_EB": "410", "AVS_REF": "390"}}]
    })
    assert ground == {
        "microtopography_code": "10",
        "microtopography_name": "台地",
        "avs": 350.0,
        "arv": 1.25,
        "avs_eb": 410.0,
        "avs_ref": 390.0,
    }
    hazard = normalize_hazard_payload({
        "features": [{"properties": {
            "T30_I45_PS": "0.80",
            "T30_I50_PS": "0.60",
            "T30_I55_PS": "0.30",
            "T30_I60_PS": "0.08",
            "T30_P03_SI": "6.2",
            "T30_P06_SI": "5.9",
            "T30_P03_SV": "52.0",
            "T30_P06_SV": "41.0",
        }}]
    })
    assert hazard["t30_i55_ps"] == 0.30
    assert hazard["t30_p03_si"] == 6.2
    assert hazard["t30_p06_sv"] == 41.0


def test_compute_seismic_metrics_export_and_mesh_payload(tmp_path: Path):
    db_path = tmp_path / "jshis.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed(conn)
        ensure_jshis_schema(conn)
        ground_source = conn.execute(
            "INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at) VALUES ('J-SHIS','ground','https://example.test/ground','2026-09-01')"
        ).lastrowid
        hazard_source = conn.execute(
            "INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at) VALUES ('J-SHIS','hazard','https://example.test/hazard','2026-09-01')"
        ).lastrowid
        upsert_mesh_seismic(
            conn,
            mesh_id="5339461111",
            area_id="13101",
            ground={"microtopography_code": "10", "microtopography_name": "台地", "avs": 300.0, "arv": 1.2, "avs_eb": None, "avs_ref": None},
            hazard={"t30_i45_ps": 0.8, "t30_i50_ps": 0.6, "t30_i55_ps": 0.3, "t30_i60_ps": 0.1, "t30_p03_si": 6.2, "t30_p06_si": 5.8, "t30_p03_sv": 50.0, "t30_p06_sv": 40.0},
            source_ground_id=ground_source,
            source_hazard_id=hazard_source,
        )
        upsert_mesh_seismic(
            conn,
            mesh_id="5339461112",
            area_id="13101",
            ground={"microtopography_code": "20", "microtopography_name": "谷底低地", "avs": 200.0, "arv": 1.8, "avs_eb": None, "avs_ref": None},
            hazard={"t30_i45_ps": 1.0, "t30_i50_ps": 0.8, "t30_i55_ps": 0.5, "t30_i60_ps": 0.2, "t30_p03_si": 6.6, "t30_p06_si": 6.0, "t30_p03_sv": 70.0, "t30_p06_sv": 50.0},
            source_ground_id=ground_source,
            source_hazard_id=hazard_source,
        )
        count = compute_ward_seismic_metrics(conn)
        assert count == 12
        metrics = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE geo_id='ward:13101'")}
        assert metrics["seismic.ground_coverage"] == 100
        assert metrics["seismic.hazard_coverage"] == 100
        assert metrics["seismic.avs_median"] == 250
        assert metrics["seismic.arv_median"] == 1.5
        # Population weights are 25% / 75%.
        assert metrics["seismic.t30_i55_population_weighted_probability"] == 45
        assert metrics["seismic.t30_i60_population_weighted_probability"] == 17.5
        assert metrics["seismic.t30_p03_si_population_weighted"] == 6.5

        map_payload = build_ward_mesh_payload(conn, "13101")
        mesh = next(row for row in map_payload["meshes"] if row["mesh_id"] == "5339461112")
        assert mesh["microtopography"] == "谷底低地"
        assert mesh["avs30"] == 200
        assert mesh["earthquake_probability_30y_6lower"] == 50
        assert map_payload["seismic"]["hazard_version"] == "Y2024"

    output = tmp_path / "webdata"
    export_analysis_data(db_path, output)
    import json
    payload = json.loads((output / "analysis" / "ward" / "13101.json").read_text(encoding="utf-8"))
    assert "seismic" in payload["metrics"]
    assert payload["seismic_ground_types"][0]["name"] == "谷底低地"
    assert payload["seismic_ground_types"][0]["population_share"] == 75
    assert "J-SHIS" in payload["seismic_note"]["provider"]
