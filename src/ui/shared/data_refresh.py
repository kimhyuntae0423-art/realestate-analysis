"""데이터 최신화 상태 조회 + 원클릭 갱신.

src/ui/shared.py 에서 분리 (모듈화 3단계).
"""
from __future__ import annotations
import streamlit as st

from config.settings import ROOT as APP_ROOT, DATABASE_URL
ROOT = APP_ROOT


def _data_freshness() -> dict:
    """각 데이터의 마지막 갱신 시점 + 경과일."""
    import json as _json
    from datetime import date as _date
    from sqlalchemy import text
    from src.database.models import engine as _engine
    out = {}
    try:
        with _engine.connect() as conn:
            for tbl, col, label in [
                ("apt_trade", "deal_date", "실거래 매매"),
                ("apt_rent", "deal_date", "실거래 전월세"),
            ]:
                try:
                    row = conn.execute(
                        text(f"SELECT MAX({col}), COUNT(*) FROM {tbl}")
                    ).fetchone()
                    last, n = row
                    if last:
                        d = _date.fromisoformat(str(last)[:10])
                        out[label] = {
                            "last": d, "days_ago": (_date.today() - d).days, "rows": n,
                        }
                    else:
                        out[label] = {"last": None, "days_ago": None, "rows": 0}
                except Exception:
                    out[label] = {"last": None, "days_ago": None, "rows": 0}
    except Exception:
        pass
    # config 파일
    for fname, label in [("catalysts.json", "호재(catalysts)"),
                         ("region_tiers.json", "등급(tiers)"),
                         ("supply.json", "수동 공급(supply)")]:
            try:
                with open(ROOT / "config" / fname, encoding="utf-8") as f:
                    j = _json.load(f)
                upd = j.get("_meta", {}).get("updated", "?")
                out[label] = {"last": upd, "days_ago": None, "rows": None}
            except Exception:
                out[label] = {"last": "?", "days_ago": None, "rows": None}
    return out


def _refresh_recent_data(months: int = 3, regions: list[str] | None = None,
                          do_supply: bool = False) -> dict:
    """원클릭 데이터 갱신.

    1) 국토부 실거래(매매·전월세): 모든 보유 시군구의 최근 N개월 (incremental upsert)
    2) (옵션) KOSIS 입주물량 — 2026-05 시뮬레이션 후 점수 산식에서 제외됨. default off.
    인구이동·호재·등급은 수동 (KOSIS CSV / JSON 편집).
    """
    import sqlite3
    from datetime import date as _date
    from src.collectors.molit_api import MolitCollector
    from src.database.repository import upsert_trades, upsert_rents
    from src.collectors.kosis_api import KosisCollector
    summary = {"trade": 0, "rent": 0, "supply": 0, "errors": []}

    # 1) 최근 N개월 ymd 리스트
    today = _date.today()
    ymds = []
    y, m = today.year, today.month
    for _ in range(months):
        ymds.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    ymds = list(reversed(ymds))

    # 2) 보유 시군구
    if regions is None:
        conn = sqlite3.connect(str(DATABASE_URL).replace("sqlite:///", ""))
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT region_code FROM apt_trade ORDER BY region_code")
        regions = [r[0] for r in cur.fetchall()]
        conn.close()

    # 3) 국토부 수집 (시군구 × 월)
    try:
        mc = MolitCollector()
    except Exception as e:
        summary["errors"].append(f"MOLIT 키 미설정: {e}")
        return summary

    prog = st.progress(0.0, text="국토부 실거래 수집 시작…")
    total = len(regions) * len(ymds)
    done = 0
    for region in regions:
        for ymd in ymds:
            try:
                rows = mc.fetch_trades(region, ymd)
                ins_t = upsert_trades(rows)
                summary["trade"] += ins_t
                rows = mc.fetch_rents(region, ymd)
                ins_r = upsert_rents(rows)
                summary["rent"] += ins_r
            except Exception as e:
                summary["errors"].append(f"{region}/{ymd}: {e}")
            done += 1
            prog.progress(done / total, text=f"실거래 {region} {ymd} ({done}/{total})")
    prog.empty()

    # 4) KOSIS 입주물량 (시도 17개 × 최근 12개월)
    if do_supply:
        try:
            from src.database.models import SupplySchedule, SessionLocal
            from src.database.repository import _make_upsert
            col = KosisCollector()
            today = _date.today()
            y, m = today.year, today.month
            for _ in range(11):
                m -= 1
                if m == 0:
                    m = 12; y -= 1
            start_ym = f"{y:04d}{m:02d}"
            end_ym = f"{today.year:04d}{today.month:02d}"
            rows = col.fetch_supply_schedule(start_ym, end_ym)
            if rows:
                payload = []
                for r in rows:
                    region = r.get("C1") or ""
                    ym = r.get("PRD_DE") or ""
                    units = int(float(r.get("DT") or 0))
                    if not region or len(region) != 2 or units <= 0:
                        continue
                    payload.append({
                        "region_code": region,
                        "move_in_date": _date(int(ym[:4]), int(ym[4:6]), 1),
                        "units": units, "source": "kosis_sido",
                    })
                if payload:
                    with SessionLocal() as s:
                        stmt = _make_upsert(SupplySchedule, payload)
                        s.execute(stmt)
                        s.commit()
                    summary["supply"] = len(payload)
        except Exception as e:
            summary["errors"].append(f"KOSIS 공급: {e}")

    return summary


