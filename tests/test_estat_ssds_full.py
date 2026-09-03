from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_ssds_full import SSDS_TABLES, fetch_ssds_full_catalog

AREA = "13101"
CODES = {
    "A": ("A1101", "総人口（人）"),
    "B": ("B1101", "総面積（北方地域及び竹島を除く）"),
    "C": ("C120110", "課税対象所得"),
    "D": ("D2201", "財政力指数"),
    "E": ("E9101", "最終学歴人口（卒業者総数）"),
    "F": ("F1101", "労働力人口"),
    "G": ("G1201", "公民館数"),
    "H": ("H1100", "総住宅数"),
    "I": ("I5101", "病院数"),
    "J": ("J2301", "老人福祉施設数"),
}


class FakeClient:
    def _section(self, stats_id):
        return next(section for section, (sid, _, _) in SSDS_TABLES.items() if sid == stats_id)

    def get_meta_info(self, stats_id):
        section = self._section(stats_id)
        code, label = CODES[section]
        return {
            "GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": [
                {"@id": "cat01", "@name": "観測値", "CLASS": [{"@code": code, "@name": f"{code}_{label}"}]},
                {"@id": "area", "@name": "地域", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                {"@id": "time", "@name": "時間軸", "CLASS": [
                    {"@code": "2023", "@name": "2023年度"},
                    {"@code": "2025", "@name": "2025年度"},
                ]},
            ]}}}
        }

    def get_stats_data_all(self, stats_id, params, **kwargs):
        section = self._section(stats_id)
        code, label = CODES[section]
        base = ord(section) - ord("A") + 1
        values = [
            {"@cat01": code, "@area": AREA, "@time": "2023", "@unit": "人" if section == "A" else "値", "$": str(base * 10)},
            {"@cat01": code, "@area": AREA, "@time": "2025", "@unit": "人" if section == "A" else "値", "$": str(base * 20)},
        ]
        return {
            "GET_STATS_DATA": {"STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": [
                    {"@id": "cat01", "CLASS": [{"@code": code, "@name": f"{code}_{label}"}]},
                    {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                    {"@id": "time", "CLASS": [
                        {"@code": "2023", "@name": "2023年度"},
                        {"@code": "2025", "@name": "2025年度"},
                    ]},
                ]},
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": 2, "FROM_NUMBER": 1, "TO_NUMBER": 2},
            }}
        }


def test_full_ssds_catalog_stores_latest_a_to_j_cells(tmp_path: Path):
    db_path = tmp_path / "ssds.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        count = fetch_ssds_full_catalog(FakeClient(), conn, [AREA], batch_size=2)
        assert count == 10
        metrics = {
            row["metric_key"]: (row["period"], row["value"])
            for row in conn.execute("SELECT metric_key,period,value FROM geo_metrics WHERE metric_key LIKE 'ssds.%'")
        }
        assert metrics["ssds.a.a1101"] == ("2025年度", 20)
        assert metrics["ssds.j.j2301"] == ("2025年度", 200)
        definitions = {
            row["metric_key"]: (row["category"], row["label"], row["unit"])
            for row in conn.execute("SELECT metric_key,category,label,unit FROM metric_definitions WHERE metric_key LIKE 'ssds.%'")
        }
        assert definitions["ssds.a.a1101"] == ("population_detail", "総人口（人）", "人")
        assert definitions["ssds.b.b1101"][0] == "environment_detail"
        datasets = conn.execute("SELECT COUNT(*) FROM dataset_catalog WHERE dataset_key LIKE 'estat_ssds_full_%'").fetchone()[0]
        assert datasets == 10
