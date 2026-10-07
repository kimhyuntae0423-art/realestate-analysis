"""빈 Supabase 프로젝트에 조회 전용 복제본 스키마를 세운다.

`migrate_to_supabase.py` 는 테이블이 이미 있다고 전제하고 데이터만 밀어넣는다.
프로젝트를 새로 만들었을 때(= 테이블이 하나도 없을 때) 그 앞단을 담당한다.

## 왜 제약을 지우면서 만드는가

`Base.metadata.create_all` 은 models.py 에 정의된 uq_trade / uq_rent 중복방지
제약까지 같이 만든다. 이 둘이 195MB(57+138)를 먹어 무료 한도 500MB 를 넘긴 것이
2026-09-10 사고였다. 조회에는 안 쓰이고 upsert 의 ON CONFLICT 대상일 뿐이라
제거했는데, 새 프로젝트에 create_all 을 그냥 돌리면 되살아난다.
→ 만든 직후 지운다. 중복 제거는 로컬 SQLite 가 이미 한다.

## 사용법
    python -m scripts.bootstrap_supabase            # 스키마 생성 + 제약 제거
    python -m scripts.bootstrap_supabase --check     # 아무것도 안 바꾸고 현재 상태만
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse

from sqlalchemy import create_engine, inspect, text

from config.settings import SUPABASE_DATABASE_URL
from src.database.models import Base
from src.utils.logger import get_logger

log = get_logger(__name__)

# create_all 이 만들지만 조회에 안 쓰이고 용량만 먹는 제약 (위 docstring 참고)
DROP_CONSTRAINTS = (
    ("apt_trade", "uq_trade"),
    ("apt_rent", "uq_rent"),
)


def _engine():
    if not SUPABASE_DATABASE_URL:
        log.error("SUPABASE_DATABASE_URL 이 비어 있다 — .env 를 먼저 갱신할 것")
        return None
    return create_engine(SUPABASE_DATABASE_URL, pool_pre_ping=True,
                         connect_args={"connect_timeout": 30})


def report(pg) -> None:
    """현재 테이블·행수·용량을 찍는다."""
    names = sorted(inspect(pg).get_table_names())
    log.info("테이블 %d개: %s", len(names), ", ".join(names) or "(없음)")
    with pg.connect() as conn:
        for t in names:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            log.info("  %-20s %s행", t, f"{n:,}")
        size = conn.execute(text(
            "SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    log.info("DB 크기 %s (무료 한도 500MB)", size)


def bootstrap(pg) -> None:
    before = set(inspect(pg).get_table_names())
    Base.metadata.create_all(pg)
    created = sorted(set(inspect(pg).get_table_names()) - before)
    log.info("생성된 테이블 %d개: %s", len(created), ", ".join(created) or "(없음)")

    for table, name in DROP_CONSTRAINTS:
        with pg.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}"))
        log.info("제약 제거: %s.%s", table, name)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="바꾸지 않고 현재 상태만 출력")
    args = ap.parse_args()

    pg = _engine()
    if pg is None:
        return 1
    if not args.check:
        bootstrap(pg)
    report(pg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
