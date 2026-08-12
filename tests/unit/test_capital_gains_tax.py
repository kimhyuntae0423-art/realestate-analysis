"""src/analysis/capital_gains_tax.py — 양도소득세 추정 계산 검증."""
from __future__ import annotations

from src.analysis.capital_gains_tax import capital_gains_tax_man


def test_no_gain_returns_zero_tax():
    out = capital_gains_tax_man(sale_price_man=50000, acquisition_price_man=60000)
    assert out["tax_man"] == 0
    assert out["gain_man"] < 0


def test_sole_home_under_12eok_is_tax_free():
    out = capital_gains_tax_man(
        sale_price_man=100000, acquisition_price_man=50000,
        hold_years=5, residency_years=3, is_sole_home=True,
    )
    assert out["tax_man"] == 0
    assert out["deduction_pct"] == 100.0


def test_sole_home_over_12eok_taxes_only_excess_portion():
    out = capital_gains_tax_man(
        sale_price_man=150000, acquisition_price_man=50000,
        hold_years=10, residency_years=10, is_sole_home=True,
    )
    assert out["tax_man"] > 0
    # 전액 과세(무주택자 다주택 케이스)보다는 세금이 적어야 함 (12억 초과분만 과세)
    full_taxable = capital_gains_tax_man(
        sale_price_man=150000, acquisition_price_man=50000,
        hold_years=10, residency_years=10, is_sole_home=False,
    )
    assert out["tax_man"] < full_taxable["tax_man"]


def test_short_term_hold_uses_penal_rate_not_progressive():
    under_1y = capital_gains_tax_man(
        sale_price_man=100000, acquisition_price_man=50000,
        hold_years=0.5, is_sole_home=False,
    )
    assert "단기보유" in under_1y["note"]
    assert under_1y["tax_man"] > 0


def test_multihome_surcharge_increases_tax():
    base = capital_gains_tax_man(
        sale_price_man=100000, acquisition_price_man=50000,
        hold_years=5, is_sole_home=False, multihome_surcharge=False,
    )
    surcharged = capital_gains_tax_man(
        sale_price_man=100000, acquisition_price_man=50000,
        hold_years=5, is_sole_home=False, multihome_surcharge=True,
    )
    assert surcharged["tax_man"] > base["tax_man"]
