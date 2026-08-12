"""0단계 인프라 자체 검증: 테스트 DB가 운영 DB와 분리되는지 확인."""
from __future__ import annotations

import os

from config.settings import ROOT


def test_database_url_is_isolated_from_production():
    prod_db = ROOT / "data" / "processed" / "realestate.db"
    assert str(prod_db) not in os.environ["DATABASE_URL"]


def test_can_write_and_read_trade(sample_trade_df):
    from src.database.repository import upsert_trades, fetch_trades_df

    rows = sample_trade_df.to_dict("records")
    n = upsert_trades(rows)
    assert n == len(rows)

    df = fetch_trades_df(region_code="11680")
    assert len(df) == 3
    assert set(df["apt_name"]) == {"래미안A"}
