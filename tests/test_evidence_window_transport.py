import copy
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_evidence_window_transport import pool_hotword_windows, reconstruct_term_windows


def window(start, end, text='真实政策原文与具体实施条件', source='original-row'):
    return {'source_row': source, 'source': '媒体甲', 'title': '原标题', 'url_ref': 'url-1',
            'excerpt': text[start:end], 'excerpt_start_in_packet': start, 'excerpt_end_in_packet': end}


def packet(windows):
    return {'candidates': [{'term': '政策', 'independent_document_count': 2}],
            'candidate_source_windows': [{'term': '政策', 'source_windows': windows},
                                         {'term': '无证据词', 'source_windows': []}]}


def test_overlapping_adjacent_and_duplicate_windows_round_trip_exactly():
    original = packet([window(0, 7), window(4, 10), window(4, 10), window(10, 13)])
    frozen = copy.deepcopy(original)
    pooled = pool_hotword_windows(original)
    assert len(pooled['source_window_pool']) == 1
    assert reconstruct_term_windows(pooled)['candidate_source_windows'] == original['candidate_source_windows']
    assert pooled['candidates'] == original['candidates'] and original == frozen


def test_gaps_and_different_source_metadata_are_never_merged():
    original = packet([window(0, 3), window(7, 10), window(0, 3, source='different-row')])
    pooled = pool_hotword_windows(original)
    assert len(pooled['source_window_pool']) == 3
    assert reconstruct_term_windows(pooled)['candidate_source_windows'] == original['candidate_source_windows']


@pytest.mark.parametrize('change', ['offset', 'inconsistent_overlap', 'boolean_offset'])
def test_invalid_source_windows_cannot_be_silently_repaired(change):
    windows = [window(0, 7), window(4, 10)]
    if change == 'offset':
        windows[1]['excerpt_end_in_packet'] += 1
    elif change == 'boolean_offset':
        windows[0]['excerpt_start_in_packet'] = False
    else:
        windows[1]['excerpt'] = '伪' + windows[1]['excerpt'][1:]
    with pytest.raises(ValueError):
        pool_hotword_windows(packet(windows))


def test_empty_evidence_stays_empty_without_new_source_or_candidate():
    original = packet([])
    pooled = pool_hotword_windows(original)
    assert not pooled['source_window_pool']
    assert reconstruct_term_windows(pooled)['candidate_source_windows'] == original['candidate_source_windows']
