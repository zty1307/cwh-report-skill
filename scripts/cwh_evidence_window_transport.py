"""Lossless pooling of overlapping evidence windows for model transport only."""
import copy
import json


def pool_hotword_windows(packet):
    """Keep candidates unchanged and reversible term-to-original-span bindings.

    Merge only overlapping/adjacent windows from identical source metadata.
    Never fill a missing gap, mix sources or resolve inconsistent source text.
    The host's original compact packet stays available to all evidence gates.
    """
    output = copy.deepcopy(packet)
    entries = output.get('candidate_source_windows')
    if not isinstance(entries, list):
        return output
    groups = {}
    for entry in entries:
        for window in entry['source_windows']:
            start, end = window['excerpt_start_in_packet'], window['excerpt_end_in_packet']
            if type(start) is not int or type(end) is not int or start < 0 or end < start or end - start != len(window['excerpt']):
                raise ValueError('Invalid source-window offsets; cannot pool evidence')
            metadata = {k: v for k, v in window.items() if k not in
                        ('excerpt', 'excerpt_start_in_packet', 'excerpt_end_in_packet')}
            identity = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            groups.setdefault(identity, []).append(window)
    pool, bindings = {}, {}
    for windows in groups.values():
        current = None
        current_id = None
        for window in sorted(windows, key=lambda row: (row['excerpt_start_in_packet'], row['excerpt_end_in_packet'])):
            start, end = window['excerpt_start_in_packet'], window['excerpt_end_in_packet']
            if current is None or start > current['excerpt_end_in_packet']:
                current = copy.deepcopy(window)
                current_id = f'window-{len(pool) + 1}'
                pool[current_id] = current
            else:
                offset = start - current['excerpt_start_in_packet']
                overlap = min(end, current['excerpt_end_in_packet']) - start
                if current['excerpt'][offset:offset + overlap] != window['excerpt'][:overlap]:
                    raise ValueError('Overlapping source windows disagree; cannot pool evidence')
                if end > current['excerpt_end_in_packet']:
                    current['excerpt'] += window['excerpt'][overlap:]
                    current['excerpt_end_in_packet'] = end
            bindings[id(window)] = {'window_id': current_id, 'start': start, 'end': end}
    for entry in entries:
        entry['source_window_refs'] = [bindings[id(window)] for window in entry.pop('source_windows')]
    output['source_window_pool'] = pool
    output['transport_note'] = str(output.get('transport_note') or '') + (
        ' Term source_window_refs point to source_window_pool. Each ref preserves its original '
        'start/end character offsets in the retained source packet; pool windows merge only '
        'overlap or adjacency with exact matching text and identical source metadata. '
        'Read the pooled original text, not the IDs as evidence. Distinct-source counts and '
        'candidate order are unchanged. The host retains unpooled windows for evidence gates.')
    return output


def reconstruct_term_windows(pooled):
    """Audit round-trip; restore each exact original evidence window."""
    output = copy.deepcopy(pooled)
    pool = output.pop('source_window_pool')
    for entry in output['candidate_source_windows']:
        restored = []
        for ref in entry.pop('source_window_refs'):
            source = pool[ref['window_id']]
            start, end = ref['start'], ref['end']
            offset = start - source['excerpt_start_in_packet']
            if offset < 0 or end > source['excerpt_end_in_packet']:
                raise ValueError('Window reference outside retained source span')
            restored.append({**source, 'excerpt': source['excerpt'][offset:offset + end - start],
                'excerpt_start_in_packet': start, 'excerpt_end_in_packet': end})
        entry['source_windows'] = restored
    return output
