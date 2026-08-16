from contextlib import contextmanager
from datetime import date
import pandas as pd
from sqlalchemy import select, and_

from src.database.models import SessionLocal, AptTrade, AptRent, CollectionLog, PopulationFlow, engine
from src.utils.logger import get_logger

log = get_logger(__name__)


def _make_upsert(model, rows: list[dict]):
    """DB 방언에 따라 ON CONFLICT DO NOTHING INSERT 반환."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model).values(rows).on_conflict_do_nothing()


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# SQLite 바인드 파라미터 상한 보수적 값. 빌드에 따라 999(구버전)~32766(3.32+)로
# 다르므로, 거래량 많은 지역·월(예: 강남구 특정월 전월세 2천건+)에서 한 INSERT문에
# rows*컬럼수 파라미터를 다 넣으면 "too many SQL variables"로 배치 전체가 조용히
# 실패할 수 있어(실제로 5년 백필 중 39건 발생·확인됨) 청크로 나눠 커밋한다.
_MAX_SQL_VARIABLES = 900


def _chunked(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _bulk_upsert(session, model, rows: list[dict]) -> int:
    if not rows:
        return 0
    chunk_size = max(1, _MAX_SQL_VARIABLES // len(rows[0]))
    total = 0
    for chunk in _chunked(rows, chunk_size):
        stmt = _make_upsert(model, chunk)
        result = session.execute(stmt)
        total += result.rowcount if result.rowcount is not None else 0
    return total


def upsert_trades(rows: list[dict]) -> int:
    with session_scope() as s:
        n = _bulk_upsert(s, AptTrade, rows)
        log.info("apt_trade upsert: %d rows", n)
        return n


def upsert_rents(rows: list[dict]) -> int:
    with session_scope() as s:
        n = _bulk_upsert(s, AptRent, rows)
        log.info("apt_rent upsert: %d rows", n)
        return n


def upsert_population_flow(rows: list[dict]) -> int:
    with session_scope() as s:
        n = _bulk_upsert(s, PopulationFlow, rows)
        log.info("population_flow upsert: %d rows", n)
        return n


def log_collection(source: str, region_code: str, ym: str,
                   fetched: int, inserted: int, status: str, error: str = ""):
    with session_scope() as s:
        s.add(CollectionLog(
            source=source, region_code=region_code, year_month=ym,
            rows_fetched=fetched, rows_inserted=inserted,
            status=status, error=error[:500],
        ))


def fetch_trades_df(region_code: str | None = None,
                    date_from: date | None = None,
                    date_to: date | None = None,
                    apt_name: str | None = None) -> pd.DataFrame:
    q = select(AptTrade)
    conds = []
    if region_code:
        conds.append(AptTrade.region_code == region_code)
    if date_from:
        conds.append(AptTrade.deal_date >= date_from)
    if date_to:
        conds.append(AptTrade.deal_date <= date_to)
    if apt_name:
        conds.append(AptTrade.apt_name.like(f"%{apt_name}%"))
    if conds:
        q = q.where(and_(*conds))
    with engine.connect() as conn:
        df = pd.read_sql(q, conn)
    return df


def fetch_rents_df(region_code: str | None = None,
                   date_from: date | None = None,
                   date_to: date | None = None,
                   apt_name: str | None = None,
                   jeonse_only: bool = False) -> pd.DataFrame:
    q = select(AptRent)
    conds = []
    if region_code:
        conds.append(AptRent.region_code == region_code)
    if date_from:
        conds.append(AptRent.deal_date >= date_from)
    if date_to:
        conds.append(AptRent.deal_date <= date_to)
    if apt_name:
        conds.append(AptRent.apt_name.like(f"%{apt_name}%"))
    if jeonse_only:
        conds.append(AptRent.monthly_rent == 0)
    if conds:
        q = q.where(and_(*conds))
    with engine.connect() as conn:
        df = pd.read_sql(q, conn)
    return df
