import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_author_batches import extend_unique_attribution_context, article_span_problems


def fixture():
    packet = {'items': [{'id': 'r1', 'segments': [
        {'id': 'p/1', 'text': '研究员张甲介绍了背景。'},
        {'id': 'p/2', 'text': '其他背景。'},
        {'id': 'p/3', 'text': '张甲认为应解决执行环节的具体困难。'}]}]}
    response = {'items': [{'id': 'r1', 'decision': 'eligible', 'claims': [
        {'speaker': '张甲', 'role': '研究员', 'speaker_type': 'named_person',
         'claim': '应解决执行环节的具体困难', 'quote_range': ['p/3', 'p/3']}]}]}
    return packet, response


def test_unique_literal_anchor_extends_context_without_rewriting_claim_or_source():
    packet, response = fixture()
    before = copy.deepcopy((packet, response))
    result = extend_unique_attribution_context(packet, response, {'session_id': 'actual'})
    claim = result['items'][0]['claims'][0]
    assert claim['quote_range'] == ['p/1', 'p/3']
    assert {k: v for k, v in claim.items() if k != 'quote_range'} == {
        k: v for k, v in response['items'][0]['claims'][0].items() if k != 'quote_range'}
    assert not article_span_problems(packet, result)
    assert result['transport_repairs'][0]['items'][0]['original_model_run']['session_id'] == 'actual'
    assert (packet, response) == before


def test_ambiguous_anchor_or_missing_speaker_never_expands():
    packet, response = fixture()
    packet['items'][0]['segments'][1]['text'] = '研究员张甲也谈过背景。'
    assert extend_unique_attribution_context(packet, response, {}) == response
    packet, response = fixture()
    packet['items'][0]['segments'][2]['text'] = '李乙认为应解决具体困难。'
    assert extend_unique_attribution_context(packet, response, {}) == response


def test_role_alone_or_other_article_cannot_supply_identity():
    packet, response = fixture()
    packet['items'][0]['segments'][0]['text'] = '研究员李乙接受张甲采访介绍了背景。'
    packet['items'].append({'id': 'r2', 'segments': [{'id': 'q/1', 'text': '研究员张甲介绍了背景。'}]})
    assert extend_unique_attribution_context(packet, response, {}) == response


def test_excess_context_and_malformed_ranges_stay_for_native_review():
    packet, response = fixture()
    packet['items'][0]['segments'][1]['text'] = '背景' * 2000
    assert extend_unique_attribution_context(packet, response, {}) == response
    response['items'][0]['claims'][0]['quote_range'] = ['p/3', 'q/1']
    assert extend_unique_attribution_context(packet, response, {}) == response
