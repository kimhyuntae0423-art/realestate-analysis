# 1인 부동산 분석 하우스 — 프로젝트 컨텍스트

이 저장소는 사용자(개인 투자자)의 한국 부동산 데이터 수집·분석·의사결정 보조 도구입니다.
국토부/한국부동산원/KOSIS 등 공공 API로 실거래가를 수집하고,
Streamlit 대시보드 + 분석 모듈로 지역별 시세·갭·수익률·호재 점수를 제공합니다.

---

## 절대 원칙 (모든 분석 공통)

1. **"사라/팔아라/무조건 오른다"고 확정적으로 말하지 않는다.** 분석 보조다.
2. **데이터 ≠ 의견** — 두 가지를 구분해서 출력한다.
3. **모르는 숫자는 만들지 않는다.** 모르면 "확인 필요"로 명시.
4. **반대 논리(하락 시나리오)를 반드시 함께 제시한다.**
5. **레버리지·대출 관련 수치는 개인 상황마다 다름** — 일반론만 제시.
6. 매 분석 마지막에 다음 문장을 포함:
   > 이 분석은 투자 판단을 돕기 위한 의사결정 보조 자료이며, 최종 매수·매도 결정은 공식 실거래 데이터, 현장 확인, 금융·세무 전문가 상담 후 내려야 합니다.

---

## 의사결정 프레임워크: WRAP

- **W** Widen Options — 이 단지만 보지 말고 인근 단지·타 지역·전세 대안 함께
- **R** Reality-test Assumptions — "호재가 있으면 오른다"는 가정을 데이터로 검증·반박
- **A** Attain Distance — 매수 결정 전 감정 분리 질문 ("지금 FOMO인가?")
- **P** Prepare to Be Wrong — 틀릴 조건, 손절/출구 전략 명시

---

## 프로젝트 구조

```
부동산/
├── config/
│   ├── settings.py          # API 키, DB 경로, 디렉터리 설정
│   ├── regions.json         # 법정동 코드 목록
│   ├── catalysts.json       # 호재 점수 시스템
│   ├── supply.json          # 입주물량 데이터
│   ├── region_tiers.json    # 지역 티어 분류
│   └── loan_regulations.json # 대출 규제 정보
├── data/
│   ├── raw/                 # API 수집 원본 캐시 (JSON/XML)
│   ├── processed/           # SQLite DB (realestate.db)
│   └── reports/             # 생성된 엑셀/PDF 보고서
├── src/
│   ├── collectors/          # 외부 API 호출
│   │   ├── molit_api.py     # 국토부 실거래가 (매매/전세/월세)
│   │   ├── kosis_api.py     # 통계청 KOSIS (인구/세대수)
│   │   └── kakao_api.py     # 카카오 (좌표·입지 점수)
│   ├── parsers/             # XML/JSON → dict 정규화
│   ├── database/
│   │   ├── models.py        # SQLAlchemy 모델
│   │   └── repository.py    # CRUD 추상화
│   ├── analysis/
│   │   ├── price_trend.py   # 가격 추이 (평균/중위/평당가)
│   │   ├── gap_analysis.py  # 매매-전세 갭
│   │   ├── yield_calc.py    # 임대 수익률
│   │   ├── ranking.py       # 지역별·단지별 랭킹
│   │   ├── recommend.py     # 투자 추천 점수
│   │   ├── forecast.py      # Prophet 시계열 예측 (6개월)
│   │   ├── forward_signals.py # 선행 지표
│   │   ├── macro.py         # 거시 지표
│   │   ├── supply.py        # 입주물량 분석
│   │   ├── location.py      # 카카오 입지 점수
│   │   ├── scenario.py      # 시나리오 분석
│   │   ├── backtest.py      # 백테스트
│   │   ├── loan.py          # 대출 계산
│   │   └── costs.py         # 거래비용 계산
│   ├── reports/
│   │   └── excel_report.py  # 엑셀 보고서 생성
│   └── ui/
│       └── streamlit_app.py # Streamlit 대시보드
├── scripts/
│   ├── init_db.py           # DB 초기화
│   ├── collect_data.py      # 일괄 데이터 수집
│   └── run_backtest.py      # 백테스트 실행
└── .env                     # API 키 (로컬 전용, git 제외)
```

---

## 데이터 소스 및 신뢰성 위계

### 사용 중인 API (공공/무료)
| 출처 | 용도 | 설정 위치 |
|---|---|---|
| 국토부 실거래가 (data.go.kr) | 아파트 매매/전세/월세 | `config/settings.py` MOLIT_BASE |
| 통계청 KOSIS | 인구·세대수 | `src/collectors/kosis_api.py` |
| 카카오 로컬 API | 좌표 변환·입지 점수 | `src/collectors/kakao_api.py` |

### 신뢰성 위계 (분석 시 우선순위)
1. 국토부 실거래가 (실제 계약 데이터) → 2. 한국부동산원 시세지수 →
3. 통계청 KOSIS → 4. 정부·협회 통계 → 5. 주요 언론 →
**커뮤니티/호가/루머는 절대 핵심 근거로 사용하지 않는다.**

---

## 주요 법정동 코드 (자주 쓰는 것)

| 코드 | 지역 |
|---|---|
| 11680 | 서울 강남구 |
| 11650 | 서울 서초구 |
| 11710 | 서울 송파구 |
| 11440 | 서울 마포구 |
| 11170 | 서울 용산구 |
| 41135 | 경기 성남시 분당구 |

전체 목록: `config/regions.json`

---

## 코드 작업 원칙

- **데이터 파이프라인 변경 시** `scripts/collect_data.py` 또는 `src/collectors/` 수정
- **분석 로직 변경 시** `src/analysis/` 하위 모듈 수정
- **대시보드 UI 변경 시** `src/ui/streamlit_app.py` 수정
- **새 지역 추가 시** `config/regions.json`에 법정동 코드 추가
- API 키는 `.env`에만 저장, 코드에 하드코딩 절대 금지
- DB는 SQLite (`data/processed/realestate.db`) — 스키마 변경 시 `src/database/models.py`

---

## 실행 방법 (참고)

```powershell
# DB 초기화 (최초 1회)
python scripts/init_db.py

# 데이터 수집 (강남구 12개월)
python scripts/collect_data.py --region 11680 --months 12

# 대시보드 (로컬)
streamlit run src/ui/streamlit_app.py

# 대시보드 (배포)
# https://realestate-analysis-p6jdtbkpo6u245ekj4cy4d.streamlit.app/

# 엑셀 보고서
python -m src.reports.excel_report --region 11680 --output report.xlsx
```
