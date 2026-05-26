"""투자수익 추천 검증"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ast
for f in ["src/analysis/recommend.py", "src/ui/streamlit_app.py"]:
    try:
        ast.parse(open(ROOT / f, encoding="utf-8").read())
        print(f"문법 OK: {f}")
    except SyntaxError as e:
        print(f"문법 FAIL: {f} -> {e}")
        sys.exit(1)

from src.analysis.recommend import recommend_investment_focus

print("\n=== 투자수익 전략 검증 (시드 5억, 무주택, 대출 O) ===")
rec = recommend_investment_focus(50000, months=12, ownership="무주택",
                                  first_time_buyer=False, use_loan=True)
print(f"총 매물 후보: {len(rec):,} 건")
if not rec.empty:
    print(f"\n최고 예상수익률 매물 TOP 10:")
    cols = ["region_code", "apt_name", "area_bucket", "trade_median",
            "ltv_%", "leverage", "required_equity",
            "price_growth_%", "expected_roi_%", "score"]
    print(rec[cols].head(10).to_string(index=False))

    print(f"\n예상수익률 통계:")
    print(f"  중위 ROI : {rec['expected_roi_%'].median():.2f}%")
    print(f"  최고 ROI : {rec['expected_roi_%'].max():.2f}%")
    print(f"  최저 ROI : {rec['expected_roi_%'].min():.2f}%")

    # 지역별 평균 예상 ROI
    print(f"\n지역별 평균 예상 ROI TOP 10:")
    g = rec.groupby("region_code").agg(
        n=("apt_name", "count"),
        avg_roi=("expected_roi_%", "mean"),
        max_roi=("expected_roi_%", "max"),
    ).sort_values("avg_roi", ascending=False).head(10)
    print(g.round(2).to_string())
