from pathlib import Path

from japan_area_insights.appraisal_analysis import compute_appraisal_metrics, ensure_appraisal_schema, normalize_appraisals
from japan_area_insights.db import connect, initialize


def test_normalize_xct001_and_compute_metrics(tmp_path: Path):
    payload = {
        "data": [
            {
                "標準地番号　市区町村コード　県コード": "13",
                "標準地番号　市区町村コード　市区町村コード": "101",
                "1㎡当たりの価格": "1000000",
                "路線価　相続税路線価": "800000",
                "鑑定評価手法の適用 取引事例比較法比準価格": "1050000",
                "鑑定評価手法の適用 収益還元法 収益価格": "900000",
                "鑑定評価手法の適用 原価法 積算価格": "950000",
                "収益価格算定内訳還元利回り": "3.5",
                "緯度": "35.68",
                "経度": "139.75",
            },
            {
                "標準地番号　市区町村コード　県コード": "13",
                "標準地番号　市区町村コード　市区町村コード": "101",
                "1㎡当たりの価格": "1200000",
                "路線価　相続税路線価": "960000",
                "鑑定評価手法の適用 取引事例比較法比準価格": "1250000",
                "鑑定評価手法の適用 収益還元法 収益価格": "0",
            },
            {
                "標準地番号　市区町村コード　県コード": "13",
                "標準地番号　市区町村コード　市区町村コード": "101",
                "1㎡当たりの価格": "1400000",
                "路線価　相続税路線価": "1120000",
                "鑑定評価手法の適用 取引事例比較法比準価格": "1450000",
                "鑑定評価手法の適用 収益還元法 収益価格": "1100000",
            },
        ]
    }
    rows = normalize_appraisals(payload, year=2025, division="00", allowed_area_ids=["13101"])
    assert len(rows) == 3
    assert rows[0]["area_id"] == "13101"
    assert rows[0]["inheritance_road_value"] == 800000
    assert rows[0]["income_price"] == 900000
    assert '"1㎡当たりの価格"' in rows[0]["raw_json"]

    db_path = tmp_path / "appraisal.db"
    initialize(db_path)
    with connect(db_path) as conn:
        conn.execute("INSERT INTO areas VALUES ('13101','13','13101','東京都','千代田区',NULL,NULL)")
        conn.execute(
            """
            INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
            VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
            """
        )
        ensure_appraisal_schema(conn)
        source_id = conn.execute(
            "INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at) VALUES ('test','XCT001','https://example.test','2026-01-01')"
        ).lastrowid
        conn.executemany(
            """
            INSERT INTO appraisal_records(
                appraisal_id,area_id,year,division,public_price,inheritance_road_value,
                comparison_price,income_price,cost_price,development_price,
                capitalization_rate,latitude,longitude,raw_json,source_id
            ) VALUES (
                :appraisal_id,:area_id,:year,:division,:public_price,:inheritance_road_value,
                :comparison_price,:income_price,:cost_price,:development_price,
                :capitalization_rate,:latitude,:longitude,:raw_json,:source_id
            )
            """,
            [{**row, "source_id": source_id} for row in rows],
        )
        count = compute_appraisal_metrics(conn)
        assert count == 6
        metrics = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics")}
        assert metrics["market.appraisal_count"] == 3
        assert metrics["market.appraisal_public_price_median"] == 1200000
        assert metrics["market.appraisal_income_price_median"] == 1000000
        assert round(metrics["market.appraisal_income_method_share"], 2) == 66.67
        assert metrics["market.inheritance_road_value_ratio"] == 80
