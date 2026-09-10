"""로컬 SQLite(SSOT) → Supabase(조회 전용 복제본) 동기화.

배포 Streamlit 이 읽는 클라우드 DB 를 로컬과 맞춘다. PC 의 수집·분석은 계속
로컬 SQLite 에 하고, 이 스크립트는 밀어넣기만 한다(단방향).

## 왜 upsert 가 아니라 "월 단위 삭제 후 삽입"인가

Supabase 무료 한도는 500MB 인데, uq_trade(57MB)+uq_rent(138MB) 중복방지 제약이
195MB 를 먹어 총 562MB 로 한도를 넘겼다(2026-09-10). 이 제약은 upsert 의
ON CONFLICT 대상일 뿐 조회에는 안 쓰이므로 제거해서 385MB 로 줄였다.

제약이 없으니 ON CONFLICT 를 못 쓴다. 대신 중복 제거는 **로컬 SQLite 가 이미
하고 있으므로**, 바뀐 달만 통째로 지우고 로컬 내용을 그대로 넣으면 결과가 같다.
(제약을 되살려야 하면 아래 정의로 복구:
   ALTER TABLE apt_trade ADD CONSTRAINT uq_trade UNIQUE
     (region_code, deal_date, apt_name, area_m2, floor, deal_amount);
   ALTER TABLE apt_rent  ADD CONSTRAINT uq_rent  UNIQUE
     (region_code, deal_date, apt_name, area_m2, floor, deposit, monthly_rent);
 단 195MB 가 다시 늘어 한도를 넘는다.)

## 사용법
    python -m scripts.migrate_to_supabase              # 차이나는 달만 동기화
    python -m scripts.migrate_to_supabase --full       # 전체 재적재
    python -m scripts.migrate_to_supabase --keep-months 24   # 24개월치만 유지(오래된 달 삭제)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import argparse
import csv
import io
import sqlite3

from sqlalchemy import create_engine, text

from config.settings import SUPABASE_DATABASE_URL
from src.utils.logger import get_logger

log = get_logger(__name__)

SQLITE_PATH = ROOT / "data" / "processed" / "realestate.db"

# 월 파티션이 있는 테이블(deal_year/deal_month 기준으로 비교·교체)
MONTHLY_TABLES = ("apt_trade", "apt_rent")
# 통째로 갈아끼우는 소형 테이블
SMALL_TABLES = ("ecos_series", "kb_price_series", "kb_sentiment_index")


def _sqlite():
    con = sqlite3.connect(str(SQLITE_PATH))
    con.row_factory = sqlite3.Row
    return con


def _cols(con, table) -> list[str]:
    cur = con.execute(f"SELECT * FROM {table} LIMIT 1")
    return [d[0] for d in cur.description]


def _insert_rows(pg, table, cols, rows):
    """id 를 뺀 나머지 컬럼을 COPY 로 적재.

    처음엔 executemany INSERT 였는데 사내망→도쿄 리전 왕복에서 분당 2,500행밖에
    안 나와 11만 행에 45분이 걸렸다. COPY 는 한 번의 스트림이라 왕복이 사라진다.
    """
    use = [c for c in cols if c != "id"]
    if not rows:
        return

    raw = pg.raw_connection()
    try:
        cur = raw.cursor()
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in use])
        buf.seek(0)
        cur.copy_expert(
            f"COPY {table} ({', '.join(use)}) FROM STDIN WITH (FORMAT csv, NULL '')",
            buf,
        )
        raw.commit()
    finally:
        raw.close()


def _month_bounds(y: int, m: int) -> tuple[str, str]:
    """[해당 월 1일, 다음 달 1일) — deal_date 인덱스를 타는 범위 조건용."""
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-01", f"{ny:04d}-{nm:02d}-01"


def sync_monthly(con, pg, table, full: bool) -> int:
    """로컬과 건수가 다른 달만 삭제 후 재삽입. 반환: 넣은 행 수."""
    local = {(r[0], r[1]): r[2] for r in con.execute(
        f"SELECT deal_year, deal_month, COUNT(*) FROM {table} GROUP BY 1, 2")}
    if full:
        target = sorted(local)
    else:
        with pg.connect() as conn:
            remote = {(r[0], r[1]): r[2] for r in conn.execute(text(
                f"SELECT deal_year, deal_month, COUNT(*) FROM {table} GROUP BY 1, 2"))}
        target = sorted(k for k in local if local[k] != remote.get(k, 0))

    if not target:
        log.info("[%s] 동기화할 달 없음", table)
        return 0

    cols = _cols(con, table)
    total = 0
    for (y, m) in target:
        rows = con.execute(
            f"SELECT * FROM {table} WHERE deal_year = ? AND deal_month = ?", (y, m)
        ).fetchall()
        # deal_year/deal_month 에는 인덱스가 없어 그 조건으로 지우면 매번 전체
        # 테이블(60만~125만행)을 훑는다. deal_date 는 인덱스가 있으므로 같은 달을
        # 범위 조건으로 지운다. 두 값의 정합성은 로컬에서 불일치 0행으로 확인함.
        lo, hi = _month_bounds(y, m)
        with pg.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {table} "
                     f"WHERE deal_date >= :lo AND deal_date < :hi"),
                {"lo": lo, "hi": hi},
            )
        _insert_rows(pg, table, cols, rows)
        total += len(rows)
        log.info("[%s] %d-%02d: %d행 교체", table, y, m, len(rows))
    return total


def sync_small(con, pg, table) -> int:
    """소형 테이블은 통째로 교체."""
    try:
        rows = con.execute(f"SELECT * FROM {table}").fetchall()
    except sqlite3.OperationalError:
        log.warning("[%s] 로컬에 테이블 없음 — 건너뜀", table)
        return 0
    cols = _cols(con, table)
    with pg.begin() as conn:
        conn.execute(text(f"DELETE FROM {table}"))
    if rows:
        _insert_rows(pg, table, cols, rows)
    log.info("[%s] %d행 교체", table, len(rows))
    return len(rows)


def prune(pg, keep_months: int):
    """오래된 달을 지워 무료 한도 안에 유지. keep_months 개월치만 남긴다."""
    from datetime import date
    today = date.today()
    cutoff = today.year * 12 + today.month - keep_months
    for table in MONTHLY_TABLES:
        with pg.begin() as conn:
            n = conn.execute(text(
                f"DELETE FROM {table} WHERE (deal_year * 12 + deal_month) < :c"
            ), {"c": cutoff}).rowcount
        log.info("[%s] 오래된 %d행 삭제 (최근 %d개월 유지)", table, n or 0, keep_months)


def run_sync(full: bool = False, keep_months: int = 0) -> int:
    """동기화 본체. argparse 를 타지 않으므로 다른 스크립트에서 직접 부를 수 있다.

    scheduled_refresh.py 가 `--months 3` 같은 자기 인자를 달고 실행되는데,
    여기서 parse_args() 를 부르면 그 인자를 못 알아보고 죽는다. 그래서 분리했다.
    """
    if not SUPABASE_DATABASE_URL:
        log.error("SUPABASE_DATABASE_URL 이 비어 있다 — .env 확인. 동기화를 건너뛴다.")
        return 1

    pg = create_engine(SUPABASE_DATABASE_URL, pool_pre_ping=True,
                       connect_args={"connect_timeout": 30})
    con = _sqlite()
    try:
        total = 0
        for t in MONTHLY_TABLES:
            total += sync_monthly(con, pg, t, full)
        for t in SMALL_TABLES:
            total += sync_small(con, pg, t)
        if keep_months > 0:
            prune(pg, keep_months)

        with pg.connect() as conn:
            size = conn.execute(text(
                "select pg_size_pretty(pg_database_size(current_database()))")).scalar()
        log.info("동기화 완료: %d행 전송, Supabase 크기 %s", total, size)
    finally:
        con.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="차이 비교 없이 전체 재적재")
    ap.add_argument("--keep-months", type=int, default=0,
                    help="0보다 크면 그 개월수만 남기고 오래된 달 삭제")
    args = ap.parse_args()
    return run_sync(full=args.full, keep_months=args.keep_months)


if __name__ == "__main__":
    sys.exit(main())
