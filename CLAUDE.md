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
│   │   ├── (신호·거시)      # forward_signals·macro·market_timing·supply·location·scenario·
│   │   │                    #   co_movement(지역 동조)
│   │   ├── (검증)           # backtest·gap_backtest·hypothesis_lab +
│   │   │                    #   hypothesis_tests{,_cycles,_ecos,_ecos_rate,_kb,
│   │   │                    #   _valuation,_spillover}
│   │   └── (비용·세금)      # loan·costs·capital_gains_tax
│   ├── reports/             # excel_report.py
│   ├── utils/               # ca_bundle.py(사내망 SSL)·logger.py
│   └── ui/
│       ├── streamlit_app.py # 라우팅만 (42줄)
│       ├── pages/           # 페이지별 화면 (invest·region·backtest·lab 등)
│       └── shared/          # 공용 헬퍼 (cache·format·columns_spec·sidebar_nav 등)
├── scripts/
│   ├── init_db.py           # DB 초기화
│   ├── collect_data.py      # 일괄 데이터 수집
│   ├── scheduled_refresh.py # 정기 갱신 본체 (작업 스케줄러가 .bat 경유로 호출)
│   ├── migrate_to_supabase.py # 로컬 SQLite → Supabase 단방향 동기화
│   ├── bootstrap_supabase.py # 빈 Supabase 프로젝트에 스키마 세우기
│   ├── run_backtest.py      # 백테스트 실행
│   ├── quarterly_strategy_check.py # 전략 분기 재검증
│   └── backfill_*.py / export_summary.py
├── tests/                   # 264개 (pytest)
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

위 4개 전부 `scripts/scheduled_refresh.py`가 주 1회 자동 재수집한다.

🚫 **통계청 KOSIS 수집은 2026-10-08에 영구 중단했다 — 되살리지 말 것.** 인구이동
(`population_flow`)·입주물량(`supply_schedule`) 테이블과 수집기(`backfill_population_api.py`,
`import_kosis_csv.py`), 그 데이터로 돌던 가설 3개·신호 함수 2개를 전부 삭제했다. 근거는
아래 "삭제된 지표" 절 참고. `.env`에 `KOSIS_API_KEY`가 남아 있어도 이 용도로는 쓰지 않는다.
두 테이블이 "없다/0행이다"를 결함으로 보고 복구를 제안하지 말 것 — 의도된 삭제다.

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

**배포 주소**: https://realestate-analysis-p6jdtbkpo6u245ekj4cy4d.streamlit.app/

⚠️ **이 앱은 조회자 인증이 걸려 있어 에이전트가 직접 열어볼 수 없다.** 로그인 없는 요청은
`/`도 `/_stcore/stream`도 303으로 `share.streamlit.io/-/auth/app`에 튕긴다(`/healthz`만
인증 없이 `{"status":"ok"}`를 주는데, 이건 컨테이너가 떴다는 뜻일 뿐 앱이 정상 렌더링
된다는 증거가 아니다 — 스크립트 예외는 웹소켓으로만 전달되므로 HTTP 200 과 공존한다).
→ 배포 앱 상태 확인이 필요하면 사용자에게 화면을 봐 달라고 요청하거나, 임시로 공개
전환을 받아야 한다. 혼자 "200이니 정상"이라고 결론내지 말 것.

배포 쪽 `DATABASE_URL` secret 은 `postgresql+psycopg://`(psycopg 3) 방언이라
`requirements.txt`에 `psycopg[binary]`가 있어야 한다. 로컬 수집·동기화는
`postgresql://`(psycopg2)를 쓰므로 둘 다 필요하다 — 2026-10-07에 psycopg 3 가 빠져
있어서 배포 앱이 `ModuleNotFoundError: psycopg`로 기동 실패했다.
2026-10-08 `psycopg[binary]` 추가분 반영 후 앱 정상 기동 확인(사용자 확인).

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

**빈 프로젝트에 다시 세울 때는 `scripts/bootstrap_supabase.py`를 먼저 돌린다.**
`migrate_to_supabase.py`는 테이블이 있다고 전제하고 데이터만 밀어넣는다. 그리고
`Base.metadata.create_all`은 `uq_trade`/`uq_rent`를 같이 만드는데 이 둘이 195MB라
만들자마자 한도를 넘긴다 — 부트스트랩이 생성 직후 그 둘을 제거한다.

⚠️ **"주 1회 동기화 접속이 자동 정지도 막는다"는 더 이상 사실이 아니다.** 그 접속은
PC가 켜져 있어야 생긴다. 2026-09-22·09-29 정기 갱신이 연속으로 누락되자 7일 무활동으로
프로젝트가 **실제로 자동 정지됐다**(2026-10-07 확인, 정지되면 호스트 DNS까지 내려가
배포 앱이 통째로 죽는다). 그래서 PC와 무관한 경로로 분리했다 —
`.github/workflows/supabase_keepalive.yml`이 월·목에 `SELECT 1`만 날린다.
저장소 시크릿 `SUPABASE_DATABASE_URL`은 2026-10-08에 등록했고 수동 실행으로
`alive 2026-10-08 05:14:22+00` 응답까지 확인했다. GitHub은 저장소가 60일 조용하면
예약 워크플로를 꺼버리므로 오래 손대지 않았으면 Actions 탭을 확인할 것.

