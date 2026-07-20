# 아키텍처 — 크로스커팅 연계 맵

여러 파일이 공유하는 개념(정책 상수·계산 공식·문서화된 설명)이 서로 다른 곳에서
따로 정의되거나, 코드는 바뀌었는데 그걸 설명하는 텍스트가 안 바뀌는 걸 막기 위한
문서. 새 기능을 추가하기 전에 이 표에서 비슷한 개념이 있는지 먼저 확인하고,
새로운 크로스커팅 개념을 만들었으면 이 표에 행을 추가한다.

## 원칙

1. **숫자(정책 상수)**는 `config/settings.py` 또는 `config/*.json`이 SSOT다.
   `src/analysis/*.py`·`src/ui/streamlit_app.py`에 숫자를 다시 하드코딩하지 않는다.
2. **계산 공식이 바뀌면, 그 공식을 설명하는 모든 텍스트(UI 안내문·docstring)를
   같이 고친다.** 이 레포에서 실제로 반복된 문제 유형은 숫자 중복이 아니라
   "코드는 리팩터링됐는데 사용자에게 보여주는 설명 텍스트가 안 바뀐 것"이었다.
3. 새 정책 상수를 코드에 추가하기 전에 `config/`에 이미 있는지 먼저 검색한다.

## 연계 맵

| 개념 | SSOT (정의 위치) | 참조하는 곳 | 비고 |
|---|---|---|---|
| API 키·DB 경로·요청 설정 | `config/settings.py` | `src/collectors/*.py`, `src/analysis/*.py` (ROOT import) | 잘 지켜지고 있음 (감사 결과 하드코딩 재정의 없음) |
| 지역 티어(5단계: 100/80/60/40/20) | `config/region_tiers.json` | `src/analysis/recommend.py`, `src/ui/streamlit_app.py` UI 설명 | 2026-07-20: UI 설명이 4단계로 축약돼 5_하급지(20점)가 누락돼 있던 것 수정 |
| 대출 규제(LTV%, 한도cap, DSR) | `config/loan_regulations.json` | `src/analysis/loan.py::load_regulations()` | 2026-07-20: `streamlit_app.py`의 LTV 한도 경고문이 "6억"을 하드코딩하고 있던 것을 `load_regulations()` 조회로 교체 |
| 호재 점수 | `config/catalysts.json` | `src/analysis/recommend.py` | |
| **갭투자 종합점수 공식** | `src/analysis/recommend.py::_apply_gap_scores()` (tier_score 80% + activity 20%) | `recommend.py` docstring, `gap_backtest.py::gap_score_backtest()` docstring, `streamlit_app.py` UI 안내문 | **2026-07-20 수정**: 실제 공식은 이미 2요소(80/20)로 리팩터링됐는데 위 3곳 전부 예전 5요소(25/20/20/20/15%) 설명을 그대로 갖고 있었음. 계산 함수를 바꾸면 이 3곳도 항상 같이 확인할 것 |
| **투자수익 전략 가중치 기본값** (catalyst/tier/prestige) | `config/settings.py::DEFAULT_CATALYST_WEIGHT/TIER_WEIGHT/PRESTIGE_WEIGHT` (0.10/0.70/0.30) | `recommend.py`, `backtest.py`, `streamlit_app.py` 슬라이더·하드코딩 호출 전체 | **2026-07-20 해결**: `apt_backtest()`가 이미 폐기된 7요소 공식을 검증하던 버그를 먼저 고친 뒤(아래 항목 참고), `grid_search_apt(n=6251)`로 실측 — catalyst≈0(0.10과 오차범위), region_score:prestige≈0.7:0.3이 최적 구간(spearman 0.57~0.58). 이 값을 config 상수로 박고 흩어져 있던 7곳 전부 통일. `streamlit_app.py`의 `_invest_sidebar_inputs_UNUSED()`(이름 그대로 미사용 함수)는 안 건드림 |
| **apt_backtest() 점수공식** | `src/analysis/recommend.py::recommend_investment_focus()` (region_score×tw/total + prestige_score×pw/total, 2026-05 단순화) | `src/analysis/backtest.py::apt_backtest()` | **2026-07-20 해결**: 백테스트가 이미 운영에서 폐기된 7요소 가중합(rs_score 30%+jeonse_accel 25%+supply_pressure 10%+population 10%+train_growth 15%+recent_deals 10%)을 그대로 검증하고 있었음 — "아무도 안 쓰는 공식"을 최적화하고 있었던 것. 실제 운영 공식으로 교체. 무거운 신호 계산과 가중치 재계산을 분리(`_apt_backtest_base`/`_apt_backtest_score`)해서 그리드서치 245콤보가 수시간→수분으로 단축됨 |
| tier_score×0.6 + market_score×0.4 조합 | `recommend.py:357`, `recommend.py:386` (두 함수에 각각 리터럴 복붙) | `_apply_gap_scores()`, `_apply_rental_scores()` | 낮은 우선순위 — 현재는 값이 같아서 문제 없지만 한쪽만 튜닝되면 갈라질 구조. 상수화 검토 |

## 알려진 잔여 항목 (일부러 안 건드림)

- `src/ui/streamlit_app.py`가 5112줄 단일 파일 — claude-supervisor 원칙4(300줄 초과 시 모듈화)
  위반. 오늘 발견했지만 이 세션의 요청 범위(크로스커팅 연계 맵) 밖이라 별도 논의 필요.
- `src/analysis/loan.py` 모듈 docstring이 "2025-10-15 대책" → "2026-07 대책(확정판)" 순서로
  두 블록 있는데, 실제로는 정책 변경 이력을 남겨둔 체인지로그 구조라 모순은 아님. 다만
  파일을 처음 읽는 사람이 첫 블록만 보고 구버전 LTV%를 재인용할 위험은 있음.
- `src/ui/streamlit_app.py::_invest_sidebar_inputs_UNUSED()`(1255줄) — 이름 그대로 어디서도
  호출 안 되는 죽은 함수. 내부에 tier_weight=0.6 같은 stale 기본값이 있지만 실행 안 되므로
  방치. 삭제는 요청 시에만.

## 신규 기능 추가 시 체크리스트

1. 이 표에서 비슷한 개념이 이미 있는지 검색한다.
2. 있으면 그 SSOT(`config/` 또는 기존 계산 함수)를 재사용한다.
3. 계산 공식을 바꾸면, 그 공식을 언급하는 모든 docstring·UI 텍스트를 grep으로 찾아 같이 고친다.
4. 새 정책 상수면 `config/settings.py` 또는 `config/*.json`에 추가하고 이 표에 행을 추가한다.
