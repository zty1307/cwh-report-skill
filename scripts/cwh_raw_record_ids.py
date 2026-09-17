"""Short transport IDs with an exact host mapping, never fuzzy source matching."""
import copy

TRANSPORT_VERSION = 'raw_record_aliases_v1'


def alias_record_ids(packet):
    result = copy.deepcopy(packet)
    mapping, seen = {}, set()
    for number, row in enumerate(result.get('items', []), 1):
        original = row.get('record_id')
        if not isinstance(original, str) or not original or original in seen:
            raise ValueError('Raw source IDs must be nonempty and unique')
        seen.add(original)
        alias = f'r{number}'
        mapping[alias] = original
        row['record_id'] = alias
    return result, mapping


def restore_record_ids(answer, mapping):
    result = copy.deepcopy(answer)
    for row in result.get('items', []):
        alias = row.get('record_id')
        if alias not in mapping:
            raise ValueError(f'Unknown raw transport record_id: {alias!r}; use exact input IDs')
        row['record_id'] = mapping[alias]
        row['transport_record_id'] = alias
    return result


def alias_previous_review(answer, mapping):
    """Use current aliases for exact known IDs in repair context, not fuzzy fixes."""
    result = copy.deepcopy(answer)
    reverse = {original: alias for alias, original in mapping.items()}
    for row in result.get('items', []):
        original = row.get('record_id')
        if isinstance(original, str) and original in reverse:
            row['record_id'] = reverse[original]
            row.pop('transport_record_id', None)
    return result
