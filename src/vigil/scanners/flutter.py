"""Flutter and Dart pins from pubspec.yaml and FVM, plus SDK gradle defaults."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_SDK_VERSION_LINE = re.compile(
    r"(?m)^[ \t]*(?:static\s+|const\s+|final\s+|val\s+|var\s+|open\s+)*"
    r"(?:int\s+)?"
    r"(compileSdkVersionInt|minSdkVersionInt|targetSdkVersionInt|"
    r"compileSdkVersion|minSdkVersion|targetSdkVersion)"
    r"\s*(?::[^=\n]+)?=\s*['\"]?(\d+)"
)
_SDK_FILES = (
    "packages/flutter_tools/gradle/src/main/kotlin/FlutterExtension.kt",
    "packages/flutter_tools/gradle/src/main/groovy/flutter.groovy",
    "packages/flutter_tools/lib/src/android/gradle_utils.dart",
    "packages/flutter_tools/gradle/src/main/kotlin/FlutterPluginConstants.kt",
)
_KIND = {
    "compilesdkversion": "compile",
    "compilesdkversionint": "compile",
    "minsdkversion": "min",
    "minsdkversionint": "min",
    "targetsdkversion": "target",
    "targetsdkversionint": "target",
}


@dataclass
class FlutterInfo:
    dart_constraint: str | None = None
    flutter_constraint: str | None = None
    fvm_version: str | None = None
    direct_dependencies: dict[str, str] = field(default_factory=dict)
    sdk_path: Path | None = None
    sdk_versions: dict[str, int] | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def pinned_flutter(self) -> str | None:
        """Concrete FVM version, when the pin is numeric rather than a channel name."""
        if self.fvm_version and re.match(r"\d", self.fvm_version):
            return self.fvm_version
        return None


def _load_yaml(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return loaded


def parse_pubspec(data: dict) -> tuple[str | None, str | None, dict[str, str]]:
    environment = data.get("environment") or {}
    if not isinstance(environment, dict):
        environment = {}
    dart_constraint = environment.get("sdk")
    flutter_constraint = environment.get("flutter")
    dart_constraint = str(dart_constraint) if dart_constraint else None
    flutter_constraint = str(flutter_constraint) if flutter_constraint else None
    raw_deps = data.get("dependencies") or {}
    dependencies: dict[str, str] = {}
    if isinstance(raw_deps, dict):
        for name, spec in raw_deps.items():
            if name == "flutter" or _is_sdk_package(spec):
                continue
            dependencies[str(name)] = _spec_label(spec)
    return dart_constraint, flutter_constraint, dependencies


def _is_sdk_package(spec: object) -> bool:
    return isinstance(spec, dict) and spec.get("sdk") == "flutter"


def _spec_label(spec: object) -> str:
    if spec is None:
        return "*"
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        if "version" in spec:
            return str(spec["version"])
        if "path" in spec:
            return "path"
        if "git" in spec:
            return "git"
        return "custom"
    return str(spec)


def parse_fvm_version(repo: Path) -> str | None:
    fvmrc = repo / ".fvmrc"
    if fvmrc.is_file():
        try:
            data = json.loads(fvmrc.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data.get("flutter"):
            return str(data["flutter"])
    config = repo / ".fvm" / "fvm_config.json"
    if config.is_file():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data.get("flutterSdkVersion"):
            return str(data["flutterSdkVersion"])
    version_file = repo / ".fvm" / "version"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    return None


def _sdk_from_local_properties(repo: Path) -> Path | None:
    path = repo / "android" / "local.properties"
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("flutter.sdk="):
            raw = stripped.split("=", 1)[1].strip().replace("\\:", ":").replace("\\\\", "\\")
            return Path(raw)
    return None


def _sdk_from_path() -> Path | None:
    binary = shutil.which("flutter")
    if not binary:
        return None
    root = Path(binary).resolve().parent.parent
    if (root / "bin" / "flutter").exists() or (root / "bin" / "flutter.bat").exists():
        return root
    return None


def locate_flutter_sdk(repo: Path, fvm_version: str | None) -> tuple[Path | None, str | None]:
    """Find a Flutter SDK checkout for this repo.

    A channel-style or missing FVM checkout is not replaced with whatever
    ``flutter`` is on PATH. That would report another SDK's target API as if
    it were this app's.
    """
    candidates = [
        _sdk_from_local_properties(repo),
        repo / ".fvm" / "flutter_sdk",
    ]
    env_root = os.environ.get("FLUTTER_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate, None
    if fvm_version:
        return None, (
            f"FVM pins Flutter {fvm_version} but no SDK checkout was found "
            "(looked at android/local.properties, .fvm/flutter_sdk, and FLUTTER_ROOT)"
        )
    on_path = _sdk_from_path()
    if on_path is not None:
        return on_path, None
    return None, None


def parse_flutter_sdk_versions(sdk: Path) -> dict[str, int] | None:
    """Read default compile/min/target SDK ints shipped inside the Flutter SDK."""
    found: dict[str, int] = {}
    for relative in _SDK_FILES:
        path = sdk / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _SDK_VERSION_LINE.finditer(text):
            kind = _KIND[match.group(1).lower()]
            found[kind] = int(match.group(2))
        if {"compile", "min", "target"} <= set(found):
            return found
    return found or None


def read_flutter(repo: Path) -> FlutterInfo:
    info = FlutterInfo()
    pubspec = repo / "pubspec.yaml"
    if pubspec.is_file():
        info.dart_constraint, info.flutter_constraint, info.direct_dependencies = parse_pubspec(
            _load_yaml(pubspec)
        )
    else:
        info.notes.append("no pubspec.yaml")
    info.fvm_version = parse_fvm_version(repo)
    sdk, note = locate_flutter_sdk(repo, info.fvm_version)
    if note:
        info.notes.append(note)
    info.sdk_path = sdk
    if sdk is not None:
        info.sdk_versions = parse_flutter_sdk_versions(sdk)
        if info.sdk_versions is None:
            info.notes.append(f"Flutter SDK at {sdk} has no compile/min/target defaults Vigil recognizes")
    return info
