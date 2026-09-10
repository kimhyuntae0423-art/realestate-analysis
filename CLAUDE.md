# 1인 부동산 분석 하우스 — 프로젝트 컨텍스트

이 저장소는 사용자(개인 투자자)의 한국 부동산 데이터 수집·분석·의사결정 보조 도구입니다.
국토부/한국부동산원/KOSIS 등 공공 API로 실거래가를 수집하고,
Streamlit 대시보드 + 분석 모듈로 지역별 시세·갭·수익률·호재 점수를 제공합니다.

## ⚠️ 절대 규칙: 크로스커팅 값·계산식은 `ARCHITECTURE.md`부터 확인

정책 상수(config/)나 점수 계산 공식을 새로 만들거나 바꾸기 전에 `ARCHITECTURE.md`의
연계 맵을 먼저 확인한다. 계산 공식을 바꾸면 그걸 설명하는 모든 docstring·UI 텍스트를
같이 고친다 — 2026-07-20에 갭투자 점수 공식이 리팩터링된 뒤에도 UI 안내문·docstring
3곳이 예전 공식(5요소 25/20/20/20/15%)을 그대로 갖고 있던 걸 발견해서 만든 규칙.

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
│   │   ├── ecos.py          # 한국은행 ECOS (금리 등 거시지표)
│   │   ├── kb_price.py      # KB 시세지수
│   │   ├── kb_sentiment.py  # KB 매수우위지수 등 심리지표
│   │   ├── zigbang_api.py   # 직방 (단지 정보)
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
| 통계청 KOSIS | 인구이동(population_flow) | `scripts/backfill_population_api.py`, `scripts/import_kosis_csv.py` |
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
| 41597 | 경기 화성시 동탄구 (2026-07 신규 규제+토지허가) |
| 41463 | 경기 용인시 기흥구 (2026-07 신규 규제+토지허가) |
| 41310 | 경기 구리시 (2026-07 신규 규제+토지허가) |

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

# 대시보드 (로컬 — 유일한 실행 경로)
.venv\Scripts\python.exe -m streamlit run src/ui/streamlit_app.py

# 엑셀 보고서
python -m src.reports.excel_report --region 11680 --output report.xlsx
```

---

## 운영 구성 (2026-09-10 확정 — 로컬 전용)

**클라우드를 쓰지 않는다.** 배포 Streamlit·Supabase·GitHub Actions 수집을 전부 접었다.
아래는 그 결정의 근거이므로, 다시 클라우드로 가려 하기 전에 먼저 읽을 것.

| 접은 것 | 이유 |
|---|---|
| GitHub Actions 주간 수집 | 러너에서 `apis.data.go.kr` 접속이 `ConnectTimeoutError`로 전부 실패(20초×3회 재시도 → 30분 job 타임아웃 초과). 같은 API가 국내망 PC에서는 정상. 2026-08-10 실행은 1분 33초에 성공했으므로 그 사이 data.go.kr 쪽이 바뀐 것으로 보인다. `workflow_dispatch`만 남겨둠 |
| Supabase + 배포 Streamlit | 무료 플랜 한도 500MB인데 DB가 이미 **562MB**(apt_rent 377 + apt_trade 175). 실거래 이력이 2024-06~2026-09 **28개월뿐**인데, 백테스트는 train 12 + test 12 = **최소 24개월**을 요구하고 가설검증은 대부분 `months=60`이 기본값이다. 즉 한도에 맞춰 12개월로 줄이면 검증이 아예 불가능해지고, 배포 앱의 백테스트·실험실 페이지가 잘린 데이터로 **조용히 다른 결과**를 내게 된다. Pro(월 $25) 아니면 성립하지 않아 로컬 전용을 택함 |

**정기 갱신**: Windows 작업 스케줄러 `RealEstate Weekly Refresh` — 매주 월요일 09:00,
`scripts/run_scheduled_refresh.bat` 실행. `StartWhenAvailable`(놓친 실행 따라잡기) +
`WakeToRun`(절전 해제) 설정. 실거래 증분 수집 → KB/ECOS 갱신 → 가설 전체 재검증.

**사내망 SSL**: 프록시가 TLS를 가로채 자체서명 CA로 재서명하므로 certifi 만으로는
`CERTIFICATE_VERIFY_FAILED`로 전부 실패한다(2026-05 수집 중단의 원인).
`src/utils/ca_bundle.py::ensure_ca_bundle()`이 실행 시마다 Windows 인증서 저장소를
PEM으로 내보내 `REQUESTS_CA_BUNDLE`에 물린다. `verify=False`는 쓰지 않는다.

**`.venv`는 Python 3.12 여야 한다.** 3.14(OpenSSL 3.5.x)는 사내 CA를
`Missing Authority Key Identifier`로 거부해서 CA 번들을 아무리 잘 만들어도 실패한다.
`.venv`를 다시 만들 일이 있으면 반드시 `py -3.12 -m venv .venv`.

**검증 상태 (2026-09-10)**: 실거래 2024-06~2026-09 / apt_trade 598,487 · apt_rent 1,316,295.
`ecos_series` 568행(6개 시리즈). `population_flow`·`supply_schedule`은 0행 —
전자는 KOSIS 키 미발급, 후자는 KOSIS가 시군구 단위 API를 안 줘서 CSV 수동 업로드만 가능.
둘 다 `recommend.py`의 점수 산식에서 제외돼 있어 추천 결과에는 영향 없음.
