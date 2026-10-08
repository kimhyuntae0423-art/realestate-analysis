"""복제 창(sync_from)이 업로드·삭제 양쪽에서 일관되게 쓰이는지."""
import sqlite3
from contextlib import contextmanager
from datetime import date

from scripts import migrate_to_supabase as m


class _FakePG:
    """pg.begin() 으로 들어온 DELETE 의 파라미터를 기록한다."""

    def __init__(self):
        self.deleted = []

    @contextmanager
    def begin(self):
        outer = self

        class _Conn:
            def execute(self, _sql, params):
                outer.deleted.append(params["lo"])
                return type("R", (), {"rowcount": 0})()

        yield _Conn()


def _months_between(lo: tuple[int, int], today: date) -> int:
    """하한(lo)부터 today 까지 양끝 포함 개월 수."""
    return (today.year * 12 + today.month) - (lo[0] * 12 + lo[1]) + 1


def test_sync_from_is_a_rolling_window():
    # SYNC_MONTHS 를 튜닝해도 깨지지 않도록 값이 아니라 성질을 검증한다
    for today in (date(2026, 10, 7), date(2026, 11, 1), date(2026, 1, 15)):
        lo = m.sync_from(today)
        assert _months_between(lo, today) == m.SYNC_MONTHS
        assert 1 <= lo[1] <= 12  # 연 경계에서 월이 0 이나 13 으로 새지 않는다

    # 한 달 지나면 창도 한 달 밀린다 — 고정 하한이면 이 단언이 깨진다
    y, mo = m.sync_from(date(2026, 10, 7))
    nxt = (y, mo + 1) if mo < 12 else (y + 1, 1)
    assert m.sync_from(date(2026, 11, 7)) == nxt

    # 백테스트 최소 요건(24개월)을 밑돌면 안 된다
    assert m.SYNC_MONTHS >= 24


def test_sync_monthly_skips_months_before_the_window():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE apt_trade (id INTEGER, deal_year INT, deal_month INT, deal_date TEXT)")
    y0, m0 = m.sync_from()
    before = (y0 - 1, m0)
    con.executemany("INSERT INTO apt_trade VALUES (?, ?, ?, ?)", [
        (1, before[0], before[1], f"{before[0]:04d}-{before[1]:02d}-15"),
        (2, y0, m0, f"{y0:04d}-{m0:02d}-15"),
    ])
    inserted = []
    # _insert_rows 는 psycopg COPY 라 여기선 대체한다
    original = m._insert_rows
    m._insert_rows = lambda pg, t, cols, rows: inserted.extend(rows)
    try:
        pg = _FakePG()
        n = m.sync_monthly(con, pg, "apt_trade", full=True)
    finally:
        m._insert_rows = original

    assert pg.deleted == [f"{y0:04d}-{m0:02d}-01"]
    assert n == 1 and inserted[0]["deal_year"] == y0


def test_prune_cutoff_equals_upload_lower_bound():
    """prune 이 지우는 경계와 업로드 하한이 같아야 한다.

    둘이 어긋나면 매주 같은 달을 올렸다 지웠다 반복한다(옛 --keep-months 사고).
    """
    pg = _FakePG()
    m.prune(pg)

    y, mo = m.sync_from()
    expected = f"{y:04d}-{mo:02d}-01"
    assert pg.deleted == [expected] * len(m.MONTHLY_TABLES)


def test_every_model_table_is_either_replicated_or_declared_local_only():
    """새 테이블이 생겼을 때 복제 여부를 정하지 않고 지나치는 걸 막는다.

    예전에 population_flow·supply_schedule 이 0행이던 시절 복제 대상에서 빠진 채
    잊혀졌다가, 데이터가 들어오자 배포 앱만 중립값(50.0)을 보여주는 불일치가 됐다
    (두 테이블은 2026-10-08에 수집째로 삭제됨).
    """
    from src.database.models import Base

    declared = set(m.MONTHLY_TABLES) | set(m.SMALL_TABLES) | set(m.LOCAL_ONLY_TABLES)
    assert set(Base.metadata.tables) == declared


def test_keep_months_option_is_gone():
    """--keep-months 는 충돌의 원인이었으므로 되살아나면 안 된다."""
    import inspect
    assert "keep_months" not in inspect.signature(m.run_sync).parameters
