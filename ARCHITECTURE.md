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
| **매크로 타이밍 최소 커버리지** | `config/settings.py::MARKET_TIMING_MIN_COVERAGE` (0.60) | `src/analysis/market_timing.py::market_timing_signal()`, `src/ui/shared/market_timing_panel.py` 미달 안내문, `tests/unit/test_market_timing.py` | **2026-09-10 신설**: ECOS 키가 없어 5개 신호 중 4개(가중치 0.65)가 null 인데, 기존 코드가 살아있는 가중치로 **재정규화**해 KB 매수우위지수(0.35) 하나의 값을 종합점수 76.9 로 표시하고 있었다. 근거 65%가 없는데 화면은 정상 — CLAUDE.md 절대원칙 3 위반. 커버리지 미달 시 `score=None` + `missing` 목록 반환으로 변경. 신호 가중치를 바꾸면 이 임계값이 여전히 타당한지 같이 볼 것 |
| 금액 → "N.NN억/N만" 표기 | `src/ui/pages/portfolio/context.py::_eok` (소수점 2자리) | `portfolio/` 패키지 5개 탭 전체 | 2026-09-09 분리 시 SSOT로 승격. `src/analysis/portfolio_strategy.py:17`에 **소수점 1자리** 판이 따로 있음 — 자리수가 달라 일부러 통합하지 않았다(통합하면 화면 표기가 바뀜). 표기를 바꿀 일이 생기면 두 곳을 같이 볼 것 |
| tier_score×0.6 + market_score×0.4 조합 | `recommend.py:357`, `recommend.py:386` (두 함수에 각각 리터럴 복붙) | `_apply_gap_scores()`, `_apply_rental_scores()` | 낮은 우선순위 — 현재는 값이 같아서 문제 없지만 한쪽만 튜닝되면 갈라질 구조. 상수화 검토 |
| **추천 매매가(trade_median) 기준 기간** | `src/analysis/recommend.py::_trade_agg()`/`_recent_window()` (최근 `trade_months`개월 median → 없으면 `fallback_months`(기본 3개월) → 그래도 없으면 전체기간, 3단계 fallback) | `recommend_gap_investment/rental_yield/investment_focus()` 3개 전략 전부, `src/ui/shared/cache.py` 3개 `_cached_*` 래퍼, `src/ui/pages/invest.py` "현재 매매가 기준 기간" 슬라이더 | **2026-09-20 신설**: `recommend_buy_outright`·`recommend_investment_focus`가 분석기간(months, 기본 12·24개월) 전체 median을 그대로 매매가로 써서, 최근 급등한 단지의 추천가가 실제 호가보다 훨씬 낮게 표시되던 문제(갭투자·임대수익은 이미 `trade_months=3` 최근창을 쓰고 있어 두 전략만 어긋나 있었음)를 수정. `_trade_agg()` 공용 사용으로 통일하고 분석기간(months)과 별개 슬라이더로 분리. 기본값을 `trade_months=3` → 2개월 → **1개월**로 재조정했는데, 1개월 창에 거래가 없는 단지가 곧장 분석기간 전체(12~24개월) median으로 떨어지면 그 값이 현실과 괴리가 커서(오래된 가격까지 섞임) `_trade_agg`에 **중간 fallback_months=3개월 단계**를 추가 — trade_months 창 → 3개월 창 → 전체기간 순으로 시도. `invest.py` 검색폼의 준공연도 기본값도 같이 조정: 하한 `이번해-10년` → **2000년**(분양권 포함 더 넓게 탐색). 전용면적 기본값은 80~110㎡(전용면적을 그대로 3.3㎡/평으로 환산한 값)이 실제 시장 '평형' 표기(공급면적 기준, 전용 84㎡=34평형·전용 59㎡=24~25평형)와 달라 24평형이 걸러지는 문제가 있어 **60~85㎡**(국민주택규모 상한 기준)로 수정. **같은 날 `recommend_buy_outright`(자가매입) 전략 자체를 완전 제거** — `backtest.py`가 이미 문서화한 대로 저평가 기준 점수가 다중 시점 백테스트에서 ρ=−0.61(음의 상관)로 기각되어 있었고 `invest.py` 메인 선택지에서도 이미 빠져 죽은 코드였음(`portfolio/tab_listings.py`에만 선택지로 남아있었음); `recommend.py`/`cache.py`/`shared/__init__.py`/`invest_recommend.py`/`portfolio/tab_listings.py`/`columns_spec.py`(value_ratio·region_median_ppp)/테스트에서 전부 제거 |

## 알려진 잔여 항목 (일부러 안 건드림)

- ~~`src/ui/streamlit_app.py`가 5112줄 단일 파일~~ → 해소됨. `streamlit_app.py`(45줄) +
  `src/ui/pages/`(페이지별) + `src/ui/shared/`(공용 헬퍼)로 분리 완료.
  2026-09-09에 마지막 남은 `pages/portfolio.py`(1065줄)를 `pages/portfolio/` 패키지
  (입력 UI + 탭 5개 + 공용 컨텍스트)로 분리. 순수 이동이라 렌더 결과는 분리 전과
  동일함을 4개 경로 × 767줄 출력 대조로 확인.
- 300줄 초과가 남아 있는 UI 파일: `invest_compare.py`(656), `invest_recommend.py`(636),
  `backtest.py`(518), `region.py`(470), `portfolio/inputs.py`(389),
  `portfolio/tab_payout.py`(343). claude-supervisor 원칙4 기준으로는 여전히 위반이지만,
  각각 응집도 있는 단위(입력 폼 하나 / 탭 하나)라 더 쪼개면 인위적이 됨 — 별도 논의 대상.
- `src/analysis/loan.py` 모듈 docstring이 "2025-10-15 대책" → "2026-07 대책(확정판)" 순서로
  두 블록 있는데, 실제로는 정책 변경 이력을 남겨둔 체인지로그 구조라 모순은 아님. 다만
  파일을 처음 읽는 사람이 첫 블록만 보고 구버전 LTV%를 재인용할 위험은 있음.

## 신규 기능 추가 시 체크리스트

1. 이 표에서 비슷한 개념이 이미 있는지 검색한다.
2. 있으면 그 SSOT(`config/` 또는 기존 계산 함수)를 재사용한다.
3. 계산 공식을 바꾸면, 그 공식을 언급하는 모든 docstring·UI 텍스트를 grep으로 찾아 같이 고친다.
4. 새 정책 상수면 `config/settings.py` 또는 `config/*.json`에 추가하고 이 표에 행을 추가한다.
