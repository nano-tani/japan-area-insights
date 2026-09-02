from __future__ import annotations

from datetime import date
from pathlib import Path

from .db import connect
from .scoring import ScoreWeights, confidence_grade, score_metric, total_score

SCORE_VERSION = "v0.2"


def _latest_values(conn, sql: str) -> dict[str, float]:
    return {str(row["area_id"]): float(row["value"]) for row in conn.execute(sql) if row["value"] is not None}


def compute_partial_scores(db_path: str | Path, *, calculation_date: str | None = None) -> None:
    calc_date = calculation_date or date.today().isoformat()
    weights = ScoreWeights()
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
            WHERE p.year=(SELECT MAX(x.year) FROM area_prices x WHERE x.area_id=p.area_id)
            """,
        )

        price_scores = score_metric(price_values, weights.price) if price_values else {}
        population_scores = score_metric(population_values, weights.population) if population_values else {}
        future_scores = score_metric(future_values, weights.future_population) if future_values else {}
        transaction_scores = score_metric(transaction_values, weights.transaction) if transaction_values else {}

        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        for area_id in area_ids:
            available = {
                "price": price_scores.get(area_id),
                "population": population_scores.get(area_id),
                "future_population": future_scores.get(area_id),
                "convenience": None,
                "transport": None,
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
                    None,
                    None,
                    available["transaction"],
                    total,
                    confidence_grade(completeness, tx_count),
                    completeness,
                    SCORE_VERSION,
                ),
            )
