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

전체 파일 목록이 아니라 **어디를 고쳐야 하는지 찾는 지도**다. 파일이 늘면 개별 파일명보다
디렉터리 역할 설명을 먼저 맞춘다.

```
realestate-analysis/
├── ARCHITECTURE.md          # 크로스커팅 연계 맵 — 정책상수·계산공식 고치기 전 필독
├── config/
│   ├── settings.py          # API 키, DB 경로, 정책 상수(가중치·임계값) SSOT
│   ├── regions.json         # 법정동 코드 목록
│   ├── region_coords.json   # 시군구 좌표
│   ├── region_tiers.json    # 지역 티어 분류 (5단계 100/80/60/40/20)
│   ├── catalysts.json       # 호재 점수 시스템 (수동 큐레이션)
│   ├── supply.json          # 입주물량 데이터
│   ├── jeonse_bands.json    # 전세가율 구간
│   └── loan_regulations.json # 대출 규제 정보 (LTV·한도·DSR)
├── data/
│   ├── raw/                 # API 수집 원본 캐시 (JSON/XML)
│   ├── processed/           # SQLite DB (realestate.db) — SSOT
│   ├── experiments/         # hypothesis_log.json (가설 재검증 이력, append-only)
│   └── reports/             # 생성된 엑셀/PDF 보고서
├── src/
│   ├── collectors/          # 외부 API 호출 (molit_api·ecos·kb_price·kb_sentiment·
│   │                        #   kakao_api·zigbang_api)
│   ├── parsers/             # XML/JSON → dict 정규화
│   ├── database/            # models.py(SQLAlchemy) + repository.py(CRUD 추상화)
│   ├── analysis/            # 분석 로직 — 아래 3계열
│   │   ├── (시세·추천)      # price_trend·gap_analysis·yield_calc·ranking·recommend·
│   │   │                    #   region_momentum·fair_value·fair_value_reverse·forecast
│   │   ├── (신호·거시)      # forward_signals·macro·market_timing·supply·location·scenario
│   │   ├── (검증)           # backtest·gap_backtest·hypothesis_lab +
│   │   │                    #   hypothesis_tests{,_cycles,_ecos,_ecos_rate,_kb,
│   │   │                    #   _valuation,_spillover}
│   │   └── (비용·세금)      # loan·costs·capital_gains_tax
│   ├── reports/             # excel_report.py
│   ├── utils/               # ca_bundle.py(사내망 SSL)·logger.py
│   └── ui/
│       ├── streamlit_app.py # 라우팅만 (42줄)
│       ├── pages/           # 페이지별 화면 (invest·region·backtest·lab·undervalued 등)
│       └── shared/          # 공용 헬퍼 (cache·format·columns_spec·sidebar_nav 등)
├── scripts/
│   ├── init_db.py           # DB 초기화
│   ├── collect_data.py      # 일괄 데이터 수집
│   ├── scheduled_refresh.py # 정기 갱신 본체 (작업 스케줄러가 .bat 경유로 호출)
│   ├── migrate_to_supabase.py # 로컬 SQLite → Supabase 단방향 동기화
│   ├── run_backtest.py      # 백테스트 실행
│   ├── quarterly_strategy_check.py # 전략 분기 재검증
│   └── backfill_*.py / import_kosis_csv.py / export_summary.py
├── tests/                   # 262개 (pytest)
└── .env                     # API 키 (로컬 전용, git 제외)
```

**UI를 고칠 때**: `streamlit_app.py`는 라우팅뿐이다. 화면 내용은 `src/ui/pages/` 아래
해당 페이지 파일을, 여러 페이지가 쓰는 표기·캐시·컬럼정의는 `src/ui/shared/`를 고친다.

---

## 데이터 소스 및 신뢰성 위계

