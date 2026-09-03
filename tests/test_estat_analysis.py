from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_analysis import fetch_migration_metrics, fetch_ssds_metrics


AREA = "13101"


def meta(classes):
    return {
        "GET_META_INFO": {
            "METADATA_INF": {
                "CLASS_INF": {
                    "CLASS_OBJ": [
                        {"@id": dim, "@name": dim, "CLASS": [{"@code": code, "@name": label} for code, label in values]}
                        for dim, values in classes.items()
                    ]
                }
            }
        }
    }


def data(classes, values):
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "CLASS_INF": {
                    "CLASS_OBJ": [
                        {"@id": dim, "@name": dim, "CLASS": [{"@code": code, "@name": label} for code, label in items]}
                        for dim, items in classes.items()
                    ]
                },
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
            }
        }
    }


class FakeSSDSClient:
    def get_meta_info(self, stats_id):
        indicators = {
            "0000020103": [("C120110", "課税対象所得"), ("C120120", "所得割納税義務者数")],
            "0000020104": [("D2201", "財政力指数"), ("D2211", "実質公債費比率"), ("D2212", "将来負担比率")],
        }[stats_id]
        return meta({"cat01": indicators, "area": [(AREA, "千代田区")], "time": [("2024", "2024年度"), ("2025", "2025年度")]})

    def get_stats_data_all(self, stats_id, params, **kwargs):
        classes = {
            "cat01": {
                "0000020103": [("C120110", "課税対象所得"), ("C120120", "所得割納税義務者数")],
                "0000020104": [("D2201", "財政力指数"), ("D2211", "実質公債費比率"), ("D2212", "将来負担比率")],
            }[stats_id],
            "area": [(AREA, "千代田区")],
            "time": [("2024", "2024年度"), ("2025", "2025年度")],
        }
        if stats_id == "0000020103":
            values = [
                {"@cat01": "C120110", "@area": AREA, "@time": "2025", "$": "5000000"},
                {"@cat01": "C120120", "@area": AREA, "@time": "2025", "$": "1000"},
            ]
        else:
            values = [
                {"@cat01": "D2201", "@area": AREA, "@time": "2025", "$": "0.95"},
                {"@cat01": "D2211", "@area": AREA, "@time": "2025", "$": "4.2"},
                {"@cat01": "D2212", "@area": AREA, "@time": "2025", "$": "8.5"},
            ]
        return data(classes, values)


class FakeMigrationClient:
    def get_meta_info(self, stats_id):
        classes = {
            "cat01": [("001", "移動者")],
            "cat02": [("000", "総数"), ("010", "0～9歳"), ("030", "20～29歳"), ("040", "30～39歳")],
            "cat03": [("000", "総数"), ("001", "男"), ("002", "女")],
            "area": [(AREA, "千代田区")],
            "time": [("2025", "2025年")],
        }
        return meta(classes)

    def get_stats_data_all(self, stats_id, params, **kwargs):
        classes = {
            "cat01": [("001", "移動者")],
            "cat02": [("000", "総数"), ("010", "0～9歳"), ("030", "20～29歳"), ("040", "30～39歳")],
            "cat03": [("000", "総数")],
            "area": [(AREA, "千代田区")],
            "time": [("2025", "2025年")],
        }
        inbound = stats_id == "0004044293"
        numbers = {"000": 5000 if inbound else 4200, "010": 500 if inbound else 400, "030": 1300 if inbound else 900, "040": 1100 if inbound else 1000}
        values = [
            {"@cat01": "001", "@cat02": age, "@cat03": "000", "@area": AREA, "@time": "2025", "$": str(value)}
            for age, value in numbers.items()
        ]
        return data(classes, values)


def seed(db_path: Path):
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


def test_ssds_metrics_and_derived_income(tmp_path):
    db_path = tmp_path / "analysis.db"
    seed(db_path)
    with connect(db_path) as conn:
        count = fetch_ssds_metrics(FakeSSDSClient(), conn, [AREA])
        assert count == 6
        rows = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics")}
        assert rows["economy.taxable_income"] == 5_000_000
        assert rows["economy.taxable_income_per_taxpayer"] == 5000
        assert rows["economy.fiscal_strength_index"] == 0.95
        assert rows["economy.real_debt_service_ratio"] == 4.2


def test_migration_metrics(tmp_path):
    db_path = tmp_path / "migration.db"
    seed(db_path)
    with connect(db_path) as conn:
        count = fetch_migration_metrics(FakeMigrationClient(), conn, [AREA])
        assert count == 5
        rows = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics")}
        assert rows["migration.in_total"] == 5000
        assert rows["migration.out_total"] == 4200
        assert rows["migration.net_total"] == 800
        assert rows["migration.net_20_39"] == 500
        assert rows["migration.net_0_9"] == 100
