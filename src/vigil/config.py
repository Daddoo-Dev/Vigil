"""Paths and YAML config. Data lives in XDG directories, overridable for tests."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml

logger = logging.getLogger("vigil.config")

EXAMPLE_FILES = (
    "repos.yaml",
    "sources.yaml",
    "requirements.yaml",
    "requirements.pending.yaml",
    "expiries.yaml",
    "settings.yaml",
)

_PRIORITIES = {"high", "normal", "low"}
_PLATFORMS = {"android", "ios"}
_SOURCE_TYPES = {"rss", "json", "html"}


class ConfigError(Exception):
    """A config file is missing or does not match the shape Vigil expects."""


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    state_dir: Path
    reports_dir: Path

    @property
    def snapshots_dir(self) -> Path:
        return self.state_dir / "snapshots"

    @property
    def status_path(self) -> Path:
        return self.state_dir / "status.json"

    @property
    def log_path(self) -> Path:
        return self.state_dir / "vigil.log"

    @classmethod
    def from_env(cls) -> Paths:
        home = Path.home()
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        state_root = Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state"))
        data_root = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
        return cls(
            config_dir=Path(os.environ.get("VIGIL_CONFIG_DIR", config_root / "vigil")),
            state_dir=Path(os.environ.get("VIGIL_STATE_DIR", state_root / "vigil")),
            reports_dir=Path(
                os.environ.get("VIGIL_REPORTS_DIR", data_root / "vigil" / "reports")
            ),
        )

    def ensure(self) -> None:
        for directory in (
            self.config_dir,
            self.state_dir,
            self.snapshots_dir,
            self.reports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Repo:
    name: str
    path: Path
    platforms: list[str]
    priority: str


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    type: str
    url: str
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Settings:
    notify: bool = True
    extractor: str = "keyword"
    projects_dir: Path | None = None


def configure_logging(state_dir: Path, verbose: bool) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("vigil")
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        state_dir / "vigil.log",
        maxBytes=1_000_000,
        backupCount=2,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    if verbose:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        log.addHandler(stream)
    log.debug("logging to %s", state_dir / "vigil.log")


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"missing config file: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name} is not valid YAML: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path.name} must be a YAML mapping")
    return loaded


def load_repos(path: Path) -> list[Repo]:
    data = _read_yaml(path)
    raw_repos = data.get("repos") or []
    if not isinstance(raw_repos, list):
        raise ConfigError("repos.yaml: 'repos' must be a list")
    repos: list[Repo] = []
    for index, raw in enumerate(raw_repos, start=1):
        if not isinstance(raw, dict):
            raise ConfigError(f"repos.yaml: entry {index} must be a mapping")
        name = str(raw.get("name") or "").strip()
        raw_path = str(raw.get("path") or "").strip()
        if not name or not raw_path:
            raise ConfigError(f"repos.yaml: entry {index} needs name and path")
        if "platforms" not in raw or raw.get("platforms") is None:
            platforms = ["android", "ios"]
        else:
            platforms = raw.get("platforms")
            if not isinstance(platforms, list):
                raise ConfigError(f"repos.yaml: {name} platforms must be a list")
            platforms = [str(item) for item in platforms]
        unknown = sorted(set(platforms) - _PLATFORMS)
        if unknown:
            raise ConfigError(f"repos.yaml: {name} has unknown platforms {unknown}")
        priority = str(raw.get("priority") or "normal")
        if priority not in _PRIORITIES:
            raise ConfigError(
                f"repos.yaml: {name} priority must be high, normal, or low"
            )
        repos.append(
            Repo(name=name, path=Path(raw_path).expanduser(), platforms=platforms, priority=priority)
        )
    return repos


def load_sources(path: Path) -> list[Source]:
    data = _read_yaml(path)
    raw_sources = data.get("sources") or []
    if not isinstance(raw_sources, list):
        raise ConfigError("sources.yaml: 'sources' must be a list")
    sources: list[Source] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_sources, start=1):
        if not isinstance(raw, dict):
            raise ConfigError(f"sources.yaml: entry {index} must be a mapping")
        source_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        source_type = str(raw.get("type") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not source_id or not name or not url:
            raise ConfigError(f"sources.yaml: entry {index} needs id, name, and url")
        if source_type not in _SOURCE_TYPES:
            raise ConfigError(
                f"sources.yaml: {source_id} type must be rss, json, or html"
            )
        if source_id in seen:
            raise ConfigError(f"sources.yaml: duplicate id {source_id}")
        seen.add(source_id)
        keywords = raw.get("keywords") or []
        if not isinstance(keywords, list):
            raise ConfigError(f"sources.yaml: {source_id} keywords must be a list")
        sources.append(
            Source(
                id=source_id,
                name=name,
                type=source_type,
                url=url,
                keywords=[str(item) for item in keywords],
            )
        )
    return sources


def load_settings(path: Path) -> Settings:
    if not path.is_file():
        return Settings()
    data = _read_yaml(path)
    notify = data.get("notify", True)
    extractor = str(data.get("extractor") or "keyword")
    if not isinstance(notify, bool):
        raise ConfigError("settings.yaml: notify must be true or false")
    raw_dir = data.get("projects_dir")
    projects_dir = Path(str(raw_dir)).expanduser() if raw_dir else None
    return Settings(notify=notify, extractor=extractor, projects_dir=projects_dir)


def example_text(name: str) -> str:
    """Read a shipped example. Works from a checkout and from an installed wheel."""
    local = Path(__file__).resolve().parent / "examples" / name
    if local.is_file():
        return local.read_text(encoding="utf-8")
    from importlib.resources import files

    return files("vigil").joinpath("examples", name).read_text(encoding="utf-8")


def init_config(paths: Paths) -> None:
    """Create XDG dirs and copy example configs that are not already present."""
    paths.ensure()
    for name in EXAMPLE_FILES:
        destination = paths.config_dir / name
        if destination.exists():
            print(f"kept {destination}")
            continue
        destination.write_text(example_text(name), encoding="utf-8")
        print(f"wrote {destination}")
    print(f"config: {paths.config_dir}")
    print(f"state:  {paths.state_dir}")
    print(f"reports: {paths.reports_dir}")


def set_projects_dir(path: Path, directory: Path) -> None:
    """Record the folder Vigil scans, keeping the rest of settings.yaml."""
    text = path.read_text(encoding="utf-8") if path.is_file() else "notify: true\nextractor: keyword\n"
    line = f"projects_dir: {_yaml_plain(str(directory))}\n"
    if re.search(r"(?m)^projects_dir:", text):
        text = re.sub(r"(?m)^projects_dir:.*(?:\n|$)", line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yaml_plain(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./~-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