### 사용 중인 API (공공/무료)
| 출처 | 용도 | 설정 위치 | 상태 |
|---|---|---|---|
| 국토부 실거래가 (data.go.kr) | 아파트 매매/전세/월세 | `config/settings.py` MOLIT_BASE | 정상 (`apt_trade`/`apt_rent`) |
| 한국은행 ECOS | 기준금리·기대인플레·M1/M2·주담대잔액, 부동산원 실거래가지수(`kab_apt_price_idx_*`) | `src/collectors/ecos.py`, `.env` `ECOS_API_KEY` | 정상 (`ecos_series`, 11개 시리즈) |
| KB 부동산 | 가격지수(`kb_price_series`), 매수우위지수(`kb_sentiment_index`) | `src/collectors/kb_price.py`, `src/collectors/kb_sentiment.py` | 정상 (키 불필요) |
| 카카오 로컬 API | 좌표 변환·입지 점수 | `src/collectors/kakao_api.py` | 정상 |
| 통계청 KOSIS | 인구이동(`population_flow`) | `scripts/backfill_population_api.py`, `scripts/import_kosis_csv.py` | **미동작** — `KOSIS_API_KEY` 미발급, 0행 |

위 5개 중 국토부·ECOS·KB는 `scripts/scheduled_refresh.py`가 주 1회 자동 재수집한다.
입주물량(`supply_schedule`)은 KOSIS가 시군구 단위 API를 안 줘서 CSV 수동 업로드만 가능 —
자동화 불가라 정기 갱신에서 빠져 있다.

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
| 41595 | 경기 화성시 병점구 (동탄 스필오버 가설 대상) |
| 41370 | 경기 오산시 (동탄 스필오버 가설 대상) |
| 41220 | 경기 평택시 (삼성 평택캠퍼스·지제역, 동탄 스필오버 가설 대상) |

전체 목록: `config/regions.json`

---

## 코드 작업 원칙

- **데이터 파이프라인 변경 시** `scripts/collect_data.py` 또는 `src/collectors/` 수정
- **분석 로직 변경 시** `src/analysis/` 하위 모듈 수정
- **대시보드 UI 변경 시** `src/ui/pages/`(해당 페이지) 또는 `src/ui/shared/`(공용 헬퍼) 수정
  — `streamlit_app.py`는 라우팅뿐이므로 여기에 화면 로직을 넣지 않는다
- **새 지역 추가 시** `config/regions.json`에 법정동 코드 추가
- **새 가설 추가 시** `src/analysis/hypothesis_tests_*.py`에 함수 작성 +
  `hypothesis_lab.get_all_hypotheses()`에 등록 + `tests/unit/`에 테스트 동반
- API 키는 `.env`에만 저장, 코드에 하드코딩 절대 금지
- DB는 SQLite (`data/processed/realestate.db`) — 스키마 변경 시 `src/database/models.py`
- **`fetch_trades_df()`가 빈 결과일 때 전 컬럼을 object dtype으로 반환한다.** 여러 지역을
  각각 조회해 `pd.concat`으로 합칠 때 데이터 없는 지역이 섞이면 `price_per_pyeong`까지
  object로 승격돼, 뒤에서 `spearmanr`이 numpy 내부에서 터진다(2026-09-21 실제 발생).
  concat 전에 `if not f.empty`로 걸러낼 것

---

## 실행 방법 (참고)

```powershell
# DB 초기화 (최초 1회)
python scripts/init_db.py

# 데이터 수집 (강남구 12개월)
python scripts/collect_data.py --region 11680 --months 12

# 대시보드 (로컬 — 로컬 SQLite를 읽는다)
.venv\Scripts\python.exe -m streamlit run src/ui/streamlit_app.py

# 정기 갱신 수동 실행 (수집 → KB/ECOS → 가설 재검증 → Supabase 동기화)
.\scripts\run_scheduled_refresh.bat

# 가설 재검증만 따로 (데이터 수집 없이)
.venv\Scripts\python.exe -c "from src.analysis.hypothesis_lab import run_all_and_log; run_all_and_log()"

# 엑셀 보고서
python -m src.reports.excel_report --region 11680 --output report.xlsx
```

배포 Streamlit은 같은 `src/ui/streamlit_app.py`를 돌리지만 Supabase를 읽는다
(`DATABASE_URL`을 Streamlit Cloud secrets로 주입). 코드는 하나이고 데이터 출처만 다르다.

