"""10.15 대책 + DSR 반영 대출 계산 검증"""
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
        print(f"FAIL {f}: line {e.lineno}: {e.msg}")
        sys.exit(1)

from src.analysis.loan import (
    get_zone, get_ltv_pct, loan_capacity_man, required_equity_man,
    max_purchase_man, dsr_loan_capacity_man,
)

print("\n=== 지역 규제 분류 ===")
for code, name in [("11680","강남구"),("11350","노원구"),("11215","광진구"),
                    ("41135","분당구"),("41591","화성시"),("28260","인천 서구")]:
    z = get_zone(code)
    ltv = get_ltv_pct(code, "무주택")
    print(f"  {name:<10s}({code})  {z:<6s}  LTV {ltv:.0f}%")

print("\n=== 시드 3억 무주택: 매수 가능 최대 매매가 ===")
for code, name in [("11680","강남구"),("11350","노원구"),("41135","분당구"),
                    ("41591","화성시"),("28260","인천 서구")]:
    p = max_purchase_man(30000, code, "무주택") / 10000
    print(f"  {name}: {p:.2f}억")

print("\n=== 시드 3억, 노원구 7억 매물 분석 ===")
loan = loan_capacity_man(70000, "11350", "무주택")
eq = required_equity_man(70000, "11350", "무주택")
print(f"  대출 가능: {loan/10000:.2f}억  /  필요자기자본: {eq/10000:.2f}억")
print(f"  → 시드 3억으로 가능? {'O' if eq <= 30000 else 'X'}")

print("\n=== 시드 6억, 강남 12억 매물 ===")
loan = loan_capacity_man(120000, "11680", "무주택")
eq = required_equity_man(120000, "11680", "무주택")
print(f"  LTV 50%={loan/10000:.0f}억 (cap 6억과 동일)  / 자기자본 {eq/10000:.0f}억")

print("\n=== 15-25억 구간 (강남 20억) ===")
loan = loan_capacity_man(200000, "11680", "무주택")
eq = required_equity_man(200000, "11680", "무주택")
print(f"  대출 {loan/10000:.0f}억 (cap 4억 적용)  / 자기자본 {eq/10000:.0f}억")

print("\n=== DSR 한도 계산 ===")
for income, name in [(5000, "연 5천만"), (7000, "연 7천만"),
                       (10000, "연 1억"), (15000, "연 1.5억")]:
    cap = dsr_loan_capacity_man(income)
    print(f"  {name}원 / 기존부채0 / 금리4.5% / 스트레스+3% / DSR40%  →  최대 {cap/10000:.2f}억")

print("\n=== DSR 적용 매수가능 (시드 3억, 무주택 연 7천만, 노원구) ===")
dsr_cap = dsr_loan_capacity_man(7000)
p_no_dsr = max_purchase_man(30000, "11350", "무주택") / 10000
p_with_dsr = max_purchase_man(30000, "11350", "무주택", dsr_cap_man=dsr_cap) / 10000
print(f"  DSR 없을 때: {p_no_dsr:.2f}억")
print(f"  DSR 적용시  : {p_with_dsr:.2f}억  (DSR 대출한도 {dsr_cap/10000:.2f}억)")
