import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cwh_author_batches import article_span_problems, quarantine_unresolved_spans, native_article_batch


def fixture():
    packet = {'formal_selection': {'allow_reserve': True}, 'items': [{'id': 'r1', 'segments': [
        {'id': 'p/1', 'text': '张甲介绍了实施困难，没有说明他的职务。'}]}]}
    bad = {'speaker': '张甲', 'role': '教授', 'speaker_type': 'named_person',
           'claim': '实施存在困难', 'quote_range': ['p/1', 'p/1']}
    good = {'speaker': '媒体甲', 'speaker_type': 'media', 'claim': '媒体原始判断', 'quote_range': ['p/1', 'p/1']}
    response = {'items': [{'id': 'r1', 'decision': 'eligible', 'reason': '原生理由', 'claims': [bad, good]}]}
    return packet, response


def test_only_failed_claim_is_quarantined_with_original_and_run():
    packet, response = fixture()
    original = copy.deepcopy(response)
    result = quarantine_unresolved_spans(packet, response, article_span_problems(packet, response), {'session_id': 'repair'})
    item = result['items'][0]
    assert item['decision'] == 'eligible' and item['claims'] == [original['items'][0]['claims'][1]]
    audit = item['transport_exclusions'][0]
    assert audit['original_item'] == original['items'][0]
    assert audit['actual_repair_run']['session_id'] == 'repair'
    assert response == original and not article_span_problems(packet, result)


def test_all_failed_claims_mark_unverified_not_no_interpretation():
    packet, response = fixture()
    response['items'][0]['claims'].pop()
    result = quarantine_unresolved_spans(packet, response, article_span_problems(packet, response), {})
    item = result['items'][0]
    assert item['decision'] == 'excluded' and item['claims'] == []
    assert item['classification_origin'] == 'deterministic_attribution_gate'
    assert '不据此断言文章没有解读' in item['reason']


def test_non_bounded_contract_remains_strict():
    packet, response = fixture()
    packet['formal_selection']['allow_reserve'] = False
    assert quarantine_unresolved_spans(packet, response, article_span_problems(packet, response), {}) is None


def test_quarantine_follows_one_actual_local_repair_not_instead_of_review(tmp_path):
    packet, response = fixture()
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        result = response if len(calls) == 1 else {'repairs': [{
            'id': 'r1', 'index': 0, 'speaker': '张甲', 'role': '教授', 'quote_range': ['p/1', 'p/1']}]}
        return copy.deepcopy(result), {'session_id': str(len(calls)), 'seconds': 1}
    result, run = native_article_batch(packet, '', [], tmp_path, 'author', 90, model, reuse_cache=False)
    assert len(calls) == 2 and run['seconds'] == 2
    assert result['items'][0]['claims'] == [response['items'][0]['claims'][1]]
    assert any(row['kind'] == 'quarantined_unverified_attribution' for row in result['transport_repairs'])
