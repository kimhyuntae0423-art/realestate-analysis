"""지역별 입주 물량 분석.

수동 등록(config/supply.json) 기반.
공공데이터포털 분양정보 API 자동 수집은 scripts/collect_supply.py 에서 (별도 활용신청 필요).
"""
from __future__ import annotations
import json
from functools import lru_cache

import pandas as pd

from config.settings import ROOT


@lru_cache(maxsize=1)
def _load_supply() -> dict:
    p = ROOT / "config" / "supply.json"
    if not p.exists():
        return {"by_region": {}}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def supply_for_region(region_code: str, lookahead_months: int = 12) -> int:
    """향후 N개월간 입주 예정 총 호수."""
    data = _load_supply().get("by_region", {})
    items = data.get(region_code, {})
    if not items:
        return 0
    today = pd.Timestamp.today().to_period("M").to_timestamp()
    end = today + pd.DateOffset(months=lookahead_months)
    total = 0
    for ym, n in items.items():
        try:
            d = pd.Timestamp(ym + "-01")
        except Exception:
            continue
        if today <= d <= end:
            total += int(n)
    return total


def supply_pressure_score(region_code: str, lookahead_months: int = 12) -> float:
    """입주 압박 점수 (0~100).

    물량이 많을수록 향후 가격 압박 (점수 ↑ = 공급 부담 ↑ = 가격 상승에 불리)
    이 함수는 '공급 부담 지수'이므로 가격 상승 점수에 반대로 작용.
    """
    n = supply_for_region(region_code, lookahead_months)
    # 1000호 = 약 30점, 3000호 = 80점, 5000호+ = 100점
    if n <= 0:
        return 0.0
    return min(100.0, (n / 50))


def supply_table() -> pd.DataFrame:
    """전체 지역 입주물량 표."""
    data = _load_supply().get("by_region", {})
    rows = []
    for code, items in data.items():
        total = sum(int(v) for v in items.values())
        rows.append({
            "region_code": code,
            "total_units": total,
            **{f"공급_{k}": v for k, v in sorted(items.items())},
        })
    return pd.DataFrame(rows).sort_values("total_units", ascending=False).reset_index(drop=True)
