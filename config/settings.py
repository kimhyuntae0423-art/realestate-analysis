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

# ── 매수심리(sentiment) 지표 기본값 (recommend.py::_buyer_sentiment_signals) ──
# 2026-08 매직넘버 정리: 클립 범위·가중치를 하드코딩에서 이전. 값 자체는 불변.
SENTIMENT_VOL_CLIP = (0.0, 3.0)
SENTIMENT_ACCEL_CLIP = (-30.0, 30.0)
SENTIMENT_SKEW_CLIP = (-15.0, 15.0)
SENTIMENT_VOL_WEIGHT = 0.5
SENTIMENT_ACCEL_WEIGHT = 0.3
SENTIMENT_SKEW_WEIGHT = 0.2
