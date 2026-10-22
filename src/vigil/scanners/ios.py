"""iOS deployment target from the Xcode project and the Podfile."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from vigil.versions import version_key, version_lt

_PBX_TARGET = re.compile(r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*([^;]+);")
_POD_PLATFORM = re.compile(
    r"platform\s+:ios\s*,\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IosTargets:
    pbx_values: list[str]
    podfile_platform: str | None
    minimum: str | None
    unresolved: list[str]

    @property
    def label(self) -> str:
        if self.minimum:
            return self.minimum
        if self.unresolved:
            return "unresolved"
        return "—"


def _clean(raw: str) -> str:
    return raw.strip().strip("'\"")


def parse_pbxproj(text: str) -> list[str]:
    return [_clean(match.group(1)) for match in _PBX_TARGET.finditer(text)]


def parse_podfile(text: str) -> str | None:
    match = _POD_PLATFORM.search(text)
    return _clean(match.group(1)) if match else None


def build_ios_targets(pbx_values: list[str], podfile_platform: str | None) -> IosTargets:
    numeric: list[str] = []
    unresolved: list[str] = []
    for value in [*pbx_values, *([podfile_platform] if podfile_platform else [])]:
        if version_key(value):
            numeric.append(value)
        else:
            unresolved.append(value)
    minimum = None
    if numeric:
        minimum = numeric[0]
        for value in numeric[1:]:
            if version_lt(value, minimum):
                minimum = value
    return IosTargets(
        pbx_values=pbx_values,
        podfile_platform=podfile_platform,
        minimum=minimum,
        unresolved=unresolved,
    )


def read_ios(repo: Path) -> tuple[IosTargets | None, str | None]:
    pbx = repo / "ios" / "Runner.xcodeproj" / "project.pbxproj"
    podfile = repo / "ios" / "Podfile"
    if not pbx.is_file() and not podfile.is_file():
        return None, "no ios/Runner.xcodeproj/project.pbxproj or Podfile"
    pbx_values = parse_pbxproj(pbx.read_text(encoding="utf-8", errors="replace")) if pbx.is_file() else []
    platform = parse_podfile(podfile.read_text(encoding="utf-8", errors="replace")) if podfile.is_file() else None
    if not pbx_values and platform is None:
        return None, "iOS project has no IPHONEOS_DEPLOYMENT_TARGET or Podfile platform"
    return build_ios_targets(pbx_values, platform), None
