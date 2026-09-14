"""Model-neutral parsing of terminal CLI transport failures."""
from __future__ import annotations

import json
import re


def terminal_transport_error(log: str) -> dict | None:
    """Return a sanitized terminal provider error without inspecting reasoning text."""
    for line in reversed(log.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "result" or event.get("is_error") is not True:
            continue
        raw = event.get("errors") or event.get("error") or event.get("message") or ""
        if isinstance(raw, (dict, list)):
            text = json.dumps(raw, ensure_ascii=False)
        else:
            text = str(raw)
        lowered = text.lower()
        error_info = event.get("errors_info") or []
        if not isinstance(error_info, list):
            error_info = []
        rate_limited = (
            re.search(r"(^|\D)429(\D|$)", text) is not None
            or "rate limit" in lowered
            or "rate_limit" in lowered
            or "频率限制" in text
            or "使用量已超出" in text
            or "请求过于频繁" in text
        )
        network_unavailable = (
            any(
                isinstance(item, dict)
                and (
                    str(item.get("category") or "").lower() == "network"
                    or item.get("status") in {502, 503, 504}
                )
                for item in error_info
            )
            or "getaddrinfo" in lowered
            or "enotfound" in lowered
            or "network connection" in lowered
            or "网络连接失败" in text
            or "无法解析服务器地址" in text
        )
        reset_match = re.search(
            r"(20\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:\s*(?:UTC)?[+-]\d{1,2}(?::\d{2})?)?)",
            text,
            re.I,
        )
        category = "rate_limited" if rate_limited else "network_unavailable" if network_unavailable else "provider_error"
        exit_code = 29 if rate_limited else 28 if network_unavailable else 70
        return {
            "category": category,
            "exit_code": exit_code,
            "retry_after": reset_match.group(1).strip() if reset_match else "",
            "subtype": str(event.get("subtype") or ""),
        }
    return None
