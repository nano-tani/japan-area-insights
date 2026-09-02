from japan_area_insights.scoring import band_score, confidence_grade, percentile_ranks, score_metric, total_score


def test_spec_example_bands_for_20_points():
    assert band_score(0.95, 20) == 20
    assert band_score(0.80, 20) == 17
    assert band_score(0.60, 20) == 13
    assert band_score(0.30, 20) == 8
    assert band_score(0.10, 20) == 3


def test_23_area_relative_scoring_is_deterministic():
    values = {f"area-{i:02d}": float(i) for i in range(1, 24)}
    first = score_metric(values, 20)
    second = score_metric(values, 20)
    assert first == second
    assert first["area-23"] == 20
    assert first["area-12"] == 13
    assert first["area-01"] == 3


def test_ties_receive_same_percentile():
    ranks = percentile_ranks({"a": 1, "b": 2, "c": 2, "d": 3})
    assert ranks["b"] == ranks["c"]


def test_lower_is_better_can_be_reversed():
    ranks = percentile_ranks({"a": 1, "b": 10}, higher_is_better=False)
    assert ranks["a"] > ranks["b"]


def test_total_score_requires_all_components():
    complete = {
        "price": 20,
        "population": 20,
        "future_population": 20,
        "convenience": 15,
        "transport": 15,
        "transaction": 10,
    }
    assert total_score(complete) == 100
    complete["transaction"] = None
    assert total_score(complete) is None


def test_confidence_grade_thresholds():
    assert confidence_grade(0.95, 100) == "A"
    assert confidence_grade(0.80, 30) == "B"
    assert confidence_grade(0.60, 5) == "C"
    assert confidence_grade(0.59, 500) == "D"
