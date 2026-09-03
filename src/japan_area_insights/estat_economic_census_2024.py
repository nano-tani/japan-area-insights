from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .estat_analysis import (
    METRIC_VERSION,
    _class_map,
    _data_class_objects,
    _dimension_containing_codes,
    _filter_name,
    _meta_class_objects,
    _number,
    _source_id,
    _values,
)
from .sources.estat import EStatClient

TABLE_INDUSTRY = "0004040080"  # 4-2, industry small class x organization
TABLE_SIZE = "0004040081"      # 4-3, industry small class x organization x employee size
TABLE_SALES = "0004040087"     # 15, industry large class x HQ/branch, sales

INDUSTRIES = {
    "construction": ("建設業", "建設業"),
    "manufacturing": ("製造業", "製造業"),
    "information": ("情報通信業", "情報通信業"),
    "wholesale_retail": ("卸売業，小売業", "卸売・小売業"),
    "finance": ("金融業，保険業", "金融・保険業"),
    "professional": ("学術研究，専門・技術サービス業", "学術・専門技術サービス業"),
    "accommodation_food": ("宿泊業，飲食サービス業", "宿泊・飲食サービス業"),
    "education": ("教育，学習支援業", "教育・学習支援業"),
    "medical_welfare": ("医療，福祉", "医療・福祉"),
}


def _norm(text: str) -> str:
    return str(text).replace(" ", "").replace("　", "").replace(",", "，").strip()


def _code(mapping: Mapping[str, str], predicate: Callable[[str], bool]) -> str | None:
    for code, label in mapping.items():
        if predicate(str(label)):
            return str(code)
    return None


def _dimension_by_labels(classes: Mapping[str, Mapping[str, str]], required: tuple[str, ...]) -> str:
    best: tuple[int, str] | None = None
    for dim_id, mapping in classes.items():
        labels = [_norm(label) for label in mapping.values()]
        score = sum(any(_norm(token) == label for label in labels) for token in required)
        if score and (best is None or score > best[0]):
            best = (score, dim_id)
    if not best:
        raise ValueError(f"dimension not found for labels: {required}")
    return best[1]


def _total_code(mapping: Mapping[str, str], *tokens: str) -> str | None:
    normalized = {str(code): _norm(label) for code, label in mapping.items()}
    preferred = ["総数", "全産業（S_公務を除く）", "全産業(S_公務を除く)", "全産業", "総数（経営組織）", "総数(経営組織)"]
    for wanted in (*tokens, *preferred):
        wanted_n = _norm(wanted)
        for code, label in normalized.items():
            if label == wanted_n:
                return code
    if len(mapping) == 1:
        return str(next(iter(mapping)))
    return None


