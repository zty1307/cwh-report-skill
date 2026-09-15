"""Narrow, audited JSON framing repairs; never invent values or source text."""
import copy
import json
import hashlib
import re


def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def normalize_single_smart_quoted_member_key(text):
    """Fix one decoder-confirmed smart-quoted ASCII member key, not values.

    An intact simple key and colon must follow the decoder's error position.
    The whole object must parse after replacing just its two delimiters.
    Multiple defects, duplicates, escapes and incomplete output stay invalid.
    """
    try:
        json.loads(text, object_pairs_hook=unique_members)
        return None
    except json.JSONDecodeError as error:
        if error.msg != 'Expecting property name enclosed in double quotes':
            return None
        position = error.pos
    except ValueError:
        return None
    match = re.match(r'“([A-Za-z_][A-Za-z0-9_]*)”\s*:', text[position:])
    if not match:
        return None
    closing = position + len(match.group(1)) + 1
    repaired = text[:position] + '"' + text[position+1:closing] + '"' + text[closing+1:]
    try:
        result = json.loads(repaired, object_pairs_hook=unique_members)
    except ValueError:
        return None
    if not isinstance(result, dict):
        return None
    repairs = result.get('transport_repairs')
    if repairs is not None and not isinstance(repairs, list):
        return None
    result.setdefault('transport_repairs', []).append({
        'kind': 'normalized_single_smart_quoted_member_key',
        'positions': [position, closing],
        'original_text_sha256': hashlib.sha256(text.encode()).hexdigest()})
    return result


def insert_single_missing_member_comma(text):
    """Only a decoder-confirmed missing comma before an intact object key.

    No values, keys, containers or string content are supplied or changed.
    The entire result must parse after exactly one insertion; duplicate keys,
    multiple defects and incomplete strings remain failures.
    """
    try:
        json.loads(text, object_pairs_hook=unique_members)
        return None  # Valid JSON is not a repair request.
    except json.JSONDecodeError as error:
        if error.msg != "Expecting ',' delimiter":
            return None
        position = error.pos
    except ValueError:
        return None
    try:
        key, length = json.JSONDecoder().raw_decode(text[position:])
        if not isinstance(key, str) or not text[position+length:].lstrip().startswith(':'):
            return None
        result = json.loads(text[:position] + ',' + text[position:], object_pairs_hook=unique_members)
    except ValueError:
        return None
    if not isinstance(result, dict):
        return None
    repairs = result.get('transport_repairs')
    if repairs is not None and not isinstance(repairs, list):
        return None
    result.setdefault('transport_repairs', []).append({
        'kind': 'inserted_single_missing_member_comma', 'position': position,
        'original_text_sha256': hashlib.sha256(text.encode()).hexdigest()})
    return result


def escape_cjk_internal_quotes(text):
    """Escape CJK internal quotes, including one at the start of a value.

    Never repair keys, missing separators or truncated strings. Decoded text
    retains the original quote characters; downstream source gates still run.
    """
    output, stack, positions = [], [], []
    quoted = escaped = is_key = False
    string_start = -1
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
                      and ('\u4e00' <= text[i-1] <= '\u9fff' or i == string_start + 1)
                      and '\u4e00' <= text[i+1] <= '\u9fff'):
                    output.append('\\')
                    positions.append(i)
                else:
                    return None
        elif character == '"':
            quoted = True
            string_start = i
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
