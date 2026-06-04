"""양도소득세 추정 계산 (단순화, 2026 기준)
모든 금액 만원.

주의: 실제 세액은 개인 상황에 따라 크게 다름 (공동명의, 장특공제 세부, 주택 수 판단 등).
      반드시 세무사 상담 후 확인.
"""
from __future__ import annotations


def _progressive_tax(gain_man: float) -> float:
    """양도소득세 기본세율 누진과세 (소득세법 §55 기준)."""
    brackets = [
        (1400,         0.06),
        (5000,         0.15),
        (8800,         0.24),
        (15000,        0.35),
        (30000,        0.38),
        (45000,        0.40),
        (100000,       0.42),
        (float("inf"), 0.45),
    ]
    tax = 0.0
    prev = 0.0
    for limit, rate in brackets:
        if gain_man <= prev:
            break
        taxable = min(gain_man, limit) - prev
        tax += taxable * rate
        prev = limit
    return tax


def capital_gains_tax_man(
    sale_price_man: float,
    acquisition_price_man: float,
    acquisition_cost_man: float = 0.0,
    hold_years: float = 5.0,
    residency_years: float = 0.0,
    is_sole_home: bool = True,
    is_adjusted_area: bool = True,
    multihome_surcharge: bool = False,
) -> dict:
    """양도소득세 추정 (만원).

    Args:
        sale_price_man: 매도가
        acquisition_price_man: 취득가
        acquisition_cost_man: 취득 부대비용 (공제 가능)
        hold_years: 보유기간 (년)
        residency_years: 실거주 기간 (년)
        is_sole_home: 1세대 1주택 여부
        is_adjusted_area: 조정대상지역 (서울·수도권 대부분)
        multihome_surcharge: 다주택 중과 적용 여부 (2026 배제 연장 중이나 선택 가능)

    Returns:
        tax_man, gain_man, note 등 포함 dict
    """
    gain = sale_price_man - acquisition_price_man - acquisition_cost_man
    if gain <= 0:
        return {
            "tax_man": 0,
            "gain_man": round(gain),
            "taxable_gain_man": 0,
            "deduction_pct": 0.0,
            "note": "양도차익 없음 (손실 또는 보합)",
        }

    # ── 1세대 1주택 비과세 판단 ──────────────────────────────
    if is_sole_home:
        hold_ok = hold_years >= 2
        residence_ok = (residency_years >= 2) if is_adjusted_area else hold_ok
        if hold_ok and residence_ok:
            if sale_price_man <= 120_000:
                return {
                    "tax_man": 0,
                    "gain_man": round(gain),
                    "taxable_gain_man": 0,
                    "deduction_pct": 100.0,
                    "note": "1세대1주택 비과세 (12억 이하 전액)",
                }
            # 12억 초과분만 과세
            taxable_gain = gain * (sale_price_man - 120_000) / sale_price_man
        else:
            taxable_gain = gain
    else:
        taxable_gain = gain

    # ── 장기보유특별공제 ─────────────────────────────────────
    if is_sole_home and hold_years >= 2 and residency_years >= 2:
        # 1주택 거주자: 보유 1년당 4% + 거주 1년당 4%, 최대 80%
        deduction_pct = min((int(hold_years) * 4 + int(residency_years) * 4) / 100, 0.80)
    elif hold_years >= 3:
        # 일반: 3년 6% → 이후 연 2% 추가, 최대 30%
        deduction_pct = min(0.06 + (int(hold_years) - 3) * 0.02, 0.30)
    else:
        deduction_pct = 0.0

    after_deduction = taxable_gain * (1 - deduction_pct)

    # 양도소득 기본공제 250만원
    after_basic = max(0.0, after_deduction - 250)

    # 기본세율
    base_tax = _progressive_tax(after_basic)

    # 다주택 중과 (+20%, 조정지역 2주택)
    surcharge = after_basic * 0.20 if (multihome_surcharge and not is_sole_home) else 0.0

    # 지방소득세 10%
    total_tax = (base_tax + surcharge) * 1.10

    note = "1세대1주택 (12억 초과분 과세)" if is_sole_home else "다주택"
    if multihome_surcharge and not is_sole_home:
        note += " + 중과(+20%)"

    return {
        "tax_man": round(total_tax),
        "gain_man": round(gain),
        "taxable_gain_man": round(after_basic),
        "deduction_pct": round(deduction_pct * 100, 1),
        "base_tax_man": round(base_tax),
        "surcharge_man": round(surcharge),
        "note": note,
    }
