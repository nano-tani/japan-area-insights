from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Mapping

CENSUS_2025_TOTAL_ID = "0004050397"
CENSUS_2025_CHANGE_ID = "0004050417"


def _class_labels(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    statistical = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]
    class_objects = statistical["CLASS_INF"]["CLASS_OBJ"]
    if isinstance(class_objects, dict):
        class_objects = [class_objects]
    result: dict[str, dict[str, str]] = {}
    for obj in class_objects:
        key = str(obj["@id"])
        classes = obj.get("CLASS", [])
        if isinstance(classes, dict):
            classes = [classes]
        result[key] = {str(item["@code"]): str(item["@name"]) for item in classes}
    return result


def _values(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"].get("VALUE", [])
    return [data] if isinstance(data, dict) else list(data)


def _value_labels(value: Mapping[str, Any], labels: Mapping[str, Mapping[str, str]]) -> list[str]:
    result: list[str] = []
    for dimension, mapping in labels.items():
        code = value.get(f"@{dimension}")
        if code is not None and str(code) in mapping:
            result.append(mapping[str(code)])
    return result


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "...", "X"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(" ", "").replace("　", "")


def _find(
    payload: Mapping[str, Any],
    area_id: str,
    required_labels: Iterable[str],
    *,
    forbidden_labels: Iterable[str] = (),
) -> float | None:
    labels = _class_labels(payload)
    required = tuple(_norm(label) for label in required_labels)
    forbidden = tuple(_norm(label) for label in forbidden_labels)
    for value in _values(payload):
        if str(value.get("@area") or "") != area_id:
            continue
        combined = "|".join(_norm(label) for label in _value_labels(value, labels))
        if all(label in combined for label in required) and not any(label in combined for label in forbidden):
            return _number(value.get("$"))
    return None


def normalize_census_2025(
    total_payload: Mapping[str, Any],
    change_payload: Mapping[str, Any],
    area_ids: Iterable[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for area_id in area_ids:
        current_population = _find(total_payload, area_id, ("人口", "総数"))
        previous_population = _find(change_payload, area_id, ("2020年", "人口", "組替"))
        current_households = _find(
            change_payload,
            area_id,
            ("世帯数",),
            forbidden_labels=("2020年", "増減", "率"),
        )
        previous_households = _find(change_payload, area_id, ("2020年", "世帯数", "組替"))
        population_change_rate = _find(change_payload, area_id, ("人口増減率",))
        household_change_rate = _find(change_payload, area_id, ("世帯増減率",))

        if previous_population is not None or previous_households is not None:
            rows.append(
                {
                    "area_id": area_id,
                    "year": 2020,
                    "population": int(previous_population) if previous_population is not None else None,
                    "households": int(previous_households) if previous_households is not None else None,
                    "population_change_rate": None,
                    "household_change_rate": None,
                }
            )
        if current_population is not None or current_households is not None:
            rows.append(
                {
                    "area_id": area_id,
                    "year": 2025,
                    "population": int(current_population) if current_population is not None else None,
                    "households": int(current_households) if current_households is not None else None,
                    "population_change_rate": population_change_rate,
                    "household_change_rate": household_change_rate,
                }
            )
    return rows
