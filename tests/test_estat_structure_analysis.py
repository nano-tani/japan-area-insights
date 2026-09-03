from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_structure_analysis import fetch_structure_metrics

AREA = "13101"


class FakeClient:
    def get_meta_info(self, stats_id):
        if stats_id == "0003454499":
            classes = [
                {"@id": "cat01", "CLASS": [{"@code": "001", "@name": "昼夜間人口比率"}]},
                {"@id": "cat02", "CLASS": [{"@code": "000", "@name": "総数"}]},
                {"@id": "cat03", "CLASS": [{"@code": "000", "@name": "総数"}]},
                {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                {"@id": "time", "CLASS": [{"@code": "2020", "@name": "2020年"}]},
            ]
        else:
            classes = [
                {"@id": "cat01", "CLASS": [
                    {"@code": "01", "@name": "事業所数"},
                    {"@code": "02", "@name": "従業者数_男女計"},
                ]},
                {"@id": "cat02", "CLASS": [{"@code": "00", "@name": "全産業"}]},
                {"@id": "cat03", "CLASS": [{"@code": "00", "@name": "総数"}]},
                {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                {"@id": "time", "CLASS": [{"@code": "2021", "@name": "2021年"}]},
            ]
        return {"GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": classes}}}}

    def get_stats_data_all(self, stats_id, params, **kwargs):
        if stats_id == "0003454499":
            classes = [
                {"@id": "cat01", "CLASS": [{"@code": "001", "@name": "昼夜間人口比率"}]},
                {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                {"@id": "time", "CLASS": [{"@code": "2020", "@name": "2020年"}]},
            ]
            values = [{"@cat01": "001", "@area": AREA, "@time": "2020", "$": "185.2"}]
        else:
            classes = [
                {"@id": "cat01", "CLASS": [
                    {"@code": "01", "@name": "事業所数"},
                    {"@code": "02", "@name": "従業者数_男女計"},
                ]},
                {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
                {"@id": "time", "CLASS": [{"@code": "2021", "@name": "2021年"}]},
            ]
            values = [
                {"@cat01": "01", "@area": AREA, "@time": "2021", "$": "10000"},
                {"@cat01": "02", "@area": AREA, "@time": "2021", "$": "200000"},
            ]
        return {"GET_STATS_DATA": {"STATISTICAL_DATA": {
            "CLASS_INF": {"CLASS_OBJ": classes},
            "DATA_INF": {"VALUE": values},
            "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
        }}}


def test_structure_metrics(tmp_path: Path):
    db_path = tmp_path / "structure.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        ensure_analysis_schema(conn)
        count = fetch_structure_metrics(FakeClient(), conn, [AREA])
        assert count == 4
        metrics = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics")}
        assert metrics["economy.day_night_population_ratio"] == 185.2
        assert metrics["economy.establishments"] == 10000
        assert metrics["economy.employees"] == 200000
        assert metrics["economy.employees_per_establishment"] == 20
