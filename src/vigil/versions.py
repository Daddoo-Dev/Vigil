"""Small version comparisons. No network, no third-party version library."""

from __future__ import annotations

import re


def version_key(value: str) -> tuple[int, ...]:
    """Turn ``3.24`` or ``13.0`` into a numeric tuple. Non-numeric text yields ``()``."""
    return tuple(int(part) for part in re.findall(r"\d+", value))


def version_lt(left: str, right: str) -> bool:
    """True when ``left`` is an older dotted version than ``right``.

    Missing trailing parts compare as zero, so ``3.24`` equals ``3.24.0``.
    Values with no digits are not ordered; the result is False.
    """
    left_key = version_key(left)
    right_key = version_key(right)
    if not left_key or not right_key:
        return False
    width = max(len(left_key), len(right_key))
    left_key = left_key + (0,) * (width - len(left_key))
    right_key = right_key + (0,) * (width - len(right_key))
    return left_key < right_key


def version_eq(left: str, right: str) -> bool:
    left_key = version_key(left)
    right_key = version_key(right)
    if not left_key or not right_key:
        return False
    width = max(len(left_key), len(right_key))
    left_key = left_key + (0,) * (width - len(left_key))
    right_key = right_key + (0,) * (width - len(right_key))
    return left_key == right_key


def constraint_lower_bound(constraint: str | None) -> str | None:
    """First version number in a pub constraint, used as a lower bound hint."""
    if not constraint:
        return None
    match = re.search(r"\d+(?:\.\d+){0,3}", constraint)
    return match.group(0) if match else None


def major(value: str | None) -> int | None:
    if not value:
        return None
    key = version_key(value)
    return key[0] if key else None
