# 부동산 분석 툴 (Real Estate Analyzer)

한국 부동산 시장 데이터를 수집·분석·시각화하는 개인용 분석 도구.

---

## 사용 데이터 소스 (전부 합법/무료 공공 API)

| 출처 | 용도 |
|---|---|
| 국토교통부 실거래가 공개 API | 아파트 매매/전월세 실거래 |
| 한국부동산원 R-ONE | 시세지수, 매매·전세 변동률 |
| 공공데이터포털 | 건축물대장, 분양정보 |
| 통계청 KOSIS | 인구/세대수 |
| 카카오 로컬 API | 좌표 변환, 입지 분석(지하철·학교·편의시설) |
| VWorld | 지적도, 용도지역 |

> KB부동산, 네이버부동산, 호갱노노는 공식 API가 없고 크롤링은 약관 위반이라 제외.
> 필요 시 `src/collectors/` 에 어댑터만 추가하면 붙일 수 있게 구조는 열려있음.

---

## 폴더 구조

```
부동산/
├── config/
│   ├── settings.py          # 환경설정, API 키 로딩
│   └── regions.json         # 법정동 코드 목록
├── data/
│   ├── raw/                 # 수집 원본 (JSON/XML 캐시)
│   ├── processed/           # SQLite DB
│   └── reports/             # 생성된 엑셀/PDF 보고서
├── src/
│   ├── collectors/          # 외부 API 호출 모듈
│   │   ├── base.py
│   │   ├── molit_api.py     # 국토부 실거래가
│   │   ├── reb_api.py       # 한국부동산원
│   │   └── kakao_api.py     # 카카오 지도
│   ├── parsers/             # XML/JSON → dict 정규화
│   ├── database/
│   │   ├── models.py        # SQLAlchemy 모델
│   │   └── repository.py    # CRUD 추상화
│   ├── analysis/
│   │   ├── price_trend.py   # 가격 추이
│   │   ├── gap_analysis.py  # 매매-전세 갭
│   │   ├── yield_calc.py    # 수익률 계산
│   │   └── ranking.py       # 지역별 랭킹
│   ├── reports/
│   │   └── excel_report.py  # 엑셀 보고서 생성
│   ├── ui/
│   │   └── streamlit_app.py # 대시보드
│   └── utils/
│       └── logger.py
├── scripts/
│   ├── init_db.py           # DB 초기화
│   └── collect_data.py      # 일괄 수집 실행
├── tests/
├── logs/
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## 기능 (구현 우선순위 순)

### Phase 1 — 데이터 파이프라인 (구현 완료)
- [x] 국토부 실거래가 수집 (매매/전세/월세)
- [x] SQLite 저장 + 중복 제거
- [x] 지역 코드 매핑

### Phase 2 — 분석 (구현 완료)
- [x] 단지별/지역별 평균가/중위가 추이
- [x] 평당가 계산
- [x] 매매-전세 갭 분석
- [x] 임대 수익률 추정 (매매가 + 월세 기반)

### Phase 3 — 시각화 (구현 완료)
- [x] Streamlit 대시보드
- [x] 시계열 차트 (Plotly)
- [x] 지역별 비교 테이블

### Phase 4 — 보고서 (구현 완료)
- [x] Excel 보고서 (openpyxl, 차트 포함)

### Phase 5 — 고급 (구현 완료)
- [x] 🚀 투자수익 전략 (호재 × 매수심리 × 레버리지)
- [x] 호재 점수 시스템 (config/catalysts.json)
- [x] 매수심리 지수 (거래량 모멘텀 + 가격 가속도)
- [x] 📈 Prophet 시계열 예측 (향후 6개월)
- [x] 🗺️ 지도 시각화 (Plotly mapbox)
- [x] 🚇 카카오 입지 점수 (선택 활성, docs/KAKAO_SETUP.md)
- [x] 🏗️ 입주물량 분석 (config/supply.json)

### Phase 6 — 미구현 / 후속
- [ ] 한국부동산원 시세지수 결합
- [ ] 통계청 인구이동 데이터
- [ ] 분양정보 자동 수집 (공공데이터포털 분양 API)
- [ ] 자동 스케줄러 (매일 새벽 수집)
- [ ] 단지별 정확 좌표 (카카오 지오코딩 일괄)
- [ ] 학군 데이터 (교육부 학교알리미)

## 📡 공유/배포
- 같은 Wi-Fi: `streamlit run ... --server.address 0.0.0.0`
- ngrok 임시 공개: `ngrok http 8501`
- Streamlit Cloud: GitHub 푸시 후 streamlit.io/cloud 연결
- Docker + VPS: 자체 호스팅

---

## 설치 & 실행

### 1. Python 환경
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. API 키 발급 (필수)
1. https://www.data.go.kr 회원가입
2. **"국토교통부 아파트매매 실거래자료"** 검색 → 활용신청
3. **"국토교통부 아파트 전월세 자료"** 검색 → 활용신청
4. 마이페이지 → 인증키(일반 인증키 Decoding) 복사

선택사항:
- 카카오 개발자센터 https://developers.kakao.com → REST API 키
- VWorld https://www.vworld.kr → 인증키

### 3. .env 작성
```powershell
Copy-Item .env.example .env
notepad .env
```

### 4. DB 초기화 + 데이터 수집
```powershell
python scripts/init_db.py
python scripts/collect_data.py --region 11680 --months 12   # 강남구 최근 12개월
```

법정동 코드는 `config/regions.json` 참고. 앞 5자리만 쓰면 시군구 단위.

### 5. 대시보드 실행
```powershell
streamlit run src/ui/streamlit_app.py
```

### 6. 엑셀 보고서
```powershell
python -m src.reports.excel_report --region 11680 --output report.xlsx
```

---

## 법정동 코드 (자주 쓰는 것)

| 코드 | 지역 |
|---|---|
| 11680 | 서울 강남구 |
| 11650 | 서울 서초구 |
| 11710 | 서울 송파구 |
| 11440 | 서울 마포구 |
| 11170 | 서울 용산구 |
| 41135 | 경기 성남시 분당구 |
| 41117 | 경기 수원시 영통구 |

전체 목록: https://www.code.go.kr (법정동코드)
