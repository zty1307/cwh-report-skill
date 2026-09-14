"""Read host tool events, not article text, to classify permission blockers."""
from __future__ import annotations
import json


def permission_denials(log_text: str) -> list[dict]:
    names, denied = {}, []
    for line in log_text.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        message = event.get("message") or {}
        blocks = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[block.get("id")] = block.get("name")
            if block.get("type") != "tool_result":
                continue
            content = block.get("content")
            if isinstance(content, str):
                texts = [content]
            elif isinstance(content, dict):
                texts = [content.get("text", "")]
            elif isinstance(content, list):
                texts = [x.get("text", "") for x in content if isinstance(x, dict)]
            else:
                texts = []
            for text in texts:
                if isinstance(text, str) and text.startswith("Error: Permission to use ") and "has been denied" in text:
                    denied.append({"tool": names.get(block.get("tool_use_id"), "unknown"),
                                   "tool_use_id": block.get("tool_use_id"), "reason": "host_permission_denied"})
                    break
    return denied
