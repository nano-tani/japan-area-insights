from japan_area_insights.transactions import aggregate_transactions, normalize_xit001


def test_normalize_official_xit001_shape():
    payload = {
        "status": "OK",
        "data": [
            {
                "PriceCategory": "不動産取引価格情報",
                "Type": "宅地(土地と建物)",
                "MunicipalityCode": "13102",
                "DistrictName": "日本橋小網町",
                "TradePrice": "85000000",
                "Area": "80",
                "UnitPrice": "",
                "Period": "2015年第2四半期",
            }
        ],
    }
    rows = normalize_xit001(payload, area_id="13102", year=2015)
    assert len(rows) == 1
    assert rows[0]["quarter"] == 2
    assert rows[0]["unit_price"] == 1_062_500
    assert rows[0]["district_name"] == "日本橋小網町"


def test_identical_records_are_not_collapsed():
    record = {
        "PriceCategory": "不動産取引価格情報",
        "MunicipalityCode": "13101",
        "TradePrice": "10000000",
        "Area": "10",
        "Period": "2025年第1四半期",
    }
    rows = normalize_xit001({"data": [record, record]}, area_id="13101", year=2025)
    assert len(rows) == 2
    assert rows[0]["transaction_id"] != rows[1]["transaction_id"]


def test_aggregate_uses_numeric_unit_prices_only():
    rows = [
        {"unit_price": 100.0},
        {"unit_price": 300.0},
        {"unit_price": None},
    ]
    result = aggregate_transactions(rows)
    assert result["transaction_count"] == 3
    assert result["avg_transaction_unit_price"] == 200.0
    assert result["median_transaction_unit_price"] == 200.0
