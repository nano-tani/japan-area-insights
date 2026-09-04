from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema, upsert_metric
from japan_area_insights.db import connect, initialize
from japan_area_insights.population_profile import derive_population_profile


def _put(conn, source_id, key, label, value):
    conn.execute(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?, 'population_detail', ?, '人', 'neutral', 'ward', 'estat_ssds_full_a', 1, '')
        """,
        (key, label),
    )
    upsert_metric(
        conn,
        geo_id='ward:13101',metric_key=key,period='2025年度',value=value,
        sample_size=1,source_id=source_id,metric_version='detail-v1',
        quality_grade='A',source_year='2025年度',
    )


def test_population_profile_uses_same_period_ssds_a_values(tmp_path: Path):
    db_path = tmp_path / 'people.db'
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute("INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active) VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)")
        ensure_analysis_schema(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO dataset_catalog(
                dataset_key,provider,api_id,category,title,source_vintage,
                granularity,refresh_mode,enabled,notes
            ) VALUES ('estat_ssds_full_a','政府統計の総合窓口 e-Stat','0000020101','population','社会・人口統計体系 A','2025年度','municipality','extended',1,'test fixture')
            """
        )
        source_id = conn.execute("INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at) VALUES ('e-Stat','A','https://example.test','2026-09-01')").lastrowid
        for key, label, value in (
            ('ssds.a.a1','総人口',1000),
            ('ssds.a.a2','15歳未満人口',120),
            ('ssds.a.a3','15～64歳人口',650),
            ('ssds.a.a4','65歳以上人口',230),
            ('ssds.a.a5','75歳以上人口',100),
            ('ssds.a.a6','外国人人口',80),
            ('ssds.a.a7','一般世帯数',600),
            ('ssds.a.a8','単独世帯数',300),
        ):
            _put(conn, source_id, key, label, value)
        count = derive_population_profile(conn, ['13101'])
        assert count == 14
        metrics = {row['metric_key']: row['value'] for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE metric_key LIKE 'people.%' OR metric_key LIKE 'household.%'")}
        assert metrics['people.population_total'] == 1000
        assert metrics['people.child_share'] == 12
        assert metrics['people.working_age_share'] == 65
        assert metrics['people.elderly_share'] == 23
        assert metrics['people.age75plus_share'] == 10
        assert metrics['people.foreign_share'] == 8
        assert metrics['household.general_households'] == 600
        assert metrics['household.single_household_share'] == 50
