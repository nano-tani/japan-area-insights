from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_housing_2023 import (
    TABLE_STRUCTURE_AGE,
    TABLE_TENURE_AGE,
    fetch_housing_survey_2023,
)

AREA = "13101"


AGE_CLASSES = [
    {"@code": "all", "@name": "総数"},
    {"@code": "a0", "@name": "1970年以前"},
    {"@code": "a1", "@name": "1971～1980年"},
    {"@code": "a2", "@name": "1981～1990年"},
    {"@code": "a3", "@name": "1991～2000年"},
    {"@code": "a4", "@name": "2001～2010年"},
    {"@code": "a5", "@name": "2011～2020年"},
    {"@code": "a6", "@name": "2021～2023年9月"},
]

TENURE_CLASSES = [
    {"@code": "all", "@name": "総数"},
    {"@code": "owner", "@name": "持ち家"},
    {"@code": "rental", "@name": "借家"},
    {"@code": "public", "@name": "公営の借家"},
    {"@code": "ur", "@name": "都市再生機構・公社の借家"},
    {"@code": "private", "@name": "民営借家"},
    {"@code": "salary", "@name": "給与住宅"},
]

STRUCTURE_CLASSES = [
    {"@code": "wood", "@name": "木造"},
    {"@code": "nonwood", "@name": "非木造"},
    {"@code": "rc", "@name": "鉄筋・鉄骨コンクリート造"},
    {"@code": "steel", "@name": "鉄骨造"},
]


def _classes(stats_id):
    common = [
        {"@id": "item", "CLASS": [{"@code": "housing", "@name": "住宅数"}]},
        {"@id": "age", "CLASS": AGE_CLASSES},
    ]
    if stats_id == TABLE_TENURE_AGE:
        common.append({"@id": "tenure", "CLASS": TENURE_CLASSES})
    else:
        common.append({"@id": "structure", "CLASS": STRUCTURE_CLASSES})
    common.extend([
        {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
        {"@id": "time", "CLASS": [{"@code": "2023", "@name": "2023年10月"}]},
    ])
    return common


class FakeClient:
    def get_meta_info(self, stats_id):
        return {"GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": _classes(stats_id)}}}}

    def get_stats_data_all(self, stats_id, params, **kwargs):
        if stats_id == TABLE_TENURE_AGE:
            values = [
                {"@item": "housing", "@age": "all", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "1000"},
                {"@item": "housing", "@age": "all", "@tenure": "owner", "@area": AREA, "@time": "2023", "$": "400"},
                {"@item": "housing", "@age": "all", "@tenure": "rental", "@area": AREA, "@time": "2023", "$": "600"},
                {"@item": "housing", "@age": "all", "@tenure": "public", "@area": AREA, "@time": "2023", "$": "80"},
                {"@item": "housing", "@age": "all", "@tenure": "ur", "@area": AREA, "@time": "2023", "$": "100"},
                {"@item": "housing", "@age": "all", "@tenure": "private", "@area": AREA, "@time": "2023", "$": "390"},
                {"@item": "housing", "@age": "a0", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "50"},
                {"@item": "housing", "@age": "a1", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "100"},
                {"@item": "housing", "@age": "a2", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "150"},
                {"@item": "housing", "@age": "a3", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "150"},
                {"@item": "housing", "@age": "a4", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "200"},
                {"@item": "housing", "@age": "a5", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "250"},
                {"@item": "housing", "@age": "a6", "@tenure": "all", "@area": AREA, "@time": "2023", "$": "100"},
            ]
        else:
            values = [
                {"@item": "housing", "@age": "all", "@structure": "wood", "@area": AREA, "@time": "2023", "$": "300"},
                {"@item": "housing", "@age": "all", "@structure": "nonwood", "@area": AREA, "@time": "2023", "$": "700"},
                {"@item": "housing", "@age": "all", "@structure": "rc", "@area": AREA, "@time": "2023", "$": "500"},
                {"@item": "housing", "@age": "all", "@structure": "steel", "@area": AREA, "@time": "2023", "$": "180"},
            ]
        return {
            "GET_STATS_DATA": {"STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": _classes(stats_id)},
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
            }}
        }


def test_housing_survey_2023_metrics(tmp_path: Path):
    db_path = tmp_path / "housing.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        count = fetch_housing_survey_2023(FakeClient(), conn, [AREA])
        assert count == 14
        metrics = {
            row["metric_key"]: row["value"]
            for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE metric_key LIKE 'housing2023.%'")
        }
        assert metrics["housing2023.total_housing"] == 1000
        assert metrics["housing2023.owner_occupied_share"] == 40
        assert metrics["housing2023.rental_share"] == 60
        assert metrics["housing2023.private_rental_share"] == 39
        assert metrics["housing2023.public_rental_share"] == 8
        assert metrics["housing2023.ur_public_corp_rental_share"] == 10
        assert metrics["housing2023.pre1980_share"] == 15
        assert metrics["housing2023.pre2000_share"] == 45
        assert metrics["housing2023.post2011_share"] == 35
        assert metrics["housing2023.2021_2023_share"] == 10
        assert metrics["housing2023.wooden_share"] == 30
        assert metrics["housing2023.nonwooden_share"] == 70
        assert metrics["housing2023.rc_share"] == 50
        assert metrics["housing2023.steel_share"] == 18
