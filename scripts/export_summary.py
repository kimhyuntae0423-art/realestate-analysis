"""주요 지역 거래 데이터 요약 CSV 내보내기
GitHub Actions 주간 워크플로우에서 실행됨.
생성 파일: data/exports/monthly_price_summary.csv, apt_summary.csv, gap_summary.csv
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datetime import date, timedelta
import pandas as pd
from src.database.models import init_db
from src.database.repository import fetch_trades_df, fetch_rents_df

EXPORT_DIR = ROOT / "data" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

REGIONS = {
    "11680": "서울강남구",
    "11650": "서울서초구",
    "11710": "서울송파구",
    "11440": "서울마포구",
    "11170": "서울용산구",
    "41135": "경기분당구",
}


def export_monthly_summary():
    date_from = date.today() - timedelta(days=365)
    rows = []
    for code, name in REGIONS.items():
        df = fetch_trades_df(region_code=code, date_from=date_from)
        if df.empty:
            continue
        df["ym"] = pd.to_datetime(df["deal_date"]).dt.to_period("M").astype(str)
        monthly = df.groupby("ym").agg(
            avg_price=("price_man", "mean"),
            median_price=("price_man", "median"),
            count=("price_man", "count"),
        ).reset_index()
        monthly["region_code"] = code
        monthly["region_name"] = name
        rows.append(monthly)

    if not rows:
        print("SKIP: monthly_price_summary (데이터 없음)")
        return
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(EXPORT_DIR / "monthly_price_summary.csv", index=False, encoding="utf-8-sig")
    print(f"OK: monthly_price_summary.csv ({len(out)} rows)")


def export_apt_summary():
    date_from = date.today() - timedelta(days=90)
    rows = []
    for code, name in REGIONS.items():
        df = fetch_trades_df(region_code=code, date_from=date_from)
        if df.empty:
            continue
        agg = df.groupby("apt_name").agg(
            avg_price=("price_man", "mean"),
            count=("price_man", "count"),
            avg_area=("exclusive_area", "mean"),
        ).reset_index()
        agg["region_code"] = code
        agg["region_name"] = name
        rows.append(agg)

    if not rows:
        print("SKIP: apt_summary (데이터 없음)")
        return
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(EXPORT_DIR / "apt_summary.csv", index=False, encoding="utf-8-sig")
    print(f"OK: apt_summary.csv ({len(out)} rows)")


def export_gap_summary():
    date_from = date.today() - timedelta(days=90)
    rows = []
    for code, name in REGIONS.items():
        trade = fetch_trades_df(region_code=code, date_from=date_from)
        rent = fetch_rents_df(region_code=code, date_from=date_from, jeonse_only=True)
        if trade.empty or rent.empty:
            continue
        t = trade.groupby("apt_name")["price_man"].mean().rename("trade_price")
        r = rent.groupby("apt_name")["deposit_man"].mean().rename("jeonse_price")
        merged = pd.concat([t, r], axis=1).dropna()
        if merged.empty:
            continue
        merged["gap_man"] = merged["trade_price"] - merged["jeonse_price"]
        merged["gap_ratio"] = (merged["gap_man"] / merged["trade_price"]).round(4)
        merged["region_code"] = code
        merged["region_name"] = name
        rows.append(merged.reset_index())

    if not rows:
        print("SKIP: gap_summary (데이터 없음)")
        return
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(EXPORT_DIR / "gap_summary.csv", index=False, encoding="utf-8-sig")
    print(f"OK: gap_summary.csv ({len(out)} rows)")


if __name__ == "__main__":
    init_db()
    export_monthly_summary()
    export_apt_summary()
    export_gap_summary()
    print(f"\n내보내기 완료 → {EXPORT_DIR}")
