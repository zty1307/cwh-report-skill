"""Reading-only batches cannot skip final native selection or source gates."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_article_reading import reading_prompt, reading_contract, reading_input_packet
from cwh_article_reading import materialize_literal_claims
import copy
import pytest


def literal_fixture():
    return ({'items': [{'id': 'r1', 'segments': [
        {'id': 'r1/1', 'text': '甲研究院副院长张三表示，'},
        {'id': 'r1/2', 'text': '只有配套到位，措施才可能有效。'},
        {'id': 'r1/3', 'text': '不能保证立即见效。'}]}]},
        {'items': [{'id': 'r1', 'decision': 'eligible', 'claims': [{'speaker': '张三',
            'role': '甲研究院副院长', 'speaker_type': 'named_person',
            'quote_range': ['r1/1', 'r1/3'], 'claim_range': ['r1/2', 'r1/3']}]}]})


def test_script_copies_selected_original_sentences_without_changing_identity_or_conditions():
    packet, response = literal_fixture()
    original = copy.deepcopy((packet, response))
    result = materialize_literal_claims(packet, response)
    claim = result['items'][0]['claims'][0]
    assert claim['claim'] == '只有配套到位，措施才可能有效。不能保证立即见效。'
    assert {k:v for k,v in claim.items() if k != 'claim'} == response['items'][0]['claims'][0]
    assert (packet, response) == original
    assert materialize_literal_claims(packet, result) == result
    assert 'semantic_review' not in claim and 'wording_fidelity' not in claim


@pytest.mark.parametrize('change', ['cross_article', 'reversed', 'outside_excerpt', 'conflicting_text', 'unknown_item'])
def test_literal_selection_does_not_guess_or_silently_rewrite_invalid_ranges(change):
    packet, response = literal_fixture()
    claim = response['items'][0]['claims'][0]
    if change == 'cross_article': claim['claim_range'] = ['other/2', 'other/3']
    elif change == 'reversed': claim['claim_range'] = ['r1/3', 'r1/2']
    elif change == 'outside_excerpt': claim['quote_range'] = ['r1/1', 'r1/2']
    elif change == 'conflicting_text': claim['claim'] = '措施必然有效。'
    elif change == 'unknown_item': response['items'][0]['id'] = 'other'
    with pytest.raises(ValueError): materialize_literal_claims(packet, response)


def test_existing_paraphrases_are_never_silently_replaced_by_source_text():
    packet, response = literal_fixture()
    claim = response['items'][0]['claims'][0]
    claim.pop('claim_range')
    claim['claim'] = '效果取决于配套措施，不能保证立即见效。'
    assert materialize_literal_claims(packet, response) == response


def test_production_reading_materializes_native_range_before_synthesis(tmp_path, monkeypatch):
    import time
    import run_cwh_compiled_worker as worker
    original_text = '甲研究院副院长张三表示，配套完成后可能改善服务。仍须观察实施效果。'
    def model(request, *args, **kwargs):
        ids = [s['id'] for s in request['items'][0]['segments']]
        return {'items': [{'id': 'r1', 'decision': 'eligible', 'reason': '具有条件限制的判断',
            'claims': [{'speaker': '张三', 'role': '甲研究院副院长', 'speaker_type': 'named_person',
                'claim_kind': 'policy_reasoning', 'quote_range': [ids[0], ids[-1]],
                'claim_range': [ids[0], ids[-1]]}]}]}, {'session_id': 'native-range-selection'}
    monkeypatch.setattr(worker, 'semantic_json', model)
    packet = {'topic': '公共服务', 'items': [{'id': 'r1', 'origin': 'monitoring', 'content': original_text}]}
    result, _ = worker.author_topic_decisions([packet], reading_prompt(), [], tmp_path, time.monotonic() + 60,
        reuse_cache=False, allow_article_batches=False, reading_only=True)
    claim = result[0]['items'][0]['claims'][0]
    assert claim['claim'] == original_text
    assert claim['claim_range'] == claim['quote_range']
    assert packet['items'][0]['content'] == original_text


def test_reading_contract_does_not_request_provisional_topic_composition():
    prompt = reading_prompt()
    assert '不输出cluster、heading、clusters' in prompt
    assert 'quote_range' in prompt and 'published_at' in prompt
    assert 'actual_model' not in prompt
    contract = reading_contract({'items': [{'id': 'r1'}, {'id': 'w2'}]})
    assert '["r1","w2"]' in contract
    assert 'claim_kind不能漏、不能为null' in contract
    assert '50—120字是摘写软目标' in contract


def test_production_reading_prompt_matches_the_tested_semantic_scope():
    prompt = reading_prompt()
    assert '单纯说明会议首次核准' in prompt
    assert '本阶段不写标题、不分组、不选最终声音数' in prompt
    assert '完整年' in prompt or '连续完整年月日' in prompt


def test_reading_input_preserves_every_source_but_not_later_selection_instructions():
    import copy
    packet = {'topic': '公共服务', 'items': [{'id': 'r1', 'content': '完整原文',
        'segments': [{'id': 'r1/1', 'text': '完整原文'}]}],
        'formal_selection': {'allow_reserve': True, 'max_independent_voices': 12},
        'agenda_topics': ['公共服务', '基础设施']}
    original = copy.deepcopy(packet)
    observed = reading_input_packet(packet)
    assert packet == original
    assert observed == {key: value for key, value in original.items() if key != 'formal_selection'}
    assert packet['formal_selection']['max_independent_voices'] == 12


def test_production_reading_call_does_not_receive_final_selection_rules(tmp_path, monkeypatch):
    import time
    import run_cwh_compiled_worker as worker
    observed = []
    def model(packet, *args, **kwargs):
        observed.append(packet)
        return {'items': [{'id': 'r1', 'decision': 'excluded', 'claims': [], 'reason': '只有事实通稿'}]}, {'session_id': 'native-reading'}
    monkeypatch.setattr(worker, 'semantic_json', model)
    source = {'topic': '公共服务', 'items': [{'id': 'r1', 'origin': 'monitoring', 'content': '完整事实通稿'}],
              'formal_selection': {'allow_reserve': True, 'max_independent_voices': 12}}
    choices, run = worker.author_topic_decisions([source], reading_prompt(), [], tmp_path,
        time.monotonic()+60, reuse_cache=False, allow_article_batches=False, reading_only=True)
    assert len(observed) == 1 and 'formal_selection' not in observed[0]
    assert ''.join(row['text'] for row in observed[0]['items'][0]['segments']) == '完整事实通稿'
    assert source['formal_selection']['max_independent_voices'] == 12
    assert choices[0]['items'][0]['decision'] == 'excluded'
