"""Cross-repo drift. Outliers are values with no majority across the apps that have one."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

_EMPTY = {"", "—", "unresolved"}
_BASE_COLUMNS = ("Flutter", "Dart", "targetSdk", "iOS")
_PRIORITY = {"high": 0, "normal": 1, "low": 2}


@dataclass
class DriftInput:
    name: str
    priority: str
    flutter: str
    dart: str
    target_sdk: str
    ios: str
    packages: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DriftCell:
    text: str
    outlier: bool


@dataclass(frozen=True)
class DriftRow:
    name: str
    priority: str
    cells: list[DriftCell]


@dataclass(frozen=True)
class DriftTable:
    columns: list[str]
    rows: list[DriftRow]


def outlier_mask(values: list[str]) -> list[bool]:
    usable = [(index, value) for index, value in enumerate(values) if value not in _EMPTY]
    mask = [False] * len(values)
    if len(usable) < 2:
        return mask
    counts = Counter(value for _, value in usable)
    if len(counts) == 1:
        return mask
    majority = None
    for value, count in counts.items():
        if count > len(usable) / 2:
            majority = value
            break
    for index, value in usable:
        if majority is None or value != majority:
            mask[index] = True
    return mask


def shared_package_names(rows: list[DriftInput], limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        for name, version in row.packages.items():
            if version and version not in _EMPTY:
                counts[name] += 1
    shared = [name for name, count in counts.items() if count >= 2]
    shared.sort(key=lambda name: (-counts[name], name))
    return shared[:limit]


def build_drift(rows: list[DriftInput]) -> DriftTable:
    packages = shared_package_names(rows)
    columns = [*_BASE_COLUMNS, *packages]
    ordered = sorted(rows, key=lambda row: (_PRIORITY.get(row.priority, 1), row.name))
    matrix: list[list[str]] = []
    for row in ordered:
        matrix.append(
            [
                row.flutter or "—",
                row.dart or "—",
                row.target_sdk or "—",
                row.ios or "—",
                *[row.packages.get(name) or "—" for name in packages],
            ]
        )
    masks = [outlier_mask([matrix[row][col] for row in range(len(matrix))]) for col in range(len(columns))]
    drift_rows: list[DriftRow] = []
    for index, row in enumerate(ordered):
        cells = [
            DriftCell(matrix[index][col], masks[col][index])
            for col in range(len(columns))
        ]
        drift_rows.append(DriftRow(row.name, row.priority, cells))
    return DriftTable(columns, drift_rows)
