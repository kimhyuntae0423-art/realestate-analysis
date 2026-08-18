"""전국 매크로 타이밍 진단 — "지금이 매수하기 좋은 시점인가".

hypothesis_tests_ecos.py/hypothesis_tests_ecos_rate.py에서 검증된 신호들을
"현재값이 역사적으로 얼마나 높은/낮은 수준인가"(percentile)로 변환해 타이밍
판단에 쓴다. 신호마다 시차가 다르므로(단기 1개월 vs 장기 12~18개월) 하나의
숫자로 억지로 합치지 않고, 신뢰도(가중치)로 구분해 반영한다.

- 단기 실행신호(1개월 지연, 직접효과, 높은 신뢰도 35%씩): 주담대 YoY, KB 매수심리
- 장기 배경지표(12~18개월, 정책내생성 의심, 낮은 신뢰도 10%씩): M2 YoY, 실질금리, M1/M2비율

각 신호의 expected_sign은 실험실에서 실DB로 재검증된 방향(2026-08-18) 그대로 사용 —
naive 통념이 아니라 실제 확인된 부호(예: M2는 naive하게는 +1이지만 검증 결과 -1).
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from src.database.repository import session_scope
from src.database.models import KbSentimentIndex
from src.analysis.hypothesis_tests_ecos import _m2_yoy_panel, _ecos_yoy_panel, MORTGAGE_SERIES
from src.analysis.hypothesis_tests_ecos_rate import _real_rate_panel, _m1_m2_ratio_panel


def _kb_sentiment_panel() -> pd.DataFrame:
    """KB 매수우위지수 — 우리가 추적하는 시/도 전체 평균, 월별."""
    with session_scope() as s:
        rows = s.execute(select(KbSentimentIndex.ym_date, KbSentimentIndex.sentiment_index)).all()
    df = pd.DataFrame(rows, columns=["ym_date", "value"])
    if df.empty:
        return pd.DataFrame(columns=["ym", "value"])
    df["ym"] = pd.to_datetime(df["ym_date"]).dt.to_period("M")
    g = df.groupby("ym")["value"].mean().reset_index()
    return g[["ym", "value"]]


# (id, 표시명, 패널함수, expected_sign, 신뢰도구간, 가중치, 근거 가설)
SIGNALS = [
    dict(id="mortgage_loan", label="주택담보대출 증가율(YoY)",
         panel_fn=lambda: _ecos_yoy_panel(MORTGAGE_SERIES, "value"),
         expected_sign=1, tier="단기(1개월, 직접효과)", weight=0.35,
         hypothesis="mortgage_loan_leads_price"),
    dict(id="kb_sentiment", label="KB 매수우위지수",
         panel_fn=_kb_sentiment_panel,
         expected_sign=1, tier="단기(1개월, 직접효과)", weight=0.35,
         hypothesis="buyer_sentiment_leads_price(_kb)"),
    dict(id="m2_yoy", label="M2(통화량) 증가율(YoY)",
         panel_fn=lambda: _m2_yoy_panel().rename(columns={"m2_yoy": "value"}),
         expected_sign=-1, tier="장기(12~18개월, 정책내생성 의심)", weight=0.10,
         hypothesis="money_supply_leads_price"),
    dict(id="real_rate", label="실질금리(기준금리-기대인플레)",
         panel_fn=lambda: _real_rate_panel().rename(columns={"real_rate": "value"}),
         expected_sign=1, tier="장기(12~18개월, 정책내생성 의심)", weight=0.10,
         hypothesis="real_rate_leads_price"),
    dict(id="m1_m2_ratio", label="M1/M2 비율",
         panel_fn=lambda: _m1_m2_ratio_panel().rename(columns={"m1_m2_ratio": "value"}),
         expected_sign=-1, tier="장기(12~18개월, 정책내생성 의심)", weight=0.10,
         hypothesis="m1_m2_ratio_leads_price"),
]


def market_timing_signal() -> dict:
    """전국 매크로 타이밍 진단.

    각 신호의 "현재값"(가장 최근 관측치)이 그 신호 자신의 과거 분포에서 몇
    퍼센타일인지 구하고, 검증된 방향(expected_sign)과 결합해 favorability(0~100,
    높을수록 우호적)로 바꾼 뒤 신뢰도 가중평균한다.

    반환: {"score": 0~100 또는 None, "signals": [신호별 상세], "computed_at": ISO 문자열}
    score 해석: 50=중립, 높을수록 우호적, 낮을수록 불리. 장기 배경지표는 인과가 아니라
    상관 기반이라(정책 내생성 의심) 가중치를 낮게 뒀다 — caveats는 hypothesis_tests_ecos*.py
    참고.
    """
    rows = []
    weighted_sum = 0.0
    weight_total = 0.0

    for sig in SIGNALS:
        panel = sig["panel_fn"]().dropna(subset=["value"])
        row = {"id": sig["id"], "label": sig["label"], "tier": sig["tier"],
               "weight": sig["weight"], "hypothesis": sig["hypothesis"],
               "current_value": None, "percentile": None, "favorability": None, "as_of": None}
        if panel.empty or len(panel) < 6:
            rows.append(row)
            continue
        panel = panel.sort_values("ym")
        current = panel["value"].iloc[-1]
        percentile = float((panel["value"] < current).mean() * 100)
        favorability = percentile if sig["expected_sign"] > 0 else (100 - percentile)

        row.update({
            "current_value": round(float(current), 3),
            "percentile": round(percentile, 1),
            "favorability": round(favorability, 1),
            "as_of": str(panel["ym"].iloc[-1]),
        })
        rows.append(row)
        weighted_sum += favorability * sig["weight"]
        weight_total += sig["weight"]

    score = round(weighted_sum / weight_total, 1) if weight_total > 0 else None
    return {
        "score": score,
        "signals": rows,
        "computed_at": pd.Timestamp.now().isoformat(timespec="seconds"),
    }
