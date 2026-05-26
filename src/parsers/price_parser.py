"""국토부 API 응답 item -> DB row dict 변환

API 필드명은 시기마다 약간 변동되므로 alias 매핑을 통해 흡수.
금액은 쉼표/공백 포함 문자열 -> int (만원 단위).
"""
from __future__ import annotations
from datetime import date

PYEONG = 3.305785  # 1평 ≈ 3.3058 m²


def _g(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            v = d[k]
            if isinstance(v, str):
                v = v.strip()
                if v == "":
                    continue
            return v
    return default


def _to_int(v, default=0) -> int:
    if v is None:
        return default
    s = str(v).replace(",", "").replace(" ", "").strip()
    if s == "" or s == "-":
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def _to_float(v, default=0.0) -> float:
    if v is None:
        return default
    s = str(v).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return default


def parse_trade_item(item: dict, region_code: str) -> dict:
    y = _to_int(_g(item, "dealYear"))
    m = _to_int(_g(item, "dealMonth"))
    d = _to_int(_g(item, "dealDay"))
    deal_date = date(y, m, d)

    apt_name = _g(item, "aptNm", "apartmentName", default="") or ""
    dong = _g(item, "umdNm", "dong", default="") or ""
    jibun = _g(item, "jibun", default="") or ""
    road_name = _g(item, "roadNm", default="") or ""
    area = _to_float(_g(item, "excluUseAr", "area"))
    floor = _to_int(_g(item, "floor"))
    build_year = _to_int(_g(item, "buildYear"))
    amount = _to_int(_g(item, "dealAmount", "tradeAmount"))

    ppp = int(amount / (area / PYEONG)) if area > 0 and amount > 0 else 0

    return {
        "region_code": region_code,
        "deal_year": y, "deal_month": m, "deal_day": d,
        "deal_date": deal_date,
        "apt_name": apt_name.strip(),
        "dong": dong.strip(),
        "jibun": str(jibun).strip(),
        "road_name": road_name.strip(),
        "area_m2": area,
        "floor": floor,
        "build_year": build_year,
        "deal_amount": amount,
        "price_per_pyeong": ppp,
        "cancel_deal_type": _g(item, "cdealType", default="") or "",
        "cancel_deal_day": _g(item, "cdealDay", default="") or "",
    }


def parse_rent_item(item: dict, region_code: str) -> dict:
    y = _to_int(_g(item, "dealYear"))
    m = _to_int(_g(item, "dealMonth"))
    d = _to_int(_g(item, "dealDay"))
    deal_date = date(y, m, d)

    return {
        "region_code": region_code,
        "deal_year": y, "deal_month": m, "deal_day": d,
        "deal_date": deal_date,
        "apt_name": (_g(item, "aptNm", default="") or "").strip(),
        "dong": (_g(item, "umdNm", default="") or "").strip(),
        "jibun": str(_g(item, "jibun", default="") or "").strip(),
        "area_m2": _to_float(_g(item, "excluUseAr")),
        "floor": _to_int(_g(item, "floor")),
        "build_year": _to_int(_g(item, "buildYear")),
        "deposit": _to_int(_g(item, "deposit")),
        "monthly_rent": _to_int(_g(item, "monthlyRent")),
        "contract_type": _g(item, "contractType", default="") or "",
    }
