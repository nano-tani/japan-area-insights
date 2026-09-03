from __future__ import annotations

# Public datasets that can materially deepen area analysis.  Core datasets that
# already have dedicated importers are listed as well so the UI can expose a
# single lineage/catalog view.
DATASET_CATALOG = [
    # MLIT price / appraisal
    {"dataset_key": "reinfolib_xit001", "provider": "国土交通省 不動産情報ライブラリ", "api_id": "XIT001", "category": "market", "title": "不動産価格（取引価格・成約価格）", "source_vintage": "2005Q3-", "granularity": "transaction", "refresh_mode": "core", "enabled": 1, "notes": "取引属性を含む"},
    {"dataset_key": "reinfolib_xpt002", "provider": "国土交通省 不動産情報ライブラリ", "api_id": "XPT002", "category": "market", "title": "地価公示・地価調査ポイント", "source_vintage": "1995-/1997-", "granularity": "point", "refresh_mode": "core", "enabled": 1, "notes": "駅距離・道路・法規制・供給処理を含む"},
    {"dataset_key": "reinfolib_xct001", "provider": "国土交通省 不動産情報ライブラリ", "api_id": "XCT001", "category": "market", "title": "鑑定評価書情報", "source_vintage": "直近5年", "granularity": "appraisal_point", "refresh_mode": "extended", "enabled": 1, "notes": "鑑定過程の詳細分析用"},
    # Existing population / facilities / transport
    {"dataset_key": "reinfolib_xkt013", "provider": "国土交通省 不動産情報ライブラリ", "api_id": "XKT013", "category": "population", "title": "将来推計人口250mメッシュ", "source_vintage": "R6推計", "granularity": "mesh250", "refresh_mode": "core", "enabled": 1, "notes": None},
    {"dataset_key": "reinfolib_xkt015", "provider": "国土交通省 不動産情報ライブラリ", "api_id": "XKT015", "category": "transport", "title": "駅別乗降客数", "source_vintage": "令和5年度", "granularity": "point", "refresh_mode": "core", "enabled": 1, "notes": None},
    # e-Stat detailed analysis
    {"dataset_key": "estat_migration_in_2025", "provider": "政府統計の総合窓口 e-Stat", "api_id": "0004044293", "category": "migration", "title": "年齢10歳階級・移動前住所地別転入者数（2025）", "source_vintage": "2025", "granularity": "municipality", "refresh_mode": "extended", "enabled": 1, "notes": "移動者（外国人含む）"},
    {"dataset_key": "estat_migration_out_2025", "provider": "政府統計の総合窓口 e-Stat", "api_id": "0004044294", "category": "migration", "title": "年齢10歳階級・移動後住所地別転出者数（2025）", "source_vintage": "2025", "granularity": "municipality", "refresh_mode": "extended", "enabled": 1, "notes": "移動者（外国人含む）"},
    {"dataset_key": "estat_ssds_economy", "provider": "政府統計の総合窓口 e-Stat", "api_id": "0000020103", "category": "economy", "title": "社会・人口統計体系 C 経済基盤", "source_vintage": "年度次", "granularity": "municipality", "refresh_mode": "extended", "enabled": 1, "notes": "課税対象所得・納税義務者数等"},
    {"dataset_key": "estat_ssds_admin", "provider": "政府統計の総合窓口 e-Stat", "api_id": "0000020104", "category": "economy", "title": "社会・人口統計体系 D 行政基盤", "source_vintage": "年度次", "granularity": "municipality", "refresh_mode": "extended", "enabled": 1, "notes": "財政力指数・実質公債費比率等"},
]

# Generic Reinfolib GIS layers.  Dedicated importers remain the source of truth
# for facilities / future population / stations; the layers below are fetched
# by the extended analysis workflow and summarized against 250m mesh centers.
REINFOLIB_SPATIAL_LAYERS = {
    "XKT001": ("urban_planning_area", "urban", "都市計画区域・区域区分", "令和7年度"),
    "XKT002": ("zoning", "urban", "用途地域", "令和7年度"),
    "XKT003": ("location_optimization", "urban", "立地適正化計画", "令和7年度"),
    "XKT004": ("elementary_school_zone", "community", "小学校区", "令和5年度"),
    "XKT005": ("junior_high_school_zone", "community", "中学校区", "令和5年度"),
    "XKT011": ("welfare_facility", "community", "福祉施設", "令和5年度"),
    "XKT014": ("fire_prevention_zone", "urban", "防火・準防火地域", "令和7年度"),
    "XKT016": ("disaster_danger_zone", "hazard", "災害危険区域", "令和3年度"),
    "XKT019": ("natural_park", "environment", "自然公園地域", "平成27年度"),
    "XKT020": ("large_fill", "hazard", "大規模盛土造成地", "令和5年"),
    "XKT021": ("landslide_prevention", "hazard", "地すべり防止地区", "令和3年度"),
    "XKT022": ("steep_slope", "hazard", "急傾斜地崩壊危険区域", "令和3年度"),
    "XKT023": ("district_plan", "urban", "地区計画", "令和7年度"),
    "XKT024": ("high_utilization_district", "urban", "高度利用地区", "令和7年度"),
    "XKT025": ("liquefaction", "hazard", "液状化の発生傾向", "国土交通省都市局"),
    "XKT026": ("flood", "hazard", "洪水浸水想定区域（想定最大規模）", "令和6年度"),
    "XKT027": ("storm_surge", "hazard", "高潮浸水想定区域", "令和6年度"),
    "XKT028": ("tsunami", "hazard", "津波浸水想定", "令和6年度"),
    "XKT029": ("sediment_disaster", "hazard", "土砂災害警戒区域", "令和6年度"),
    "XKT030": ("urban_planning_road", "urban", "都市計画道路", "令和7年度"),
    "XKT031": ("densely_inhabited_district", "urban", "人口集中地区", "2020年度"),
}

