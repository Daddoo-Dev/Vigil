"""pub.dev package metadata. One scan shares a single in-memory cache."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx

PUB_DEV_PACKAGE = "https://pub.dev/api/packages/{name}"


@dataclass(frozen=True)
class PubInfo:
    name: str
    discontinued: bool
    replaced_by: str | None
    retracted: frozenset[str]


def parse_pub_payload(name: str, payload: dict) -> PubInfo | None:
    if not isinstance(payload, dict):
        return None
    latest = payload.get("latest")
    if not isinstance(latest, dict) or "version" not in latest:
        return None
    retracted: set[str] = set()
    if latest.get("retracted") is True and latest.get("version"):
        retracted.add(str(latest["version"]))
    for entry in payload.get("versions") or []:
        if isinstance(entry, dict) and entry.get("retracted") is True and entry.get("version"):
            retracted.add(str(entry["version"]))
    replaced = payload.get("replacedBy")
    return PubInfo(
        name=str(payload.get("name") or name),
        discontinued=bool(payload.get("isDiscontinued")),
        replaced_by=str(replaced) if replaced else None,
        retracted=frozenset(retracted),
    )


@dataclass
class PubDevClient:
    """Looks up package names one at a time and pauses between uncached requests."""

    client: httpx.Client
    delay_seconds: float = 0.25
    sleeper: object = time.sleep
    cache: dict[str, PubInfo] = field(default_factory=dict)

    def lookup(self, names: list[str]) -> tuple[dict[str, PubInfo], list[str]]:
        errors: list[str] = []
        ordered = list(dict.fromkeys(names))
        first = True
        for name in ordered:
            if name in self.cache:
                continue
            if not first:
                self.sleeper(self.delay_seconds)  # type: ignore[operator]
            first = False
            try:
                response = self.client.get(PUB_DEV_PACKAGE.format(name=name))
            except httpx.HTTPError as exc:
                errors.append(f"pub.dev {name}: {exc}")
                continue
            if response.status_code == 429:
                errors.append("pub.dev rate limit reached; remaining packages were not checked")
                break
            if response.status_code >= 400:
                errors.append(f"pub.dev {name}: HTTP {response.status_code}")
                continue
            try:
                payload = response.json()
            except ValueError:
                errors.append(f"pub.dev {name}: response was not JSON")
                continue
            info = parse_pub_payload(name, payload)
            if info is None:
                errors.append(f"pub.dev {name}: unexpected response")
                continue
            self.cache[name] = info
        found = {name: self.cache[name] for name in ordered if name in self.cache}
        return found, errors
