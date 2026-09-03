from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_social_analysis import SOCIAL_TABLES, fetch_social_metrics

AREA = "13101"


def meta(stats_id):
    codes = [(code, values[1]) for code, values in SOCIAL_TABLES[stats_id]["metrics"].items()]
    return {
        "GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": [
            {"@id": "cat01", "CLASS": [{"@code": code, "@name": label} for code, label in codes]},
            {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
            {"@id": "time", "CLASS": [{"@code": "2025", "@name": "2025年度"}]},
        ]}}}
    }


VALUES = {
    "0000020205": {"E9101": 1000, "E9106": 600},
    "0000020206": {"F1101": 1000, "F1102": 970},
    "0000020207": {"G1201": 4, "G1401": 8},
    "0000020208": {"H1100": 50000, "H110202": 4000},
    "0000020209": {"I5101": 10, "I5102": 100, "I5211": 1500, "I6101": 500},
    "0000020210": {"J2301": 12},
}


class FakeClient:
    def get_meta_info(self, stats_id):
        return meta(stats_id)

    def get_stats_data_all(self, stats_id, params, **kwargs):
        codes = [(code, values[1]) for code, values in SOCIAL_TABLES[stats_id]["metrics"].items()]
        values = [
            {"@cat01": code, "@area": AREA, "@time": "2025", "$": str(number)}
            for code, number in VALUES[stats_id].items()
        ]
        return {
            "GET_STATS_DATA": {"STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": [
                    {"@id": "cat01", "CLASS": [{"@code": code, "@name": label} for code, label in codes]},
                    {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                    {"@id": "time", "CLASS": [{"@code": "2025", "@name": "2025年度"}]},
                ]},
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
            }}
        }


def test_social_metrics_and_derived_values(tmp_path: Path):
    db_path = tmp_path / "social.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        conn.execute(
            "INSERT INTO population(area_id,year,population) VALUES ('13101',2025,100000)"
        )
        ensure_analysis_schema(conn)
        count = fetch_social_metrics(FakeClient(), conn, [AREA])
        assert count == 20
        metrics = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics")}
        assert metrics["education.university_graduate_share"] == 60
        assert metrics["labor.employed_share_of_labor_force"] == 97
        assert metrics["housing.vacancy_rate"] == 8
        assert metrics["health.hospital_beds_per_10k"] == 150
        assert metrics["health.doctors_per_10k"] == 50
        assert metrics["welfare.elderly_facilities"] == 12
