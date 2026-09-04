import json
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_census_mobility import CENSUS_COMMUTING_ID, fetch_census_commuting_flows
from japan_area_insights.mobility_export import export_commuting_flows

AREA = '13101'


class FakeClient:
    def get_meta_info(self, stats_id):
        assert stats_id == CENSUS_COMMUTING_ID
        return {
            'GET_META_INFO': {'METADATA_INF': {'CLASS_INF': {'CLASS_OBJ': [
                {'@id':'cat01','@name':'常住地による市区町村','CLASS':[
                    {'@code':'13101','@name':'千代田区'},
                    {'@code':'13102','@name':'中央区'},
                    {'@code':'14100','@name':'横浜市'},
                ]},
                {'@id':'cat02','@name':'従業地・通学地による市区町村','CLASS':[
                    {'@code':'13101','@name':'千代田区'},
                    {'@code':'13102','@name':'中央区'},
                    {'@code':'13103','@name':'港区'},
                    {'@code':'14100','@name':'横浜市'},
                ]},
                {'@id':'cat03','@name':'人口区分','CLASS':[{'@code':'0','@name':'総数'}]},
                {'@id':'time','@name':'時間軸','CLASS':[{'@code':'2020','@name':'2020年'}]},
            ]}}}
        }

    def get_stats_data_all(self, stats_id, params, **kwargs):
        outbound = 'cdCat01' in params and params.get('cdCat01') == AREA
        if outbound:
            values = [
                {'@cat01':AREA,'@cat02':'13101','@cat03':'0','@time':'2020','$':'100'},
                {'@cat01':AREA,'@cat02':'13102','@cat03':'0','@time':'2020','$':'300'},
                {'@cat01':AREA,'@cat02':'13103','@cat03':'0','@time':'2020','$':'200'},
                {'@cat01':AREA,'@cat02':'14100','@cat03':'0','@time':'2020','$':'500'},
            ]
        else:
            values = [
                {'@cat01':'13101','@cat02':AREA,'@cat03':'0','@time':'2020','$':'100'},
                {'@cat01':'13102','@cat02':AREA,'@cat03':'0','@time':'2020','$':'400'},
                {'@cat01':'14100','@cat02':AREA,'@cat03':'0','@time':'2020','$':'600'},
            ]
        classes = self.get_meta_info(stats_id)['GET_META_INFO']['METADATA_INF']['CLASS_INF']
        return {
            'GET_STATS_DATA': {'STATISTICAL_DATA': {
                'CLASS_INF': classes,
                'DATA_INF': {'VALUE': values},
                'RESULT_INF': {'TOTAL_NUMBER':len(values),'FROM_NUMBER':1,'TO_NUMBER':len(values)},
            }}
        }


def test_census_commuting_flows_and_export(tmp_path: Path):
    db_path = tmp_path / 'mobility.db'
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute("INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active) VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)")
        count = fetch_census_commuting_flows(FakeClient(), conn, [AREA])
        assert count == 7
        flows = conn.execute("SELECT direction,counterpart_code,count FROM commuting_flows ORDER BY direction,counterpart_code").fetchall()
        assert len(flows) == 5
        metrics = {row['metric_key']: row['value'] for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE metric_key LIKE 'mobility.%'")}
        assert metrics['mobility.outbound_count'] == 1000
        assert metrics['mobility.inbound_count'] == 1000
        assert metrics['mobility.net_inflow'] == 0
        assert metrics['mobility.top_outbound_destination_share'] == 50
        assert metrics['mobility.top_inbound_origin_share'] == 60
        # For this test, only 13102 is another target Tokyo-23 code because area_ids contains one target ward.
        assert metrics['mobility.tokyo23_outbound_share'] == 0

    output = tmp_path / 'webdata'
    export_commuting_flows(db_path, output, top_n=2)
    payload = json.loads((output/'analysis'/'mobility'/'13101.json').read_text(encoding='utf-8'))
    assert payload['outbound'][0]['counterpart_code'] == '14100'
    assert payload['outbound'][0]['count'] == 500
    assert payload['inbound'][0]['counterpart_code'] == '14100'
    assert len(payload['outbound']) == 2
