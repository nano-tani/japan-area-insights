from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ScoreWeights:
    price: float = 20.0
    population: float = 20.0
    future_population: float = 20.0
    convenience: float = 15.0
    transport: float = 15.0
    transaction: float = 10.0

    @property
    def total(self) -> float:
        return sum((self.price, self.population, self.future_population, self.convenience, self.transport, self.transaction))


def percentile_ranks(values: Mapping[str, float], *, higher_is_better: bool = True) -> dict[str, float]:
    """Return deterministic percentile ranks in [0, 1] using average rank for ties."""
    if not values:
        return {}

    items = list(values.items())
    numeric = [float(v) for _, v in items]
    n = len(numeric)
    result: dict[str, float] = {}

    for key, raw in items:
        value = float(raw)
        lower = sum(1 for x in numeric if x < value)
        equal = sum(1 for x in numeric if x == value)
        percentile = (lower + equal / 2.0) / n
        if not higher_is_better:
            percentile = 1.0 - percentile
        result[key] = percentile

    return result


def band_score(percentile: float, max_points: float) -> float:
    """Convert percentile to the v0.1 relative-score band."""
    p = max(0.0, min(1.0, float(percentile)))
    if p >= 0.90:
        ratio = 1.00
    elif p >= 0.75:
        ratio = 0.85
    elif p >= 0.50:
        ratio = 0.65
    elif p >= 0.25:
        ratio = 0.40
    else:
        ratio = 0.15
    return round(max_points * ratio, 2)


def score_metric(values: Mapping[str, float], max_points: float, *, higher_is_better: bool = True) -> dict[str, float]:
    ranks = percentile_ranks(values, higher_is_better=higher_is_better)
    return {area_id: band_score(rank, max_points) for area_id, rank in ranks.items()}


def total_score(components: Mapping[str, float | None], weights: ScoreWeights = ScoreWeights()) -> float | None:
    """Return total only when all six component scores are present."""
    required = ("price", "population", "future_population", "convenience", "transport", "transaction")
    if any(components.get(name) is None for name in required):
        return None
    total = sum(float(components[name]) for name in required)
    return round(min(total, weights.total), 2)


def confidence_grade(data_completeness: float, transaction_count: int) -> str:
    completeness = max(0.0, min(1.0, float(data_completeness)))
    count = max(0, int(transaction_count))
    if completeness >= 0.95 and count >= 100:
        return "A"
    if completeness >= 0.80 and count >= 30:
        return "B"
    if completeness >= 0.60 and count >= 5:
        return "C"
    return "D"
