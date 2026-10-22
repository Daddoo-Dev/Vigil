from pathlib import Path

from vigil.notify import LinuxNotifySend, NullNotifier, get_notifier


def test_get_notifier_selects_by_host(monkeypatch):
    monkeypatch.setattr("vigil.notify.system_name", lambda: "linux")
    assert isinstance(get_notifier(), LinuxNotifySend)
    monkeypatch.setattr("vigil.notify.system_name", lambda: "other")
    assert isinstance(get_notifier(), NullNotifier)
    assert isinstance(get_notifier("linux"), LinuxNotifySend)


def test_linux_notifier_spawns_waiter(monkeypatch, tmp_path):
    report = tmp_path / "report.html"
    report.write_text("ok", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_popen(command, **_kwargs):
        calls.append(list(command))

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(
        "vigil.notify.shutil.which",
        lambda name: "/usr/bin/notify-send" if name == "notify-send" else None,
    )
    monkeypatch.setattr("vigil.notify.subprocess.Popen", fake_popen)
    LinuxNotifySend().notify("Vigil", "Vigil: 3 maintenance actions", report=report)
    assert len(calls) == 1
    assert "wait-notify" in calls[0]
    assert calls[0][-1] == str(report)
