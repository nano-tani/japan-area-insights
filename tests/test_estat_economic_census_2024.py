from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_economic_census_2024 import (
    TABLE_INDUSTRY,
    TABLE_SALES,
    TABLE_SIZE,
    fetch_economic_census_2024,
)

AREA = "13101"


class FakeClient:
    def get_meta_info(self, stats_id):
        if stats_id == TABLE_INDUSTRY:
            classes = [
                {"@id":"item","CLASS":[{"@code":"e","@name":"事業所数"},{"@code":"p","@name":"従業者数"},{"@code":"r","@name":"従業者数_うち常用雇用者"}]},
                {"@id":"industry","CLASS":[
                    {"@code":"all","@name":"全産業（S_公務を除く）"},
                    {"@code":"mfg","@name":"製造業"},{"@code":"info","@name":"情報通信業"},
                    {"@code":"med","@name":"医療，福祉"},{"@code":"food","@name":"宿泊業，飲食サービス業"},
                ]},
                {"@id":"org","CLASS":[{"@code":"0","@name":"総数"}]},
                {"@id":"area","CLASS":[{"@code":AREA,"@name":"千代田区"}]},
                {"@id":"time","CLASS":[{"@code":"2024","@name":"2024年"}]},
            ]
        elif stats_id == TABLE_SIZE:
            classes = [
                {"@id":"item","CLASS":[{"@code":"e","@name":"事業所数"},{"@code":"p","@name":"従業者数"}]},
                {"@id":"industry","CLASS":[{"@code":"all","@name":"全産業（S_公務を除く）"},{"@code":"mfg","@name":"製造業"}]},
                {"@id":"org","CLASS":[{"@code":"0","@name":"総数"}]},
                {"@id":"size","CLASS":[
                    {"@code":"total","@name":"総数"},{"@code":"1","@name":"1～4人"},{"@code":"50","@name":"50～99人"},{"@code":"100","@name":"100～299人"},{"@code":"300","@name":"300人以上"},
                ]},
                {"@id":"area","CLASS":[{"@code":AREA,"@name":"千代田区"}]},
                {"@id":"time","CLASS":[{"@code":"2024","@name":"2024年"}]},
            ]
        else:
            classes = [
                {"@id":"item","CLASS":[{"@code":"p","@name":"従業者数"},{"@code":"s","@name":"売上（収入）金額"},{"@code":"e","@name":"事業所数"}]},
                {"@id":"industry","CLASS":[{"@code":"all","@name":"全産業（S_公務を除く）"},{"@code":"mfg","@name":"製造業"}]},
                {"@id":"hq","CLASS":[{"@code":"0","@name":"総数"}]},
                {"@id":"area","CLASS":[{"@code":AREA,"@name":"千代田区"}]},
                {"@id":"time","CLASS":[{"@code":"2024","@name":"2024年"}]},
            ]
        return {"GET_META_INFO":{"METADATA_INF":{"CLASS_INF":{"CLASS_OBJ":classes}}}}

    def get_stats_data_all(self, stats_id, params, **kwargs):
        if stats_id == TABLE_INDUSTRY:
            values = [
                {"@item":"e","@industry":"all","@org":"0","@area":AREA,"@time":"2024","$":"1000"},
                {"@item":"p","@industry":"all","@org":"0","@area":AREA,"@time":"2024","$":"12000"},
                {"@item":"r","@industry":"all","@org":"0","@area":AREA,"@time":"2024","$":"9000"},
                {"@item":"e","@industry":"mfg","@org":"0","@area":AREA,"@time":"2024","$":"100"},
                {"@item":"p","@industry":"mfg","@org":"0","@area":AREA,"@time":"2024","$":"2400"},
                {"@item":"e","@industry":"info","@org":"0","@area":AREA,"@time":"2024","$":"200"},
                {"@item":"p","@industry":"info","@org":"0","@area":AREA,"@time":"2024","$":"3600"},
                {"@item":"e","@industry":"med","@org":"0","@area":AREA,"@time":"2024","$":"150"},
                {"@item":"p","@industry":"med","@org":"0","@area":AREA,"@time":"2024","$":"1800"},
                {"@item":"e","@industry":"food","@org":"0","@area":AREA,"@time":"2024","$":"120"},
                {"@item":"p","@industry":"food","@org":"0","@area":AREA,"@time":"2024","$":"600"},
            ]
            classes = self.get_meta_info(stats_id)["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]
        elif stats_id == TABLE_SIZE:
            values = [
                {"@item":"e","@industry":"all","@org":"0","@size":"total","@area":AREA,"@time":"2024","$":"1000"},
                {"@item":"e","@industry":"all","@org":"0","@size":"1","@area":AREA,"@time":"2024","$":"700"},
                {"@item":"e","@industry":"all","@org":"0","@size":"50","@area":AREA,"@time":"2024","$":"100"},
                {"@item":"e","@industry":"all","@org":"0","@size":"100","@area":AREA,"@time":"2024","$":"60"},
                {"@item":"e","@industry":"all","@org":"0","@size":"300","@area":AREA,"@time":"2024","$":"40"},
            ]
            classes = self.get_meta_info(stats_id)["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]
        else:
            values = [
                {"@item":"p","@industry":"all","@hq":"0","@area":AREA,"@time":"2024","$":"12000"},
                {"@item":"s","@industry":"all","@hq":"0","@area":AREA,"@time":"2024","$":"240000"},
            ]
            classes = self.get_meta_info(stats_id)["GET_META_INFO"]["METADATA_INF"]["CLASS_INF"]
        return {"GET_STATS_DATA":{"STATISTICAL_DATA":{"CLASS_INF":classes,"DATA_INF":{"VALUE":values},"RESULT_INF":{"TOTAL_NUMBER":len(values),"FROM_NUMBER":1,"TO_NUMBER":len(values)}}}}


def test_economic_census_2024_metrics(tmp_path: Path):
    db_path=tmp_path/"econ.db"; initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute("INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active) VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)")
        count=fetch_economic_census_2024(FakeClient(),conn,[AREA])
        assert count == 26
        metrics={row["metric_key"]:row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE metric_key LIKE 'economy2024.%'")}
        assert metrics["economy2024.establishments"]==1000
        assert metrics["economy2024.employees"]==12000
        assert metrics["economy2024.regular_employee_share"]==75
        assert metrics["economy2024.employees_per_establishment"]==12
        assert metrics["economy2024.manufacturing_establishment_share"]==10
        assert metrics["economy2024.information_employee_share"]==30
        assert metrics["economy2024.medical_welfare_employee_share"]==15
        assert metrics["economy2024.establishments_50plus_share"]==20
        assert metrics["economy2024.sales"]==240000
        assert metrics["economy2024.sales_per_employee"]==20
