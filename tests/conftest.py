"""pytest 공통 설정 및 fixture.

주의: src.database.models 는 import 시점에 config.settings.DATABASE_URL 로
엔진을 바인딩하고 init_db()까지 실행한다. 실제 운영 DB(data/processed/realestate.db)를
건드리지 않도록, 어떤 src.* 모듈보다도 먼저 이 파일에서 DATABASE_URL을 임시 파일로 덮어쓴다.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="realestate_test_")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

import pandas as pd
import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    yield
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """실수로 실제 외부 API(카카오/국토부 등)를 호출하지 않도록 기본 차단.

    .env에 실제 API 키가 들어있어 목킹을 빠뜨리면 조용히 실네트워크를 태울 수 있다.
    collectors 테스트(5단계)처럼 의도적으로 HTTP를 다루는 테스트는 그 안에서
    requests.Session.get/request를 직접 mocker.patch 하면 이 차단을 덮어쓴다.
    """
    import requests

    def _blocked(*args, **kwargs):
        raise RuntimeError(
            "테스트에서 실제 네트워크 호출이 시도되었습니다. "
            "requests.Session.get/request를 mocker로 패치했는지 확인하세요."
        )

    monkeypatch.setattr(requests.sessions.Session, "get", _blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)


@pytest.fixture(autouse=True)
def _clean_tables():
    """각 테스트 전후로 테스트 DB 테이블을 비운다 (테스트 간 격리)."""
    from src.database.models import Base, engine

    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def sample_trade_df() -> pd.DataFrame:
    """gap/price_trend/recommend 등에서 공통으로 쓰는 매매 실거래 표본."""
    rows = [
        {"region_code": "11680", "deal_date": date(2025, 1, 15), "apt_name": "래미안A",
         "area_m2": 84.9, "floor": 10, "build_year": 2015, "deal_amount": 150000},
        {"region_code": "11680", "deal_date": date(2025, 3, 20), "apt_name": "래미안A",
         "area_m2": 84.9, "floor": 5, "build_year": 2015, "deal_amount": 155000},
        {"region_code": "11680", "deal_date": date(2025, 6, 10), "apt_name": "래미안A",
         "area_m2": 84.9, "floor": 15, "build_year": 2015, "deal_amount": 162000},
        {"region_code": "11650", "deal_date": date(2025, 2, 5), "apt_name": "자이B",
         "area_m2": 59.9, "floor": 8, "build_year": 2018, "deal_amount": 110000},
    ]
    for r in rows:
        d = r["deal_date"]
        r["deal_year"], r["deal_month"], r["deal_day"] = d.year, d.month, d.day
    return pd.DataFrame(rows)


@pytest.fixture
def sample_rent_df() -> pd.DataFrame:
    """gap_analysis 등에서 쓰는 전월세 실거래 표본 (전세만, monthly_rent=0)."""
    rows = [
        {"region_code": "11680", "deal_date": date(2025, 1, 10), "apt_name": "래미안A",
         "area_m2": 84.9, "floor": 3, "deposit": 90000, "monthly_rent": 0},
        {"region_code": "11680", "deal_date": date(2025, 4, 1), "apt_name": "래미안A",
         "area_m2": 84.9, "floor": 7, "deposit": 95000, "monthly_rent": 0},
        {"region_code": "11650", "deal_date": date(2025, 2, 1), "apt_name": "자이B",
         "area_m2": 59.9, "floor": 2, "deposit": 70000, "monthly_rent": 0},
    ]
    for r in rows:
        d = r["deal_date"]
        r["deal_year"], r["deal_month"], r["deal_day"] = d.year, d.month, d.day
    return pd.DataFrame(rows)
