import time
import requests
from typing import Any
from config.settings import REQUEST_TIMEOUT, REQUEST_RETRY, REQUEST_SLEEP
from src.utils.logger import get_logger

log = get_logger(__name__)


class HttpClient:
    def __init__(self, base_headers: dict | None = None):
        self.session = requests.Session()
        if base_headers:
            self.session.headers.update(base_headers)

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        last_err = None
        for attempt in range(1, REQUEST_RETRY + 1):
            try:
                r = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT, verify=False)
                if r.status_code == 200:
                    time.sleep(REQUEST_SLEEP)
                    return r
                log.warning("GET %s status=%s try=%d", url, r.status_code, attempt)
                last_err = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                log.warning("GET %s err=%s try=%d", url, e, attempt)
                last_err = str(e)
            time.sleep(0.5 * attempt)
        raise RuntimeError(f"GET failed after {REQUEST_RETRY} tries: {last_err}")
