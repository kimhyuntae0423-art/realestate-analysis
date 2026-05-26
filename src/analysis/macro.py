"""매크로 신호등 — 6개 요인의 시장 환경 종합 진단

각 요인을 녹(우호)/황(중립)/적(불리) 3단계로 평가.
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config.settings import ROOT
from src.database.repository import fetch_trades_df, fetch_rents_df
from src.analysis.gap_analysis import to_jeonse_equiv


def _signal(score: float, green_threshold: float, red_threshold: float,
             reverse: bool = False) -> str:
    """score 가 green ≥ 면 녹, red ≤ 면 적, 사이는 황."""
    if reverse:
        if score <= green_threshold: return "green"
        if score >= red_threshold: return "red"
        return "yellow"
    if score >= green_threshold: return "green"
    if score <= red_threshold: return "red"
    return "yellow"


def signal_volume_momentum() -> dict:
    """전국 거래량 모멘텀: 최근 3mo vs 이전 3mo."""
    now = date.today()
    df = fetch_trades_df(date_from=now - timedelta(days=180))
    if df.empty:
        return {"name": "거래량 동향", "level": "yellow", "value": "N/A", "detail": "데이터 없음"}
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    cut = pd.Timestamp(now - timedelta(days=90))
    recent = (df["deal_date"] > cut).sum()
    prior = (df["deal_date"] <= cut).sum()
    ratio = recent / max(prior, 1)
    level = _signal(ratio, 1.2, 0.8)  # 20%↑ 녹 / 20%↓ 적
    return {
        "name": "거래량 동향",
        "level": level,
        "value": f"{ratio:.2f}x",
        "detail": f"최근 3mo {recent:,}건 vs 이전 3mo {prior:,}건",
    }


def signal_jeonse_ratio() -> dict:
    """전국 평균 전세가율 (전세환산/매매)."""
    now = date.today()
    df_t = fetch_trades_df(date_from=now - timedelta(days=90))
    df_r = fetch_rents_df(date_from=now - timedelta(days=90))
    if df_t.empty or df_r.empty:
        return {"name": "전세가율", "level": "yellow", "value": "N/A", "detail": ""}
    df_r = to_jeonse_equiv(df_r)
    median_trade = df_t["deal_amount"].median()
    median_rent = df_r["jeonse_equiv"].median()
    ratio = median_rent / median_trade * 100 if median_trade else 0
    level = _signal(ratio, 70, 55)  # 70%↑ 녹(매수 유리), 55%↓ 적
    return {
        "name": "전세가율",
        "level": level,
        "value": f"{ratio:.1f}%",
        "detail": "전국 평균. 70% 이상이면 갭축소·매매 강세 신호",
    }


def signal_price_momentum() -> dict:
    """전국 평균 매매가 모멘텀."""
    now = date.today()
    df = fetch_trades_df(date_from=now - timedelta(days=270))
    if df.empty:
        return {"name": "가격 모멘텀", "level": "yellow", "value": "N/A", "detail": ""}
    df["deal_date"] = pd.to_datetime(df["deal_date"])
    cut3 = pd.Timestamp(now - timedelta(days=90))
    cut6 = pd.Timestamp(now - timedelta(days=180))
    recent_ppp = df[df["deal_date"] > cut3]["price_per_pyeong"].median()
    mid_ppp = df[(df["deal_date"] > cut6) & (df["deal_date"] <= cut3)]["price_per_pyeong"].median()
    if mid_ppp and recent_ppp:
        change = (recent_ppp - mid_ppp) / mid_ppp * 100
    else:
        change = 0
    level = _signal(change, 2.0, -2.0)
    return {
        "name": "가격 모멘텀",
        "level": level,
        "value": f"{change:+.2f}%",
        "detail": f"최근 3mo 평당가 변화율 (전체 시장)",
    }


def signal_regulation() -> dict:
    """대출 규제 강도 — 현재 10.15 대책 적용 중 = 강(적)"""
    return {
        "name": "대출 규제",
        "level": "red",
        "value": "강화",
        "detail": "10.15 대책: 서울+경기12 규제, 한도 6억 cap, 스트레스 DSR 3%",
    }


def signal_interest_rate() -> dict:
    """기준금리 방향 — 수동 토글 권장 (현재는 정적 데이터)."""
    # 2026 기준 한은 인하 기조
    return {
        "name": "기준금리",
        "level": "yellow",
        "value": "인하 기조",
        "detail": "2025~2026 한은 점진적 인하. 대출 부담 완화 방향",
    }


def signal_supply() -> dict:
    """공급(입주물량) 부담."""
    # config/supply.json 기반 — 단순 합산
    try:
        p = ROOT / "config" / "supply.json"
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        total = 0
        for code, items in data.get("by_region", {}).items():
            for _, n in items.items():
                total += int(n)
    except Exception:
        return {"name": "공급량", "level": "yellow", "value": "N/A", "detail": ""}

    # 수도권 12개월 5만호 = 기준
    if total < 30000:   level = "green"  # 부족 → 가격 우호
    elif total < 60000: level = "yellow"
    else:                level = "red"
    return {
        "name": "공급량",
        "level": level,
        "value": f"{total:,} 호",
        "detail": "config/supply.json 등록 향후 입주 합. 적을수록 가격 우호.",
    }


def macro_dashboard() -> list[dict]:
    """6요인 신호등 한 번에."""
    return [
        signal_regulation(),
        signal_interest_rate(),
        signal_volume_momentum(),
        signal_jeonse_ratio(),
        signal_supply(),
        signal_price_momentum(),
    ]
