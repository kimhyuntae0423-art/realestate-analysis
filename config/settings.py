from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "")
KOSIS_API_KEY = os.getenv("KOSIS_API_KEY", "")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'processed' / 'realestate.db'}")
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
