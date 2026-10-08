"""src/utils/notify.py — 실패 알림. 실제 전송은 하지 않는다."""
from pathlib import Path

from src.utils import notify


class _Result:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def test_success_sends_nothing(monkeypatch):
    """성공했을 때 알림을 보내면 곧 안 읽게 되고 진짜 실패도 묻힌다."""
    called = []
    monkeypatch.setattr(notify, "send_kakao", lambda m: called.append(m) or True)
    assert notify.notify_refresh_failure([], "2026-10-08 09:00") is False
    assert called == []


def test_failure_message_has_count_and_each_item(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_kakao", lambda m: sent.append(m) or True)
    ok = notify.notify_refresh_failure(
        ["Supabase 동기화 실패: timeout", "KB/ECOS 수집 오류 2건"], "2026-10-08 09:00")
    assert ok
    msg = sent[0]
    assert "실패 2건" in msg
    assert "Supabase 동기화 실패: timeout" in msg
    assert "KB/ECOS 수집 오류 2건" in msg
    assert "2026-10-08 09:00" in msg


def test_long_failure_list_is_truncated(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_kakao", lambda m: sent.append(m) or True)
    notify.notify_refresh_failure([f"오류{i}" for i in range(14)], "t")
    msg = sent[0]
    assert "실패 14건" in msg
    assert "외 4건" in msg          # 10건까지만 본문에 싣는다
    assert "오류13" not in msg


def test_missing_sender_script_is_not_an_exception(monkeypatch, tmp_path):
    """외장하드가 빠져 있어도 갱신 자체를 죽이면 안 된다."""
    monkeypatch.setattr(notify, "KAKAO_SENDER_PS1", tmp_path / "없는파일.ps1")
    assert notify.send_kakao("hello") is False


def test_nonzero_exit_is_reported_as_failure(monkeypatch, tmp_path):
    """send-kakao.ps1 은 전송 실패 시 1 을 돌려준다 — 그걸 성공으로 보면 안 된다."""
    script = tmp_path / "send-kakao.ps1"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(notify, "KAKAO_SENDER_PS1", script)

    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: _Result(1))
    assert notify.send_kakao("hello") is False

    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: _Result(0))
    assert notify.send_kakao("hello") is True


def test_subprocess_exception_is_swallowed(monkeypatch, tmp_path):
    script = tmp_path / "send-kakao.ps1"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(notify, "KAKAO_SENDER_PS1", script)

    def _boom(*a, **k):
        raise OSError("powershell 없음")

    monkeypatch.setattr(notify.subprocess, "run", _boom)
    assert notify.send_kakao("hello") is False


def test_sender_path_is_a_path_object():
    """설정에서 오는 값이라 문자열이면 .exists() 에서 터진다."""
    from config.settings import KAKAO_SENDER_PS1
    assert isinstance(KAKAO_SENDER_PS1, Path)