def _seed(conn) -> None:
    datasets = [
        ("estat_economic_census_2024_industry", "政府統計の総合窓口 e-Stat", TABLE_INDUSTRY, "economy", "2024年経済センサス 産業別事業所・従業者", "2024", "municipality", "extended", 1, "民営事業所。雇用者のいない個人経営事業所を除く。"),
        ("estat_economic_census_2024_size", "政府統計の総合窓口 e-Stat", TABLE_SIZE, "economy", "2024年経済センサス 従業者規模別事業所", "2024", "municipality", "extended", 1, "民営事業所。雇用者のいない個人経営事業所を除く。"),
        ("estat_economic_census_2024_sales", "政府統計の総合窓口 e-Stat", TABLE_SALES, "economy", "2024年経済センサス 売上（収入）金額", "2024", "municipality", "extended", 1, "売上は産業により意味・会計処理が異なるため比較は参考値。"),
    ]
    conn.executemany(
        """
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,notes=excluded.notes
        """,
        datasets,
    )
    definitions = [
        ("economy2024.establishments", "economy", "2024民営事業所数", "事業所", "higher", "ward", "estat_economic_census_2024_industry", 1, "全産業（公務除く）の民営事業所数"),
        ("economy2024.employees", "economy", "2024民営事業所従業者数", "人", "higher", "ward", "estat_economic_census_2024_industry", 1, "全産業（公務除く）の従業者数"),
        ("economy2024.regular_employees", "economy", "2024常用雇用者数", "人", "neutral", "ward", "estat_economic_census_2024_industry", 1, "全産業（公務除く）の常用雇用者数"),
        ("economy2024.regular_employee_share", "economy", "常用雇用者比率", "%", "neutral", "ward", "estat_economic_census_2024_industry", 1, "常用雇用者数÷従業者数"),
        ("economy2024.employees_per_establishment", "economy", "1事業所当たり従業者数（2024）", "人/事業所", "neutral", "ward", "estat_economic_census_2024_industry", 1, "従業者数÷事業所数"),
        ("economy2024.establishments_50plus_share", "economy", "従業者50人以上事業所比率", "%", "neutral", "ward", "estat_economic_census_2024_size", 1, "従業者規模50人以上の事業所数÷従業者規模総数"),
        ("economy2024.sales", "economy", "2024売上（収入）金額", "百万円", "neutral", "ward", "estat_economic_census_2024_sales", 1, "全産業（公務除く）の売上（収入）金額"),
        ("economy2024.sales_per_employee", "economy", "従業者1人当たり売上", "百万円/人", "neutral", "ward", "estat_economic_census_2024_sales", 1, "売上（収入）金額÷従業者数。産業構成差に注意。"),
    ]
    for slug, (_, label) in INDUSTRIES.items():
        definitions.extend([
            (f"economy2024.{slug}_establishment_share", "economy", f"{label}事業所比率", "%", "neutral", "ward", "estat_economic_census_2024_industry", 1, f"全産業事業所数に占める{label}の比率"),
            (f"economy2024.{slug}_employee_share", "economy", f"{label}従業者比率", "%", "neutral", "ward", "estat_economic_census_2024_industry", 1, f"全産業従業者数に占める{label}の比率"),
        ])
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        definitions,
    )


def _write(conn, area_id: str, key: str, value: float | None, source_id: int, note: str) -> int:
    upsert_metric(
        conn,geo_id=f"ward:{area_id}",metric_key=key,period="2024",value=value,
        sample_size=1,source_id=source_id,metric_version=METRIC_VERSION,
        quality_grade="A",source_year="2024",notes=note,
    )
    return 1


