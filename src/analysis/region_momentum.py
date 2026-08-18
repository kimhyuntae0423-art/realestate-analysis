"""지역(시군구) 모멘텀 랭킹 — "지금 어느 지역이 좋은가".

recommend.py는 이미 822줄이라 새 파일로 분리(300줄 제한).

backtest.py의 region_backtest() 그리드서치 검증 결과(2026-08-18, n=84,
spearman=0.783, top10=60%) 기반. 예전 기본 가중치(tier 60% 단독 위주, spearman
0.732, top10 40%)보다 가격모멘텀+거래량모멘텀 비중을 높인 조합이 확실히 더
정확했음 — apt 단위(recommend_investment_focus) 쪽은 같은 방식으로 확장 그리드서치
해봤지만 개선폭이 노이즈 수준(<0.02)이라 그대로 유지, 지역 단위만 이 새 랭킹으로 반영.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.analysis.backtest import _region_price_growth, _region_volume_momentum
from src.analysis.recommend import region_tier_score, region_tier_label


def region_momentum_ranking(months: int = 12, min_deals: int = 10) -> pd.DataFrame:
    """시군구 단위 "지금 사기 좋은 지역" 랭킹.

    종합점수 = tier_score(입지등급) 20% + 가격모멘텀(단지+평형 추적, 구성효과 제거) 48%
             + 거래량모멘텀(최근/이전 거래건수 비율) 32%
    (region_backtest 그리드서치 최적 조합: catalyst_weight=0, tier_weight=0.2,
    나머지 0.8을 train_growth 60% : vol_momentum 40%로 나눈 것과 동일 비율)

    반환 컬럼: region_code, growth_%(가격모멘텀), vol_momentum, tier_score,
    tier_label, momentum_score. min_deals 미달 지역은 growth_% 자체가 없어 제외됨.
    """
    half_days = 30 * max(months // 2, 3)
    end = date.today()
    mid = end - timedelta(days=half_days)
    start = mid - timedelta(days=half_days)

    price_g = _region_price_growth(start, mid, end, min_deals=min_deals)
    if price_g.empty:
        return pd.DataFrame()
    vol_g = _region_volume_momentum(start, mid, end)

    g = price_g.merge(vol_g, on="region_code", how="left")
    g["vol_momentum"] = g["vol_momentum"].fillna(1.0)
    g["tier_score"] = g["region_code"].apply(region_tier_score)
    g["tier_label"] = g["region_code"].apply(region_tier_label)

    g["momentum_score"] = (
        g["tier_score"].rank(pct=True) * 0.20
        + g["growth_%"].rank(pct=True) * 0.48
        + g["vol_momentum"].rank(pct=True) * 0.32
    ) * 100
    g["momentum_score"] = g["momentum_score"].round(1)

    return g.sort_values("momentum_score", ascending=False).reset_index(drop=True)
