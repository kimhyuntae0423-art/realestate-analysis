from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get_secret(key: str, default: str = "") -> str:
    """환경변수 → Streamlit secrets 순서로 키 읽기."""
    val = os.getenv(key, "")
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, default)
        except Exception:
            val = default
    return val


DATA_GO_KR_API_KEY = _get_secret("DATA_GO_KR_API_KEY")
KAKAO_REST_API_KEY = _get_secret("KAKAO_REST_API_KEY")
VWORLD_API_KEY     = _get_secret("VWORLD_API_KEY")
KOSIS_API_KEY      = _get_secret("KOSIS_API_KEY")
ECOS_API_KEY       = _get_secret("ECOS_API_KEY")

DATABASE_URL = _get_secret("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'processed' / 'realestate.db'}")

# 조회 전용 클라우드 복제본(배포 Streamlit 이 읽는 곳). PC 에서는 비워두고 로컬
# SQLite 를 SSOT 로 쓰되, scripts/migrate_to_supabase.py 가 이 주소로 밀어넣는다.
# DATABASE_URL 과 분리한 이유: PC 의 수집·분석은 로컬 SQLite 에 그대로 하고,
# 동기화 대상만 따로 지정하기 위함.
SUPABASE_DATABASE_URL = _get_secret("SUPABASE_DATABASE_URL")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

RAW_DIR = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "data" / "reports"
LOG_DIR = ROOT / "logs"

for d in (RAW_DIR, REPORT_DIR, LOG_DIR, ROOT / "data" / "processed"):
    d.mkdir(parents=True, exist_ok=True)

MOLIT_BASE = "https://apis.data.go.kr/1613000"
MOLIT_ENDPOINTS = {
    "apt_trade": f"{MOLIT_BASE}/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "apt_rent": f"{MOLIT_BASE}/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}

REQUEST_TIMEOUT = 20
REQUEST_RETRY = 3
REQUEST_SLEEP = 0.3

# ── 투자수익 전략 가중치 기본값 (recommend.py::recommend_investment_focus) ──
# 2026-07-20 grid_search_apt(n=6251) 검증: catalyst=0.0이 근소 우위(spearman 0.581 vs
# 0.573)이나 오차범위 수준이고 호재 수동발굴 용도가 있어 0.10 유지. region_score:prestige는
# 0.70:0.30 근방(0.71~0.86 구간)이 최적 — 지금 기본값이 이미 그 안에 있어 그대로 채택.
# streamlit_app.py 슬라이더·backtest.py 기본값·recommend.py 기본값이 전부 이 상수를 쓴다.
DEFAULT_CATALYST_WEIGHT = 0.10
DEFAULT_TIER_WEIGHT = 0.70      # 파라미터명은 tier_weight이지만 실제로는 region_score(시세+호재) 비중
DEFAULT_PRESTIGE_WEIGHT = 0.30

# ── 매크로 타이밍 최소 데이터 커버리지 (market_timing.py::market_timing_signal) ──
# 신호 5개 중 값이 있는 것들의 가중치 합이 전체의 이 비율에 못 미치면 종합점수를
# 내지 않고 None 을 반환한다(UI는 "데이터 부족"으로 표시).
#
# 2026-09-10에 넣은 이유: ECOS 키가 없어 ecos_series 가 0행이면 5개 중 4개
# (주담대 0.35 + M2 0.10 + 실질금리 0.10 + M1/M2 0.10 = 0.65)가 null 인데,
# 기존 코드는 살아있는 가중치로 재정규화해서 KB 매수우위지수(0.35) 하나의 값을
# 종합점수 76.9 로 그대로 표시했다. 근거의 65%가 없는데 화면은 정상으로 보였다 —
# CLAUDE.md 절대원칙 3("모르는 숫자는 만들지 않는다") 위반.
#
# 0.60 인 이유: 단기(직접효과) 두 신호 합이 0.70 이라 그 축이 살아있으면 통과하고,
# 배경지표(장기 0.30)만 남거나 KB(0.35) 하나만 남는 경우는 걸러진다.
MARKET_TIMING_MIN_COVERAGE = 0.60

# ── 매수심리(sentiment) 지표 기본값 (recommend.py::_buyer_sentiment_signals) ──
# 2026-08 매직넘버 정리: 클립 범위·가중치를 하드코딩에서 이전. 값 자체는 불변.
SENTIMENT_VOL_CLIP = (0.0, 3.0)
SENTIMENT_ACCEL_CLIP = (-30.0, 30.0)
SENTIMENT_SKEW_CLIP = (-15.0, 15.0)
SENTIMENT_VOL_WEIGHT = 0.5
SENTIMENT_ACCEL_WEIGHT = 0.3
SENTIMENT_SKEW_WEIGHT = 0.2
