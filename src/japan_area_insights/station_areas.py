from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median

from .db import connect, initialize
from .geo import mesh_code_250m
from .scoring import ScoreWeights, percentile_ranks, score_metric, total_score
from .station_transactions import ensure_station_transaction_schema

STATION_RADIUS_M = 1000
STATION_DEFINITION_VERSION = "r1000:v1"
STATION_METRIC_VERSION = "station-metrics-v0.1"
STATION_SCORE_VERSION = "station-v0.1"
STATION_PEER_GROUP = "tokyo23:station_area:r1000"
CONVENIENCE_TYPES = ("school", "childcare", "medical", "library", "public_facility")


def station_geo_id(group_code: str) -> str:
    return f"station:{str(group_code).strip()}:r1000:v1"


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _pick(values: list[str]) -> str | None:
    clean = [value for value in values if value]
    if not clean:
        return None
    counts = Counter(clean)
    best = max(counts.values())
    return sorted(value for value, count in counts.items() if count == best)[0]


def _single_source(source_ids: set[int]) -> int | None:
    return next(iter(source_ids)) if len(source_ids) == 1 else None


def _composite_percentile_index(metric_values: list[dict[str, float]]) -> dict[str, float]:
    ranked = [percentile_ranks(values) for values in metric_values if values]
    if not ranked:
        return {}
    common = set(ranked[0])
    for ranks in ranked[1:]:
        common &= set(ranks)
    return {geo_id: mean(ranks[geo_id] for ranks in ranked) for geo_id in common}


@dataclass(frozen=True)
class StationAreaSyncStats:
    station_area_count: int
    mapping_count: int


@dataclass(frozen=True)
class StationScoreStats:
    station_area_count: int
    eligible_count: int
    partially_scored_count: int


