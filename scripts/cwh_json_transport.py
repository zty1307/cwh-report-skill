"""Narrow, audited JSON framing repairs; never invent values or source text."""
import copy
import json


def escape_cjk_internal_quotes(text):
    """Escape only quotes sandwiched by CJK text inside value strings.

    Never repair keys, missing separators or truncated strings. Decoded text
    retains the original quote characters; downstream source gates still run.
    """
    output, stack, positions = [], [], []
    quoted = escaped = is_key = False
    previous = ''
    for i, character in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                tail = text[i+1:].lstrip()
                following = tail[:1]
                closing = following == ':' if is_key else following in (',', '}', ']', '')
                if closing:
                    quoted = False
                elif (not is_key and i > 0 and i+1 < len(text)
                      and '\u4e00' <= text[i-1] <= '\u9fff'
                      and '\u4e00' <= text[i+1] <= '\u9fff'):
                    output.append('\\')
                    positions.append(i)
                else:
                    return None
        elif character == '"':
            quoted = True
            is_key = bool(stack and stack[-1] == '{' and previous != ':')
        elif character in '[{':
            stack.append(character)
        elif character in ']}':
            if not stack or (stack.pop(), character) not in (('[', ']'), ('{', '}')):
                return None
        output.append(character)
        if not quoted and not character.isspace():
            previous = character
    if not positions or quoted or stack:
        return None
    try:
        result = json.loads(''.join(output))
    except ValueError:
        return None
    if not isinstance(result, dict):
        return None
    result.setdefault('transport_repairs', []).append({'kind': 'escaped_cjk_internal_quotes', 'positions': positions})
    return result


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