⚠️ **성공 표시만 믿지 말고 로그 본문을 볼 것.** 접속 문자열 끝에 개행이 섞여 들어가면
`psql`이 URL을 못 알아보고 로컬 소켓을 찾다 죽는다(2026-10-08 실제로 겪음 — PowerShell
파이프로 시크릿을 넣은 게 원인). 지금은 워크플로가 공백류를 털어내고 접두사를 먼저
검사하지만, 판정 기준은 로그에 `alive <타임스탬프>`가 찍혔는지다.

⚠️ **용량이 빠듯해지면 `VACUUM FULL`을 기억할 것.** 일반 `VACUUM`은 지운 자리를 테이블
안에 재사용 공간으로 들고 있을 뿐이라 `pg_database_size`(= Supabase가 한도를 재는 값)가
안 줄어든다. 2026-10-08에 28→26개월로 줄이고 22만 행을 지웠는데도 469MB 그대로였다가,
`VACUUM FULL`(인덱스까지 재구축) 후 **338MB로 떨어졌다**(22초 소요). 단 도는 동안
배타적 잠금이 걸려 배포 앱 조회가 막히므로, 정기 갱신에 넣지 말고 필요할 때만 수동으로.

**복제 범위는 롤링 창이다 (2026-10-07 변경).** `migrate_to_supabase.SYNC_MONTHS = 26`,
하한은 `sync_from()` 하나로 정하고 **업로드와 창 밖 삭제가 같은 값을 공유한다.**
창 너비가 일정하므로 용량도 385MB 안팎에서 평형을 유지한다.

이전 구조(고정 하한 + `--keep-months` 옵션)는 쓰면 안 된다. 고정 하한 2024-06 에
`--keep-months 24`를 걸면 prune 이 2024-09 이전을 지우는데 업로드는 2024-06 이후를
올리므로, 2024-06~09가 **매주 재전송·재삭제되는 왕복**이 생긴다. 그래서 옵션을 없앴다
(`tests/unit/test_migrate_to_supabase.py`가 이 불변식을 잠근다).

`SUPABASE_DATABASE_URL`은 `DATABASE_URL`과 분리돼 있다 — PC의 수집·분석은 계속 로컬
SQLite에 하고 동기화 대상만 따로 지정하기 위함이다. 배포 앱 쪽 키는 로컬 `.env`가 아니라
Streamlit Cloud secrets에 있다(`.streamlit/secrets.toml`은 git 제외이며 로컬에는 없음).

**실패 알림 (2026-10-08 추가)**: 정기 갱신이 **실패했을 때만** 카카오톡이 온다
(`src/utils/notify.py`). 2026-09에 Supabase 동기화가 2주 내리 실패했는데 로그에만 남아
아무도 몰랐던 게 계기다. 성공 알림은 일부러 안 보낸다 — 매주 오는 "정상"은 곧 안 읽게
되고 그러면 진짜 실패도 같이 묻힌다.

카카오 토큰은 **이 저장소가 다루지 않는다.** `카카오알림` 저장소의 `send-kakao.ps1`을
호출만 한다(경로는 `config/settings.py::KAKAO_SENDER_PS1`, 드라이브 문자가 바뀌면 같은
이름의 환경변수로 덮어쓸 것). 같은 계정 토큰을 두 곳에서 갱신하면 리프레시 토큰 교체
때 한쪽이 무효화되기 때문이다. 외장하드가 빠져 있으면 경고만 남기고 갱신은 계속한다.

이 카카오 알림은 **"돌았는데 실패한 경우"만** 잡는다. PC가 꺼져 작업 자체가
건너뛰어지면 알림도 같이 건너뛴다(2026-09-22·09-29가 그 경우였다). 그 절반은
아래 신선도 감시가 맡는다 — 둘은 짝이다.

**신선도 감시 (2026-10-08 추가)**: `supabase_keepalive.yml`이 접속만 하는 게 아니라
**마지막 적재 이후 며칠인지**를 보고 10일을 넘으면 job을 실패시킨다 → GitHub이 실패
메일을 보낸다. PC와 무관하게 돌므로 "아예 안 돌아간 경우"가 여기서 걸린다. 카카오
토큰을 이 저장소에 복제할 필요가 없어서 메일을 택했다.

기준은 `deal_date`가 아니라 **`apt_trade.created_at`(로컬 삽입 시각)**이다. `deal_date`는
신고 지연이 섞여 오탐이 난다. `created_at` 분포에는 실제로 갱신이 돈 날이 그대로 찍혀
있다(2026-09-21 → 10-06 의 15일 공백이 여기서 바로 보였다).

