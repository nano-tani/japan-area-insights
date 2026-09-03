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

TABLE_TENURE_AGE = "0004021676"  # 5-3, municipality
TABLE_STRUCTURE_AGE = "0004021696"  # 6-3-2, municipality


def _norm(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("　", "").replace("〜", "～").strip()


def _code(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(_norm(label)):
            return str(code)
    return None


def _dimension(classes: Mapping[str, Mapping[str, str]], required: tuple[str, ...], excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    best: tuple[int, str] | None = None
    wanted = [_norm(value) for value in required]
    for dim_id, mapping in classes.items():
        if dim_id in excluded:
            continue
        labels = [_norm(value) for value in mapping.values()]
        score = sum(any(label == token for label in labels) for token in wanted)
        if score and (best is None or score > best[0]):
            best = (score, dim_id)
    if not best:
        raise ValueError(f"housing dimension not found: {required}")
    return best[1]


def _total(mapping: Mapping[str, str]) -> str | None:
    return _code(mapping, lambda label: label == "総数") or (str(next(iter(mapping))) if len(mapping) == 1 else None)


def _seed(conn) -> None:
    datasets = [
        ("estat_housing_2023_tenure_age", "政府統計の総合窓口 e-Stat", TABLE_TENURE_AGE, "housing", "2023住宅・土地統計 住宅所有関係×建築時期", "2023-10", "municipality", "extended", 1, "表5-3。全国・都道府県・市区町村。"),
        ("estat_housing_2023_structure_age", "政府統計の総合窓口 e-Stat", TABLE_STRUCTURE_AGE, "housing", "2023住宅・土地統計 構造×建築時期", "2023-10", "municipality", "extended", 1, "表6-3-2。全国・都道府県・市区町村。"),
    ]
    conn.executemany("""
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,notes=excluded.notes
    """, datasets)
    definitions = [
        ("housing2023.total_housing", "housing", "住宅数（2023）", "戸", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "2023年10月の住宅数"),
        ("housing2023.owner_occupied_share", "housing", "持ち家比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "持ち家÷住宅総数"),
        ("housing2023.rental_share", "housing", "借家比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "借家÷住宅総数"),
        ("housing2023.private_rental_share", "housing", "民営借家比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "民営借家÷住宅総数"),
        ("housing2023.public_rental_share", "housing", "公営借家比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "公営の借家÷住宅総数"),
        ("housing2023.ur_public_corp_rental_share", "housing", "UR・公社借家比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "UR・公社の借家÷住宅総数"),
        ("housing2023.pre1980_share", "housing", "1980年以前建築住宅比率", "%", "lower", "ward", "estat_housing_2023_tenure_age", 1, "1970年以前と1971～1980年の住宅数÷総数"),
        ("housing2023.pre2000_share", "housing", "2000年以前建築住宅比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "2000年以前に建築された住宅数÷総数"),
        ("housing2023.post2011_share", "housing", "2011年以降建築住宅比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "2011年以降に建築された住宅数÷総数"),
        ("housing2023.2021_2023_share", "housing", "2021～2023年9月建築比率", "%", "neutral", "ward", "estat_housing_2023_tenure_age", 1, "2021～2023年9月建築住宅数÷総数"),
        ("housing2023.wooden_share", "housing", "木造住宅比率", "%", "neutral", "ward", "estat_housing_2023_structure_age", 1, "木造住宅÷住宅総数"),
        ("housing2023.nonwooden_share", "housing", "非木造住宅比率", "%", "neutral", "ward", "estat_housing_2023_structure_age", 1, "非木造住宅÷住宅総数"),
        ("housing2023.rc_share", "housing", "RC・SRC等住宅比率", "%", "neutral", "ward", "estat_housing_2023_structure_age", 1, "鉄筋・鉄骨コンクリート造住宅÷住宅総数"),
        ("housing2023.steel_share", "housing", "鉄骨造住宅比率", "%", "neutral", "ward", "estat_housing_2023_structure_age", 1, "鉄骨造住宅÷住宅総数"),
    ]
    conn.executemany("""
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
    """, definitions)


def _write(conn, area_id: str, key: str, value: float | None, source_id: int, note: str) -> int:
    upsert_metric(conn, geo_id=f"ward:{area_id}", metric_key=key, period="2023", value=value,
                  sample_size=1, source_id=source_id, metric_version=METRIC_VERSION,
                  quality_grade="A", source_year="2023-10", notes=note)
    return 1


def _fetch_tenure_age(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(TABLE_TENURE_AGE)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    item_dim = _dimension(classes, ("住宅数",), {area_dim})
    age_dim = _dimension(classes, ("1970年以前", "2021～2023年9月"), {area_dim, item_dim})
    tenure_dim = _dimension(classes, ("持ち家", "民営借家"), {area_dim, item_dim, age_dim})
    item = _code(classes[item_dim], lambda label: label == "住宅数")
    total_age = _total(classes[age_dim]); total_tenure = _total(classes[tenure_dim])
    tenure_codes = {
        "owner": _code(classes[tenure_dim], lambda label: label == "持ち家"),
        "rental": _code(classes[tenure_dim], lambda label: label == "借家"),
        "public": _code(classes[tenure_dim], lambda label: label == "公営の借家"),
        "ur": _code(classes[tenure_dim], lambda label: "都市再生機構" in label or "UR" in label),
        "private": _code(classes[tenure_dim], lambda label: label == "民営借家"),
    }
    age_codes = {label: _code(classes[age_dim], lambda value, wanted=_norm(label): value == wanted) for label in (
        "1970年以前","1971～1980年","1981～1990年","1991～2000年","2001～2010年","2011～2020年","2021～2023年9月"
    )}
    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids), _filter_name(item_dim): item,
        _filter_name(age_dim): ",".join(code for code in [total_age,*age_codes.values()] if code),
        _filter_name(tenure_dim): ",".join(code for code in [total_tenure,*tenure_codes.values()] if code),
        "metaGetFlg":"Y","cntGetFlg":"N",
    }
    payload = client.get_stats_data_all(TABLE_TENURE_AGE, params, max_rows=20000)
    source_id = _source_id(conn,title="2023住宅・土地統計 表5-3",dataset_id=TABLE_TENURE_AGE,payload=payload)
    values: dict[tuple[str,str,str],float] = {}
    for row in _values(payload):
        area_id=str(row.get(f"@{area_dim}") or ""); age=str(row.get(f"@{age_dim}") or ""); tenure=str(row.get(f"@{tenure_dim}") or ""); number=_number(row.get("$"))
        if area_id in area_ids and number is not None: values[(area_id,age,tenure)] = number
    written=0
    for area_id in area_ids:
        total = values.get((area_id,total_age,total_tenure)) if total_age and total_tenure else None
        def tenure_value(name):
            code=tenure_codes.get(name); return values.get((area_id,total_age,code)) if total_age and code else None
        def age_value(label):
            code=age_codes.get(label); return values.get((area_id,code,total_tenure)) if code and total_tenure else None
        pre1980=sum(v for v in (age_value("1970年以前"),age_value("1971～1980年")) if v is not None)
        pre2000=sum(v for v in (age_value("1970年以前"),age_value("1971～1980年"),age_value("1981～1990年"),age_value("1991～2000年")) if v is not None)
        post2011=sum(v for v in (age_value("2011～2020年"),age_value("2021～2023年9月")) if v is not None)
        latest=age_value("2021～2023年9月")
        metrics=[("housing2023.total_housing",total)]
        for key,name in (("housing2023.owner_occupied_share","owner"),("housing2023.rental_share","rental"),("housing2023.private_rental_share","private"),("housing2023.public_rental_share","public"),("housing2023.ur_public_corp_rental_share","ur")):
            number=tenure_value(name); metrics.append((key, number/total*100 if number is not None and total else None))
        metrics.extend([
            ("housing2023.pre1980_share",pre1980/total*100 if total else None),
            ("housing2023.pre2000_share",pre2000/total*100 if total else None),
            ("housing2023.post2011_share",post2011/total*100 if total else None),
            ("housing2023.2021_2023_share",latest/total*100 if latest is not None and total else None),
        ])
        for key,value in metrics: written += _write(conn,area_id,key,round(value,3) if value is not None else None,source_id,"2023住宅・土地統計調査 表5-3。市区町村粒度。")
    return written


def _fetch_structure(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta=client.get_meta_info(TABLE_STRUCTURE_AGE); classes=_class_map(_meta_class_objects(meta))
    area_dim=_dimension_containing_codes(classes,area_ids); item_dim=_dimension(classes,("住宅数",),{area_dim})
    age_dim=_dimension(classes,("1970年以前","2021～2023年9月"),{area_dim,item_dim})
    structure_dim=_dimension(classes,("木造","非木造","鉄骨造"),{area_dim,item_dim,age_dim})
    item=_code(classes[item_dim],lambda label:label=="住宅数"); total_age=_total(classes[age_dim]); total_structure=_total(classes[structure_dim])
    structure_codes={
        "wood":_code(classes[structure_dim],lambda label:label=="木造"),
        "nonwood":_code(classes[structure_dim],lambda label:label=="非木造"),
        "rc":_code(classes[structure_dim],lambda label:"鉄筋・鉄骨コンクリート造" in label),
        "steel":_code(classes[structure_dim],lambda label:label=="鉄骨造"),
    }
    params={_filter_name(area_dim):",".join(area_ids),_filter_name(item_dim):item,_filter_name(age_dim):total_age,_filter_name(structure_dim):",".join(code for code in [total_structure,*structure_codes.values()] if code),"metaGetFlg":"Y","cntGetFlg":"N"}
    payload=client.get_stats_data_all(TABLE_STRUCTURE_AGE,params,max_rows=5000)
    source_id=_source_id(conn,title="2023住宅・土地統計 表6-3-2",dataset_id=TABLE_STRUCTURE_AGE,payload=payload)
    values:dict[tuple[str,str],float]={}
    for row in _values(payload):
        area_id=str(row.get(f"@{area_dim}") or ""); structure=str(row.get(f"@{structure_dim}") or ""); number=_number(row.get("$"))
        if area_id in area_ids and number is not None: values[(area_id,structure)]=number
    written=0
    for area_id in area_ids:
        total=values.get((area_id,total_structure)) if total_structure else None
        for key,name in (("housing2023.wooden_share","wood"),("housing2023.nonwooden_share","nonwood"),("housing2023.rc_share","rc"),("housing2023.steel_share","steel")):
            code=structure_codes.get(name); number=values.get((area_id,code)) if code else None; value=number/total*100 if number is not None and total else None
            written+=_write(conn,area_id,key,round(value,3) if value is not None else None,source_id,"2023住宅・土地統計調査 表6-3-2。市区町村粒度。")
    return written


def fetch_housing_survey_2023(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn); _seed(conn)
    return _fetch_tenure_age(client,conn,area_ids)+_fetch_structure(client,conn,area_ids)
