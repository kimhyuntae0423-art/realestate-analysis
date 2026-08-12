"""src/database/models.py — 스키마 무결성(NOT NULL, UNIQUE) 검증."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from src.database.models import AptTrade, SessionLocal, init_db


def test_init_db_is_idempotent():
    init_db()
    init_db()  # 두 번 호출해도 에러 없어야 함


def test_apt_trade_requires_deal_amount():
    with SessionLocal() as s:
        s.add(AptTrade(
            region_code="11680", deal_year=2025, deal_month=6, deal_day=1,
            deal_date=date(2025, 6, 1), apt_name="A", area_m2=84.9,
            deal_amount=None,
        ))
        with pytest.raises(IntegrityError):
            s.commit()


def test_apt_trade_unique_constraint_blocks_exact_duplicate():
    def _row():
        return AptTrade(
            region_code="11680", deal_year=2025, deal_month=6, deal_day=1,
            deal_date=date(2025, 6, 1), apt_name="A", area_m2=84.9,
            floor=5, deal_amount=100000,
        )

    with SessionLocal() as s:
        s.add(_row())
        s.commit()

    with SessionLocal() as s:
        s.add(_row())
        with pytest.raises(IntegrityError):
            s.commit()
