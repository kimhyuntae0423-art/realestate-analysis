"""SQLite 데이터를 Supabase(PostgreSQL)로 이전."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3
from tqdm import tqdm
from sqlalchemy import create_engine, text
from src.database.repository import _make_upsert
from src.database.models import AptTrade, AptRent

SQLITE_PATH = ROOT / "data" / "processed" / "realestate.db"
CHUNK = 2000


def migrate():
    from config.settings import DATABASE_URL
    pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    sq = sqlite3.connect(str(SQLITE_PATH))
    sq.row_factory = sqlite3.Row

    for tbl, model in [("apt_trade", AptTrade), ("apt_rent", AptRent)]:
        cur = sq.execute(f"SELECT COUNT(*) FROM {tbl}")
        total = cur.fetchone()[0]
        print(f"\n[{tbl}] 총 {total:,}건 이전 시작")

        offset = 0
        cols = None
        with tqdm(total=total, unit="rows") as bar:
            while offset < total:
                rows = sq.execute(
                    f"SELECT * FROM {tbl} LIMIT {CHUNK} OFFSET {offset}"
                ).fetchall()
                if not rows:
                    break
                if cols is None:
                    cols = [d[0] for d in sq.execute(
                        f"SELECT * FROM {tbl} LIMIT 1"
                    ).description]
                payload = [dict(zip(cols, r)) for r in rows]
                # id 제거 (PostgreSQL이 autoincrement로 생성)
                for p in payload:
                    p.pop("id", None)
                with pg_engine.begin() as conn:
                    stmt = _make_upsert(model, payload)
                    conn.execute(stmt)
                offset += len(rows)
                bar.update(len(rows))

    sq.close()
    print("\n이전 완료!")


if __name__ == "__main__":
    migrate()
