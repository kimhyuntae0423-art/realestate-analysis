"""처분·매수 전략 플래너 — 탭 공용 컨텍스트.

`portfolio.py` (1065줄 단일 함수) 분리 시 탭들이 공유하던 지역변수를
담아 넘기기 위한 컨테이너. 계산 로직은 없다.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


def _eok(v: float) -> str:
    return f"{v/10000:.2f}억" if abs(v) >= 10000 else f"{v:,.0f}만"


@dataclass
class PortfolioContext:
    """`시나리오 분석 실행` 이후 5개 탭이 공유하는 값."""
    result: dict
    props_mine: list
    props_partner: list
    target: Any
    rec: Any
    order: list

    # _port_inputs 에서 복원한 입력값
    t_min: float
    t_max: float
    t_kb: float
    t_close: Any
    income: float
    ex_pay: float
    int_rent: float
    cash_seed: float
    my_cash_seed: float
    partner_cash_seed: float
    household_homes: int
    buy_strategy: str
