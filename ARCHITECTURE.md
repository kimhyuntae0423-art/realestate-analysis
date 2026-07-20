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
| **투자수익 전략 가중치 기본값** (catalyst/tier/prestige) | ⚠️ **미해결 — SSOT 없음** | `recommend.py:602-604`(0.10/0.70/0.30), `streamlit_app.py:119-121`(-/0.6/0.10), `streamlit_app.py` 슬라이더 3세트(탭마다 tier 0.3~0.7로 제각각), `streamlit_app.py:2826`(0.10/0.7 하드코딩 호출), `scripts/run_backtest.py:42-43`(--cw/--tw 0.30/0.30) | 아직 안 고침 — 뭐가 진짜 "권장값"인지 확인 필요(grid_search_region/grid_search_apt로 데이터 기반 산출 가능). 다음에 다시 볼 때 반드시 처리 |
| tier_score×0.6 + market_score×0.4 조합 | `recommend.py:357`, `recommend.py:386` (두 함수에 각각 리터럴 복붙) | `_apply_gap_scores()`, `_apply_rental_scores()` | 낮은 우선순위 — 현재는 값이 같아서 문제 없지만 한쪽만 튜닝되면 갈라질 구조. 상수화 검토 |

## 알려진 잔여 항목 (일부러 안 건드림)

- `src/ui/streamlit_app.py`가 5112줄 단일 파일 — claude-supervisor 원칙4(300줄 초과 시 모듈화)
  위반. 오늘 발견했지만 이 세션의 요청 범위(크로스커팅 연계 맵) 밖이라 별도 논의 필요.
- `src/analysis/loan.py` 모듈 docstring이 "2025-10-15 대책" → "2026-07 대책(확정판)" 순서로
  두 블록 있는데, 실제로는 정책 변경 이력을 남겨둔 체인지로그 구조라 모순은 아님. 다만
  파일을 처음 읽는 사람이 첫 블록만 보고 구버전 LTV%를 재인용할 위험은 있음.

## 신규 기능 추가 시 체크리스트

1. 이 표에서 비슷한 개념이 이미 있는지 검색한다.
2. 있으면 그 SSOT(`config/` 또는 기존 계산 함수)를 재사용한다.
3. 계산 공식을 바꾸면, 그 공식을 언급하는 모든 docstring·UI 텍스트를 grep으로 찾아 같이 고친다.
4. 새 정책 상수면 `config/settings.py` 또는 `config/*.json`에 추가하고 이 표에 행을 추가한다.
