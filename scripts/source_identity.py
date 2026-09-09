from __future__ import annotations

import re
from typing import Any


PUBLIC_ACCOUNT_SUFFIXES = (
    "微信公众号",
    "官方公众号",
    "公众号",
    "官方账号",
    "微信号",
)


def normalize_public_source(value: Any) -> str:
    source = str(value or "").strip().casefold()
    for suffix in PUBLIC_ACCOUNT_SUFFIXES:
        if source.endswith(suffix):
            source = source[: -len(suffix)]
            break
    return re.sub(r"[^\w\u3400-\u9fff]+", "", source)


def public_source_family(value: Any, config: dict[str, Any] | None = None) -> str:
    """Return a configurable publisher-family identity for public-account ranking.

    Exact account normalization remains the default.  Explicit aliases are used
    only for publisher siblings that the reporting unit has decided must share
    one ranking slot; this avoids unsafe fuzzy grouping of unrelated accounts.
    """

    normalized = normalize_public_source(value)
    if not normalized:
        return ""
    for group in (config or {}).get("public_publisher_families") or []:
        canonical = normalize_public_source(group.get("canonical") or group.get("id"))
        aliases = {
            normalize_public_source(alias)
            for alias in group.get("aliases") or []
            if normalize_public_source(alias)
        }
        if normalized == canonical or normalized in aliases:
            return f"publisher_family:{canonical or sorted(aliases)[0]}"
    return f"account:{normalized}"
