"""Scan schedule presets and custom day intervals for host timers."""

from __future__ import annotations

from dataclasses import dataclass

SCHEDULE_PRESETS = frozenset({"weekly", "biweekly", "monthly", "off", "days"})
_TASK_NAME = "VigilScan"
_LEGACY_TASK_NAME = "VigilMonthlyScan"


@dataclass(frozen=True)
class ScanSchedule:
    kind: str = "monthly"
    every_days: int | None = None

    def describe(self) -> str:
        if self.kind == "off":
            return "off (no automatic scan)"
        if self.kind == "days":
            days = self.every_days or 0
            unit = "day" if days == 1 else "days"
            return f"every {days} {unit}"
        if self.kind == "weekly":
            return "weekly"
        if self.kind == "biweekly":
            return "every 14 days"
        return "monthly"

    def systemd_timer(self) -> str | None:
        """Return vigil-scan.timer body, or None when schedule is off."""
        if self.kind == "off":
            return None
        description = f"Run the Vigil maintenance scan ({self.describe()})"
        if self.kind == "monthly":
            body = "OnCalendar=monthly\nPersistent=true\n"
        elif self.kind == "weekly":
            body = "OnCalendar=weekly\nPersistent=true\n"
        elif self.kind == "biweekly":
            body = "OnBootSec=15min\nOnUnitActiveSec=14d\nPersistent=true\n"
        else:
            days = self.every_days or 1
            body = f"OnBootSec=15min\nOnUnitActiveSec={days}d\nPersistent=true\n"
        return (
            "[Unit]\n"
            f"Description={description}\n"
            "\n"
            "[Timer]\n"
            f"{body}"
            "\n"
            "[Install]\n"
            "WantedBy=timers.target\n"
        )

    def launchd_interval(self) -> dict | None:
        """Keys for a LaunchAgent scan plist, or None when off.

        Returns either ``StartCalendarInterval`` or ``StartInterval`` (seconds).
        """
        if self.kind == "off":
            return None
        if self.kind == "monthly":
            return {"StartCalendarInterval": {"Day": 1, "Hour": 9, "Minute": 0}}
        if self.kind == "weekly":
            # launchd: 0 and 7 = Sunday; 1 = Monday.
            return {"StartCalendarInterval": {"Weekday": 1, "Hour": 9, "Minute": 0}}
        if self.kind == "biweekly":
            return {"StartInterval": 14 * 24 * 60 * 60}
        days = self.every_days or 1
        return {"StartInterval": days * 24 * 60 * 60}

    def windows_schtasks(self, exe: str) -> list[str] | None:
        """``schtasks /Create ...`` argv after the executable name, or None when off."""
        if self.kind == "off":
            return None
        base = [
            "/Create",
            "/TN",
            _TASK_NAME,
            "/TR",
            f'"{exe}" scan',
            "/ST",
            "09:00",
            "/F",
        ]
        if self.kind == "monthly":
            return [*base, "/SC", "MONTHLY", "/D", "1"]
        if self.kind == "weekly":
            return [*base, "/SC", "WEEKLY", "/D", "MON"]
        if self.kind == "biweekly":
            return [*base, "/SC", "DAILY", "/MO", "14"]
        days = self.every_days or 1
        return [*base, "/SC", "DAILY", "/MO", str(days)]


def parse_schedule(kind: str, every_days: object = None) -> ScanSchedule:
    """Validate settings values. Raises ``ValueError`` with a user-facing message."""
    normalized = str(kind or "monthly").strip().casefold()
    if normalized not in SCHEDULE_PRESETS:
        raise ValueError(
            "schedule must be weekly, biweekly, monthly, off, or days"
        )
    if normalized != "days":
        return ScanSchedule(kind=normalized, every_days=None)
    if every_days is None or every_days == "":
        raise ValueError("schedule: days requires every_days (a positive integer)")
    if isinstance(every_days, bool) or not isinstance(every_days, int):
        raise ValueError("every_days must be a positive integer")
    if every_days < 1:
        raise ValueError("every_days must be at least 1")
    return ScanSchedule(kind="days", every_days=every_days)


def windows_task_names() -> tuple[str, str]:
    return _TASK_NAME, _LEGACY_TASK_NAME
