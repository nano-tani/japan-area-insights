from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from .db import connect
from .scoring import ScoreWeights, confidence_grade, percentile_ranks, score_metric, total_score

SCORE_VERSION = "v0.3"
CONVENIENCE_TYPES = ("school", "childcare", "medical", "library", "public_facility")


def _latest_values(conn, sql: str, params: tuple = ()) -> dict[str, float]:
    return {
        str(row["area_id"]): float(row["value"])
        for row in conn.execute(sql, params)
        if row["value"] is not None
    }


def _latest_population(conn) -> dict[str, float]:
    return _latest_values(
        conn,
        """
        SELECT p.area_id, p.population AS value
        FROM population p
        WHERE p.year=(SELECT MAX(x.year) FROM population x WHERE x.area_id=p.area_id)
        """,
    )


def _composite_percentile_index(metric_values: list[dict[str, float]]) -> dict[str, float]:
    if not metric_values:
        return {}
    ranked = [percentile_ranks(values) for values in metric_values if values]
    if not ranked:
        return {}
    common = set(ranked[0])
    for ranks in ranked[1:]:
        common &= set(ranks)
    return {
        area_id: mean(ranks[area_id] for ranks in ranked)
        for area_id in common
    }


def _convenience_index(conn, population: dict[str, float]) -> dict[str, float]:
    if conn.execute("SELECT COUNT(*) FROM facilities").fetchone()[0] == 0:
        return {}

    counts: dict[str, dict[str, int]] = {
        area_id: {facility_type: 0 for facility_type in CONVENIENCE_TYPES}
        for area_id in population
    }
    for row in conn.execute(
        "SELECT area_id, facility_type, COUNT(*) AS count FROM facilities GROUP BY area_id, facility_type"
    ):
        area_id = str(row["area_id"])
        facility_type = str(row["facility_type"])
        if area_id in counts and facility_type in counts[area_id]:
            counts[area_id][facility_type] = int(row["count"])

    rate_metrics: list[dict[str, float]] = []
    for facility_type in CONVENIENCE_TYPES:
        values = {}
        for area_id, pop in population.items():
            if pop > 0 and area_id in counts:
                values[area_id] = counts[area_id][facility_type] / pop * 10_000.0
        if values:
            rate_metrics.append(values)
    return _composite_percentile_index(rate_metrics)


def _transport_index(conn, population: dict[str, float]) -> dict[str, float]:
    rows = conn.execute(
        """
        SELECT area_id, station_id, group_code, line_name, passenger_count
        FROM stations
        """
    ).fetchall()
    if not rows:
        return {}

    groups: dict[str, set[str]] = defaultdict(set)
    lines: dict[str, set[str]] = defaultdict(set)
    passengers: dict[str, dict[str, int]] = defaultdict(dict)

    for row in rows:
        area_id = str(row["area_id"])
        group = str(row["group_code"] or row["station_id"])
        groups[area_id].add(group)
        if row["line_name"]:
            lines[area_id].add(str(row["line_name"]))
        if row["passenger_count"] is not None:
            count = int(row["passenger_count"])
            passengers[area_id][group] = max(passengers[area_id].get(group, 0), count)

    station_rates: dict[str, float] = {}
    line_counts: dict[str, float] = {}
    passenger_rates: dict[str, float] = {}
    for area_id, pop in population.items():
        if pop <= 0:
            continue
        station_rates[area_id] = len(groups.get(area_id, set())) / pop * 100_000.0
        line_counts[area_id] = float(len(lines.get(area_id, set())))
        passenger_rates[area_id] = sum(passengers.get(area_id, {}).values()) / pop

    return _composite_percentile_index([station_rates, line_counts, passenger_rates])


def compute_partial_scores(db_path: str | Path, *, calculation_date: str | None = None) -> None:
    calc_date = calculation_date or date.today().isoformat()
    weights = ScoreWeights()
    completed_transaction_year = int(calc_date[:4]) - 1

    with connect(db_path) as conn:
        price_values = _latest_values(
            conn,
            """
            SELECT p.area_id, p.change_5y AS value
            FROM area_prices p
            WHERE p.year=(SELECT MAX(x.year) FROM area_prices x WHERE x.area_id=p.area_id)
            """,
        )
        if not price_values:
            price_values = _latest_values(
                conn,
                """
                SELECT p.area_id, p.yoy_change AS value
                FROM area_prices p
                WHERE p.year=(SELECT MAX(x.year) FROM area_prices x WHERE x.area_id=p.area_id)
                """,
            )

        population_values = _latest_values(
            conn,
            """
            SELECT p.area_id, p.population_change_rate AS value
            FROM population p
            WHERE p.year=(SELECT MAX(x.year) FROM population x WHERE x.area_id=p.area_id)
            """,
        )
        population = _latest_population(conn)

        future_values = _latest_values(
            conn,
            """
            SELECT fp.area_id,
                   100.0 * SUM(CASE WHEN fp.year=2045 THEN fp.projected_population ELSE 0 END)
                   / NULLIF(SUM(CASE WHEN fp.year=2025 THEN fp.projected_population ELSE 0 END), 0) AS value
            FROM future_population fp
            WHERE fp.year IN (2025, 2045)
            GROUP BY fp.area_id
            """,
        )

        transaction_values = _latest_values(
            conn,
            """
            SELECT p.area_id, p.transaction_count AS value
            FROM area_prices p
            WHERE p.year=(
                SELECT MAX(x.year) FROM area_prices x
                WHERE x.area_id=p.area_id AND x.year<=?
            )
            """,
            (completed_transaction_year,),
        )

        convenience_index = _convenience_index(conn, population)
        transport_index = _transport_index(conn, population)

        price_scores = score_metric(price_values, weights.price) if price_values else {}
        population_scores = score_metric(population_values, weights.population) if population_values else {}
        future_scores = score_metric(future_values, weights.future_population) if future_values else {}
        convenience_scores = score_metric(convenience_index, weights.convenience) if convenience_index else {}
        transport_scores = score_metric(transport_index, weights.transport) if transport_index else {}
        transaction_scores = score_metric(transaction_values, weights.transaction) if transaction_values else {}

        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        for area_id in area_ids:
            available = {
                "price": price_scores.get(area_id),
                "population": population_scores.get(area_id),
                "future_population": future_scores.get(area_id),
                "convenience": convenience_scores.get(area_id),
                "transport": transport_scores.get(area_id),
                "transaction": transaction_scores.get(area_id),
            }
            completeness = sum(value is not None for value in available.values()) / len(available)
            tx_count = int(transaction_values.get(area_id, 0))
            total = total_score(available)
            conn.execute(
                """
                INSERT INTO area_scores (
                    area_id, calculation_date, price_score, population_score,
                    future_population_score, convenience_score, transport_score,
                    transaction_score, total_score, confidence, data_completeness,
                    score_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(area_id, calculation_date, score_version) DO UPDATE SET
                    price_score=excluded.price_score,
                    population_score=excluded.population_score,
                    future_population_score=excluded.future_population_score,
                    convenience_score=excluded.convenience_score,
                    transport_score=excluded.transport_score,
                    transaction_score=excluded.transaction_score,
                    total_score=excluded.total_score,
                    confidence=excluded.confidence,
                    data_completeness=excluded.data_completeness
                """,
                (
                    area_id,
                    calc_date,
                    available["price"],
                    available["population"],
                    available["future_population"],
                    available["convenience"],
                    available["transport"],
                    available["transaction"],
                    total,
                    confidence_grade(completeness, tx_count),
                    completeness,
                    SCORE_VERSION,
                ),
            )
