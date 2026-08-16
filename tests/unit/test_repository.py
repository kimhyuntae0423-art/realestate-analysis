"""src/database/repository.py — CRUD/조회 계층 검증 (격리된 테스트 DB, conftest 참고)."""
from __future__ import annotations

from datetime import date

import pandas as pd

from src.database.repository import (
    upsert_trades, upsert_rents, upsert_population_flow,
    fetch_trades_df, fetch_rents_df, log_collection,
)
from src.database.models import CollectionLog, PopulationFlow, SessionLocal


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


def test_upsert_trades_large_batch_does_not_hit_sqlite_variable_limit():
    # 5년 백필 실행 중 실제로 발생한 버그 재현: 컬럼수 x 행수가 SQLite 바인드
    # 파라미터 상한을 넘으면 INSERT문 전체가 "too many SQL variables"로 실패해
    # 그 배치의 모든 행이 조용히 유실됐음 (repository._bulk_upsert가 청크 분할 안 함).
    # 청크 크기(_MAX_SQL_VARIABLES=900) 경계를 넘나드는 3000행으로 회귀 검증.
    rows = [_trade_row(apt=f"단지{i}", floor=i % 30 + 1) for i in range(3000)]
    n = upsert_trades(rows)
    assert n == 3000
    assert len(fetch_trades_df(region_code="11680")) == 3000

    # 동일 배치 재삽입 -> 청크 경계와 무관하게 전부 중복 판정(0건)돼야 함
    assert upsert_trades(rows) == 0


def _population_row(region="11680", d=date(2025, 6, 1), inflow=100, outflow=80, source="test"):
    return {"region_code": region, "flow_date": d, "inflow": inflow, "outflow": outflow,
            "net_inflow": inflow - outflow, "source": source}


def test_upsert_population_flow_deduplicates_by_region_and_date():
    row = _population_row()
    n1 = upsert_population_flow([row])
    n2 = upsert_population_flow([row])  # 동일 (region_code, flow_date) 재삽입 -> 무시
    assert n1 == 1
    assert n2 == 0
    with SessionLocal() as s:
        assert s.query(PopulationFlow).count() == 1


def test_upsert_population_flow_empty_list_is_noop():
    assert upsert_population_flow([]) == 0


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
