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
    """전국 평균 전세가율 (전세환산/매매) — 참고용 서술 지표.

    매매·전세 각각 독립적으로 구한 전국 median끼리 나누면 그 90일간 우연히 어떤
    단지·평형이 거래됐는지(구성효과)가 분자·분모에 이중으로 껴서 왜곡된다 — KB 공식
    전세가격비율과 비교했더니 지역별로 쪼개면 전부 반대 부호였음(2026-08-17 감리).
    같은 단지+평형 유닛에서 매매·전세가 동시에 관측된 경우만 매칭해 계산한다.

    실험실에서 시차·누적·인구·공급·규제 5방향으로 검증했지만 전부 기각됨(2026-08-18,
    전세가율은 가격 선행지표가 아님) — 그래서 green/red 판정 없이 항상 yellow(참고용)로만
    표시하고, 매수·매도 신호로 쓰지 않는다는 점을 detail에 명시한다.
    """
    from src.analysis.hypothesis_lab import jeonse_ratio_via_unit_matching

    now = date.today()
    df_t = fetch_trades_df(date_from=now - timedelta(days=90))
    df_r = fetch_rents_df(date_from=now - timedelta(days=90))
    if df_t.empty or df_r.empty:
        return {"name": "전세가율", "level": "yellow", "value": "N/A", "detail": ""}
    df_r = to_jeonse_equiv(df_r)
    df_r["ppp"] = df_r["jeonse_equiv"] / df_r["area_m2"] * 3.3058
    ratio_g = jeonse_ratio_via_unit_matching(df_t, df_r, [])
    if ratio_g.empty:
        return {"name": "전세가율", "level": "yellow", "value": "N/A", "detail": ""}
    ratio = (ratio_g["jeonse_ratio"] * ratio_g["n"]).sum() / ratio_g["n"].sum()
    return {
        "name": "전세가율",
        "level": "yellow",
        "value": f"{ratio:.1f}%",
        "detail": "전국 평균(단지+평형 유닛 매칭). 실험실 검증 결과 가격 선행지표 아님(참고용)",
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
    """대출 규제 강도 — 현재 10.15 대책 + 2026-07 대책 적용 중 = 강(적)"""
    return {
        "name": "대출 규제",
        "level": "red",
        "value": "강화",
        "detail": "10.15+2026-07 대책: 서울+경기15 규제, 무주택 LTV 40%, 한도 flat 6억, 스트레스 DSR 3%",
    }


def signal_interest_rate() -> dict:
    """기준금리 방향 — ECOS 실데이터(base_rate, 매달 자동 수집) 기준.

    이전엔 하드코딩된 정적 텍스트("인하 기조")였으나, ECOS 연동(2026-08-19) 이후
    실제 수치로 교체. 3개월 전 대비 변화로 인상/인하/동결을 판정한다.
    """
    from src.analysis.hypothesis_tests_ecos_rate import _ecos_level_panel

    panel = _ecos_level_panel("base_rate", "base_rate")
    if panel.empty or len(panel) < 2:
        return {"name": "기준금리", "level": "yellow", "value": "N/A", "detail": "ECOS 데이터 없음"}
    panel = panel.sort_values("ym")
    latest = panel.iloc[-1]
    prior_idx = max(0, len(panel) - 1 - 3)  # 3개월 전(데이터 부족 시 가장 이른 시점)
    prior = panel.iloc[prior_idx]
    change = round(float(latest["base_rate"]) - float(prior["base_rate"]), 2)
    level = _signal(change, -0.05, 0.05, reverse=True)  # 인하(↓)=우호(녹), 인상(↑)=불리(적)
    direction = "인하" if change < -0.01 else ("인상" if change > 0.01 else "동결")
    return {
        "name": "기준금리",
        "level": level,
        "value": f"{latest['base_rate']:.2f}%",
        "detail": f"{prior['ym']}→{latest['ym']} {direction} ({change:+.2f}%p). 인하=대출부담완화(우호)",
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
