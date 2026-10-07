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


def test_sync_from_is_a_rolling_window():
    assert m.sync_from(date(2026, 10, 7)) == (2024, 7)
    # 한 달 지나면 창도 한 달 밀린다 — 고정 하한이면 이 단언이 깨진다
    assert m.sync_from(date(2026, 11, 1)) == (2024, 8)
    # 연 경계에서 월이 0 이나 13 으로 새지 않는지
    assert m.sync_from(date(2026, 1, 15)) == (2023, 10)


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


def test_keep_months_option_is_gone():
    """--keep-months 는 충돌의 원인이었으므로 되살아나면 안 된다."""
    import inspect
    assert "keep_months" not in inspect.signature(m.run_sync).parameters