def sync_station_areas(
    db_path: str | Path,
    *,
    radius_m: int = STATION_RADIUS_M,
    definition_version: str = STATION_DEFINITION_VERSION,
) -> StationAreaSyncStats:
    """Create one 1km station-area geo unit per XKT015 group code.

    Station areas are represented by the Tokyo-23-ward 250m meshes whose center
    is within radius_m of the grouped station center. The group is independent of
    ward boundaries; primary_area_id is display metadata only.
    """
    initialize(db_path)
    with connect(db_path) as conn:
        station_rows = conn.execute(
            """
            SELECT group_code, station_code, station_name, line_name, operator_name,
                   area_id, latitude, longitude
            FROM stations
            WHERE COALESCE(group_code, station_code) IS NOT NULL
              AND latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY station_name, line_name
            """
        ).fetchall()
        mesh_rows = conn.execute(
            """
            SELECT geo_id, canonical_code AS mesh_id, latitude, longitude
            FROM geo_units
            WHERE geo_type='mesh250' AND is_active=1
              AND latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY canonical_code
            """
        ).fetchall()

        grouped: dict[str, list] = defaultdict(list)
        for row in station_rows:
            code = str(row["group_code"] or row["station_code"] or "").strip()
            if code:
                grouped[code].append(row)

        if grouped and not mesh_rows:
            raise ValueError("active 250m meshes are required before station-area sync")

        conn.execute(
            "UPDATE geo_units SET is_active=0 WHERE geo_type='station_area' AND definition_version=?",
            (definition_version,),
        )
        conn.execute(
            """
            DELETE FROM geo_unit_meshes
            WHERE geo_id IN (
                SELECT geo_id FROM geo_units
                WHERE geo_type='station_area' AND definition_version=?
            )
            """,
            (definition_version,),
        )

        mapping_rows: list[tuple[str, str, float, str, float]] = []
        for group_code, rows in sorted(grouped.items()):
            latitudes = [float(row["latitude"]) for row in rows]
            longitudes = [float(row["longitude"]) for row in rows]
            latitude = mean(latitudes)
            longitude = mean(longitudes)
            name = _pick([str(row["station_name"] or "") for row in rows]) or group_code
            primary_area_id = _pick([str(row["area_id"] or "") for row in rows])
            geo_id = station_geo_id(group_code)

            conn.execute(
                """
                INSERT INTO geo_units (
                    geo_id, geo_type, canonical_code, name, parent_geo_id,
                    primary_area_id, prefecture_code, latitude, longitude,
                    radius_m, definition_version, is_active
                ) VALUES (?, 'station_area', ?, ?, NULL, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(geo_id) DO UPDATE SET
                    geo_type=excluded.geo_type,
                    canonical_code=excluded.canonical_code,
                    name=excluded.name,
                    parent_geo_id=NULL,
                    primary_area_id=excluded.primary_area_id,
                    prefecture_code=excluded.prefecture_code,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    radius_m=excluded.radius_m,
                    definition_version=excluded.definition_version,
                    is_active=1
                """,
                (
                    geo_id,
                    group_code,
                    name,
                    primary_area_id,
                    primary_area_id[:2] if primary_area_id else "13",
                    latitude,
                    longitude,
                    int(radius_m),
                    definition_version,
                ),
            )

            lat_delta = radius_m / 111_320.0 * 1.10
            lon_scale = max(0.2, math.cos(math.radians(latitude)))
            lon_delta = radius_m / (111_320.0 * lon_scale) * 1.10
            for mesh in mesh_rows:
                mesh_lat = float(mesh["latitude"])
                mesh_lon = float(mesh["longitude"])
                if abs(mesh_lat - latitude) > lat_delta or abs(mesh_lon - longitude) > lon_delta:
                    continue
                distance = _distance_m(longitude, latitude, mesh_lon, mesh_lat)
                if distance <= radius_m:
                    mapping_rows.append(
                        (geo_id, str(mesh["mesh_id"]), 1.0, "station_radius_center", round(distance, 2))
                    )

        if mapping_rows:
            conn.executemany(
                """
                INSERT INTO geo_unit_meshes(geo_id, mesh_id, weight, method, distance_m)
                VALUES (?, ?, ?, ?, ?)
                """,
                mapping_rows,
            )

        station_area_count = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM geo_units
                WHERE geo_type='station_area' AND definition_version=? AND is_active=1
                """,
                (definition_version,),
            ).fetchone()[0]
        )
        mapping_count = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM geo_unit_meshes gum
                JOIN geo_units gu ON gu.geo_id=gum.geo_id
                WHERE gu.geo_type='station_area' AND gu.definition_version=? AND gu.is_active=1
                """,
                (definition_version,),
            ).fetchone()[0]
        )

    return StationAreaSyncStats(station_area_count=station_area_count, mapping_count=mapping_count)


def _station_confidence(completeness: float, transaction_count: int, price_year_count: int) -> str:
    if completeness >= 1.0 and transaction_count >= 100 and price_year_count >= 5:
        return "A"
    if completeness >= 0.95 and transaction_count >= 50 and price_year_count >= 4:
        return "B"
    if completeness >= 0.80 and transaction_count >= 30 and price_year_count >= 3:
        return "C"
    return "D"


