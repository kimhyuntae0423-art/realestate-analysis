"""사내망 SSL 인터셉션 대응 — Windows 인증서 저장소를 CA 번들로 내보낸다.

배경: 사내망 프록시가 TLS를 가로채고 자체서명 루트 CA로 재서명하기 때문에,
certifi 번들만 쓰는 requests 는 apis.data.go.kr 호출 시 전부
`CERTIFICATE_VERIFY_FAILED (self-signed certificate in certificate chain)` 로 실패한다.
2026-05-27 수집이 멈춘 원인이 이것이었다.

해결: certifi 번들 + Windows 인증서 저장소(LocalMachine/CurrentUser 의 Root·CA)를
합친 PEM 을 만들어 REQUESTS_CA_BUNDLE 로 지정한다. `verify=False` 는 쓰지 않는다.

주의: `ssl.enum_certificates()` 는 이 목적에 못 쓴다 — 실측 결과 141개만 반환해
정작 필요한 사내 루트 CA 가 있는 저장소를 놓친다(PowerShell 은 267개). 그래서
PowerShell 로 내보낸다.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.utils.logger import get_logger

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLE_PATH = ROOT / "data" / "processed" / "ca_bundle.pem"

# LocalMachine 을 먼저 봐야 한다 — 사내 CA 는 보통 여기 배포된다.
_PS_EXPORT = r"""
$out = New-Object System.Text.StringBuilder
foreach ($store in @("Cert:\LocalMachine\Root","Cert:\LocalMachine\CA",
                     "Cert:\CurrentUser\Root","Cert:\CurrentUser\CA")) {
  foreach ($c in (Get-ChildItem $store -ErrorAction SilentlyContinue)) {
    $b64 = [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks')
    [void]$out.AppendLine("-----BEGIN CERTIFICATE-----")
    [void]$out.AppendLine($b64)
    [void]$out.AppendLine("-----END CERTIFICATE-----")
  }
}
[Console]::Out.Write($out.ToString())
"""


def _windows_store_pem() -> str:
    """Windows 인증서 저장소를 PEM 문자열로. 실패하면 빈 문자열."""
    if os.name != "nt":
        return ""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_EXPORT],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # PowerShell 자체가 없거나 막힌 환경
        log.warning("CA 저장소 내보내기 실패 (PowerShell): %s", e)
        return ""
    if r.returncode != 0:
        log.warning("CA 저장소 내보내기 실패 rc=%s: %s", r.returncode, r.stderr[:200])
        return ""
    return r.stdout


def ensure_ca_bundle(force: bool = True) -> str | None:
    """CA 번들을 만들고 REQUESTS_CA_BUNDLE 에 설정한다. 경로를 반환(실패 시 None).

    이미 REQUESTS_CA_BUNDLE 가 외부에서 지정돼 있으면 그것을 존중하고 건드리지 않는다.
    매 실행마다 다시 만든다 — 사내 CA 가 교체돼도 자동으로 따라간다.
    """
    existing = os.environ.get("REQUESTS_CA_BUNDLE")
    if existing and Path(existing).exists():
        log.info("REQUESTS_CA_BUNDLE 이 이미 지정돼 있어 그대로 사용: %s", existing)
        return existing

    if BUNDLE_PATH.exists() and not force:
        os.environ["REQUESTS_CA_BUNDLE"] = str(BUNDLE_PATH)
        return str(BUNDLE_PATH)

    store_pem = _windows_store_pem()
    if not store_pem.strip():
        log.warning("Windows 인증서를 못 읽었다 — certifi 기본값으로 진행한다.")
        return None

    try:
        import certifi
        base = Path(certifi.where()).read_text(encoding="utf-8")
    except Exception:
        base = ""

    BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUNDLE_PATH.write_text(base + "\n" + store_pem, encoding="utf-8")

    n = store_pem.count("BEGIN CERTIFICATE")
    log.info("CA 번들 생성: %s (OS 인증서 %d개 + certifi)", BUNDLE_PATH, n)
    os.environ["REQUESTS_CA_BUNDLE"] = str(BUNDLE_PATH)
    return str(BUNDLE_PATH)
