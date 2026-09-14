"""Narrow, audited JSON framing repairs; never invent values or source text."""
import copy
import json


def load_framed_json(text: str):
    try:
        return json.loads(text)
    except ValueError:
        pass
    stack, quoted, escaped = [], False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            stack.append("]" if character == "[" else "}")
        elif character in "]}":
            if not stack or stack.pop() != character:
                raise ValueError("Mismatched JSON container")
    if quoted or not stack or text.rstrip().endswith((",", ":")):
        raise ValueError("Not an unambiguous container-close repair")
    suffix = "".join(reversed(stack))
    result = json.loads(text + suffix)
    if not isinstance(result, dict):
        raise ValueError("Worker output must be an object")
    result.setdefault("transport_repairs", []).append({"kind": "closed_containers_at_eof", "appended": suffix})
    return result


def normalize_authoring_envelope(value: dict) -> dict:
    research = value.get("research_audit")
    if ("viewpoints" not in value and isinstance(value.get("metadata"), dict)
            and isinstance(research, dict) and isinstance(research.get("domestic_media_research"), dict)
            and isinstance(research.get("viewpoints"), dict)):
        result = copy.deepcopy(value)
        result["viewpoints"] = result["research_audit"].pop("viewpoints")
        result.setdefault("transport_repairs", []).append({"kind": "moved_unique_misnested_viewpoints",
                                                          "from": "research_audit.viewpoints", "to": "viewpoints"})
        return result
    return value
