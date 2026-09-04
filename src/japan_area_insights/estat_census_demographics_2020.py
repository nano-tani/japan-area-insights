from __future__ import annotations

from typing import Any, Callable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .estat_analysis import (
    METRIC_VERSION,
    _class_map,
    _dimension_containing_codes,
    _filter_name,
    _meta_class_objects,
    _number,
    _source_id,
    _values,
)
from .sources.estat import EStatClient

FOREIGN_NATIONALITY_ID = "0003445244"  # 44-1 男女，国籍別人口
HOUSEHOLD_SIZE_ID = "0003445278"       # 6-3-1 世帯人員の人数別一般世帯数


def _norm(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("　", "").replace(",", "，").strip()


def _code(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(_norm(label)):
            return str(code)
    return None


def _dimension(
    classes: Mapping[str, Mapping[str, str]],
    labels: tuple[str, ...],
    excluded: set[str] | None = None,
) -> str:
    excluded = excluded or set()
    wanted = tuple(_norm(label) for label in labels)
    best: tuple[int, str] | None = None
    for dim_id, mapping in classes.items():
        if dim_id in excluded:
            continue
        names = [_norm(label) for label in mapping.values()]
        score = sum(any(name == token for name in names) for token in wanted)
        if score and (best is None or score > best[0]):
            best = (score, dim_id)
    if best is None:
        raise ValueError(f"census dimension not found: {labels}")
    return best[1]


def _total_code(mapping: Mapping[str, str]) -> str | None:
    return (
        _code(mapping, lambda label: label in {"総数", "男女計", "総数（男女計）", "人口"})
        or _code(mapping, lambda label: label.startswith("総数"))
        or (str(next(iter(mapping))) if len(mapping) == 1 else None)
    )


def _base_params(classes: Mapping[str, Mapping[str, str]], keep: set[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for dim_id, mapping in classes.items():
        if dim_id in keep:
            continue
        code = _total_code(mapping)
        if code:
            params[_filter_name(dim_id)] = code
    return params


def _seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO dataset_catalog(
            dataset_key,provider,api_id,category,title,source_vintage,
            granularity,refresh_mode,enabled,notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET
            api_id=excluded.api_id,title=excluded.title,notes=excluded.notes
        """,
        [
            (
                "estat_census_2020_nationality",
                "政府統計の総合窓口 e-Stat",
                FOREIGN_NATIONALITY_ID,
                "demographics",
                "2020年国勢調査 国籍別人口",
                "2020-10",
                "municipality",
                "extended",
                1,
                "人口等基本集計 表44-1。男女計・市区町村粒度。",
            ),
            (
                "estat_census_2020_household_size",
                "政府統計の総合窓口 e-Stat",
                HOUSEHOLD_SIZE_ID,
                "demographics",
                "2020年国勢調査 一般世帯の世帯人員",
                "2020-10",
                "municipality",
                "extended",
                1,
                "人口等基本集計 表6-3-1。市区町村粒度。",
            ),
        ],
    )
    definitions = [
        ("demographics2020.foreign_population", "demographics", "外国人人口", "人", "neutral", "ward", "estat_census_2020_nationality", 1, "国籍区分が外国人の人口（男女計）"),
        ("demographics2020.foreign_share", "demographics", "外国人人口比率", "%", "neutral", "ward", "estat_census_2020_nationality", 1, "外国人人口÷国籍総数人口"),
        ("demographics2020.china_share_of_foreign", "demographics", "外国人に占める中国籍比率", "%", "neutral", "ward", "estat_census_2020_nationality", 1, "中国籍人口÷外国人人口"),
        ("demographics2020.korea_share_of_foreign", "demographics", "外国人に占める韓国・朝鮮籍比率", "%", "neutral", "ward", "estat_census_2020_nationality", 1, "韓国・朝鮮籍人口÷外国人人口"),
        ("demographics2020.vietnam_share_of_foreign", "demographics", "外国人に占めるベトナム籍比率", "%", "neutral", "ward", "estat_census_2020_nationality", 1, "ベトナム籍人口÷外国人人口"),
        ("demographics2020.philippines_share_of_foreign", "demographics", "外国人に占めるフィリピン籍比率", "%", "neutral", "ward", "estat_census_2020_nationality", 1, "フィリピン籍人口÷外国人人口"),
        ("demographics2020.nepal_share_of_foreign", "demographics", "外国人に占めるネパール籍比率", "%", "neutral", "ward", "estat_census_2020_nationality", 1, "ネパール籍人口÷外国人人口"),
        ("demographics2020.general_households", "demographics", "一般世帯数", "世帯", "neutral", "ward", "estat_census_2020_household_size", 1, "一般世帯総数"),
        ("demographics2020.single_household_share", "demographics", "1人世帯比率", "%", "neutral", "ward", "estat_census_2020_household_size", 1, "世帯人員1人の一般世帯÷一般世帯総数"),
        ("demographics2020.two_person_household_share", "demographics", "2人世帯比率", "%", "neutral", "ward", "estat_census_2020_household_size", 1, "世帯人員2人の一般世帯÷一般世帯総数"),
        ("demographics2020.four_plus_household_share", "demographics", "4人以上世帯比率", "%", "neutral", "ward", "estat_census_2020_household_size", 1, "世帯人員4人以上の一般世帯÷一般世帯総数"),
    ]
    conn.executemany(
        """
        INSERT INTO metric_definitions(
            metric_key,category,label,unit,direction,granularity,
            source_dataset_key,min_sample_size,description
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET
            label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        definitions,
    )


def _write(conn, area_id: str, key: str, value: float | None, source_id: int, note: str) -> int:
    upsert_metric(
        conn,
        geo_id=f"ward:{area_id}",
        metric_key=key,
        period="2020",
        value=round(value, 3) if value is not None else None,
        sample_size=1,
        source_id=source_id,
        metric_version=METRIC_VERSION,
        quality_grade="A",
        source_year="2020-10",
        notes=note,
    )
    return 1


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100.0


def fetch_nationality(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(FOREIGN_NATIONALITY_ID)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    nationality_dim = _dimension(
        classes,
        ("外国人", "中国", "フィリピン", "ベトナム", "ネパール"),
        {area_dim},
    )
    nationality_map = classes[nationality_dim]
    codes = {
        "total": _code(nationality_map, lambda label: label == "総数"),
        "foreign": _code(nationality_map, lambda label: label == "外国人"),
        "china": _code(nationality_map, lambda label: label == "中国"),
        "korea": _code(nationality_map, lambda label: label in {"韓国，朝鮮", "韓国・朝鮮", "韓国,朝鮮"}),
        "vietnam": _code(nationality_map, lambda label: label == "ベトナム"),
        "philippines": _code(nationality_map, lambda label: label == "フィリピン"),
        "nepal": _code(nationality_map, lambda label: label == "ネパール"),
    }
    if not codes["total"] or not codes["foreign"]:
        raise ValueError("2020 census nationality total/foreign categories not found")

    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(nationality_dim): ",".join(code for code in codes.values() if code),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }
    params.update(_base_params(classes, {area_dim, nationality_dim}))
    payload = client.get_stats_data_all(FOREIGN_NATIONALITY_ID, params, max_rows=5000)
    source_id = _source_id(
        conn,
        title="2020年国勢調査 国籍別人口",
        dataset_id=FOREIGN_NATIONALITY_ID,
        payload=payload,
    )

    values: dict[tuple[str, str], float] = {}
    reverse = {code: name for name, code in codes.items() if code}
    for row in _values(payload):
        area_id = str(row.get(f"@{area_dim}") or "")
        name = reverse.get(str(row.get(f"@{nationality_dim}") or ""))
        number = _number(row.get("$"))
        if area_id in area_ids and name and number is not None:
            values[(area_id, name)] = number

    written = 0
    for area_id in area_ids:
        total = values.get((area_id, "total"))
        foreign = values.get((area_id, "foreign"))
        metrics = [
            ("demographics2020.foreign_population", foreign),
            ("demographics2020.foreign_share", _pct(foreign, total)),
            ("demographics2020.china_share_of_foreign", _pct(values.get((area_id, "china")), foreign)),
            ("demographics2020.korea_share_of_foreign", _pct(values.get((area_id, "korea")), foreign)),
            ("demographics2020.vietnam_share_of_foreign", _pct(values.get((area_id, "vietnam")), foreign)),
            ("demographics2020.philippines_share_of_foreign", _pct(values.get((area_id, "philippines")), foreign)),
            ("demographics2020.nepal_share_of_foreign", _pct(values.get((area_id, "nepal")), foreign)),
        ]
        for key, value in metrics:
            written += _write(
                conn,
                area_id,
                key,
                value,
                source_id,
                "2020年国勢調査 表44-1。男女計・市区町村粒度。",
            )
    return written


def fetch_household_size(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(HOUSEHOLD_SIZE_ID)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    size_dim = _dimension(
        classes,
        ("世帯人員が1人", "世帯人員が2人", "世帯人員が4人"),
        {area_dim},
    )
    size_map = classes[size_dim]
    total_code = _code(size_map, lambda label: label == "総数")
    one_code = _code(size_map, lambda label: label == "世帯人員が1人")
    two_code = _code(size_map, lambda label: label == "世帯人員が2人")
    four_plus_codes = [
        str(code)
        for code, label in size_map.items()
        if _norm(label)
        in {
            "世帯人員が4人",
            "世帯人員が5人",
            "世帯人員が6人",
            "世帯人員が7人",
            "世帯人員が8人",
            "世帯人員が9人",
            "世帯人員が10人以上",
        }
    ]
    if not total_code or not one_code or not two_code:
        raise ValueError("2020 census household-size categories not found")

    selected = [total_code, one_code, two_code, *four_plus_codes]
    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(size_dim): ",".join(selected),
        "metaGetFlg": "Y",
        "cntGetFlg": "N",
    }
    params.update(_base_params(classes, {area_dim, size_dim}))
    payload = client.get_stats_data_all(HOUSEHOLD_SIZE_ID, params, max_rows=10000)
    source_id = _source_id(
        conn,
        title="2020年国勢調査 一般世帯の世帯人員",
        dataset_id=HOUSEHOLD_SIZE_ID,
        payload=payload,
    )

    values: dict[tuple[str, str], float] = {}
    for row in _values(payload):
        area_id = str(row.get(f"@{area_dim}") or "")
        size = str(row.get(f"@{size_dim}") or "")
        number = _number(row.get("$"))
        if area_id in area_ids and size in selected and number is not None:
            values[(area_id, size)] = number

    written = 0
    for area_id in area_ids:
        total = values.get((area_id, total_code))
        one = values.get((area_id, one_code))
        two = values.get((area_id, two_code))
        four_plus_values = [values.get((area_id, code)) for code in four_plus_codes]
        four_plus = (
            sum(value for value in four_plus_values if value is not None)
            if any(value is not None for value in four_plus_values)
            else None
        )
        for key, value in (
            ("demographics2020.general_households", total),
            ("demographics2020.single_household_share", _pct(one, total)),
            ("demographics2020.two_person_household_share", _pct(two, total)),
            ("demographics2020.four_plus_household_share", _pct(four_plus, total)),
        ):
            written += _write(
                conn,
                area_id,
                key,
                value,
                source_id,
                "2020年国勢調査 表6-3-1。一般世帯・市区町村粒度。",
            )
    return written


def fetch_census_demographics_2020(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn)
    _seed(conn)
    return fetch_nationality(client, conn, area_ids) + fetch_household_size(client, conn, area_ids)
