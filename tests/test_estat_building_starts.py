from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema, upsert_metric
from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_analysis import METRIC_VERSION
from japan_area_insights.estat_building_starts import STRUCTURE_TABLE, USE_TABLE, fetch_building_starts

AREA = "13101"


STRUCTURE_CLASSES = [
    {"@id": "item", "CLASS": [
        {"@code": "count", "@name": "建築物の数"},
        {"@code": "area", "@name": "床面積の合計"},
    ]},
    {"@id": "structure", "CLASS": [
        {"@code": "total", "@name": "総計"},
        {"@code": "wood", "@name": "木造"},
        {"@code": "src", "@name": "鉄骨鉄筋コンクリート造"},
        {"@code": "rc", "@name": "鉄筋コンクリート造"},
        {"@code": "steel", "@name": "鉄骨造"},
    ]},
    {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
    {"@id": "time", "CLASS": [
        {"@code": "2022", "@name": "2022年"},
        {"@code": "2023", "@name": "2023年"},
    ]},
]

USE_CLASSES = [
    {"@id": "item", "CLASS": [{"@code": "area", "@name": "床面積の合計"}]},
    {"@id": "use", "CLASS": [
        {"@code": "total", "@name": "総計"},
        {"@code": "res", "@name": "居住専用"},
        {"@code": "semi", "@name": "居住専用準住宅"},
        {"@code": "mixed", "@name": "居住産業併用"},
        {"@code": "info", "@name": "情報通信業用建築物"},
        {"@code": "retail", "@name": "卸売業，小売業用建築物"},
        {"@code": "finance", "@name": "金融業，保険業用建築物"},
        {"@code": "estate", "@name": "不動産業用建築物"},
        {"@code": "food", "@name": "宿泊業，飲食サービス業用建築物"},
        {"@code": "education", "@name": "教育，学習支援業用建築物"},
        {"@code": "medical", "@name": "医療，福祉用建築物"},
    ]},
    {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
    {"@id": "time", "CLASS": [
        {"@code": "2022", "@name": "2022年"},
        {"@code": "2023", "@name": "2023年"},
    ]},
]


class FakeClient:
    def get_meta_info(self, stats_id):
        classes = STRUCTURE_CLASSES if stats_id == STRUCTURE_TABLE else USE_CLASSES
        return {"GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": classes}}}}

    def get_stats_data_all(self, stats_id, params, **kwargs):
        if stats_id == STRUCTURE_TABLE:
            values = [
                {"@item": "count", "@structure": "total", "@area": AREA, "@time": "2022", "$": "50"},
                {"@item": "area", "@structure": "total", "@area": AREA, "@time": "2022", "$": "5000"},
                {"@item": "count", "@structure": "total", "@area": AREA, "@time": "2023", "$": "100"},
                {"@item": "area", "@structure": "total", "@area": AREA, "@time": "2023", "$": "10000"},
                {"@item": "area", "@structure": "wood", "@area": AREA, "@time": "2023", "$": "2000"},
                {"@item": "area", "@structure": "src", "@area": AREA, "@time": "2023", "$": "1000"},
                {"@item": "area", "@structure": "rc", "@area": AREA, "@time": "2023", "$": "4000"},
                {"@item": "area", "@structure": "steel", "@area": AREA, "@time": "2023", "$": "2500"},
            ]
            classes = STRUCTURE_CLASSES
        else:
            values = [
                {"@item": "area", "@use": "total", "@area": AREA, "@time": "2023", "$": "10000"},
                {"@item": "area", "@use": "res", "@area": AREA, "@time": "2023", "$": "5000"},
                {"@item": "area", "@use": "semi", "@area": AREA, "@time": "2023", "$": "500"},
                {"@item": "area", "@use": "mixed", "@area": AREA, "@time": "2023", "$": "1000"},
                {"@item": "area", "@use": "info", "@area": AREA, "@time": "2023", "$": "800"},
                {"@item": "area", "@use": "retail", "@area": AREA, "@time": "2023", "$": "500"},
                {"@item": "area", "@use": "food", "@area": AREA, "@time": "2023", "$": "400"},
                {"@item": "area", "@use": "medical", "@area": AREA, "@time": "2023", "$": "700"},
            ]
            classes = USE_CLASSES
        return {
            "GET_STATS_DATA": {"STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": classes},
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
            }}
        }


def test_building_start_metrics_use_latest_api_year(tmp_path: Path):
    db_path = tmp_path / "starts.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        conn.execute("INSERT INTO population(area_id,year,population) VALUES ('13101',2025,100000)")
        ensure_analysis_schema(conn)
        conn.execute(
            """
            INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,min_sample_size)
            VALUES ('housing2023.total_housing','housing','住宅数','戸','neutral','ward',1)
            """
        )
        upsert_metric(
            conn,
            geo_id="ward:13101",
            metric_key="housing2023.total_housing",
            period="2023",
            value=1000,
            sample_size=1,
            source_id=None,
            metric_version=METRIC_VERSION,
            quality_grade="A",
            source_year="2023",
        )

        count = fetch_building_starts(FakeClient(), conn, [AREA])
        assert count == 15
        metrics = {
            row["metric_key"]: (row["period"], row["value"])
            for row in conn.execute("SELECT metric_key,period,value FROM geo_metrics WHERE metric_key LIKE 'construction.%'")
        }
        assert metrics["construction.building_count"] == ("2023年", 100)
        assert metrics["construction.floor_area"] == ("2023年", 10000)
        assert metrics["construction.floor_area_per_building"][1] == 100
        assert metrics["construction.buildings_per_10k_population"][1] == 10
        assert metrics["construction.floor_area_per_capita"][1] == 0.1
        assert metrics["construction.floor_area_per_100_homes"][1] == 1000
        assert metrics["construction.wood_floor_area_share"][1] == 20
        assert metrics["construction.src_floor_area_share"][1] == 10
        assert metrics["construction.rc_floor_area_share"][1] == 40
        assert metrics["construction.steel_floor_area_share"][1] == 25
        assert metrics["construction.residential_floor_area_share"][1] == 65
        assert metrics["construction.office_floor_area_share"][1] == 8
        assert metrics["construction.wholesale_retail_floor_area_share"][1] == 5
        assert metrics["construction.accommodation_food_floor_area_share"][1] == 4
        assert metrics["construction.medical_welfare_floor_area_share"][1] == 7