---

## 운영 구성 (2026-09-21 기준 — 로컬 수집 + 클라우드 조회 복제본)

**수집·분석은 로컬 PC에서만 한다. 조회는 배포 Streamlit에서도 된다.**
로컬 SQLite가 SSOT이고, 거기서 Supabase로 **단방향**으로 밀어넣는다.
배포 Streamlit은 Supabase를 읽기만 한다.

| 구성 요소 | 상태 | 근거 |
|---|---|---|
| Windows 작업 스케줄러 주간 수집 | **운영 중** (유일한 수집 경로) | 아래 "정기 갱신" 참고 |
| Supabase 조회 전용 복제본 + 배포 Streamlit | **운영 중** (2026-09-10 복구, 커밋 `93948a2`) | 아래 참고 |
| GitHub Actions 주간 수집 | **접음** (`workflow_dispatch`만 남김) | 러너에서 `apis.data.go.kr` 접속이 `ConnectTimeoutError`로 전부 실패(20초×3회 재시도 → 30분 job 타임아웃 초과). 같은 API가 국내망 PC에서는 정상. 2026-08-10 실행은 1분 33초에 성공했으므로 그 사이 data.go.kr 쪽이 바뀐 것으로 보인다 |

**Supabase를 접었다가 되살린 경위 — 같은 오판을 반복하지 않기 위해 남긴다.**
2026-09-10 낮에는 "DB가 562MB라 무료 한도 500MB를 넘으니, 데이터를 12개월로 줄여야 하는데
그러면 백테스트(최소 24개월)·가설검증(기본 60개월)이 망가진다"는 이유로 로컬 전용을
택했다. **총량만 보고 내린 잘못된 결론이었다.** 같은 날 실측해보니 본체는 267MB뿐이고
인덱스가 324MB였으며, 그중 `uq_trade`(57MB)+`uq_rent`(138MB) 중복방지 제약이 195MB였다.
이 제약은 upsert의 `ON CONFLICT` 대상일 뿐 **조회에는 안 쓰인다.** 제거하니 562MB→385MB로
줄어, 데이터를 한 줄도 자르지 않고 28개월 전체를 유지한 채 한도 안에 들어갔다.
→ **용량 문제를 만나면 행 수를 줄이기 전에 인덱스 비중을 먼저 실측할 것.**

동기화는 `scripts/migrate_to_supabase.py::run_sync()`이고 `scheduled_refresh.py` 말미에
붙어 있다. 제약이 없으니 `ON CONFLICT`를 못 써서, 건수가 다른 달만 통째로 지우고 다시
넣는다(중복 제거는 로컬 SQLite가 이미 함). 실패해도 로컬 결과는 유효하므로 예외를 삼킨다.
주 1회 접속이 생기므로 Supabase 무료플랜의 "7일 미사용 자동 정지"도 함께 막힌다.

⚠️ **용량 주의**: 2026-09-21 동기화 후 Supabase **456MB / 한도 500MB**. 9/14에 450MB였으니
주당 약 6MB씩 늘고 있어 **7~8주 내 한도에 닿는다.** 그때는 `--keep-months 24`로 전환한다
(약 343MB로 고정, 백테스트 최소 요건 24개월은 유지됨). 이 수치는 갱신 로그 말미의
"Supabase 크기" 줄에서 매번 확인할 수 있다.

`SUPABASE_DATABASE_URL`은 `DATABASE_URL`과 분리돼 있다 — PC의 수집·분석은 계속 로컬
SQLite에 하고 동기화 대상만 따로 지정하기 위함이다. 배포 앱 쪽 키는 로컬 `.env`가 아니라
Streamlit Cloud secrets에 있다(`.streamlit/secrets.toml`은 git 제외이며 로컬에는 없음).

