"""호재 기반 투자수익 추천 검증"""
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

from src.analysis.recommend import (
    recommend_investment_focus, manual_catalyst_score, manual_catalyst_text,
)

print("\n=== 수동 호재 점수 샘플 ===")
for code, name in [("11680","강남구"),("11170","용산구"),("41135","분당"),
                    ("41591","화성시"),("41360","남양주"),("11500","강서구")]:
    sc = manual_catalyst_score(code)
    tx = manual_catalyst_text(code)
    print(f"  {name:<8s}({code}) score={sc:5.1f}  | {tx[:60]}")

print("\n=== 투자수익 추천 (시드 5억, 무주택, 호재 가중치 50%) ===")
rec = recommend_investment_focus(50000, months=12, ownership="무주택",
                                   first_time_buyer=False, use_loan=True,
                                   catalyst_weight=0.5)
print(f"총 후보: {len(rec):,}건")

if not rec.empty:
    print("\nTOP 10:")
    cols = ["region_code","apt_name","trade_median","catalyst_score",
            "manual_catalyst","vol_score","new_build_score",
            "price_growth_%","expected_roi_%","score"]
    print(rec[cols].head(10).to_string(index=False))

    print("\n호재 가중치 0 (과거 모멘텀만) - TOP 5:")
    rec0 = recommend_investment_focus(50000, months=12, catalyst_weight=0.0)
    print(rec0[cols].head(5).to_string(index=False))

    print("\n호재 가중치 1.0 (호재만) - TOP 5:")
    rec1 = recommend_investment_focus(50000, months=12, catalyst_weight=1.0)
    print(rec1[cols].head(5).to_string(index=False))
