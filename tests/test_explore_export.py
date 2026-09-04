import json
from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema, upsert_metric
from japan_area_insights.db import connect, initialize
from japan_area_insights.explore_export import export_explore_data


def test_explore_export_contains_core_detail_and_hazard_metrics(tmp_path: Path):
    db_path = tmp_path / "explore.db"
    out = tmp_path / "webdata"
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
        conn.execute(
            """
            INSERT INTO area_scores(
                area_id,calculation_date,price_score,population_score,future_population_score,
                convenience_score,transport_score,transaction_score,total_score,confidence,
                data_completeness,score_version
            ) VALUES ('13101','2026-09-04',20,17,20,15,12,8,92,'A',1,'v-test')
            """
        )
        conn.execute("INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101','5339460011',2025,100)")
        conn.execute("INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101','5339460011',2045,120)")
        conn.execute(
            """
            INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
            VALUES ('test_market','test','TEST','market','test',NULL,'ward','extended',1,NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
            VALUES ('market.land_price_median','market','公示地価中央値','円/㎡','neutral','ward','test_market',1,'test')
            ON CONFLICT(metric_key) DO NOTHING
            """
        )
        upsert_metric(
            conn,
            geo_id='ward:13101', metric_key='market.land_price_median', period='2026',
            value=500000, sample_size=10, source_id=None, metric_version='detail-v1',
            quality_grade='A', source_year='2026'
        )
        conn.execute(
            """
            INSERT INTO geo_exposures(
                geo_id,layer_key,period,exposed_mesh_count,total_mesh_count,
                exposed_population,total_population,population_share,feature_count,source_id,calculated_at
            ) VALUES ('ward:13101','flood','2025',1,4,20,100,20,1,NULL,'2026-09-04')
            """
        )

    export_explore_data(db_path, out)
    payload = json.loads((out / 'explore' / 'wards.json').read_text(encoding='utf-8'))
    assert payload['peer_group'] == 'tokyo23:ward'
    assert len(payload['themes']) == 8
    ward = payload['wards'][0]
    assert ward['municipality_name'] == '千代田区'
    assert ward['metrics']['core.total_score']['value'] == 92
    assert ward['metrics']['market.land_price_median']['value'] == 500000
    assert ward['metrics']['people.retention_2045']['value'] == 120
    assert ward['metrics']['hazard.flood_population_share']['value'] == 20
