import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from run_cwh_inline_review import overseas_span_packet, resolve_overseas_spans


def packet():
    return {'instructions': ['复制interpretive_excerpt'], 'items': [
        {'record_id': 'first', 'title': '标题', 'content': '第一句。第二句。'},
        {'record_id': 'second', 'title': '标题', 'content': '另一篇第一句。另一篇第二句。'}]}


@pytest.mark.parametrize('span', ['o2/2', ['o2/2']])
def test_singleton_resolves_exact_source_without_mutating_inputs(span):
    source = packet()
    response = {'items': [{'record_id': 'second', 'decision': 'include',
                            'interpretive_range': span, 'summary_cn_simplified': '原摘要'}]}
    before = copy.deepcopy((source, response))
    row = resolve_overseas_spans(source, response)['items'][0]
    assert row['interpretive_range'] == ['o2/2', 'o2/2']
    assert row['interpretive_excerpt'] == '另一篇第二句。'
    assert row['interpretive_source_span'] == {'start': 7, 'end': 14, 'scheme': 'sentence_v2'}
    assert row['summary_cn_simplified'] == '原摘要'
    assert row['transport_repairs'][0]['original_interpretive_range'] == span
    assert (source, response) == before


@pytest.mark.parametrize('span', ['o1/2', ['o1/2'], 'o2/3', 'o2/0', [2], ['o2/1', 'o2/2', 'o2/2']])
def test_singleton_never_guesses_namespace_index_or_range(span):
    with pytest.raises(ValueError):
        resolve_overseas_spans(packet(), {'items': [{'record_id': 'second', 'decision': 'include',
                                                      'interpretive_range': span}]})


def test_existing_pair_keeps_original_audit_and_no_repair():
    row = resolve_overseas_spans(packet(), {'items': [{'record_id': 'second', 'decision': 'include',
                      'interpretive_range': ['o2/1', 'o2/2']}]})['items'][0]
    assert row['interpretive_excerpt'] == '另一篇第一句。另一篇第二句。'
    assert 'transport_repairs' not in row


def test_transport_instructions_require_two_boundaries_even_for_one_segment():
    transformed = overseas_span_packet(packet())
    assert '单片段也写两个相同ID' in transformed['instructions'][0]
    assert transformed['items'][1]['interpretive_segments'][1]['id'] == 'o2/2'
