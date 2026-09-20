import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from cwh_semantic_recovery import preserve_extracted_claims


def test_synthesis_failure_does_not_publish_eight_uses_of_same_subject():
    decisions = [{'id': 'a1', 'source': '示例来源', 'decision': 'eligible',
                  'claims': [{'speaker': '示例来源', 'role': '', 'speaker_type': 'media',
                              'claim': f'独立原始观点{i}'} for i in range(8)]}]
    original = copy.deepcopy(decisions)
    result, run = preserve_extracted_claims({'topic': '当期议题', 'formal_selection': {'max_independent_voices': 12}},
                                           decisions, {'kind': 'model_timeout'})
    claims = result['items'][0]['claims']
    assert sum(c.get('formal_use') != 'reserve' for c in claims) == 0
    assert result['clusters'] == [] and result['heading'] == ''
    assert len(claims) == 8 and decisions == original
    assert run['model_invoked'] is False
    assert len(result['transport_repairs'][0]['reservations']) == 8
    assert result['transport_repairs'][0]['formal_prose_emitted'] is False


def test_direct_and_cached_author_paths_also_apply_source_caps():
    from cwh_editorial_selection import enforce_author_layout
    from cwh_viewpoint_gate import independent_voice_keys
    decision = {'heading': '认为具体政策有助改善治理', 'clusters': [{'key': 'g1', 'heading': '认为改善治理'}],
        'items': [{'id': 'a1', 'source': '来源甲', 'decision': 'eligible',
                   'claims': [{'speaker': '来源甲', 'claim': f'真实判断{i}', 'cluster': 'g1'} for i in range(3)]}]}
    fixed, audit = enforce_author_layout(decision)
    assert sum(c.get('formal_use') != 'reserve' for c in fixed['items'][0]['claims']) == 1
    key = next(iter(independent_voice_keys([{'speaker_name': '来源甲', 'source': '来源甲'}])))
    fixed, _ = enforce_author_layout(decision, {key: 2})
    assert all(c.get('formal_use') == 'reserve' for c in fixed['items'][0]['claims'])
    assert len(decision['items'][0]['claims']) == 3


def test_legacy_source_order_cache_cannot_reintroduce_prose():
    from cwh_editorial_selection import enforce_author_layout
    old = {'heading': '旧议程', 'clusters': [{'key': 'source_order', 'heading': '旧议程'}],
           'items': [{'id': 'a1', 'source': '来源甲', 'decision': 'eligible',
                      'claims': [{'speaker': '来源甲', 'claim': '完整原始判断', 'cluster': 'source_order'}]}],
           'transport_repairs': [{'kind': 'host_source_order_after_synthesis_interruption'}]}
    revised, audit = enforce_author_layout(old)
    assert revised['clusters'] == []
    assert revised['items'][0]['claims'][0]['formal_use'] == 'reserve'
    assert revised['items'][0]['claims'][0]['claim'] == '完整原始判断'
    assert audit['formal_prose_emitted'] is False
