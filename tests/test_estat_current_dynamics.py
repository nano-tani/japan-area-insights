from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_current_dynamics import fetch_current_dynamics

AREA = "13101"
BIRTH_ID = "birth-2024"
DEATH_ID = "death-2024"


def class_objects(stats_id):
    common = [
        {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
        {"@id": "time", "CLASS": [{"@code": "2024", "@name": "2024年"}]},
    ]
    if stats_id == BIRTH_ID:
        return [
            {"@id": "item", "CLASS": [{"@code": "births", "@name": "出生数"}]},
            {"@id": "place", "CLASS": [{"@code": "all", "@name": "総数"}, {"@code": "hospital", "@name": "病院"}]},
            {"@id": "attendant", "CLASS": [{"@code": "all", "@name": "総数"}, {"@code": "doctor", "@name": "医師"}]},
            *common,
        ]
    return [
        {"@id": "item", "CLASS": [{"@code": "deaths", "@name": "死亡数"}]},
        {"@id": "sex", "CLASS": [{"@code": "all", "@name": "総数"}, {"@code": "m", "@name": "男"}]},
        {"@id": "age", "CLASS": [{"@code": "all", "@name": "総数"}, {"@code": "0", "@name": "0～4歳"}]},
        *common,
    ]


class FakeClient:
    def get_stats_list(self, params=None):
        search = str((params or {}).get("searchWord") or "")
        if "出生" in search:
            entry = {
                "@id": BIRTH_ID,
                "TITLE_SPEC": {"TABLE_NAME": "出生数，都道府県・市区町村・出生の場所・出生時の立会者別"},
                "SURVEY_DATE": "2024",
            }
        else:
            entry = {
                "@id": DEATH_ID,
                "TITLE_SPEC": {"TABLE_NAME": "死亡数，都道府県・市区町村・性・年齢別・市区町村別"},
                "SURVEY_DATE": "2024",
            }
        return {"GET_STATS_LIST": {"DATALIST_INF": {"TABLE_INF": [entry]}}}

    def get_meta_info(self, stats_id):
        return {"GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": class_objects(stats_id)}}}}

    def get_stats_data_all(self, stats_id, params, **kwargs):
        if stats_id == BIRTH_ID:
            values = [{"@item": "births", "@place": "all", "@attendant": "all", "@area": AREA, "@time": "2024", "$": "800"}]
        else:
            values = [{"@item": "deaths", "@sex": "all", "@age": "all", "@area": AREA, "@time": "2024", "$": "600"}]
        return {
            "GET_STATS_DATA": {"STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": class_objects(stats_id)},
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
            }}
        }


def test_current_vital_dynamics(tmp_path: Path):
    db_path = tmp_path / "dynamics.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        conn.execute("INSERT INTO population(area_id,year,population) VALUES (?, ?, ?)", (AREA, 2025, 100000))
        count = fetch_current_dynamics(FakeClient(), conn, [AREA])
        assert count == 6
        metrics = {
            row["metric_key"]: row["value"]
            for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE metric_key LIKE 'demographics.%'")
        }
        assert metrics["demographics.vital_births"] == 800
        assert metrics["demographics.vital_deaths"] == 600
        assert metrics["demographics.natural_change"] == 200
        assert metrics["demographics.births_per_1000_reference"] == 8
        assert metrics["demographics.deaths_per_1000_reference"] == 6
        assert metrics["demographics.natural_change_per_1000_reference"] == 2
        quality = conn.execute(
            "SELECT quality_grade,is_estimate,source_year FROM metric_quality WHERE metric_key='demographics.births_per_1000_reference'"
        ).fetchone()
        assert quality["quality_grade"] == "B"
        assert quality["is_estimate"] == 1
        assert quality["source_year"] == "2024/pop:2025"