**정기 갱신**: Windows 작업 스케줄러 `RealEstate Weekly Refresh` — 매주 월요일 09:00,
`scripts/run_scheduled_refresh.bat` 실행. `StartWhenAvailable`(놓친 실행 따라잡기) +
`WakeToRun`(절전 해제) 설정. 실거래 증분 수집(`--months 3`) → KB/ECOS 갱신 →
가설 전체 재검증 → Supabase 동기화. 소요 약 13분.

`StartWhenAvailable`은 실제로 동작한다 — 2026-09-21에 09:00 PC가 꺼져 있어 실행이
누락됐고, PC 가용 직후 11:04:55에 자동으로 따라잡아 실행됐다. 따라서 `LastRunTime`이
지난주로 보이고 `NextRunTime`이 다음 주로 넘어가 있어도 **"이번 주가 건너뛰어졌다"고
단정하지 말 것** — 아직 따라잡기 대기 중일 수 있다. 실제 실행 여부는
`logs/scheduled_refresh.log` 말미의 "정기 갱신 완료"와 DB 수정시각으로 판단한다.

⚠️ **수동 실행 시 주의**: 스케줄러 실행분이 돌고 있으면 `.bat`이 로그 파일 append 잠금에
걸려 `The process cannot access the file...`로 죽는다(python은 아예 시작도 못 한다).
수동 실행 전에 `Get-Process python`으로 `scripts.scheduled_refresh`가 이미 도는지 볼 것.

**사내망 SSL**: 프록시가 TLS를 가로채 자체서명 CA로 재서명하므로 certifi 만으로는
`CERTIFICATE_VERIFY_FAILED`로 전부 실패한다(2026-05 수집 중단의 원인).
`src/utils/ca_bundle.py::ensure_ca_bundle()`이 실행 시마다 Windows 인증서 저장소를
PEM으로 내보내 `REQUESTS_CA_BUNDLE`에 물린다. `verify=False`는 쓰지 않는다.

**`.venv`는 Python 3.12 여야 한다.** 3.14(OpenSSL 3.5.x)는 사내 CA를
`Missing Authority Key Identifier`로 거부해서 CA 번들을 아무리 잘 만들어도 실패한다.
`.venv`를 다시 만들 일이 있으면 반드시 `py -3.12 -m venv .venv`.

**검증 상태 (2026-09-21 정기 갱신 직후 실측)**

| 항목 | 값 |
|---|---|
| 실거래 기간 | 2024-06-01 ~ 2026-09-19 (약 28개월) |
| `apt_trade` / `apt_rent` | 604,913 / 1,334,163행 |
| `ecos_series` | 622행 / 11개 시리즈 (`base_rate`, `expected_inflation`, `m1_eop_raw`, `m2_eop_raw`, `m2_eop_sa`, `mortgage_loan_eop`, `kab_apt_price_idx_00/11/26/28/41`) |
| `kb_price_series` / `kb_sentiment_index` | 225 / 52행 |
| `population_flow` / `supply_schedule` | **0행** (아래 참고) |
| 로컬 DB 크기 | 593MB |
| Supabase 복제본 | 456MB (한도 500MB) |
| 매크로 타이밍 | score 61.4, **coverage 1.0, missing 없음** — ECOS 키가 살아 있어 5개 신호 전부 채워짐 |
| 실험실 가설 | 19개 (지지 4 / 기각 1 / 불확실 14) |
| 테스트 | 262개 전부 통과 |

`population_flow`·`supply_schedule`이 0행인 이유: 전자는 `KOSIS_API_KEY` 미발급, 후자는
KOSIS가 시군구 단위 API를 안 줘서 CSV 수동 업로드만 가능. 둘 다 `recommend.py`의 점수
산식에서 제외돼 있어 추천 결과에는 영향 없음. 이 둘에 의존하는 가설 3개
(`supply_glut`, `supply_glut_kb_price`, `population_migration`)는 항상 n=0으로 나온다 —
버그가 아니라 데이터 부재다.

숫자를 갱신할 때는 `logs/scheduled_refresh.log` 말미가 아니라 DB를 직접 세어서 쓸 것
(로그의 "N행 교체"는 Supabase에 밀어넣은 최근 3개월치이지 전체 행수가 아니다).
