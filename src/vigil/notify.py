"""Desktop notifications. Host backends are selected by :func:`get_notifier`.

Linux uses ``notify-send`` with an Open report action. macOS and Windows get a
best-effort banner without action buttons. Tests inject a callable via
``run_scan(..., notify_fn=...)`` and never hit these backends.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from vigil.host import open_path, system_name

logger = logging.getLogger("vigil.notify")


class Notifier(Protocol):
    def notify(self, title: str, message: str, *, report: Path | None = None) -> None:
        """Show a notification. Must not block the scan for long."""


class NullNotifier:
    def notify(self, title: str, message: str, *, report: Path | None = None) -> None:
        logger.info("notify skipped (%s): %s", title, message)


class LinuxNotifySend:
    """GNOME/libnotify. Spawns a waiter so Open report still works from the clock menu."""

    def notify(self, title: str, message: str, *, report: Path | None = None) -> None:
        if shutil.which("notify-send") is None:
            logger.warning("notify-send is not installed; skipped desktop notification")
            return
        report_arg = str(report) if report and report.exists() else ""
        subprocess.Popen(
            [sys.executable, "-m", "vigil.desktop", "wait-notify", message, report_arg],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class MacOsNotifier:
    def notify(self, title: str, message: str, *, report: Path | None = None) -> None:
        body = message.replace("\\", "\\\\").replace('"', '\\"')
        head = title.replace("\\", "\\\\").replace('"', '\\"')
        script = f'display notification "{body}" with title "{head}"'
        try:
            subprocess.run(["osascript", "-e", script], check=False, timeout=10, capture_output=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("macOS notification failed: %s", exc)
            return
        if report is not None and report.exists():
            # Action buttons are not available here; open the report so the alert is useful.
            open_path(report)


class WindowsNotifier:
    def notify(self, title: str, message: str, *, report: Path | None = None) -> None:
        # PowerShell toast APIs vary by Windows build; keep a simple MessageBox-free balloon.
        safe_title = title.replace("'", "''")
        safe_body = message.replace("'", "''")
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] > $null; "
            "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$text = $template.GetElementsByTagName('text'); "
            f"$text.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) > $null; "
            f"$text.Item(1).AppendChild($template.CreateTextNode('{safe_body}')) > $null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Vigil')"
            ".Show($toast)"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                check=False,
                timeout=15,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Windows notification failed: %s", exc)
            return
        if completed.returncode != 0:
            logger.warning("Windows notification failed: %s", (completed.stderr or completed.stdout)[:200])
            return
        if report is not None and report.exists():
            open_path(report)


def get_notifier(name: str | None = None) -> Notifier:
    """Return the notifier for this host, or ``name`` when tests force a backend."""
    chosen = name or system_name()
    if chosen == "linux":
        return LinuxNotifySend()
    if chosen == "darwin":
        return MacOsNotifier()
    if chosen == "windows":
        return WindowsNotifier()
    return NullNotifier()
