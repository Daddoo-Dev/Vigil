"""Parse compileSdk, targetSdk, and minSdk from Groovy and Kotlin Gradle files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//.*?$", re.MULTILINE)
_SDK_LINE = re.compile(
    r"(?im)^[ \t]*(compileSdkVersion|compileSdk|minSdkVersion|minSdk|"
    r"targetSdkVersion|targetSdk)[ \t]*(?:=[ \t]*)?([^\n]+?)\s*$"
)
_KIND = {
    "compilesdk": "compile",
    "compilesdkversion": "compile",
    "minsdk": "min",
    "minsdkversion": "min",
    "targetsdk": "target",
    "targetsdkversion": "target",
}
_FLUTTER_REF = re.compile(r"flutter\.(compile|min|target)SdkVersion\b", re.IGNORECASE)


@dataclass(frozen=True)
class SdkPin:
    """A Gradle SDK value, or a ``flutter.*SdkVersion`` reference."""

    raw: str
    number: int | None
    inherited: bool
    unresolved: bool

    @property
    def label(self) -> str:
        if self.number is not None and self.inherited:
            return f"{self.number} (inherited from Flutter SDK)"
        if self.inherited and self.unresolved:
            return "inherited from Flutter SDK (unresolved)"
        if self.number is not None:
            return str(self.number)
        if self.unresolved:
            return f"unresolved ({self.raw})"
        return self.raw


@dataclass(frozen=True)
class AndroidSdk:
    compile_sdk: SdkPin | None
    target_sdk: SdkPin | None
    min_sdk: SdkPin | None
    source: str | None


def strip_gradle_comments(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _BLOCK_COMMENT.sub("", text)
    return _LINE_COMMENT.sub("", text)


def _pin_from_raw(raw: str) -> SdkPin:
    raw = raw.strip().rstrip(";").strip().strip("'\"")
    flutter_ref = _FLUTTER_REF.search(raw) is not None
    literal = re.fullmatch(r"\d+", raw)
    if literal and not flutter_ref:
        return SdkPin(raw=raw, number=int(raw), inherited=False, unresolved=False)
    if flutter_ref:
        return SdkPin(raw=raw, number=None, inherited=True, unresolved=True)
    return SdkPin(raw=raw, number=None, inherited=False, unresolved=True)


def parse_gradle(text: str) -> AndroidSdk:
    """Last assignment of each SDK kind wins. Comments are ignored."""
    found: dict[str, SdkPin] = {}
    for match in _SDK_LINE.finditer(strip_gradle_comments(text)):
        kind = _KIND[match.group(1).lower()]
        raw = match.group(2).strip()
        if not raw:
            continue
        found[kind] = _pin_from_raw(raw)
    return AndroidSdk(
        compile_sdk=found.get("compile"),
        target_sdk=found.get("target"),
        min_sdk=found.get("min"),
        source=None,
    )


def resolve_inherited(sdk: AndroidSdk, versions: dict[str, int] | None) -> AndroidSdk:
    """Fill flutter.*SdkVersion pins from a Flutter SDK. Never guess."""
    if not versions:
        return sdk

    def resolve(pin: SdkPin | None, kind: str) -> SdkPin | None:
        if pin is None or not pin.inherited:
            return pin
        number = versions.get(kind)
        if number is None:
            return pin
        return SdkPin(raw=pin.raw, number=number, inherited=True, unresolved=False)

    return AndroidSdk(
        compile_sdk=resolve(sdk.compile_sdk, "compile"),
        target_sdk=resolve(sdk.target_sdk, "target"),
        min_sdk=resolve(sdk.min_sdk, "min"),
        source=sdk.source,
    )


def read_android(repo: Path, sdk_versions: dict[str, int] | None) -> tuple[AndroidSdk | None, str | None]:
    """Read ``android/app/build.gradle`` or the Kotlin script beside it.

    When both exist, the Kotlin script is the one Flutter writes on current
    templates, so it wins.
    """
    app_dir = repo / "android" / "app"
    kts = app_dir / "build.gradle.kts"
    groovy = app_dir / "build.gradle"
    path = kts if kts.is_file() else groovy if groovy.is_file() else None
    if path is None:
        return None, "no android/app/build.gradle or build.gradle.kts"
    sdk = parse_gradle(path.read_text(encoding="utf-8", errors="replace"))
    sdk = resolve_inherited(sdk, sdk_versions)
    return (
        AndroidSdk(sdk.compile_sdk, sdk.target_sdk, sdk.min_sdk, source=str(path)),
        None,
    )
