"""정기 갱신이 실패했을 때만 카카오톡으로 알린다.

## 왜 여기서 토큰을 안 다루는가

카카오 토큰 갱신·보관은 `카카오알림` 저장소의 `send-kakao.ps1` 이 이미 하고 있다
(전송 전 선제 갱신 → `config.ps1` 에 기록). 같은 계정의 토큰을 두 곳에서 굴리면
리프레시 토큰이 교체될 때 다른 쪽이 무효화된다 — 실제로 겪은 문제다. 그래서 이
모듈은 토큰을 한 줄도 다루지 않고 그 스크립트를 호출만 한다.

## 실패해도 조용히 넘어간다

알림이 안 갔다고 수집·분석 결과까지 버릴 이유는 없다. 예외는 전부 삼키고 로그만
남긴다. 다만 **알림 자체가 조용히 실패하면 알림을 붙인 의미가 없으므로**, 전송
실패는 종료코드로 구분한다(그래서 2026-10-08 에 send-kakao.ps1 이 실패 시 1 을
돌려주도록 고쳤다).
"""
from __future__ import annotations

import subprocess

from config.settings import KAKAO_SENDER_PS1
from src.utils.logger import get_logger

log = get_logger(__name__)

TIMEOUT_SEC = 90


def send_kakao(message: str) -> bool:
    """카카오톡 전송. 성공하면 True. 예외는 올리지 않는다."""
    if not message.strip():
        return False
    if not KAKAO_SENDER_PS1.exists():
        log.warning("카카오 발송 스크립트 없음: %s — 알림을 건너뛴다 "
                    "(외장하드 미연결이거나 드라이브 문자가 바뀜)", KAKAO_SENDER_PS1)
        return False
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(KAKAO_SENDER_PS1), "-Message", message],
            capture_output=True, text=True, timeout=TIMEOUT_SEC,
        )
    except Exception:
        log.exception("카카오 발송 예외 — 알림만 실패, 갱신 결과는 유효")
        return False

    if r.returncode != 0:
        log.warning("카카오 발송 실패 rc=%s %s", r.returncode,
                    (r.stderr or r.stdout or "")[:300])
        return False
    log.info("카카오 알림 전송 완료")
    return True


def notify_refresh_failure(failures: list[str], when: str) -> bool:
    """정기 갱신 실패 요약을 보낸다. failures 가 비면 아무것도 안 보낸다.

    성공했을 때는 보내지 않는다 — 매주 오는 '정상' 알림은 곧 안 읽게 되고,
    그러면 진짜 실패도 같이 안 읽힌다.
    """
    if not failures:
        return False
    body = "\n".join(f"- {f}" for f in failures[:10])
    if len(failures) > 10:
        body += f"\n- (외 {len(failures) - 10}건)"
    msg = (f"[부동산] 정기 갱신 실패 {len(failures)}건\n"
           f"{when}\n\n{body}\n\n"
           f"로그: logs/scheduled_refresh.log")
    return send_kakao(msg)
