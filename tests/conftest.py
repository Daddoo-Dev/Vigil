"""Shared paths and a quiet notify hook so tests never call notify-send."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from vigil.config import Paths

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Paths:
    config = Paths(
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        reports_dir=tmp_path / "reports",
    )
    monkeypatch.setenv("VIGIL_CONFIG_DIR", str(config.config_dir))
    monkeypatch.setenv("VIGIL_STATE_DIR", str(config.state_dir))
    monkeypatch.setenv("VIGIL_REPORTS_DIR", str(config.reports_dir))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    config.ensure()
    return config


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def quiet(_message: str) -> None:
    """Stand-in for notify-send."""