def compute_station_scores(
    db_path: str | Path,
    *,
    calculation_date: str | None = None,
    definition_version: str = STATION_DEFINITION_VERSION,
    metric_version: str = STATION_METRIC_VERSION,
    score_version: str = STATION_SCORE_VERSION,
) -> StationScoreStats:
    """Compute station-area metrics and station-only relative scores.

    Population score v0.1 is explicitly provisional: XKT013 2020 baseline to
    2025 projected population change is used because fine-grained 2025 Census
    population is not yet part of this project. Future population uses 2045/2025.
    Price and transaction metrics come from XIT001 queried with the station group
    code, not from a guessed property coordinate inside the 1km radius.
    """
    initialize(db_path)
    calc_date = calculation_date or date.today().isoformat()
    calculated_at = datetime.now(timezone.utc).isoformat()
    completed_year = int(calc_date[:4]) - 1
    window_start = completed_year - 4
    weights = ScoreWeights()

    with connect(db_path) as conn:
        ensure_station_transaction_schema(conn)
        station_units = conn.execute(
            """
            SELECT geo_id, canonical_code, name, primary_area_id
            FROM geo_units
            WHERE geo_type='station_area' AND definition_version=? AND is_active=1
            ORDER BY canonical_code
            """,
            (definition_version,),
        ).fetchall()
        geo_ids = [str(row["geo_id"]) for row in station_units]
        if not geo_ids:
            return StationScoreStats(0, 0, 0)

        station_code_by_geo = {str(row["geo_id"]): str(row["canonical_code"]) for row in station_units}
        geo_by_station_code = {value: key for key, value in station_code_by_geo.items()}

        mesh_to_geos: dict[str, set[str]] = defaultdict(set)
        mesh_count: dict[str, int] = defaultdict(int)
        for row in conn.execute(
            """
            SELECT gum.geo_id, gum.mesh_id
            FROM geo_unit_meshes gum
            JOIN geo_units gu ON gu.geo_id=gum.geo_id
            WHERE gu.geo_type='station_area' AND gu.definition_version=? AND gu.is_active=1
            """,
            (definition_version,),
        ):
            geo_id = str(row["geo_id"])
            mesh_id = str(row["mesh_id"])
            mesh_to_geos[mesh_id].add(geo_id)
            mesh_count[geo_id] += 1

        population: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        population_sources: dict[str, set[int]] = defaultdict(set)
        for row in conn.execute(
            """
            SELECT gum.geo_id, fp.year, fp.projected_population, fp.source_id
            FROM geo_unit_meshes gum
            JOIN geo_units gu ON gu.geo_id=gum.geo_id
            JOIN future_population fp ON fp.mesh_id=gum.mesh_id
            WHERE gu.geo_type='station_area' AND gu.definition_version=? AND gu.is_active=1
              AND fp.year IN (2020, 2025, 2045)
            """,
            (definition_version,),
        ):
            if row["projected_population"] is not None:
                geo_id = str(row["geo_id"])
                population[geo_id][int(row["year"])] += float(row["projected_population"])
                if row["source_id"] is not None:
                    population_sources[geo_id].add(int(row["source_id"]))

        facility_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        facility_sources: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
        for row in conn.execute(
            """
            SELECT facility_id, facility_type, latitude, longitude, source_id
            FROM facilities
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ):
            facility_type = str(row["facility_type"])
            if facility_type not in CONVENIENCE_TYPES:
                continue
            try:
                mesh_id = mesh_code_250m(float(row["longitude"]), float(row["latitude"]))
            except ValueError:
                continue
            for geo_id in mesh_to_geos.get(mesh_id, set()):
                facility_counts[geo_id][facility_type] += 1
                if row["source_id"] is not None:
                    facility_sources[geo_id][facility_type].add(int(row["source_id"]))

        nearby_groups: dict[str, set[str]] = defaultdict(set)
        nearby_lines: dict[str, set[str]] = defaultdict(set)
        nearby_passengers: dict[str, dict[str, int]] = defaultdict(dict)
        transport_sources: dict[str, set[int]] = defaultdict(set)
        for row in conn.execute(
            """
            SELECT station_id, station_code, group_code, line_name, passenger_count,
                   latitude, longitude, source_id
            FROM stations
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ):
            try:
                mesh_id = mesh_code_250m(float(row["longitude"]), float(row["latitude"]))
            except ValueError:
                continue
            group = str(row["group_code"] or row["station_code"] or row["station_id"])
            for geo_id in mesh_to_geos.get(mesh_id, set()):
                nearby_groups[geo_id].add(group)
                if row["line_name"]:
                    nearby_lines[geo_id].add(str(row["line_name"]))
                if row["passenger_count"] is not None:
                    count = int(row["passenger_count"])
                    nearby_passengers[geo_id][group] = max(nearby_passengers[geo_id].get(group, 0), count)
                if row["source_id"] is not None:
                    transport_sources[geo_id].add(int(row["source_id"]))

        tx_rows_by_geo_year: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        tx_sources: dict[str, set[int]] = defaultdict(set)
        for row in conn.execute(
            """
            SELECT station_group_code, year, unit_price, source_id
            FROM station_transactions
            WHERE year BETWEEN ? AND ?
            """,
            (window_start, completed_year),
        ):
            geo_id = geo_by_station_code.get(str(row["station_group_code"]))
            if geo_id is None:
                continue
            tx_rows_by_geo_year[geo_id][int(row["year"])].append(row)
            if row["source_id"] is not None:
                tx_sources[geo_id].add(int(row["source_id"]))

        price_values: dict[str, float] = {}
        population_values: dict[str, float] = {}
        future_values: dict[str, float] = {}
        transaction_values: dict[str, float] = {}
        price_year_counts: dict[str, int] = {}
        tx_counts: dict[str, int] = {}
        raw_metrics: dict[str, dict[str, float | int | None]] = defaultdict(dict)

        facility_rate_metrics: list[dict[str, float]] = []
        station_rates: dict[str, float] = {}
        line_counts: dict[str, float] = {}
        passenger_rates: dict[str, float] = {}

        for geo_id in geo_ids:
            p2020 = population[geo_id].get(2020)
            p2025 = population[geo_id].get(2025)
            p2045 = population[geo_id].get(2045)
            raw_metrics[geo_id]["mesh_count"] = mesh_count.get(geo_id, 0)
            raw_metrics[geo_id]["population_2020"] = p2020
            raw_metrics[geo_id]["population_2025_projection"] = p2025
            raw_metrics[geo_id]["future_population_2045"] = p2045

            if p2020 and p2020 > 0 and p2025 is not None:
                pop_change = (p2025 / p2020 - 1.0) * 100.0
                population_values[geo_id] = pop_change
                raw_metrics[geo_id]["population_change_2020_2025_projection"] = pop_change
            else:
                raw_metrics[geo_id]["population_change_2020_2025_projection"] = None

            if p2025 and p2025 > 0 and p2045 is not None:
                retention = p2045 / p2025 * 100.0
                future_values[geo_id] = retention
                raw_metrics[geo_id]["future_population_retention_2045"] = retention
            else:
                raw_metrics[geo_id]["future_population_retention_2045"] = None

            if p2025 and p2025 > 0:
                station_rates[geo_id] = len(nearby_groups.get(geo_id, set())) / p2025 * 100_000.0
                line_counts[geo_id] = float(len(nearby_lines.get(geo_id, set())))
                passenger_total = sum(nearby_passengers.get(geo_id, {}).values())
                passenger_rates[geo_id] = passenger_total / p2025
                raw_metrics[geo_id]["nearby_station_count"] = len(nearby_groups.get(geo_id, set()))
                raw_metrics[geo_id]["nearby_line_count"] = len(nearby_lines.get(geo_id, set()))
                raw_metrics[geo_id]["ridership_daily"] = passenger_total
                raw_metrics[geo_id]["ridership_per_capita"] = passenger_rates[geo_id]
            else:
                raw_metrics[geo_id]["nearby_station_count"] = len(nearby_groups.get(geo_id, set()))
                raw_metrics[geo_id]["nearby_line_count"] = len(nearby_lines.get(geo_id, set()))
                raw_metrics[geo_id]["ridership_daily"] = sum(nearby_passengers.get(geo_id, {}).values())
                raw_metrics[geo_id]["ridership_per_capita"] = None

            years = tx_rows_by_geo_year.get(geo_id, {})
            tx_count = sum(len(rows) for rows in years.values())
            tx_counts[geo_id] = tx_count
            transaction_values[geo_id] = float(tx_count)
            raw_metrics[geo_id]["transaction_count_5y"] = tx_count

            annual_medians: dict[int, float] = {}
            for year, rows in years.items():
                values = [float(row["unit_price"]) for row in rows if row["unit_price"] is not None]
                if values:
                    annual_medians[year] = float(median(values))
            price_year_count = len(annual_medians)
            price_year_counts[geo_id] = price_year_count
            raw_metrics[geo_id]["price_year_count"] = price_year_count
            if annual_medians:
                latest_year = max(annual_medians)
                raw_metrics[geo_id]["transaction_unit_price_median_latest"] = annual_medians[latest_year]
            else:
                raw_metrics[geo_id]["transaction_unit_price_median_latest"] = None
            if len(annual_medians) >= 2:
                first_year = min(annual_medians)
                last_year = max(annual_medians)
                first_value = annual_medians[first_year]
                last_value = annual_medians[last_year]
                if first_value > 0:
                    change = (last_value / first_value - 1.0) * 100.0
                    price_values[geo_id] = change
                    raw_metrics[geo_id]["transaction_unit_price_change"] = change
                else:
                    raw_metrics[geo_id]["transaction_unit_price_change"] = None
            else:
                raw_metrics[geo_id]["transaction_unit_price_change"] = None

        for facility_type in CONVENIENCE_TYPES:
            values: dict[str, float] = {}
            for geo_id in geo_ids:
                p2025 = population[geo_id].get(2025)
                count = facility_counts[geo_id].get(facility_type, 0)
                raw_metrics[geo_id][f"facility_{facility_type}_count"] = count
                if p2025 and p2025 > 0:
                    rate = count / p2025 * 10_000.0
                    values[geo_id] = rate
                    raw_metrics[geo_id][f"facility_{facility_type}_per_10k"] = rate
                else:
                    raw_metrics[geo_id][f"facility_{facility_type}_per_10k"] = None
            if values:
                facility_rate_metrics.append(values)

        convenience_index = _composite_percentile_index(facility_rate_metrics)
        transport_index = _composite_percentile_index([station_rates, line_counts, passenger_rates])
        for geo_id in geo_ids:
            raw_metrics[geo_id]["convenience_index"] = convenience_index.get(geo_id)
            raw_metrics[geo_id]["transport_index"] = transport_index.get(geo_id)

        price_scores = score_metric(price_values, weights.price) if price_values else {}
        population_scores = score_metric(population_values, weights.population) if population_values else {}
        future_scores = score_metric(future_values, weights.future_population) if future_values else {}
        convenience_scores = score_metric(convenience_index, weights.convenience) if convenience_index else {}
        transport_scores = score_metric(transport_index, weights.transport) if transport_index else {}
        transaction_scores = score_metric(transaction_values, weights.transaction) if transaction_values else {}

        placeholders = ",".join("?" for _ in geo_ids)
        conn.execute(
            f"DELETE FROM geo_metrics WHERE metric_version=? AND geo_id IN ({placeholders})",
            (metric_version, *geo_ids),
        )

        metric_periods = {
            "mesh_count": f"r{STATION_RADIUS_M}",
            "population_2020": "2020",
            "population_2025_projection": "2025",
            "population_change_2020_2025_projection": "2020-2025",
            "future_population_2045": "2045",
            "future_population_retention_2045": "2045/2025",
            "nearby_station_count": f"r{STATION_RADIUS_M}",
            "nearby_line_count": f"r{STATION_RADIUS_M}",
            "ridership_daily": "latest",
            "ridership_per_capita": "latest/2025",
            "transaction_count_5y": f"{window_start}-{completed_year}",
            "price_year_count": f"{window_start}-{completed_year}",
            "transaction_unit_price_median_latest": f"<= {completed_year}",
            "transaction_unit_price_change": f"{window_start}-{completed_year}",
            "convenience_index": f"r{STATION_RADIUS_M}",
            "transport_index": f"r{STATION_RADIUS_M}",
        }
        for facility_type in CONVENIENCE_TYPES:
            metric_periods[f"facility_{facility_type}_count"] = f"r{STATION_RADIUS_M}"
            metric_periods[f"facility_{facility_type}_per_10k"] = f"r{STATION_RADIUS_M}/2025"

        for geo_id in geo_ids:
            for key, value in raw_metrics[geo_id].items():
                source_id = None
                if key.startswith("population_") or key.startswith("future_population_"):
                    source_id = _single_source(population_sources[geo_id])
                elif key.startswith("facility_"):
                    facility_type = key.removeprefix("facility_").split("_count")[0].split("_per_10k")[0]
                    source_id = _single_source(facility_sources[geo_id].get(facility_type, set()))
                elif key in {"nearby_station_count", "nearby_line_count", "ridership_daily", "ridership_per_capita"}:
                    source_id = _single_source(transport_sources[geo_id])
                elif key in {"transaction_count_5y", "price_year_count", "transaction_unit_price_median_latest", "transaction_unit_price_change"}:
                    source_id = _single_source(tx_sources[geo_id])

                sample_size = None
                if key.startswith("facility_") and key.endswith("_count"):
                    sample_size = int(value or 0)
                elif key in {"transaction_count_5y", "price_year_count", "mesh_count", "nearby_station_count", "nearby_line_count"}:
                    sample_size = int(value or 0)

                conn.execute(
                    """
                    INSERT INTO geo_metrics(
                        geo_id, metric_key, period, value, sample_size,
                        source_id, metric_version, calculated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        geo_id,
                        key,
                        metric_periods.get(key, "current"),
                        None if value is None else float(value),
                        sample_size,
                        source_id,
                        metric_version,
                        calculated_at,
                    ),
                )

        eligible_count = 0
        partially_scored_count = 0
        for geo_id in geo_ids:
            available = {
                "price": price_scores.get(geo_id),
                "population": population_scores.get(geo_id),
                "future_population": future_scores.get(geo_id),
                "convenience": convenience_scores.get(geo_id),
                "transport": transport_scores.get(geo_id),
                "transaction": transaction_scores.get(geo_id),
            }
            completeness = sum(value is not None for value in available.values()) / len(available)
            if any(value is not None for value in available.values()):
                partially_scored_count += 1

            reasons: list[str] = []
            tx_count = tx_counts.get(geo_id, 0)
            price_year_count = price_year_counts.get(geo_id, 0)
            p2020 = population[geo_id].get(2020)
            p2025 = population[geo_id].get(2025)
            p2045 = population[geo_id].get(2045)
            if any(value is None for value in available.values()):
                reasons.append("6構成項目の一部が未算出")
            if tx_count < 30:
                reasons.append("直近5完了年の取引件数が30件未満")
            if price_year_count < 3:
                reasons.append("価格指標に使える年が3年未満")
            if not p2020 or p2020 <= 0 or not p2025 or p2025 <= 0 or p2045 is None:
                reasons.append("2020・2025・2045人口が不足")
            if mesh_count.get(geo_id, 0) <= 0:
                reasons.append("1km圏メッシュが未生成")

            eligibility = "eligible" if not reasons else "insufficient_data"
            total = total_score(available) if eligibility == "eligible" else None
            if total is not None:
                eligible_count += 1

            conn.execute(
                """
                INSERT INTO geo_scores(
                    geo_id, calculation_date, peer_group,
                    price_score, population_score, future_population_score,
                    convenience_score, transport_score, transaction_score,
                    total_score, confidence, data_completeness,
                    score_version, eligibility, eligibility_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(geo_id, calculation_date, score_version) DO UPDATE SET
                    peer_group=excluded.peer_group,
                    price_score=excluded.price_score,
                    population_score=excluded.population_score,
                    future_population_score=excluded.future_population_score,
                    convenience_score=excluded.convenience_score,
                    transport_score=excluded.transport_score,
                    transaction_score=excluded.transaction_score,
                    total_score=excluded.total_score,
                    confidence=excluded.confidence,
                    data_completeness=excluded.data_completeness,
                    eligibility=excluded.eligibility,
                    eligibility_reason=excluded.eligibility_reason
                """,
                (
                    geo_id,
                    calc_date,
                    STATION_PEER_GROUP,
                    available["price"],
                    available["population"],
                    available["future_population"],
                    available["convenience"],
                    available["transport"],
                    available["transaction"],
                    total,
                    _station_confidence(completeness, tx_count, price_year_count),
                    completeness,
                    score_version,
                    eligibility,
                    " / ".join(reasons) if reasons else None,
                ),
            )

    return StationScoreStats(
        station_area_count=len(geo_ids),
        eligible_count=eligible_count,
        partially_scored_count=partially_scored_count,
    )