한계값은 수동 실행 때 입력으로 낮출 수 있다 — **감시가 실제로 걸리는지 확인할 때 쓸 것**:
`gh workflow run supabase_keepalive.yml -f max_stale_days=1` → 실패해야 정상이다.
통과 경로만 확인하면 "항상 통과하는 감시"와 구분이 안 된다.

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

**검증 상태 (2026-10-08 로컬 DB 직접 실측)**

| 항목 | 값 |
|---|---|
| 실거래 기간 | 2021-08 ~ 2026-10 (약 62개월, 최신 거래일 2026-10-05) |
| `apt_trade` / `apt_rent` | 1,011,307 / 3,190,610행 |
| `ecos_series` | 1,060행 / 11개 시리즈 (`base_rate`, `expected_inflation`, `m1_eop_raw`, `m2_eop_raw`, `m2_eop_sa`, `mortgage_loan_eop`, `kab_apt_price_idx_00/11/26/28/41`) |
| `kb_price_series` / `kb_sentiment_index` | 1,064 / 252행 |
| 로컬 DB 크기 | 1,275MB (테이블 6개: `apt_trade`·`apt_rent`·`collection_log`·`ecos_series`·`kb_price_series`·`kb_sentiment_index`) |
| Supabase 복제본 | **338MB / 한도 500MB** (2026-10-08 복구·재동기화·`VACUUM FULL` 후). 복제 창 2024-09~2026-10(26개월), 매매 533,419 / 전월세 1,208,929행 — 로컬 창 안 행수와 일치 확인 |
| 매크로 타이밍 | score 61.4, **coverage 1.0, missing 없음** — ECOS 키가 살아 있어 5개 신호 전부 채워짐 |
| 실험실 가설 | 정기 재검증 **15개** (2026-10-08에 3개 삭제, 아래 참고). 마지막 18개 실행은 2026-10-06 (지지 11 / 기각 2 / 불확실 5). 동탄 스필오버 가설은 결론이 나서 기록용으로만 유지(`hypothesis_tests_spillover.py` docstring) |
| 테스트 | 264개 전부 통과 |

숫자를 갱신할 때는 로그가 아니라 DB를 직접 세어서 쓸 것 — 이 표가 2026-09-21 기준으로
한참 틀어져 있었다(실거래 기간 28→62개월, 전월세 1.33M→3.19M행).

## 삭제된 지표 — 입주물량·인구이동 (2026-10-08)

🚫 **되살리지 말 것.** 사용자 명시 결정이다.

**무엇을 지웠나**: `population_flow`·`supply_schedule` 테이블과 모델, KOSIS 수집기 2개,
신호 함수 2개(`forward_signals.supply_pressure`·`population_inflow`), 가설 3개
(`supply_glut`·`supply_glut_kb_price`·`population_migration`), UI 컬럼 4개,
Supabase 복제 대상 등록.

**왜**: 세 가설이 2026-08-12~10-06 **22회 실행 내내 전부 "🟡 불확실"**이었다. ρ 부호까지
뒤집혔다(`supply_glut` +0.041→−0.015, `population_migration` +0.008→−0.016) — 노이즈다.
`supply_glut_kb_price`는 ρ가 −0.0954, n=228로 **소수 4자리까지 고정**이었는데,
`supply_schedule`이 수동 CSV(2026-05-23 업로드, 데이터 2026-03까지)라 입력이 안 변하기
때문이다. 즉 다시 돌려도 영원히 같은 값이 나온다. `recommend.py` 종합점수 산식에는
원래부터 안 들어가 있었고(근거: ρ 약하거나 역상관), 화면에만 표시되고 있었다.

**남긴 것**: 과거 판정은 `data/experiments/hypothesis_log.json`에 그대로 있고 실험실
화면의 "판정 이력"에서 계속 보인다(이 화면은 로그에서만 렌더링하므로 등록 해제와 무관).
삭제 직전 데이터는 `data/raw/kosis/_deleted_20261008_*.csv`로 덤프해 뒀다(git 제외,
외장하드에만 있음). 원천 CSV `supply_sido_사용검사실적_20260523.csv`도 그대로 둔다.
수집기 코드는 git 히스토리에 있다.

⚠️ **혼동 주의**: 지역분석 화면의 "공급압박"은 **다른 파이프라인**이다 —
`config/supply.json` 기반 `src/analysis/supply.py::supply_pressure_score()`로 살아 있다.
이름이 비슷하다고 같이 지우거나, 없어진 줄 알고 다시 만들지 말 것.

숫자를 갱신할 때는 `logs/scheduled_refresh.log` 말미가 아니라 DB를 직접 세어서 쓸 것
(로그의 "N행 교체"는 Supabase에 밀어넣은 최근 3개월치이지 전체 행수가 아니다).
