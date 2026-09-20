"""Quarantine malformed review rows without inventing any review or identifier."""
import hashlib
import json
import re
from cwh_json_transport import unique_members


def recover_review_array(log, expected_ids, array_key):
    """Read intact JSON row objects from one completed terminal answer only.

    The outer object must contain exactly the requested review array. Broken
    framing, duplicate keys, ambiguous row boundaries and partial streaming
    output are not repaired. Invalid row bodies remain in the original log.
    """
    answers = []
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            if event.get('subtype') != 'success' or event.get('is_error'):
                return None
            if not isinstance(event.get('result'), str):
                return None
            answers.append(event['result'])
    if len(answers) != 1:
        return None
    text = answers[0].strip()
    match = re.fullmatch(r'\{\s*"' + re.escape(array_key) + r'"\s*:\s*\[(.*)\]\s*\}', text, re.S)
    if not match:
        return None
    body = match.group(1)
    chunks, start, depth, quoted, escaped = [], 0, [], False, False
    for index, char in enumerate(body):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in '[{':
            depth.append(char)
        elif char in ']}':
            if not depth or depth.pop() != {']': '[', '}': '{'}[char]:
                return None
        elif char == ',' and not depth:
            chunks.append(body[start:index].strip())
            start = index + 1
    if quoted or depth:
        return None
    chunks.append(body[start:].strip())
    if not chunks or any(not row.startswith('{') or not row.endswith('}') for row in chunks):
        return None
    rows, invalid, suspect = [], [], set()
    def reject_constant(value):
        raise ValueError('Non-standard JSON constant')
    for index, chunk in enumerate(chunks):
        try:
            row = json.loads(chunk, object_pairs_hook=unique_members, parse_constant=reject_constant)
            if not isinstance(row, dict):
                raise ValueError('Review row is not an object')
            rows.append(row)
        except ValueError:
            invalid.append(index)
            # A malformed row might conflict with an earlier ID. Conservatively
            # quarantine any known review ID it mentions rather than guessing.
            suspect.update(identity for identity in expected_ids
                           if re.search(r'(?<![A-Za-z0-9_])' + re.escape(identity) + r'(?![A-Za-z0-9_])', chunk))
    if not invalid or not rows:
        return None
    rows = [row for row in rows if row.get('id') not in suspect]
    if not rows:
        return None
    return {array_key: rows, 'transport_recovery': {
        'kind': 'intact_native_rows_only', 'original_answer_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'invalid_row_indices': invalid, 'quarantined_possible_ids': sorted(suspect),
        'scope': 'No values or IDs repaired; missing rows remain unreviewed, not approved'}}


def recover_heading_rows(log, expected_ids):
    recovered = recover_review_array(log, expected_ids, 'heading_reviews')
    if recovered:
        recovered['heading_transport_recovery'] = recovered.pop('transport_recovery')
    return recovered
