from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_census_demographics_2020 import (
    FOREIGN_NATIONALITY_ID,
    HOUSEHOLD_SIZE_ID,
    fetch_census_demographics_2020,
)

AREA = "13101"

NATIONALITIES = [
    {"@code": "all", "@name": "総数"},
    {"@code": "foreign", "@name": "外国人"},
    {"@code": "korea", "@name": "韓国，朝鮮"},
    {"@code": "china", "@name": "中国"},
    {"@code": "ph", "@name": "フィリピン"},
    {"@code": "vn", "@name": "ベトナム"},
    {"@code": "np", "@name": "ネパール"},
]

SIZES = [
    {"@code": "all", "@name": "総数"},
    *[{"@code": str(i), "@name": f"世帯人員が{i}人"} for i in range(1, 10)],
    {"@code": "10p", "@name": "世帯人員が10人以上"},
]


def classes(stats_id):
    common = [
        {"@id": "area", "CLASS": [{"@code": AREA, "@name": "千代田区"}]},
        {"@id": "time", "CLASS": [{"@code": "2020", "@name": "2020年"}]},
    ]
    if stats_id == FOREIGN_NATIONALITY_ID:
        return [
            {"@id": "item", "CLASS": [
                {"@code": "pop", "@name": "人口"},
                {"@code": "male", "@name": "男"},
                {"@code": "female", "@name": "女"},
            ]},
            {"@id": "nationality", "CLASS": NATIONALITIES},
            *common,
        ]
    return [
        {"@id": "item", "CLASS": [{"@code": "hh", "@name": "一般世帯数"}]},
        {"@id": "size", "CLASS": SIZES},
        *common,
    ]


class FakeClient:
    def get_meta_info(self, stats_id):
        return {"GET_META_INFO": {"METADATA_INF": {"CLASS_INF": {"CLASS_OBJ": classes(stats_id)}}}}

    def get_stats_data_all(self, stats_id, params, **kwargs):
        if stats_id == FOREIGN_NATIONALITY_ID:
            data = {
                "all": 10000,
                "foreign": 1000,
                "korea": 200,
                "china": 300,
                "ph": 100,
                "vn": 250,
                "np": 50,
            }
            values = [
                {"@item": "pop", "@nationality": code, "@area": AREA, "@time": "2020", "$": str(value)}
                for code, value in data.items()
            ]
        else:
            data = {
                "all": 5000,
                "1": 2500,
                "2": 1200,
                "3": 600,
                "4": 400,
                "5": 180,
                "6": 70,
                "7": 30,
                "8": 12,
                "9": 5,
                "10p": 3,
            }
            values = [
                {"@item": "hh", "@size": code, "@area": AREA, "@time": "2020", "$": str(value)}
                for code, value in data.items()
            ]
        return {
            "GET_STATS_DATA": {"STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": classes(stats_id)},
                "DATA_INF": {"VALUE": values},
                "RESULT_INF": {"TOTAL_NUMBER": len(values), "FROM_NUMBER": 1, "TO_NUMBER": len(values)},
            }}
        }


def test_census_demographic_composition(tmp_path: Path):
    db_path = tmp_path / "census.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        count = fetch_census_demographics_2020(FakeClient(), conn, [AREA])
        assert count == 11
        metrics = {
            row["metric_key"]: row["value"]
            for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE metric_key LIKE 'demographics2020.%'")
        }
        assert metrics["demographics2020.foreign_population"] == 1000
        assert metrics["demographics2020.foreign_share"] == 10
        assert metrics["demographics2020.china_share_of_foreign"] == 30
        assert metrics["demographics2020.korea_share_of_foreign"] == 20
        assert metrics["demographics2020.vietnam_share_of_foreign"] == 25
        assert metrics["demographics2020.philippines_share_of_foreign"] == 10
        assert metrics["demographics2020.nepal_share_of_foreign"] == 5
        assert metrics["demographics2020.general_households"] == 5000
        assert metrics["demographics2020.single_household_share"] == 50
        assert metrics["demographics2020.two_person_household_share"] == 24
        assert metrics["demographics2020.four_plus_household_share"] == 14
