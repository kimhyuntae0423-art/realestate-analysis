from contextlib import contextmanager
from datetime import date
from typing import Iterable
import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.database.models import SessionLocal, AptTrade, AptRent, CollectionLog, engine
from src.utils.logger import get_logger

log = get_logger(__name__)


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


def _bulk_upsert(session, model, rows: list[dict]) -> int:
    """SQLite ON CONFLICT DO NOTHING - 중복 무시. inserted 행수 반환은 근사치."""
    if not rows:
        return 0
    before = session.execute(select(model.id).limit(1)).all()
    stmt = sqlite_insert(model).values(rows).on_conflict_do_nothing()
    result = session.execute(stmt)
    return result.rowcount if result.rowcount is not None else 0


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