METRIC_DEFINITIONS = [
    # market detail
    ("market.transaction_count", "market", "取引件数", "件", "neutral", "ward", "reinfolib_xit001", 1, "対象期間の不動産取引件数"),
    ("market.median_unit_price", "market", "取引単価中央値", "円/㎡", "neutral", "ward", "reinfolib_xit001", 5, "取引価格の平方メートル単価中央値"),
    ("market.median_area_sqm", "market", "取引面積中央値", "㎡", "neutral", "ward", "reinfolib_xit001", 5, "取引対象面積の中央値"),
    ("market.condo_share", "market", "中古マンション取引比率", "%", "neutral", "ward", "reinfolib_xit001", 10, "取引全体に占める中古マンション等の比率"),
    ("market.rc_share", "market", "RC/SRC構造比率", "%", "neutral", "ward", "reinfolib_xit001", 10, "構造情報がある取引のうちRC/SRCの比率"),
    ("market.renovated_share", "market", "改装済み比率", "%", "neutral", "ward", "reinfolib_xit001", 10, "改装情報がある取引のうち改装済みの比率"),
    ("market.median_building_age", "market", "建物年齢中央値", "年", "lower", "ward", "reinfolib_xit001", 10, "取引年から建築年を差し引いた建物年齢の中央値"),
    ("market.median_road_width", "market", "前面道路幅員中央値", "m", "neutral", "ward", "reinfolib_xit001", 5, "前面道路幅員がある取引の中央値"),
    ("market.land_price_station_distance", "market", "地価地点の駅距離中央値", "m", "lower", "ward", "reinfolib_xpt002", 3, "地価公示・地価調査地点から最寄駅までの道路距離中央値"),
    ("market.land_price_far_median", "market", "地価地点の容積率中央値", "%", "neutral", "ward", "reinfolib_xpt002", 3, "地価地点の法定容積率中央値"),
    ("market.land_price_utility_complete_share", "market", "三インフラ整備地点比率", "%", "higher", "ward", "reinfolib_xpt002", 3, "ガス・水道・下水道がすべて有る地価地点の比率"),
    # migration
    ("migration.in_total", "migration", "転入者数", "人", "neutral", "ward", "estat_migration_in_2025", 1, "市区町村への年間転入者数"),
    ("migration.out_total", "migration", "転出者数", "人", "neutral", "ward", "estat_migration_out_2025", 1, "市区町村からの年間転出者数"),
    ("migration.net_total", "migration", "転入超過数", "人", "higher", "ward", "estat_migration_in_2025", 1, "転入者数から転出者数を差し引いた値"),
    ("migration.net_20_39", "migration", "20〜39歳転入超過数", "人", "higher", "ward", "estat_migration_in_2025", 1, "20〜29歳・30〜39歳の転入超過数"),
    ("migration.net_0_9", "migration", "0〜9歳転入超過数", "人", "higher", "ward", "estat_migration_in_2025", 1, "0〜9歳の転入超過数"),
    # economy / administration
    ("economy.taxable_income", "economy", "課税対象所得", "千円", "higher", "ward", "estat_ssds_economy", 1, "社会・人口統計体系 C120110"),
    ("economy.income_taxpayers", "economy", "所得割納税義務者数", "人", "neutral", "ward", "estat_ssds_economy", 1, "社会・人口統計体系 C120120"),
    ("economy.taxable_income_per_taxpayer", "economy", "納税義務者1人当たり課税対象所得", "千円/人", "higher", "ward", "estat_ssds_economy", 1, "課税対象所得を所得割納税義務者数で除した参考指標"),
    ("economy.fiscal_strength_index", "economy", "財政力指数", "指数", "higher", "ward", "estat_ssds_admin", 1, "社会・人口統計体系 D2201"),
    ("economy.real_debt_service_ratio", "economy", "実質公債費比率", "%", "lower", "ward", "estat_ssds_admin", 1, "社会・人口統計体系 D2211"),
    ("economy.future_burden_ratio", "economy", "将来負担比率", "%", "lower", "ward", "estat_ssds_admin", 1, "社会・人口統計体系 D2212"),
]
