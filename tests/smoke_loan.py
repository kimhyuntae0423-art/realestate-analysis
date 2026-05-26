"""대출 기능 동작 검증 스크립트"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ast
for f in ["src/analysis/loan.py", "src/analysis/recommend.py", "src/ui/streamlit_app.py"]:
    try:
        ast.parse(open(ROOT / f, encoding="utf-8").read())
        print(f"문법 OK: {f}")
    except SyntaxError as e:
        print(f"문법 FAIL: {f} -> {e}")
        sys.exit(1)

from src.analysis.loan import get_ltv_pct, get_zone, max_purchase_man

print("\n=== LTV 테스트 ===")
cases = [
    ("11680", "강남구", "무주택", False),
    ("11680", "강남구", "1주택", False),
    ("11680", "강남구", "다주택", False),
    ("11350", "노원구", "무주택", False),
    ("11350", "노원구", "무주택", True),   # 생애최초
    ("41135", "분당구", "1주택", False),
    ("28260", "인천 서구", "무주택", False),
]
for code, name, own, ft in cases:
    ltv = get_ltv_pct(code, own, ft)
    zone = get_zone(code)
    print(f"  {name:<10s} {own:<5s} 생애최초={'O' if ft else 'X'}  →  zone={zone:<5s} LTV={ltv:.0f}%")

print("\n=== 시드 5억 → 매수 가능 최대 매매가 ===")
for code, name in [("11680", "강남구"), ("11710", "송파구"), ("11350", "노원구"), ("41135", "분당구")]:
    p = max_purchase_man(50000, code, "무주택")
    print(f"  {name:<10s} 무주택: {p/10000:6.2f}억")

print("\n=== 추천 함수 (시드 3억, 무주택) ===")
from src.analysis.recommend import (
    recommend_gap_investment, recommend_rental_yield, recommend_buy_outright,
)
r1 = recommend_gap_investment(30000, months=6, ownership="무주택")
print(f"  갭투자: {len(r1):,} 건")
r2 = recommend_rental_yield(30000, months=12, ownership="무주택", use_loan=True)
print(f"  임대수익(대출O): {len(r2):,} 건")
r3 = recommend_rental_yield(30000, months=12, ownership="무주택", use_loan=False)
print(f"  임대수익(대출X): {len(r3):,} 건")
r4 = recommend_buy_outright(30000, months=12, ownership="무주택", use_loan=True)
max_p4 = r4["max_buy_price"].max() / 10000 if not r4.empty else 0
print(f"  자가매입(대출O): {len(r4):,} 건  매수가능 최고가: {max_p4:.1f}억")
r5 = recommend_buy_outright(30000, months=12, ownership="무주택", use_loan=False)
max_p5 = r5["max_buy_price"].max() / 10000 if not r5.empty else 0
print(f"  자가매입(대출X): {len(r5):,} 건  매수가능 최고가: {max_p5:.1f}억")

print("\n=== 자가매입 컬럼 (대출 적용) 샘플 5건 ===")
sample_cols = ["region_code", "apt_name", "trade_median", "ltv_%", "loan_capacity", "required_equity"]
print(r4[sample_cols].head(5).to_string(index=False))
