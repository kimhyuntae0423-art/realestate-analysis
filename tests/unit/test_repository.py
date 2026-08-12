"""src/database/repository.py — CRUD/조회 계층 검증 (격리된 테스트 DB, conftest 참고)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.database.repository import (
    upsert_trades, upsert_rents, fetch_trades_df, fetch_rents_df, log_collection,
)
from src.database.models import CollectionLog, SessionLocal


def _trade_row(region="11680", d=date(2025, 6, 1), apt="A", amount=100000, area=84.9, floor=5):
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "floor": floor, "deal_amount": amount}


def _rent_row(region="11680", d=date(2025, 6, 1), apt="A", deposit=70000,
              monthly_rent=0, area=84.9, floor=5):
    return {"region_code": region, "deal_date": d, "deal_year": d.year,
            "deal_month": d.month, "deal_day": d.day, "apt_name": apt,
            "area_m2": area, "floor": floor, "deposit": deposit, "monthly_rent": monthly_rent}


def test_upsert_trades_deduplicates_identical_rows():
    row = _trade_row()
    n1 = upsert_trades([row])
    n2 = upsert_trades([row])  # 완전히 동일한 행 재삽입 → ON CONFLICT DO NOTHING
    assert n1 == 1
    assert n2 == 0
    df = fetch_trades_df(region_code="11680")
    assert len(df) == 1


def test_upsert_trades_empty_list_is_noop():
    assert upsert_trades([]) == 0


def test_fetch_trades_df_filters_by_region_and_date_range():
    upsert_trades([
        _trade_row(region="11680", d=date(2025, 1, 1), apt="A"),
        _trade_row(region="11680", d=date(2025, 6, 1), apt="B"),
        _trade_row(region="11650", d=date(2025, 6, 1), apt="C"),
    ])
    by_region = fetch_trades_df(region_code="11680")
    assert set(by_region["apt_name"]) == {"A", "B"}

    by_date = fetch_trades_df(region_code="11680",
                               date_from=date(2025, 3, 1), date_to=date(2025, 12, 31))
    assert set(by_date["apt_name"]) == {"B"}


def test_fetch_trades_df_apt_name_like_filter():
    upsert_trades([
        _trade_row(apt="래미안강남"),
        _trade_row(apt="자이서초", d=date(2025, 2, 1)),
    ])
    out = fetch_trades_df(apt_name="래미안")
    assert len(out) == 1
    assert out.iloc[0]["apt_name"] == "래미안강남"


def test_fetch_rents_df_jeonse_only_filter():
    upsert_rents([
        _rent_row(apt="전세단지", monthly_rent=0),
        _rent_row(apt="월세단지", monthly_rent=50, d=date(2025, 2, 1)),
    ])
    jeonse = fetch_rents_df(jeonse_only=True)
    assert set(jeonse["apt_name"]) == {"전세단지"}

    all_rents = fetch_rents_df(jeonse_only=False)
    assert set(all_rents["apt_name"]) == {"전세단지", "월세단지"}


def test_log_collection_persists_record():
    log_collection("molit_trade", "11680", "202506", fetched=10, inserted=8, status="ok")
    with SessionLocal() as s:
        rows = s.query(CollectionLog).all()
    assert len(rows) == 1
    assert rows[0].source == "molit_trade"
    assert rows[0].rows_inserted == 8
    assert rows[0].status == "ok"


def test_log_collection_truncates_long_error():
    long_error = "x" * 1000
    log_collection("molit_trade", "11680", "202506", fetched=0, inserted=0,
                    status="fail", error=long_error)
    with SessionLocal() as s:
        row = s.query(CollectionLog).first()
    assert len(row.error) == 500