def _fetch_industry(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(TABLE_INDUSTRY)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    item_dim = _dimension_by_labels(classes, ("事業所数", "従業者数"))
    industry_dim = _dimension_by_labels(classes, ("全産業（S_公務を除く）", "製造業", "情報通信業"))
    item_map = classes[item_dim]
    industry_map = classes[industry_dim]
    item_codes = {
        "establishments": _code(item_map, lambda label: _norm(label) == "事業所数"),
        "employees": _code(item_map, lambda label: _norm(label) in {"従業者数", "従業者数_男女計"}),
        "regular": _code(item_map, lambda label: "常用雇用者" in _norm(label)),
    }
    total_industry = _total_code(industry_map, "全産業（S_公務を除く）")
    industry_codes = {slug: _code(industry_map, lambda label, wanted=name: _norm(label) == _norm(wanted)) for slug, (name, _) in INDUSTRIES.items()}
    selected_industries = [code for code in [total_industry, *industry_codes.values()] if code]
    selected_items = [code for code in item_codes.values() if code]
    params: dict[str, Any] = {
        _filter_name(area_dim): ",".join(area_ids),
        _filter_name(item_dim): ",".join(selected_items),
        _filter_name(industry_dim): ",".join(selected_industries),
        "metaGetFlg": "Y","cntGetFlg": "N",
    }
    for dim_id, mapping in classes.items():
        if dim_id in {area_dim, item_dim, industry_dim}:
            continue
        code = _total_code(mapping)
        if code:
            params[_filter_name(dim_id)] = code
    payload = client.get_stats_data_all(TABLE_INDUSTRY, params, max_rows=10000)
    source_id = _source_id(conn,title="2024年経済センサス 産業別事業所・従業者",dataset_id=TABLE_INDUSTRY,payload=payload)
    saved: dict[tuple[str, str, str], float] = {}
    reverse_items = {code: key for key, code in item_codes.items() if code}
    reverse_industry = {code: slug for slug, code in industry_codes.items() if code}
    if total_industry:
        reverse_industry[total_industry] = "total"
    for row in _values(payload):
        area_id = str(row.get(f"@{area_dim}") or "")
        item = reverse_items.get(str(row.get(f"@{item_dim}") or ""))
        industry = reverse_industry.get(str(row.get(f"@{industry_dim}") or ""))
        number = _number(row.get("$"))
        if area_id in area_ids and item and industry and number is not None:
            saved[(area_id, industry, item)] = number
    written = 0
    for area_id in area_ids:
        establishments = saved.get((area_id,"total","establishments"))
        employees = saved.get((area_id,"total","employees"))
        regular = saved.get((area_id,"total","regular"))
        for key, value in (
            ("economy2024.establishments",establishments),
            ("economy2024.employees",employees),
            ("economy2024.regular_employees",regular),
            ("economy2024.regular_employee_share", regular / employees * 100 if regular is not None and employees else None),
            ("economy2024.employees_per_establishment", employees / establishments if employees is not None and establishments else None),
        ):
            written += _write(conn,area_id,key,round(value,3) if value is not None else None,source_id,"2024年経済センサス‐基礎調査 4-2。民営事業所、公務除く。")
        for slug in INDUSTRIES:
            sector_est = saved.get((area_id,slug,"establishments"))
            sector_emp = saved.get((area_id,slug,"employees"))
            written += _write(conn,area_id,f"economy2024.{slug}_establishment_share",round(sector_est / establishments * 100,3) if sector_est is not None and establishments else None,source_id,"産業別事業所数÷全産業事業所数。")
            written += _write(conn,area_id,f"economy2024.{slug}_employee_share",round(sector_emp / employees * 100,3) if sector_emp is not None and employees else None,source_id,"産業別従業者数÷全産業従業者数。")
    return written


def _size_lower_bound(label: str) -> int | None:
    text = _norm(label)
    if "総数" in text or "全規模" in text:
        return None
    match = re.search(r"(\d+)人", text)
    return int(match.group(1)) if match else None


def _fetch_size(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta = client.get_meta_info(TABLE_SIZE)
    classes = _class_map(_meta_class_objects(meta))
    area_dim = _dimension_containing_codes(classes, area_ids)
    item_dim = _dimension_by_labels(classes, ("事業所数", "従業者数"))
    industry_dim = _dimension_by_labels(classes, ("全産業（S_公務を除く）", "製造業"))
    size_dim = None
    for dim_id, mapping in classes.items():
        if dim_id in {area_dim,item_dim,industry_dim}:
            continue
        if sum("人" in str(label) and re.search(r"\d", str(label)) is not None for label in mapping.values()) >= 3:
            size_dim = dim_id
            break
    if size_dim is None:
        raise ValueError("employee-size dimension not found")
    establishment_code = _code(classes[item_dim],lambda label: _norm(label)=="事業所数")
    total_industry = _total_code(classes[industry_dim],"全産業（S_公務を除く）")
    total_size = _total_code(classes[size_dim],"総数")
    if not establishment_code or not total_industry:
        return 0
    params: dict[str,Any] = {
        _filter_name(area_dim): ",".join(area_ids),_filter_name(item_dim): establishment_code,
        _filter_name(industry_dim): total_industry,_filter_name(size_dim): ",".join(classes[size_dim].keys()),
        "metaGetFlg":"Y","cntGetFlg":"N",
    }
    for dim_id,mapping in classes.items():
        if dim_id in {area_dim,item_dim,industry_dim,size_dim}: continue
        code=_total_code(mapping)
        if code: params[_filter_name(dim_id)]=code
    payload=client.get_stats_data_all(TABLE_SIZE,params,max_rows=5000)
    source_id=_source_id(conn,title="2024年経済センサス 従業者規模別事業所",dataset_id=TABLE_SIZE,payload=payload)
    values: dict[tuple[str,str],float]={}
    for row in _values(payload):
        area_id=str(row.get(f"@{area_dim}") or ""); size_code=str(row.get(f"@{size_dim}") or ""); number=_number(row.get("$"))
        if area_id in area_ids and number is not None: values[(area_id,size_code)]=number
    written=0
    for area_id in area_ids:
        denominator=values.get((area_id,total_size)) if total_size else None
        large=sum(value for (aid,code),value in values.items() if aid==area_id and (_size_lower_bound(classes[size_dim].get(code,"")) or 0)>=50)
        share=large/denominator*100 if denominator else None
        written+=_write(conn,area_id,"economy2024.establishments_50plus_share",round(share,3) if share is not None else None,source_id,"2024年経済センサス‐基礎調査 4-3。従業者規模50人以上の事業所。")
    return written


def _fetch_sales(client: EStatClient, conn, area_ids: list[str]) -> int:
    meta=client.get_meta_info(TABLE_SALES); classes=_class_map(_meta_class_objects(meta))
    area_dim=_dimension_containing_codes(classes,area_ids)
    item_dim=_dimension_by_labels(classes,("事業所数","従業者数","売上（収入）金額"))
    industry_dim=_dimension_by_labels(classes,("全産業（S_公務を除く）","製造業"))
    item_codes={
        "employees":_code(classes[item_dim],lambda label:_norm(label) in {"従業者数","従業者数_男女計"}),
        "sales":_code(classes[item_dim],lambda label:"売上" in _norm(label) and "金額" in _norm(label)),
    }
    total_industry=_total_code(classes[industry_dim],"全産業（S_公務を除く）")
    if not total_industry or not item_codes["sales"]: return 0
    params: dict[str,Any]={_filter_name(area_dim):",".join(area_ids),_filter_name(item_dim):",".join(code for code in item_codes.values() if code),_filter_name(industry_dim):total_industry,"metaGetFlg":"Y","cntGetFlg":"N"}
    for dim_id,mapping in classes.items():
        if dim_id in {area_dim,item_dim,industry_dim}: continue
        code=_total_code(mapping)
        if code: params[_filter_name(dim_id)]=code
    payload=client.get_stats_data_all(TABLE_SALES,params,max_rows=5000)
    source_id=_source_id(conn,title="2024年経済センサス 売上（収入）金額",dataset_id=TABLE_SALES,payload=payload)
    reverse={code:key for key,code in item_codes.items() if code}; values:dict[tuple[str,str],float]={}
    for row in _values(payload):
        area_id=str(row.get(f"@{area_dim}") or ""); key=reverse.get(str(row.get(f"@{item_dim}") or "")); number=_number(row.get("$"))
        if area_id in area_ids and key and number is not None: values[(area_id,key)]=number
    written=0
    for area_id in area_ids:
        sales=values.get((area_id,"sales")); employees=values.get((area_id,"employees"))
        written+=_write(conn,area_id,"economy2024.sales",sales,source_id,"2024年経済センサス‐基礎調査 表15。売上の産業間比較には注意。")
        written+=_write(conn,area_id,"economy2024.sales_per_employee",round(sales/employees,3) if sales is not None and employees else None,source_id,"売上（収入）金額÷従業者数。産業構成差に注意。")
    return written


def fetch_economic_census_2024(client: EStatClient, conn, area_ids: list[str]) -> int:
    ensure_analysis_schema(conn); _seed(conn)
    return _fetch_industry(client,conn,area_ids)+_fetch_size(client,conn,area_ids)+_fetch_sales(client,conn,area_ids)
